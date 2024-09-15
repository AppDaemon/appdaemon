"""
Interface with Home Assistant, send and recieve evets, state etc.
"""

import asyncio
import datetime
import functools
import json
from multiprocessing import AuthenticationError
import ssl
from time import perf_counter
import traceback
from copy import deepcopy
from typing import Any, Literal, Optional
import aiohttp
import aiohttp.client_ws
from aiohttp import WSMsgType
from deepdiff import DeepDiff
from pydantic import BaseModel

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.models.ad_config import HASSConfig, HASSMetaData
from appdaemon.plugin_management import PluginBase


def looped_coro(coro, sleep_time: int | float):
    @functools.wraps(coro)
    async def loop(self, *args, **kwargs):
        while not self.stopping:
            try:
                await coro()
            except Exception:
                self.logger.error(f"Error running {coro.__name__} - retrying in {sleep_time}s")
            finally:
                await asyncio.sleep(sleep_time)

    return loop


async def no_func():
    pass


def hass_check(func):
    def func_wrapper(*args, **kwargs):
        self = args[0]
        if not self.reading_messages:
            self.logger.warning("Attempt to call Home Assistant while disconnected: %s", func.__name__)
            return no_func()
        else:
            return func(*args, **kwargs)

    return func_wrapper


class HAAuthenticationError(Exception):
    pass


class HAEventsSubError(Exception):
    pass


class HASSWebsocketResponse(BaseModel):
    type: Literal["result", "auth_required", "auth_ok", "auth_invalid", "event"]
    ha_version: Optional[str] = None
    message: Optional[str] = None
    id: Optional[int] = None
    success: Optional[bool] = None
    result: Optional[dict] = None


class HASSWebsocketEvent(BaseModel):
    event_type: str
    data: dict


