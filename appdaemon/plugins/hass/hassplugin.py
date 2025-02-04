"""
Interface with Home Assistant, send and recieve evets, state etc.
"""

import asyncio
import datetime
import json
import ssl
from copy import deepcopy
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Literal, Optional

import aiohttp
import aiohttp.client_exceptions
import aiohttp.client_ws
from aiohttp import ClientResponse, WSMsgType
from pydantic import BaseModel

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.models.config.plugin import HASSConfig
from appdaemon.plugin_management import PluginBase

from .exceptions import HAEventsSubError
from .models import HASSMetaData
from .utils import hass_check, looped_coro


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


@dataclass
class StartupWaitCondition:
    """Class to wrap a startup condition.

    Includes the logic to check an event (dict) against the conditions.
    """

    conditions: dict[str, Any]
    event: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    @property
    def conditions_met(self) -> bool:
        return self.event.is_set()

    def check_received_event(self, event: dict):
        if not self.conditions_met and utils.deep_compare(self.conditions, event):
            self.event.set()


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
    _silent_results: dict[int, bool]
    startup_conditions: list[StartupWaitCondition]

    first_time: bool = True
    stopping: bool = False

    def __init__(self, ad: "AppDaemon", name: str, config: HASSConfig):
        super().__init__(ad, name, config)

        self.id = 0
        self.metadata = {}
        self.services = []
        self._result_futures = {}
        self._silent_results = {}
        self.startup_conditions = []

        # Internal state flags
        self.stopping = False

        self.logger.info("HASS Plugin initialization complete")
        self.start = perf_counter()

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True

        # This will stop waiting for message on the websocket
        self.AD.loop.create_task(self.ws.close())

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
                async for msg in self.ws:
                    self.update_perf(bytes_recv=len(msg.data), updates_recv=1)
                    yield msg

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

    @utils.warning_decorator(error_text="Error during processing jSON", reraise=True)
    async def process_websocket_json(self, resp: dict):
        """Wraps a match/case statement for the ``type`` key of the JSON received from the websocket"""
        match resp["type"]:
            case "auth_required":
                self.logger.info("Connected to Home Assistant %s with aiohttp websocket", resp["ha_version"])
                await self.__post_conn__()
            case "auth_ok":
                self.logger.info("Authenticated to Home Assistant %s", resp["ha_version"])
                # Creating a task here allows the plugin to still receive events as it waits for the startup conditions
                self.AD.loop.create_task(self.__post_auth__())
            case "auth_invalid":
                self.logger.error(f'Failed to authenticate to Home Assistant: {resp["message"]}')
                await self.ws.close()
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

        await self.wait_for_start_conditions()
        self.logger.info("All startup conditions met")
        self.ready_event.set()

        await self.notify_plugin_started(
            await self.get_hass_config(),
            await self.get_complete_state()
        )
        self.first_time = False

        self.logger.info(f"Completed initialization in {self.time_str()}")

    @hass_check
    async def ping(self, timeout: float = 1.0):
        """Method for testing response times over the websocket."""
        # https://developers.home-assistant.io/docs/api/websocket/#pings-and-pongs
        return await self.websocket_send_json(timeout=timeout, type="ping")

    @utils.warning_decorator(error_text="Unexpected error during receive_result")
    async def receive_result(self, resp: dict):
        if (future := self._result_futures.pop(resp["id"], None)) is not None:
            if not future.done():
                future.set_result(resp)
            else:
                self.logger.warning(f'Request already timed out for {resp["id"]}')
        else:
            self.logger.warning(f"Received result without a matching future: {resp}")

        silent = self._silent_results.pop(resp["id"], False) or \
            self.AD.config.suppress_log_messages

        if not silent:
            match resp["success"]:
                case True:
                    self.logger.debug(f'Received successful result from ID {resp["id"]}')
                case False:
                    self.logger.warning("Error with websocket result: %s: %s", resp["error"]["code"], resp["error"]["message"])
                case None:
                    self.logger.error(f"Invalid response success value: {resp['success']}")

    @utils.warning_decorator(error_text="Unexpected error during receive_event")
    async def receive_event(self, event: dict):
        self.logger.debug(f"Received event type: {event['event_type']}")

        meta_attrs = {"origin", "time_fired", "context"}
        event["metadata"] = {a: val for a in meta_attrs if (val := event.pop(a, None)) is not None}

        await self.AD.events.process_event(self.namespace, event)

        # check startup conditions
        if not self.is_ready:
            for condition in self.startup_conditions:
                condition.check_received_event(event)

        match typ := event["event_type"]:
            # https://data.home-assistant.io/docs/events/#service_registered
            case "service_registered":
                data = event["data"]
                await self.check_register_service(data["domain"], data["service"], silent=True)
            case "call_service":
                service_name = f'{event["data"]["domain"]}.{event["data"]["service"]}'
                entity_id = event["data"]["service_data"].get('entity_id')
                self.logger.debug(f'{service_name}, {entity_id}')
            case 'entity_registry_updated':
                pass
            # https://data.home-assistant.io/docs/events/#state_changed
            case "state_changed":
                ...
            case "mobile_app_notification_action":
                ...
                # action = event['data']['action']
            case "mobile_app_notification_cleared":
                ...
            case "android.zone_entered":
                ...
            case _:
                if typ.startswith('recorder'):
                    return
            # ? 'entity_registry_updated'
                self.logger.debug('Unrecognized event %s', typ)

    async def websocket_send_json(self, timeout: float = 5.0, silent: bool = False, **request) -> dict:
        """
        Sends a json request over the websocket and gets the response.

        Handles incrementing the `id` parameter and appends
        """
        # auth requests don't have an id field assigned
        if not request.get("type") == "auth":
            self.id += 1
            request["id"] = self.id

            if not silent:
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
        self._silent_results[self.id] = silent

        try:
            result: dict = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            if not silent:
                self.logger.warning(f"Timed out [{timeout:.0f}s] waiting for request: %s", request)
            return {"success": "timeout", "ad_duration": timeout}
        else:
            travel_time = perf_counter() - send_time
            result.update({"ad_duration": travel_time})
            return result

    @hass_check
    async def http_method(
        self,
        method: Literal['get', 'post', 'delete'],
        endpoint: str,
        timeout: float = 5.0,
        **kwargs
    ) -> dict | None:
        """

        https://developers.home-assistant.io/docs/api/rest

        Args:
            typ (Literal['get', 'post', 'delete']): Type of HTTP method to use
            endpoint (str): Home Assistant REST endpoint to use. For example '/api/states'
            timeout (float, optional): Timeout for the method in seconds. Defaults to 5.0.
            **kwargs (optional): Zero or more keyword arguments. These get used as the data
                for the method, as appropriate.

        Raises:
            NotImplementedError: _description_

        Returns:
            dict | None: _description_
        """
        kwargs = utils.clean_kwargs(**kwargs)
        url = utils.make_endpoint(self.config.ha_url, endpoint)

        try:
            self.update_perf(
                bytes_sent=len(url) + len(json.dumps(kwargs).encode('utf-8')),
                requests_sent=1
            )
            self.logger.debug(f'Hass {method.upper()} {endpoint}: {kwargs}')
            match method.lower():
                case 'get':
                    coro = self.session.get(url=url, params=kwargs)
                case 'post':
                    coro = self.session.post(url=url, json=kwargs)
                case 'delete':
                    coro = self.session.delete(url=url, json=kwargs)
                case _:
                    raise ValueError(f'Invalid method: {method}')
            resp = await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.error("Timed out waiting for %s", url)
        except asyncio.CancelledError:
            self.logger.debug("Task cancelled during %s", method.upper())
        except aiohttp.ServerDisconnectedError:
            self.logger.error("HASS disconnected unexpectedly during %s to %s", method.upper(), url)
        else:
            self.update_perf(bytes_recv=resp.content_length, updates_recv=1)
            match resp.status:
                case 200 | 201:
                    if endpoint.endswith('template'):
                        return await resp.text()
                    else:
                        return await resp.json()
                case 400 | 401 | 403 | 404 | 405:
                    try:
                        msg = (await resp.json())["message"]
                    except Exception:
                        msg = await resp.text()
                    self.logger.error(f"Bad response from {url}: {msg}")
                case 500 | 502:
                    text = await resp.text()
                    self.logger.error("Internal server error %s: %s", url, text)
                case _:
                    raise NotImplementedError('Unhandled error: HTTP %s', resp.status)
            return resp

    async def wait_for_start_conditions(self):
        condition_tasks = []
        if delay := self.config.plugin_startup_conditions.get('delay'):
            self.logger.info(f'Adding a {delay:.0f}s delay to the {self.name} startup')
            condition_tasks.append(
                self.AD.loop.create_task(
                    asyncio.sleep(delay)
                )
            )

        if event := self.config.plugin_startup_conditions.get('event'):
            self.logger.info(f'Adding startup event condition: {event}')
            condition = StartupWaitCondition(event)
            self.startup_conditions.append(condition)
            condition_tasks.append(
                self.AD.loop.create_task(
                    condition.event.wait()
                )
            )

        if cond := self.config.plugin_startup_conditions.get('state'):
            state = await self.get_plugin_state(cond['entity'])
            if utils.deep_compare(cond['value'], state):
                self.logger.info(f'Startup state condition already met: {cond}')
            else:
                self.logger.info(f'Adding startup state condition: {cond}')
                condition = StartupWaitCondition({
                    'event_type': 'state_changed',
                    'data': {
                        'entity_id': cond['entity'],
                        'new_state': cond['value']
                    }
                })
                self.startup_conditions.append(condition)
                condition_tasks.append(
                    self.AD.loop.create_task(
                        condition.event.wait()
                    )
                )

        self.logger.info(f'Waiting for {len(condition_tasks)} startup condition tasks after {self.time_str()}')
        if condition_tasks:
            await asyncio.wait(condition_tasks)

    async def get_updates(self):
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
                    self.ready_event.clear()
                    await asyncio.sleep(self.config.retry_secs)

            # always do this block, no matter what
            finally:
                # notify plugin stopped
                await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                # remove callback from getting local events
                await self.AD.callbacks.clear_callbacks(self.name)

        self.logger.info("Disconnecting from Home Assistant")

    async def check_register_service(self, domain: str, services: str | dict, silent: bool = False) -> bool:
        """Used to check and register a service with AppDaemon if need be"""

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
                self.namespace,
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
                self.logger.debug("Updated internal service registry")

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
    async def call_plugin_service(
        self,
        namespace: str,
        domain: str,
        service: str,
        target: str | None = None,
        hass_timeout: float | None = None,
        return_response: bool | None = None,
        callback: Callable | None = None,
        suppress_log_messages: bool = False,
        **data
    ):
        """Used by ``self.check_register_service`` when calling ``self.AD.services.register_service``.

        This causes ``self.call_plugin_service`` to be called when a service is called in this plugin's namespace.
        """
        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        #
        # If data is a string just assume it's an entity_id
        #
        if isinstance(data, str):
            data = {"entity_id": data}

        if domain == "database":
            assert service == "history", "Use the 'history' service with 'database'"
            return await self.get_history(**data)

        # Keep this just in case anyone is still using call_service() for templates
        if domain == "template" and service == "render":
            return await self.render_template(namespace, data)

        req = {"type": "call_service", "domain": domain, "service": service, "service_data": data}

        service_properties = {
            prop: val
            for entry in self.services
            if domain == entry["domain"]
            for name, info in entry["services"].items()
            if name == service
            for prop, val in info.items()
        }

        if return_response is None:
            return_response = self.config.return_result

        # if it has a response section
        if resp := service_properties.get("response"):
            # if the response section says it's not optional
            if not resp.get("optional"):
                req["return_response"] = True

        if target is not None:
            req["target"] = target

        send_coro = self.websocket_send_json(silent=suppress_log_messages, **req)

        if callback is not None:
            error_text=f'Error in callback {callback.__name__} for service {domain}/{service}'
            cb_safety_decorator = utils.warning_decorator(error_text=error_text)

        if return_response is False:
            task = self.AD.loop.create_task(send_coro)
            if callback is not None:
                @cb_safety_decorator
                def cb_future(self, f: asyncio.Future):
                    # Includes the self parameter for the loggers in the decorator to work
                    return callback(f.result())
                task.add_done_callback(cb_future)
        else:
            try:
                res = await asyncio.wait_for(send_coro, timeout=hass_timeout)
            except asyncio.TimeoutError:
                self.logger.error(f"Timed out [{hass_timeout:.0f}s] during service call: {req}")
            else:
                if callback is not None:
                    @cb_safety_decorator
                    async def cb_safe(self):
                        # Includes the self parameter for the loggers in the decorator to work
                        callback(res)

                    await cb_safe(self)
                return res

    #
    # Events
    #

    @hass_check
    async def fire_plugin_event(self, event, namespace, timeout: float | None = None, **kwargs) -> dict | None:
        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        req = {"type": "fire_event", "event_type": event, "event_data": kwargs}

        @utils.warning_decorator('Error error firing event')
        async def safe_event(self: 'HassPlugin', timeout, req):
            return await self.websocket_send_json(timeout, **req)

        return await safe_event(self, timeout, req)

    #
    # Entities
    #

    async def remove_entity(self, namespace: str, entity_id: str):
        self.logger.debug("remove_entity() %s", entity_id)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        @utils.warning_decorator(error_text=f'Error deleting entity {entity_id}')
        async def safe_delete(self: 'HassPlugin'):
            return await self.http_method('delete', f'/api/states/{entity_id}')

        return await safe_delete(self)

    #
    # State
    #

    @utils.warning_decorator(error_text="Unexpected error while getting hass state")
    async def get_complete_state(self) -> dict[str, dict[str, Any]]:
        """This method is needed for all AppDaemon plugins"""
        hass_state = (await self.websocket_send_json(type="get_states"))["result"]
        states = {s["entity_id"]: s for s in hass_state}
        return states

    @utils.warning_decorator(error_text='Unexpected error setting state')
    async def set_plugin_state(
        self,
        namespace: str,
        entity_id: str,
        state: Any | None = None,
        attributes: Any | None = None
    ):
        self.logger.debug("set_plugin_state() %s %s %s %s", namespace, entity_id, state, attributes)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        @utils.warning_decorator(error_text=f'Error setting state for {entity_id}')
        async def safe_set_state(self: 'HassPlugin'):
            api_url = self.config.get_entity_api(entity_id)
            return await self.http_method('post', api_url, state=state, attributes=attributes)

        return await safe_set_state(self)

    @utils.warning_decorator(error_text='Unexpected error getting state')
    async def get_plugin_state(self, entity_id: str, timeout: float | None = None):
        return await self.http_method('get', f'/api/states/{entity_id}', timeout)

    async def check_for_entity(self, entity_id: str, timeout: float | None = None) -> bool:
        """Tries to get the state of an entity ID to see if it exists"""
        resp = await self.get_plugin_state(entity_id, timeout)
        if isinstance(resp, dict):
            return True
        elif isinstance(resp, ClientResponse) and resp.status == 404:
            return False

    @utils.warning_decorator(error_text='Unexpected error getting history')
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

        result: list[list[dict[str, Any]]] = await self.http_method(
            "get", endpoint,
            filter_entity_id=",".join(filter_entity_id),
            end_time=end_time,
            minimal_response=minimal_response,
            no_attributes=no_attributes,
            significant_changes_only=significant_changes_only,
        )
        # nested comprehension to convert the datetimes for convenience
        result = [
            [
                {
                    k: (
                        datetime
                        .datetime
                        .fromisoformat(v)
                        .astimezone(self.AD.tz)
                    ) if k.startswith("last_") else v
                    for k, v in individual_result.items()
                }
                for individual_result in entity_res
            ]
            for entity_res in result
        ]
        # result = {eid: r for eid, r in zip(filter_entity_id, result)}
        return result

    @utils.warning_decorator(error_text='Unexpected error getting logbook')
    async def get_logbook(
        self,
        entity: str | None = None,
        timestamp: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
    ) -> list[dict[str, str | datetime.datetime]]:
        """Used to get HA's logbook"""
        endpoint = "/api/logbook"
        if timestamp is not None:
            endpoint += f"/{timestamp.isoformat()}"

        assert await self.check_for_entity(entity_id=entity), f"'{entity}' does not exist"

        result: list[dict[str, str]] = await self.http_method(
            "get",
            endpoint,
            entity=entity,
            end_time=end_time
        )

        result = [
            {
                k: v if k != "when" else (
                    datetime
                    .datetime
                    .fromisoformat(v)
                    .astimezone(self.AD.tz)
                )
                for k, v in entry.items()
            }
            for entry in result
        ]
        return result

    @utils.warning_decorator(error_text='Unexpected error rendering template')
    async def render_template(self, namespace: str, template: str):
        self.logger.debug(
            "render_template() namespace=%s data=%s",
            namespace,
            template,
        )

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace
        return await self.http_method("post", "/api/template", template=template)
