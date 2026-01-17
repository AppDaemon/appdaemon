"""
Interface with Home Assistant, send and receive evets, state etc.
"""

import asyncio
import functools
import json
import ssl
from collections.abc import AsyncGenerator, Callable, Coroutine, Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any, Literal, Optional

import aiohttp
from aiohttp import ClientResponseError, WebSocketError, WSMsgType
from pydantic import BaseModel

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.models.config.plugin import HASSConfig, StartupConditions
from appdaemon.plugin_management import PluginBase
from appdaemon.types import TimeDeltaLike

from .exceptions import HAEventsSubError, HassConnectionError
from .utils import ServiceCallStatus, hass_check


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
    services: dict[
        str,  # Domain
        dict[
            str,  # Service name
            dict[
                str,  # Field name
                Any,  # Field information
            ],
        ],
    ]

    _result_futures: dict[int, asyncio.Future]
    _silent_results: dict[int, bool]
    _request_context: dict[int, dict[str, Any]]
    startup_conditions: list[StartupWaitCondition]
    maintenance_tasks: list[asyncio.Task]
    """List of tasks that run in the background as part of the plugin operation. These are tracked because they might
    need to get cancelled during shutdown."""

    start: float

    first_time: bool = True
    stopping: bool = False

    def __init__(self, ad: "AppDaemon", name: str, config: HASSConfig):
        super().__init__(ad, name, config)

        self.id = 0
        self.metadata = {}
        self.services = {}
        self._result_futures = {}
        self._silent_results = {}
        self._request_context = {}
        self.startup_conditions = []
        self.maintenance_tasks = []

        self.service_logger = self.diag.getChild("services")
        self.logger.info("HASS Plugin initialization complete")

    async def stop(self):
        await self.ws.close()
        self.logger.debug("Websocket closed for '%s'", self.name)

        await self.session.close()
        self.logger.debug("aiohttp session closed for '%s'", self.name)

    def _create_maintenance_task(self, coro: Coroutine, name: str) -> asyncio.Task:
        task = self.AD.loop.create_task(coro, name=name)
        self.maintenance_tasks.append(task)
        task.add_done_callback(lambda t: self.maintenance_tasks.remove(t))
        return task

    def create_session(self) -> aiohttp.ClientSession:
        """Handles creating an :py:class:`~aiohttp.ClientSession` with the cert information from the plugin config
        and the authorization headers for the `REST API <https://developers.home-assistant.io/docs/api/rest>`_.
        """
        ssl_context = ssl.create_default_context(capath=self.config.cert_path)
        conn = aiohttp.TCPConnector(ssl_context=ssl_context)

        connect_timeout_secs = self.config.connect_timeout.total_seconds()
        return aiohttp.ClientSession(
            connector=conn,
            headers=self.config.auth_headers,
            json_serialize=utils.convert_json,
            timeout=aiohttp.ClientTimeout(
                connect=connect_timeout_secs,
                sock_connect=connect_timeout_secs,
            ),
        )

    async def websocket_msg_factory(self) -> AsyncGenerator[aiohttp.WSMessage]:
        """Async generator that yields websocket messages.

        Uses :py:meth:`~HassPlugin.create_session` and :py:meth:`~aiohttp.ClientSession.ws_connect` to connect to Home
        Assistant.

        See the :py:ref:`aiohttp websockets documentation <aiohttp-client-websockets>` for more information.

        Yields:
            aiohttp.WSMessage: Incoming messages on the websocket connection
        """
        self.start = perf_counter()
        async with self.create_session() as self.session:
            try:
                async with self.session.ws_connect(
                    url=self.config.websocket_url,
                    max_msg_size=self.config.ws_max_msg_size,
                ) as self.ws:
                    if (exc := self.ws.exception()) is not None:
                        raise HassConnectionError("Failed to connect to Home Assistant websocket") from exc

                    async for msg in self.ws:
                        yield msg
            finally:
                self.connect_event.clear()

    async def match_ws_msg(self, msg: aiohttp.WSMessage) -> None:
        """Uses a :py:ref:`match <class-patterns>` statement on :py:class:`~aiohttp.WSMessage`.

        Uses :py:meth:`~HassPlugin.process_websocket_json` on :py:attr:`~aiohttp.WSMsgType.TEXT` messages.
        """
        match msg:
            case aiohttp.WSMessage(type=WSMsgType.TEXT, data=str(data)):
                # create a separate task for processing messages to keep the message reading task unblocked
                self.updates_recv += 1
                self.bytes_recv += len(data)
                # Intentionally not using self._create_maintenance_task here
                self.AD.loop.create_task(self.process_websocket_json(msg.json()), name="process_ws_msg")
            case aiohttp.WSMessage(type=WSMsgType.ERROR, data=WebSocketError() as err):
                self.logger.error("Error from aiohttp websocket: %s", err)
            case aiohttp.WSMessage(type=WSMsgType.CLOSE):
                self.logger.debug("Received %s message", msg.type)
            case _:
                self.logger.warning("Unhandled websocket message type: %s", msg.type)

    @utils.warning_decorator(error_text="Error during processing jSON", reraise=True)
    async def process_websocket_json(self, resp: dict[str, Any]) -> None:
        """Uses a :py:ref:`match <mapping-patterns>` statement around the JSON received from the websocket.

        It handles both authorization and routing the responses to :py:meth:`~HassPlugin.receive_event` and
        :py:meth:`~HassPlugin.receive_result`.
        """
        match resp:
            case {"type": "auth_required", "ha_version": ha_version}:
                self.logger.info("Connected to Home Assistant %s with aiohttp websocket", ha_version)
                # Use await here so that nothing else can happen until the post connection stuff is done
                await self.__post_conn__()
            case {"type": "auth_ok", "ha_version": ha_version}:
                self.logger.info("Authenticated to Home Assistant %s", ha_version)
                # Creating a task here allows the plugin to still receive events as it waits for the startup conditions
                self._create_maintenance_task(self.__post_auth__(), name="post_auth")
            case {"type": "auth_invalid", "message": message}:
                self.logger.error("Failed to authenticate to Home Assistant: %s", message)
                await self.ws.close()
            case {"type": "ping"}:
                await self.ping()
            case {"type": "pong", "id": resp_id}:
                if future := self._result_futures.get(resp_id):
                    future.set_result(resp)
            case {"type": "result"}:
                await self.receive_result(resp)
            case {"type": "event", "event": event}:
                await self.receive_event(event)
            case {"type": type_}:
                raise NotImplementedError(type_)

    async def __post_conn__(self) -> None:
        """Initialization to do after getting connected to the Home Assistant websocket"""
        self.connect_event.set()
        self.id = 0
        await self.websocket_send_json(**self.config.auth_json)

    async def __post_auth__(self) -> None:
        """Initialization to do after getting authenticated on the websocket"""
        res = await self.websocket_send_json(type="subscribe_events")
        match res:
            case {"success": True, "ad_duration": ad_duration}:
                self.logger.debug(
                    "Subscribed to Home Assistant events from the websocket in %s",
                    utils.format_timedelta(ad_duration),
                )
            case {"success": False, "error": {"code": code, "message": msg}}:
                raise HAEventsSubError(code, msg)
            case _:
                raise HAEventsSubError(-1, f"Unknown response from subscribe_events: {res}")

        self._create_maintenance_task(self.looped_coro(self.get_hass_config, self.config.config_sleep_time.total_seconds()), name="get_hass_config loop")
        self._create_maintenance_task(self.looped_coro(self.get_hass_services, self.config.services_sleep_time.total_seconds()), name="get_hass_services loop")

        if self.first_time:
            conditions = self.config.appdaemon_startup_conditions
        else:
            conditions = self.config.plugin_startup_conditions
        await self.wait_for_conditions(conditions)
        if conditions is not None:
            self.logger.info("All plugin startup conditions met")

        if not self.config.enable_started_event and not self.is_ready:
            # check the metadata to see if it's already running
            await self.get_hass_config()  # this will set the ready event if it is

        if not self.is_ready:
            self.logger.info("Waiting for Home Assistant to start")
            await self.ready_event.wait()

        await self.notify_plugin_started(meta=await self.get_hass_config(), state=await self.get_complete_state())
        self.first_time = False

        self.logger.info(f"Completed initialization in {self.time_str()}")

    @hass_check
    async def ping(self, timeout: float = 1.0) -> dict[str, Any] | None:
        """Method for testing response times over the websocket."""
        # https://developers.home-assistant.io/docs/api/websocket/#pings-and-pongs
        return await self.websocket_send_json(timeout=timeout, type="ping")

    @utils.warning_decorator(error_text="Unexpected error during receive_result")
    async def receive_result(self, resp: dict):
        silent = self._silent_results.pop(resp["id"], False) or self.AD.config.suppress_log_messages
        request_context = self._request_context.pop(resp["id"], {})

        if (future := self._result_futures.pop(resp["id"], None)) is not None:
            if not future.done():
                future.set_result(resp)
            else:
                if not silent:
                    self.logger.warning(f"Request already timed out for {resp['id']}")
        else:
            if not silent:
                self.logger.warning(f"Received result without a matching future: {resp}")

        if not silent:
            match resp["success"]:
                case True:
                    self.logger.debug(f"Received successful result from ID {resp['id']}")
                case False:
                    self.logger.warning("Error with websocket result: %s: %s: request=%s", resp["error"]["code"], resp["error"]["message"], str(request_context))
                case None:
                    self.logger.error(f"Invalid response success value: {resp['success']} for request: {str(request_context)}")

    @utils.warning_decorator(error_text="Unexpected error during receive_event")
    async def receive_event(self, event: dict[str, Any]) -> None:
        self.logger.debug(f"Received event type: {event['event_type']}")

        meta_attrs = {"origin", "time_fired", "context"}
        event["data"]["metadata"] = {a: val for a in meta_attrs if (val := event.pop(a, None)) is not None}

        await self.AD.events.process_event(self.namespace, event)

        # check startup conditions
        if not self.is_ready:
            for condition in self.startup_conditions:
                if not condition.conditions_met:
                    condition.check_received_event(event)
                    if condition.conditions_met:
                        self.logger.info(f"HASS startup condition met {condition}")

        match event:
            case {"event_type": "homeassistant_started"}:
                self.logger.info(f"Home Assistant fully started after {utils.time_str(self.start)}")
                self.ready_event.set()
            case {"event_type": "service_registered", "data": {"domain": domain, "service": service}}:
                # https://data.home-assistant.io/docs/events/#service_registered
                await self.check_register_service(domain, service, silent=True)
            # Everything below here is just for information/debug purposes
            case {  #
                "event_type": "call_service",
                "data": {
                    "domain": domain,
                    "service": service,
                    "service_data": {
                        "entity_id": entity_id,
                    },
                },
            }:
                self.logger.debug(f"Service {domain}.{service} called with {entity_id}")
            case {"event_type": "entity_registry_updated"}:
                pass
            case {  # https://data.home-assistant.io/docs/events/#state_changed
                "event_type": "state_changed",
                "data": {
                    "entity_id": entity_id,
                    "new_state": {"state": new_state},
                    # "old_state": {"state": old_state}, # old_state is sometimes None
                },
            }:
                self.logger.debug(f"{entity_id} state changed to {new_state}")
            case {"event_type": "mobile_app_notification_action", "data": {"action": action}}:
                self.logger.debug("Mobile action: %s", action)
            case {"event_type": "mobile_app_notification_cleared"}:
                ...
            case {"event_type": "android.zone_entered"}:
                ...
            case {"event_type": "component_loaded", "data": {"component": component}}:
                self.logger.debug("Loaded component: %s", component)
            case {"event_type": other_event}:
                if other_event.startswith("recorder"):
                    return
                elif other_event == "state_changed":
                    self.logger.debug("State changed event received, but not handled")
                self.logger.debug("Unrecognized event %s", other_event)

    @utils.warning_decorator(error_text="Unexpected error during websocket send")
    async def websocket_send_json(
        self,
        timeout: TimeDeltaLike | None = None,
        *,  # Arguments after this are keyword-only
        silent: bool = False,
        **request: Any,
    ) -> dict[str, Any] | None:
        """
        Send a JSON request over the websocket and await the response.

        The `id` parameter is handled automatically and is used to match the response to the request.

        Args:
            timeout (TimeDeltaLike, optional): Length of time to wait for a response from Home
                Assistant with a matching `id`. Defaults to the value of the `ws_timeout` setting in the plugin config.
            silent (bool, optional): If set to `True`, the method will not log the request or response. Defaults to
                `False`.
            **request (Any): Zero or more keyword arguments that will make up JSON request.

        Returns:
            A dict containing the response from Home Assistant.
        """
        request = utils.clean_kwargs(request)
        request = utils.remove_literals(request, (None,))

        if not self.connect_event.is_set():
            self.logger.debug("Not connected to websocket, skipping JSON send.")
            return

        # auth requests don't have an id field assigned
        if not request.get("type") == "auth":
            self.id += 1
            request["id"] = self.id

            if not silent:
                # include this in the "not auth" section so we don't accidentally put the token in the logs
                req_json = json.dumps(request, indent=4)
                for i, line in enumerate(req_json.splitlines()):
                    if i == 0:
                        self.logger.debug(f"Sending JSON: {line}")
                    else:
                        self.logger.debug(line)

        send_time = perf_counter()
        try:
            await self.ws.send_json(request)
        # happens when the connection closes in the middle, which could be during shutdown
        except ConnectionResetError:
            if self.AD.stopping:
                self.logger.debug("Not connected to websocket, skipping JSON send.")
                return
            else:
                raise  # Something bad actually happened, so raise the exception

        self.update_perf(bytes_sent=len(json.dumps(request)), requests_sent=1)

        match request:
            case {"type": "auth"}:
                return

        future = self.AD.loop.create_future()
        self._result_futures[self.id] = future
        self._silent_results[self.id] = silent
        self._request_context[self.id] = request

        try:
            timeout = utils.parse_timedelta(self.config.ws_timeout if timeout is None else timeout)
            result: dict = await asyncio.wait_for(future, timeout=timeout.total_seconds())
        except asyncio.TimeoutError:
            ad_status = ServiceCallStatus.TIMEOUT
            result = {"success": False}
            if not silent:
                self.logger.warning(f"Timed out [{timeout}] waiting for request: {request}")
        except asyncio.CancelledError:
            ad_status = ServiceCallStatus.TERMINATING
            result = {"success": False}
            if not silent:
                self.logger.debug(f"AppDaemon cancelled waiting for the response from the request: {request}")
        else:
            ad_status = ServiceCallStatus.OK

        travel_time = perf_counter() - send_time
        result.update({"ad_status": ad_status.name, "ad_duration": travel_time})
        return result

    @hass_check
    async def http_method(
        self,
        method: Literal["get", "post", "delete"],
        endpoint: str,
        timeout: TimeDeltaLike | None = 10,
        **kwargs: Any,
    ) -> str | dict[str, Any] | list[Any] | aiohttp.ClientResponseError | None:
        """Wrapper for making HTTP requests to Home Assistant's
        `REST API <https://developers.home-assistant.io/docs/api/rest>`_.

        Args:
            method (Literal['get', 'post', 'delete']): HTTP method to use.
            endpoint (str): Home Assistant REST endpoint to use. For example '/api/states'
            timeout (TimeDeltaLike, optional): Timeout for the method in seconds. Defaults to 10s.
            **kwargs (optional): Zero or more keyword arguments. These get used as the data for the method, as
                appropriate.
        """
        kwargs = utils.clean_http_kwargs(kwargs)
        url = self.config.ha_url / endpoint.lstrip("/")

        try:
            self.update_perf(
                bytes_sent=len(str(url)) + len(json.dumps(kwargs).encode("utf-8")),
                requests_sent=1,
            )

            self.logger.debug(f"Hass {method.upper()} {endpoint}: {kwargs}")
            match method.lower():
                case "get":
                    http_method = functools.partial(self.session.get, params=kwargs)
                case "post":
                    http_method = functools.partial(self.session.post, json=kwargs)
                case "delete":
                    http_method = functools.partial(self.session.delete, params=kwargs)
                case _:
                    raise ValueError(f"Invalid method: {method}")

            timeout = utils.parse_timedelta(timeout)
            client_timeout = aiohttp.ClientTimeout(total=timeout.total_seconds())
            async with http_method(url=url, timeout=client_timeout) as resp:
                self.logger.debug(f"HTTP {method.upper()} {resp.url}")
                self.update_perf(bytes_recv=resp.content_length, updates_recv=1)
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as cre:
                    self.logger.error("[%d] HTTP %s: %s %s", cre.status, method.upper(), cre.message, kwargs)
                    return cre
                else:
                    self.logger.debug("%s success from %s", resp.method, resp.url)
                    match resp.content_type:
                        case "application/json":
                            return await resp.json()
                        case "text/plain":
                            return await resp.text()
                        case _:
                            self.logger.warning("Unhandled content type: %s", resp.content_type)
                            return None
        except asyncio.TimeoutError:
            self.logger.error("Timed out waiting for %s", url)
        except asyncio.CancelledError:
            self.logger.debug("Task cancelled during %s", method.upper())
        except aiohttp.ServerDisconnectedError:
            self.logger.error("HASS disconnected unexpectedly during %s to %s", method.upper(), url)

    async def wait_for_conditions(self, conditions: StartupConditions | None) -> None:
        if conditions is None:
            return

        self.startup_conditions = []

        if event := conditions.event:
            self.logger.info(f"Adding startup event condition: {event}")
            event_cond_data = event.model_dump(exclude_unset=True)
            self.startup_conditions.append(StartupWaitCondition(event_cond_data))

        if cond := conditions.state:
            current_state = await self.check_for_entity(cond.entity, local=False)
            if cond.value is None:
                match current_state:
                    case dict():
                        self.logger.info(f"Startup state condition already met: {cond.entity} exists")
                    case False:
                        # Wait for entity to exist
                        self.startup_conditions.append(
                            StartupWaitCondition(
                                {"event_type": "state_changed", "data": {"entity_id": cond.entity}},
                            )
                        )
            else:
                data = cond.model_dump(exclude_unset=True)
                if isinstance(current_state, dict) and utils.deep_compare(data["value"], current_state):
                    self.logger.info(f"Startup state condition already met: {data}")
                else:
                    self.logger.info(f"Adding startup state condition: {data}")
                    self.startup_conditions.append(
                        StartupWaitCondition(
                            {"event_type": "state_changed", "data": {"entity_id": cond.entity, "new_state": data["value"]}},
                        )
                    )

        tasks: list[asyncio.Task[Literal[True] | None]] = [
            self._create_maintenance_task(cond.event.wait(), name=f"startup condition: {cond}")
            for cond in self.startup_conditions
        ]  # fmt: skip

        if delay := conditions.delay:
            self.logger.info(f"Adding a {delay:.0f}s delay to the {self.name} startup")
            task = self._create_maintenance_task(self.AD.utility.sleep(delay, timeout_ok=True), name="startup delay")
            tasks.append(task)

        self.logger.info(f"Waiting for {len(tasks)} startup condition tasks after {self.time_str()}")
        if tasks:
            await asyncio.wait(tasks)

    async def get_updates(self):
        """Main function for running the HASS plugin.

        Combines :py:meth:`~HassPlugin.websocket_msg_factory` with :py:meth:`~HassPlugin.match_ws_msg` to process
        websocket messages as they come in. This happens in a while loop that breaks on AppDaemon's internal stop event.

        This uses the :py:meth:`~appdaemon.utility_loop.Utility.sleep` utility method between retries if the connection
        fails.
        """
        while not self.AD.stopping:
            try:
                async for msg in self.websocket_msg_factory():
                    await self.match_ws_msg(msg)
                    continue
                raise HassConnectionError("Websocket connection lost")
            except Exception as exc:
                if not self.AD.stopping:
                    self.error.error(exc)
                    self.logger.info("Attempting reconnection in %s", utils.format_timedelta(self.config.retry_secs))
                    if self.is_ready:
                        # Will only run the first time through the loop after a failure
                        await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                    self.ready_event.clear()
                    await self.AD.utility.sleep(self.config.retry_secs.total_seconds(), timeout_ok=True)

            # always do this block, no matter what
            finally:
                for task in self.maintenance_tasks:
                    if not task.done():
                        task.cancel()

                if not self.AD.stopping:
                    for fut in self._result_futures.values():
                        if not fut.done():
                            fut.cancel()
                    self._result_futures.clear()
                    self._silent_results.clear()
                    self._request_context.clear()

                    # remove callback from getting local events
                    await self.AD.callbacks.clear_callbacks(self.name)

    def _check_for_service(self, domain: str, service: str) -> bool:
        return service in self.AD.services.services.get(self.namespace, {}).get(domain, {})

    async def check_register_service(
        self,
        domain: str,
        service: str,
        *,
        force: bool = False,
        silent: bool = False,
    ) -> None:
        """Register a service with AppDaemon if it doesn't already exist."""
        if (not self._check_for_service(domain, service)) or force:
            if not silent:
                self.logger.debug("Registering new service %s/%s", domain, service)
            self.AD.services.register_service(
                self.namespace,
                domain,
                service,
                self.call_plugin_service,
                silent=True,
            )
        elif not silent:
            self.logger.debug("Service %s/%s already registered", domain, service)

    #
    # Utility functions
    #

    # def utility(self):
    # self.logger.debug("Utility (currently unused)")
    # return None

    async def looped_coro(self, coro: Callable[..., Coroutine], sleep: float):
        """Run a coroutine in a loop with a sleep interval.

        This is a utility function that can be used to run a coroutine in a loop with a sleep interval. It is used
        internally to run the `get_hass_config` and
        """
        while not self.AD.stopping:
            try:
                await coro()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.logger.error("Error in looped coroutine: %s", e)
            finally:
                await self.AD.utility.sleep(sleep, timeout_ok=True)

    @utils.warning_decorator(error_text="Unexpected error while getting hass config")
    async def get_hass_config(self) -> dict[str, Any] | None:
        resp = await self.websocket_send_json(type="get_config")
        match resp:
            case {"success": True, "result": meta}:
                if meta.get("state") == "RUNNING":
                    self.ready_event.set()
                self.metadata = meta
                return self.metadata
            case _:
                return  # websocket_send_json will log warnings if something happens on the AD side

    @utils.warning_decorator(error_text="Unexpected error while getting hass services")
    async def get_hass_services(self) -> dict[str, Any] | None:
        """Use the `get_services` feature of the Home Assistant websocket API.

        This registers a service in AppDaemon for each service that is returned by Home Assistant, and sets the
        `services` attribute the a deepcopy of the services dict as returned by Home Assistant.
        """
        resp = await self.websocket_send_json(type="get_services")
        match resp:
            case {"result": full_services, "success": True}:
                with self.AD.services.services_lock:
                    await self._register_http_services()
                    self.services = deepcopy(full_services)
                    self._dump_services("ha")
                    to_register = [
                        functools.partial(self.check_register_service, domain, service, silent=True)
                        for domain, services in full_services.items()
                        for service in services
                        if not self._check_for_service(domain, service)
                    ]
                    self.logger.debug(f"Registering {len(to_register)} new services")
                    for registration in to_register:
                        await registration()
                    self.logger.debug("Updated internal service registry")
                    return self.services
            case _:
                return  # websocket_send_json method will log warnings if something happens on the AD side

    def _compare_services(self, typ: Literal["ha", "ad"]) -> dict[str, set[str]]:
        match typ:
            case "ha":
                # This gets the names of all the services as they come back from the get_hass_services method that gets
                # called when the plugin starts and at the interval defined by services_sleep_time in the plugin config.
                services = {domain: set(services.keys()) for domain, services in self.services.items()}
            case "ad":
                # This gets the names of all the services as they're stored in the services subsystem
                services = {
                    domain: set(services.keys())
                    for domain, services in self.AD.services.services[self.namespace].items()
                }  # fmt: skip
            case _:
                services = {}
        return services

    def _dump_services(self, typ: Literal["ha", "ad"]) -> None:
        services = self._compare_services(typ)
        service_str = json.dumps(services, indent=4, sort_keys=True, default=str)
        self.service_logger.debug(f"Services ({typ}):\n{service_str}")

    async def _register_http_services(self):
        """Register the services that are special cases because they use the REST API instead of the websocket API."""
        await self.check_register_service(domain="database", service="history", silent=True)
        await self.check_register_service(domain="render", service="template", silent=True)

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
        target: str | dict | None = None,
        entity_id: str | list[str] | None = None,  # Maintained for legacy compatibility
        hass_timeout: str | int | float | None = None,
        return_response: bool | None = None,
        suppress_log_messages: bool = False,
        **data,
    ):
        """Uses the websocket to call a service in Home Assistant.

        The ``self.check_register_service`` method uses this method when calling ``self.AD.services.register_service``,
        which causes ``self.call_plugin_service`` to be called when a service is called in this plugin's namespace.

        Args:
            namespace (str): Namespace for the plugin. Used as a sanity check. Don't call this from the wrong place.
            domain (str): Domain of the service to call
            service (str): Name of the service to call
            target (str | dict | None, optional): Target of the service. Defaults to None. If the ``entity_id`` argument
                is not used, then the value of the ``target`` argument is used directly.
            entity_id (str | list[str] | None, optional): Entity ID to target with the service call. This argument is
                maintained for legacy compatibility. Defaults to None.
            hass_timeout (str | int | float, optional): Sets the amount of time to wait for a response from Home
                Assistant. If no value is specified, the default timeout is 10s. The default value can be changed using
                the ``ws_timeout`` setting the in the Hass plugin configuration in ``appdaemon.yaml``. Even if no data
                is returned from the service call, Home Assistant will still send an acknowledgement back to AppDaemon,
                which this timeout applies to. Note that this is separate from the ``timeout``. If ``timeout`` is
                shorter than this one, it will trigger before this one does.
            return_response (bool, optional): Indicates whether Home Assistant should return a response to the service
                call. This is only supported for some services and Home Assistant will return an error if used with a
                service that doesn't support it. If returning a response is required or optional (based on the service
                definitions given by Home Assistant), this will automatically be set to ``True``.
            suppress_log_messages (bool, optional): If this is set to ``True``, Appdaemon will suppress logging of
                warnings for service calls to Home Assistant, specifically timeouts and non OK statuses. Use this flag
                and set it to ``True`` to suppress these log messages if you are performing your own error checking as
                described `here <APPGUIDE.html#some-notes-on-service-calls>`__
            service_data (dict, optional): Used as an additional dictionary to pass arguments into the ``service_data``
                field of the JSON that goes to Home Assistant. This is useful if you have a dictionary that you want to
                pass in that has a key like ``target`` which is otherwise used for the ``target`` argument.
            **data: Zero or more keyword arguments. These get used as the data for the service call.
        """
        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        # This match block handles the special cases for services that use the legacy service calls. These are still
        # relevant because they provide services for features that can only be used through the REST API. Otherwise,
        # service calls use the websocket API to call service actions in Home Assistant.
        match (domain, service):
            case ("database", "history"):
                return await self.get_history(**data)
            case ("render", "template"):
                return await self.render_template(namespace, data)

        # https://developers.home-assistant.io/docs/api/websocket#calling-a-service-action
        req: dict[str, Any] = {"type": "call_service", "domain": domain, "service": service}

        if return_response is not None:
            req["return_response"] = return_response

        service_data = data.pop("service_data", {})
        service_data.update(data)
        if service_data:
            req["service_data"] = service_data

        service_properties = {
            prop: val
            for domain_, service_ in self.services.items()  # For each service entry,
            if domain == domain_  # if the domain matches,
            for name, info in service_.items()
            if name == service  # and the service name matches,
            for prop, val in info.items()  # get each of the properties
        }

        match service_properties:
            case {"response": {"optional": False}}:
                # Force the return_response flag if doing so is not optional
                req["return_response"] = True
            case {"response": {"optional": True}} if "return_response" not in req:
                # If the response is optional, but not set above, default to return_response=True.
                req["return_response"] = True

        if target is None and entity_id is not None:
            if all(isinstance(s, str) for s in entity_id):
                req["target"] = {"entity_id": entity_id}
            else:
                self.logger.warning("Bad entity_id: %s", entity_id)
        elif target is not None and entity_id is None:
            req["target"] = target

        send_coro = self.websocket_send_json(timeout=hass_timeout, silent=suppress_log_messages, **req)
        return await send_coro

    #
    # Events
    #

    @hass_check
    async def fire_plugin_event(
        self,
        event: str,
        namespace: str,
        timeout: TimeDeltaLike | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:  # fmt: skip
        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        req = {"type": "fire_event", "event_type": event, "event_data": kwargs}

        @utils.warning_decorator("Error error firing event")
        async def safe_event(self: "HassPlugin", timeout, req):
            return await self.websocket_send_json(timeout, **req)

        return await safe_event(self, timeout, req)

    #
    # Entities
    #

    async def remove_entity(self, namespace: str, entity_id: str):
        self.logger.debug("remove_entity() %s", entity_id)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        @utils.warning_decorator(error_text=f"Error deleting entity {entity_id}")
        async def safe_delete(self: "HassPlugin"):
            return await self.http_method("delete", f"/api/states/{entity_id}")

        return await safe_delete(self)

    #
    # State
    #

    @utils.warning_decorator(error_text="Unexpected error while getting hass state")
    async def get_complete_state(self) -> dict[str, dict[str, Any]] | None:
        """Required method for all AppDaemon plugins.

        Uses the ``/api/states`` endpoint of the `REST API <https://developers.home-assistant.io/docs/api/rest>`_ to
        get an array of state objects. Each state has the following attributes: `entity_id`, `state`, `last_changed` and
        `attributes`.

        The API natively returns the result as a list of dicts, but this turns the result into a single dict based on
        `entity_id` to match what AppDaemon needs from this method.
        """
        resp = await self.websocket_send_json(type="get_states")
        match resp:
            case {"success": True, "result": hass_state}:
                self.logger.debug(f"Received {len(hass_state):,} states")
                return {s["entity_id"]: s for s in hass_state}
            case _:
                return  # websocket_send_json will log warnings if something happens on the AD side

    @utils.warning_decorator(error_text="Unexpected error setting state")
    async def set_plugin_state(
        self,
        namespace: str,
        entity_id: str,
        state: Any | None = None,
        attributes: Any | None = None,
    ) -> dict[str, Any] | None:
        self.logger.debug("set_plugin_state() %s %s %s %s", namespace, entity_id, state, attributes)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        @utils.warning_decorator(error_text=f"Error setting state for {entity_id}")
        async def safe_set_state(self: "HassPlugin"):
            return await self.http_method("post", f"api/states/{entity_id}", state=state, attributes=attributes)

        resp = await safe_set_state(self)
        match resp:
            case ClientResponseError(message=str(msg)):
                self.logger.error("Error setting state: %s", msg)
                return None
            case dict():
                return resp
            case _:
                return None

    @utils.warning_decorator(error_text="Unexpected error getting state")
    async def get_plugin_state(
        self,
        entity_id: str,
        timeout: TimeDeltaLike | None = 5,
    ) -> dict | None:
        resp = await self.http_method("get", f"/api/states/{entity_id}", timeout)
        match resp:
            case ClientResponseError(message=str(msg)):
                self.logger.error("Error getting state: %s", msg)
            case dict() | None:
                return resp
            case _:
                raise ValueError(f"Unexpected result from get_plugin_state: {resp}")

    @utils.warning_decorator(error_text="Unexpected error checking for entity")
    async def check_for_entity(
        self,
        entity_id: str,
        timeout: TimeDeltaLike | None = 5,
        *,  # Arguments after this are keyword-only
        local: bool = False,
    ) -> dict | Literal[False]:
        """Checks for the state of an entity to see if it exists.

        Args:
            entity_id: Entity ID of the entity to check for
            timeout: Timeout for the request to the REST API if local is `False`
            local: If `True`, this will check for the entity in the local state instead of using the REST API. Defaults
                to `False`.

        Returns:
            dict | Literal[False]: dict of the state if the entity exists, otherwise `False`"""
        if local:
            resp = self.AD.state.state.get(self.namespace, {}).get(entity_id, False)
        else:
            resp = await self.get_plugin_state(entity_id, timeout)

        match resp:
            case dict():
                return resp
            case _:
                return False

    @utils.warning_decorator(error_text="Unexpected error getting history")
    async def get_history(
        self,
        filter_entity_id: str | Iterable[str],
        timestamp: datetime | None = None,
        end_time: datetime | None = None,
        minimal_response: bool | None = None,
        no_attributes: bool | None = None,
        significant_changes_only: bool | None = None,
    ) -> list[list[dict[str, Any]]] | None:
        """Returns an array of state changes using the ``/api/history/period`` endpoint of the
        `REST API <https://developers.home-assistant.io/docs/api/rest>`_. Each object contains further details for the
        entities.

        Args:
            filter_entity_id (str, Iterable[str]): Filter on one or more entities.
            timestamp (datetime, optional): Determines the beginning of the period. Defaults to 1 day before the time of
                the request.
            end_time (datetime, optional):
            minimal_response (bool, optional): Only return last_changed and state for states other than the first and
                last state (much faster). Defaults to `False`
            no_attributes (bool, optional): Skip returning attributes from the database (much faster).
            significant_changes_only (bool, optional): Only return significant state changes.

        Returns:
            list[list[dict[str, Any]]]: List of history lists for each entity.
        """
        if isinstance(filter_entity_id, str):
            filter_entity_id = [filter_entity_id]
        filter_entity_id = ",".join(filter_entity_id)

        endpoint = "/api/history/period"
        if timestamp is not None:
            endpoint += f"/{timestamp.isoformat()}"

        result = await self.http_method(
            "get",
            endpoint,
            filter_entity_id=filter_entity_id,
            end_time=end_time,
            minimal_response=minimal_response,
            no_attributes=no_attributes,
            significant_changes_only=significant_changes_only,
        )

        match result:
            case ClientResponseError(message=str(msg)):
                self.logger.error("Error getting history: %s", msg)
            case list():
                # nested comprehension to convert the datetimes for convenience
                return [
                    [
                        {
                            k: (
                                datetime
                                .fromisoformat(v)
                                .astimezone(self.AD.tz)
                            ) if k.startswith("last_") else v
                            for k, v in individual_result.items()
                        }
                        for individual_result in entity_res
                    ]
                    for entity_res in result
                ]  # fmt: skip
            case _:
                raise ValueError(f"Unexpected result from history: {result}")

    @utils.warning_decorator(error_text="Unexpected error getting logbook")
    async def get_logbook(
        self,
        entity: str | None = None,
        timestamp: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, str | datetime]] | None:
        """Returns an array of logbook entries using the ``/api/logbook/`` endpoint of the
        `REST API <https://developers.home-assistant.io/docs/api/rest>`_

        Args:
            timestamp (datetime, optional): Determines the beginning of the period. Defaults to 1 day before the time of
                the request.
            entity (str, optional): Filter on one entity.
            end_time (datetime, optional): Choose the end of period starting from the `timestamp`
        """
        endpoint = "/api/logbook"
        if timestamp is not None:
            endpoint += f"/{timestamp.isoformat()}"

        resp = await self.http_method("get", endpoint, entity=entity, end_time=end_time)
        match resp:
            case list():
                return [
                    {
                        k: v if k != "when" else (
                            datetime
                            .fromisoformat(v)
                            .astimezone(self.AD.tz)
                        )
                        for k, v in entry.items()
                    }
                    for entry in resp
                ]  # fmt: skip
            case ClientResponseError(status=500):
                self.logger.error("Error getting logbook for '%s', it might not exist.", entity)
            case ClientResponseError(message=str(msg)):
                self.logger.error("Error getting logbook for '%s': %s", entity, msg)
            case _:
                self.logger.error("Unexpected error getting logbook: %s", resp)

    @utils.warning_decorator(error_text="Unexpected error rendering template")
    async def render_template(self, namespace: str, template: str, **kwargs) -> str | None:
        """Render the template using the ``/api/template`` endpoint of the
        `REST API <https://developers.home-assistant.io/docs/api/rest>`_.

        See the `template docs <https://www.home-assistant.io/docs/configuration/templating>`_ for more information.

        If successful, this returns a str of the raw response. It should still be processed downstream with
        :py:func:`~ast.literal_eval`, which will turn the result into its real type.
        """
        self.logger.debug(
            "render_template() namespace=%s data=%s",
            namespace,
            template,
        )

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace
        resp = await self.http_method("post", "/api/template", template=template, **kwargs)
        match resp:
            case str():
                return resp
            case ClientResponseError(message=str(msg)):
                self.logger.error("Error rendering template: %s", msg)
            case _:
                raise ValueError(f"Unexpected result from render_template: {resp}")