class HassPlugin(PluginBase):
    config: HASSConfig
    id: int
    session: aiohttp.ClientSession
    """http connection pool for general use"""
    ws: aiohttp.ClientWebSocketResponse
    """websocket dedicated for event loop"""
    metadata: dict[str, Any]
    services: list[dict[str, Any]]

    _result_futures: dict[int, asyncio.Future]

    first_time: bool = True
    first_msg: bool = False
    reading_messages: bool = False

    already_notified: bool
    hass_booting: bool
    hass_ready: bool
    stopping: bool = False

    def __init__(self, ad: "AppDaemon", name: str, config: HASSConfig):
        super().__init__(ad, name, config)

        self.id = 0
        self.metadata = {}
        self.services = []
        self._result_futures = {}

        # Internal state flags
        self.already_notified = False
        self.hass_booting = False
        self.hass_ready = False
        self.reading_messages = False
        self.stopping = False

        self.logger.info("HASS Plugin initialization complete")
        self.start = perf_counter()

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True

        # This will stop waiting for message on the websocket
        self.AD.loop.create_task(self.ws.close())

    #
    # Placeholder for constraints
    #
    def list_constraints(self):
        return []

    def create_session(self) -> aiohttp.ClientSession:
        """Handles creating an ``aiohttp.ClientSession`` with the cert information from the plugin config
        and the authorization headers for the REST API.
        """
        ssl_context = None if self.config.cert_verify else False
        if self.config.cert_verify and self.config.cert_path:
            ssl_context = ssl.create_default_context(capath=self.config.cert_path)
        conn = aiohttp.TCPConnector(ssl=ssl_context)
        return aiohttp.ClientSession(
            connector=conn,
            headers=self.config.auth_headers,
            json_serialize=utils.convert_json,
        )

    async def websocket_msg_factory(self):
        """Async generator that yields websocket messages.

        Handles creating the connection based on the HASSConfig and updates the performance counters
        """
        async with self.create_session() as self.session:
            async with self.session.ws_connect(self.config.websocket_url) as self.ws:
                self.id = 0
                self.reading_messages = True
                async for msg in self.ws:
                    self.first_msg = True
                    self.update_perf(bytes_recv=len(msg.data), updates_recv=1)
                    yield msg
        self.reading_messages = False

    async def match_ws_msg(self, msg: aiohttp.WSMessage) -> dict:
        """Wraps a match/case statement for the ``msg.type``"""
        msg_json = msg.json()
        match msg.type:
            case WSMsgType.TEXT:
                # create a separate task for processing messages to keep the message reading task unblocked
                self.AD.loop.create_task(self.process_websocket_json(msg_json))
            case WSMsgType.ERROR:
                self.logger.error("Error from aiohttp websocket: %s", msg_json)
            case WSMsgType.CLOSE:
                self.logger.debug("Received %s message", msg.type)
            case _:
                self.logger.error("Unhandled websocket message type: %s", msg.type)
        return msg_json

    @utils.warning_decorator(error_text="Unknown error during processing jSON", reraise=True)
    async def process_websocket_json(self, resp: dict):
        """Wraps a match/case statement for the ``type`` key of the JSON received from the websocket"""
        match resp["type"]:
            case "auth_required":
                self.logger.info("Connected to Home Assistant %s with aiohttp websocket", resp["ha_version"])
                await self.__post_conn__()
            case "auth_ok":
                self.logger.info("Authenticated to Home Assistant %s", resp["ha_version"])
                await self.__post_auth__()
            case "auth_invalid":
                resp = f'Failed to authenticate to Home Assistant: {resp["message"]}'
                self.logger.error(resp)
                raise AuthenticationError(resp)
            case "ping":
                await self.ping()
            case "pong":
                if future := self._result_futures.get(resp["id"]):
                    future.set_result(resp)
            case "result":
                await self.receive_result(resp)
            case "event":
                await self.receive_event(event=resp["event"])
            case _:
                raise NotImplementedError(resp["type"])

    async def __post_conn__(self):
        """Initialization to do after getting connected to the Home Assistant websocket"""
        return await self.websocket_send_json(**self.config.auth_json)

    async def __post_auth__(self):
        """Initialization to do after getting authenticated on the websocket"""
        res = await self.websocket_send_json(type="subscribe_events")
        match res:
            case None:
                raise HAEventsSubError("Unknown error in subscribe")
            case dict():
                match res["success"]:
                    case False:
                        res = res["error"]
                        raise HAEventsSubError(f'{res["code"]}: {res["message"]}')
                    case "timeout":
                        raise HAEventsSubError("Timed out waiting for subscription acknowledgement")

        config_coro = looped_coro(self.get_hass_config, self.config.config_sleep_time)
        self.AD.loop.create_task(config_coro(self))

        service_coro = looped_coro(self.get_hass_services, self.config.services_sleep_time)
        self.AD.loop.create_task(service_coro(self))

        # await self.wait_for_start()
        self.logger.info("All startup conditions met")

        state = await self.get_hass_state()
        await self.AD.plugins.notify_plugin_started(
            self.name, self.config.namespace, self.metadata, state, self.first_time
        )
        self.first_time = False
        self.already_notified = False

        self.logger.info(f"Completed initialization in {self.time_str()}")

    async def ping(self):
        """Method for testing response times over the websocket."""
        # https://developers.home-assistant.io/docs/api/websocket/#pings-and-pongs
        return await self.websocket_send_json(type="ping")

    # @utils.warning_decorator(error_text='Unexpected error during receive_result')
    async def receive_result(self, resp: dict):
        if (future := self._result_futures.pop(resp["id"], None)) is not None:
            future.set_result(resp)
        else:
            self.logger.warning(f"Received result without a matching future: {resp}")

        match resp["success"]:
            case False:
                self.logger.warning(
                    "Error with websocket result: %s: %s", resp["error"]["code"], resp["error"]["message"]
                )

    # @utils.warning_decorator(error_text='Unexpected error during receive_event')
    async def receive_event(self, event: dict):
        self.logger.debug(f"Received event type: {event['event_type']}")

        meta_attrs = {"origin", "time_fired", "context"}
        event["metadata"] = {a: val for a in meta_attrs if (val := event.pop(a, None)) is not None}

        await self.AD.events.process_event(self.config.namespace, event)

        match event["event_type"]:
            # https://data.home-assistant.io/docs/events/#state_changed
            case "state_changed":
                pass
            # https://data.home-assistant.io/docs/events/#service_registered
            case "service_registered":
                data = event["data"]
                await self.check_register_service(data["domain"], data["service"], silent=True)
            case "call_service":
                pass

    async def websocket_send_json(self, timeout: float = 1.0, **request) -> dict:
        """
        Sends a json request over the websocket and gets the response.

        Handles incrementing the `id` parameter and appends
        """
        # auth requests don't have an id field assigned
        if not request.get("type") == "auth":
            self.id += 1
            request["id"] = self.id

            # include this in the "not auth" section so we don't accidentally put the token in the logs
            self.logger.debug(f"Sending JSON: {request}")

        send_time = perf_counter()
        try:
            await self.ws.send_json(request)
        # happens when the connection closes in the middle, which could be during shutdown
        except ConnectionResetError:
            if self.stopping:
                return
            else:
                raise

        self.update_perf(bytes_sent=len(json.dumps(request)), requests_sent=1)

        if request.get("type") == "auth":
            return

        future = self.AD.loop.create_future()
        self._result_futures[self.id] = future

        try:
            result: dict = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.warning(f"Timed out [{timeout:.0f}s] waiting for request: %s", request)
            return {"success": "timeout", "ad_duration": timeout}
        else:
            travel_time = perf_counter() - send_time
            # self.logger.debug(f"Receive time: {(travel_time)*10**3:.0f} ms")
            result.update({"ad_duration": travel_time})
            return result

    async def rest_api_get(self, endpoint: str, timeout: float = 5.0, **kwargs):
        kwargs = utils.clean_kwargs(**kwargs)

        if not endpoint.startswith(self.config.ha_url):
            url = f'{self.config.ha_url}/{endpoint.strip("/")}'
        else:
            url = endpoint

        try:
            self.update_perf(bytes_sent=len(url), requests_sent=1)
            coro = self.session.get(url=url, params=kwargs)
            resp = await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.error("Timed out waiting for %s", url)
        except aiohttp.ServerDisconnectedError:
            self.logger.error("HASS disconnected unexpectedly during GET %s", url)
        else:
            self.update_perf(bytes_recv=resp.content_length, updates_recv=1)
            match resp.status:
                case 200 | 201:
                    return await resp.json()
                case 400 | 401 | 404 | 405:
                    text = await resp.text()
                    self.logger.error("Bad response from %s: %s", url, text)
                case _:
                    raise NotImplementedError

    async def rest_api_post(self, endpoint: str, timeout: float = 5.0, **kwargs):
        kwargs = utils.clean_kwargs(**kwargs)

        if not endpoint.startswith(self.config.ha_url):
            url = f'{self.config.ha_url}/{endpoint.strip("/")}'
        else:
            url = endpoint

        try:
            self.update_perf(bytes_sent=len(url), requests_sent=1)
            coro = self.session.post(url=url, json=kwargs)
            resp = await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.error("Timed out waiting for %s", url)
        except asyncio.CancelledError:
            self.logger.debug("Task cancelled during POST")
        except aiohttp.ServerDisconnectedError:
            self.logger.error("HASS disconnected unexpectedly during POST %s", url)
        else:
            self.update_perf(bytes_recv=resp.content_length, updates_recv=1)
            match resp.status:
                case 200 | 201:
                    return await resp.json()
                case 400 | 401 | 404 | 405:
                    text = await resp.text()
                    self.logger.error("Bad response from %s: %s", url, text)
                case 500:
                    text = await resp.text()
                    self.logger.error("Internal server error %s: %s", url, text)
                case _:
                    raise NotImplementedError

    async def wait_for_start(self):
        self.first_time = True
        while not self.stopping:
            start_ok = await self.evaluate_started(self.first_time, self.hass_booting)
            self.first_time = False
            if not start_ok:
                await asyncio.sleep(2.0)
                continue
            else:
                break

    async def evaluate_started(self, first_time, plugin_booting, event=None):  # noqa: C901
        if first_time is True:
            self.hass_ready = False
            self.state_matched = False

        if plugin_booting is True:
            startup_conditions = self.config.plugin_startup_conditions
        else:
            startup_conditions = self.config.appdaemon_startup_conditions

        start_ok = True

        if "hass_state" not in startup_conditions:
            startup_conditions["hass_state"] = "RUNNING"

        if "delay" in startup_conditions:
            if first_time is True:
                self.logger.info("Delaying startup for %s seconds", startup_conditions["delay"])
                await asyncio.sleep(int(startup_conditions["delay"]))

        if "hass_state" in startup_conditions:
            self.metadata = await self.get_hass_config()
            if "state" in self.metadata:
                if self.metadata["state"] == startup_conditions["hass_state"]:
                    if self.hass_ready is False:
                        self.logger.info("Startup condition met: hass state=RUNNING")
                        self.hass_ready = True
                else:
                    start_ok = False

        if "state" in startup_conditions:
            state = await self.get_hass_state()
            entry = startup_conditions["state"]
            if "value" in entry:
                # print(entry["value"], state[entry["entity"]])
                # print(DeepDiff(state[entry["entity"]], entry["value"]))
                if entry["entity"] in state and "values_changed" not in DeepDiff(
                    entry["value"], state[entry["entity"]]
                ):
                    if self.state_matched is False:
                        self.logger.info(
                            "Startup condition met: %s=%s",
                            entry["entity"],
                            entry["value"],
                        )
                        self.state_matched = True
                else:
                    start_ok = False
            elif entry["entity"] in state:
                if self.state_matched is False:
                    self.logger.info("Startup condition met: %s exists", entry["entity"])
                    self.state_matched = True
                else:
                    start_ok = False

        if "event" in startup_conditions:
            if event is not None:
                entry = startup_conditions["event"]
                if "data" not in entry:
                    if entry["event_type"] == event["event_type"]:
                        self.logger.info(
                            "Startup condition met: event type %s fired",
                            event["event_type"],
                        )
                    else:
                        start_ok = False
                else:
                    if entry["event_type"] == event["event_type"]:
                        if "values_changed" not in DeepDiff(event["data"], entry["data"]):
                            self.logger.info(
                                "Startup condition met: event type %s, data = %s fired",
                                event["event_type"],
                                entry["data"],
                            )
                    else:
                        start_ok = False
            else:
                start_ok = False

        if start_ok is True:
            # We are good to go
            self.logger.info("All startup conditions met")
            self.reading_messages = True
            state = await self.get_hass_state()
            await self.AD.plugins.notify_plugin_started(
                self.name, self.config.namespace, self.metadata, state, self.first_time
            )
            self.first_time = False
            self.already_notified = False

        return start_ok

    async def get_updates(self):  # noqa: C901
        while not self.stopping:
            try:
                async for msg in self.websocket_msg_factory():
                    await self.match_ws_msg(msg)
                    continue
                raise ValueError
            # except HAAuthenticationError:
            #     pass
            # except HAEventsSubError:
            #     pass
            except Exception:
                if not self.stopping:
                    self.logger.warning(
                        "Disconnected from Home Assistant, retrying in %s seconds",
                        self.config.retry_secs,
                    )
                    await asyncio.sleep(self.config.retry_secs)

            # always do this block, no matter what
            finally:
                # notify plugin stopped
                await self.AD.plugins.notify_plugin_stopped(self.name, self.config.namespace)
                # remove callback from getting local events
                await self.AD.callbacks.clear_callbacks(self.name)

        self.logger.info("Disconnecting from Home Assistant")

    def get_namespace(self):
        return self.config.namespace

    async def check_register_service(self, domain: str, services: str | dict, silent: bool = False) -> bool:
        """Used to check and register a service if need be"""

        existing_domains = set(s["domain"] for s in self.services)
        new_services = set()
        match services:
            case str():
                service = services  # rename for clarity
                if domain not in existing_domains:
                    self.services.append({"domain": domain, "services": {service: {}}})
                    new_services = {service}
            case dict():
                if domain in existing_domains:
                    for i, s in enumerate(self.services):
                        if domain == s["domain"]:
                            self.services[i]["services"].update(services)
                            new_services = set(s for s in services if s not in self.services[i]["services"])
                else:
                    self.services.append({"domain": domain, "services": services})
                    new_services = services
                    pass

        for service in new_services:
            if not silent:
                self.logger.debug("Registering new service %s/%s", domain, service)

            self.AD.services.register_service(
                self.get_namespace(),
                domain,
                service,
                self.call_plugin_service,
                __silent=True,
                return_result=self.config.return_result,
            )

    #
    # Utility functions
    #

    # def utility(self):
    # self.logger.debug("Utility (currently unused)")
    # return None

    async def get_complete_state(self):
        """This method is needed for all AppDaemon plugins"""
        return await self.get_hass_state()

    @utils.warning_decorator(error_text="Unexpected error while getting hass state")
    async def get_hass_state(self):
        hass_state = (await self.websocket_send_json(type="get_states"))["result"]
        states = {s["entity_id"]: s for s in hass_state}
        return states

    @utils.warning_decorator(error_text="Unexpected error while getting hass config")
    async def get_hass_config(self) -> dict:
        meta = (await self.websocket_send_json(type="get_config"))["result"]
        HASSMetaData.model_validate(meta)
        self.metadata = meta
        return self.metadata

    @utils.warning_decorator(error_text="Unexpected error while getting hass services")
    async def get_hass_services(self):
        """ "Gets a fresh list of services from the websocket and updates the various internal AppDaemon entries."""
        # raise ValueError
        try:
            services: dict[str, dict[str, dict]] = (await self.websocket_send_json(type="get_services"))["result"]
            services = [{"domain": domain, "services": services} for domain, services in services.items()]

            # manually added HASS services
            new_services = {}
            new_services["database"] = {"history": {}}
            new_services["template"] = {"render": {}}

            # now add the services
            for i, service in enumerate(deepcopy(services)):
                domain = service["domain"]
                if domain in new_services:
                    # the domain already exists
                    services[i]["services"].update(new_services[domain])

                    # remove from the list
                    del new_services[domain]

            if len(new_services) > 0:  # some have not been processed
                for domain, service in new_services.items():
                    services.append({"domain": domain, "services": {}})
                    services[-1]["services"].update(service)

            for s in services:
                await self.check_register_service(s["domain"], s["services"], silent=True)
            else:
                self.logger.info("Updated internal service registry")

            self.services = services
            return services

        except Exception:
            self.logger.warning("Error getting services - retrying")
            raise

    def time_str(self, now: float | None = None) -> str:
        return utils.time_str(self.start, now)

    #
    # Services
    #

    @hass_check
    async def call_plugin_service(self, namespace, domain, service, data):
        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.config.namespace

        #
        # If data is a string just assume it's an entity_id
        #
        if isinstance(data, str):
            data = {"entity_id": data}

        if domain == "database":
            assert service == "history"
            return await self.get_history(**data)

        # Keep this just in case anyone is still using call_service() for templates
        if domain == "template" and service == "render":
            return await self.render_template(namespace, data)

        target = data.pop("target", None)
        hass_timeout = data.pop("hass_timeout", None)
        return_response = data.pop("return_response", self.config.return_result)

        if data.pop("callback", False):
            return_response = True

        req = {"type": "call_service", "domain": domain, "service": service, "service_data": data}

        service_properties = {
            prop: val
            for entry in self.services
            if domain == entry["domain"]
            for name, info in entry["services"].items()
            if name == service
            for prop, val in info.items()
        }
        # if it has a response section
        if resp := service_properties.get("response"):
            # if the response section says it's not optional
            if not resp.get("optional"):
                req["return_response"] = True

        if target is not None:
            req["target"] = target

        send_coro = self.websocket_send_json(**req)

        if return_response is False:
            self.AD.loop.create_task(send_coro)
        else:
            try:
                res = await asyncio.wait_for(send_coro, timeout=hass_timeout)
            except asyncio.TimeoutError:
                self.logger.error(f"Timed out [{hass_timeout:.0f}s] during service call: {req}")
            else:
                return res

    #
    # Events
    #

    @hass_check
    async def fire_plugin_event(self, event, namespace, **kwargs):
        self.logger.info(locals())
        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.config.namespace

        timeout = kwargs.pop("timeout", 0)
        req = {"type": "fire_event", "event_type": event, "event_data": kwargs}

        try:
            res = await self.websocket_send_json(timeout, **req)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during fire_event()")
            self.logger.warning(f"Arguments: {locals()}")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
        else:
            return res

    #
    # Home Assistant REST Interactions
    #
    # Some functions can't be handled via the stream
    #

    #
    # Entities
    #

    @hass_check
    async def remove_entity(self, namespace, entity_id):
        self.logger.debug("remove_entity() %s", entity_id)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.config.namespace

        api_url = f"{self.config.ha_url}/api/states/{entity_id}"

        try:
            r = await self.session.delete(api_url)
            if r.status == 200 or r.status == 201:
                self.bytes_recv += len(await r.text())
                self.updates_recv += 1
                state = await r.json()
                self.logger.debug("return = %s", state)
            else:
                self.logger.warning("Error Removing Home Assistant entity %s", entity_id)
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                state = None

            self.update_perf(bytes_sent=len(json.dumps(api_url)), bytes_recv=len(await r.text()), requests_sent=1)
            return state
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning("Timeout in remove_entity(%s, %s)", namespace, entity_id)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during remove_entity()")
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during remove_entity()")
            self.logger.warning("Arguments: %s", entity_id)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return None

    #
    # State
    #

    # @utils.warning_decorator()
    @hass_check
    async def set_plugin_state(self, namespace: str, entity_id: str, **kwargs):
        self.logger.debug("set_plugin_state() %s %s %s", namespace, entity_id, kwargs)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.config.namespace

        api_url = self.config.get_entity_api(entity_id)

        state = await self.rest_api_post(api_url, timeout=3, **kwargs)

        return state

    #
    # History
    #

    async def get_history(
        self,
        filter_entity_id: str | list[str],
        timestamp: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        minimal_response: bool | None = None,
        no_attributes: bool | None = None,
        significant_changes_only: bool | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Used to get HA's History"""
        if isinstance(filter_entity_id, str):
            filter_entity_id = [filter_entity_id]

        endpoint = "/api/history/period"
        if timestamp is not None:
            endpoint += f"/{timestamp.isoformat()}"

        try:
            result: list[list[dict[str, Any]]] = await self.rest_api_get(
                endpoint=endpoint,
                filter_entity_id=",".join(filter_entity_id),
                end_time=end_time,
                minimal_response=minimal_response,
                no_attributes=no_attributes,
                significant_changes_only=significant_changes_only,
            )
        except Exception:
            raise
        else:
            # nested comprehension to convert the datetimes for convenience
            result = [
                [
                    {
                        k: v if not k.startswith("last_") else datetime.datetime.fromisoformat(v)
                        for k, v in individual_result.items()
                    }
                    for individual_result in entity_res
                ]
                for entity_res in result
            ]
            # result = {eid: r for eid, r in zip(filter_entity_id, result)}
            return result

    async def render_template(self, namespace, template):
        self.logger.debug(
            "render_template() namespace=%s data=%s",
            namespace,
            template,
        )

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.config.namespace

        api_url = f"{self.config.ha_url}/api/template"

        try:
            r = await self.session.post(api_url, json={"template": template})

            if r.status == 200 or r.status == 201:
                result = await r.text()
            else:
                self.logger.warning(
                    "Error calling render_template() (ns=%s, data=%s)",
                    namespace,
                    template,
                )
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                result = None

            self.update_perf(bytes_sent=len(json.dumps(template)), bytes_recv=len(await r.text()), requests_sent=1)
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning(
                "Timeout in call_service(%s, %s)",
                namespace,
                template,
            )
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during render_template()")
        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error during render_template()")
            self.logger.error("ns=%s, Arguments: %s", namespace, template)
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)
            return None
