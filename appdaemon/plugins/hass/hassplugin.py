import asyncio
import datetime
import json
import os
import ssl
import traceback
from copy import deepcopy
from typing import Union
from urllib.parse import quote, urlencode

import aiohttp
import pytz
import websocket
from deepdiff import DeepDiff

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.plugin_management import PluginBase


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


class HassPlugin(PluginBase):
    def __init__(self, ad: AppDaemon, name, args):
        super().__init__(ad, name, args)

        # Store args
        self.AD = ad
        self.config = args
        self.name = name

        self.logger.info("HASS Plugin Initializing")

        # validate basic config
        if "ha_key" in args:
            self.logger.warning("ha_key is deprecated please use HASS Long Lived Tokens instead")
        if "ha_url" not in args:
            self.logger.warning("ha_url not found in HASS configuration - module not initialized")

        # Locally store common args and their defaults
        self.appdaemon_startup_conditions = args.get("appdaemon_startup_conditions", {})
        self.cert_path = args.get("cert_path")
        self.cert_verify = args.get("cert_verify")
        self.commtype = args.get("commtype", "WS")

        # Fixes for supervised
        self.ha_key = args.get("ha_key", os.environ.get("SUPERVISOR_TOKEN"))
        self.ha_url = args.get("ha_url", "http://supervisor/core").rstrip("/")
        # End fixes for supervised

        self.namespace = args.get("namespace", "default")
        self.plugin_startup_conditions = args.get("plugin_startup_conditions", {})
        self.retry_secs = int(args.get("retry_secs", 5))
        self.timeout = args.get("timeout")
        self.token = args.get("token")

        # Connections to HA
        self._session = None  # http connection pool for general use
        self.ws = None  # websocket dedicated for event loop

        # Cached state from HA
        self.metadata = None
        self.services = None

        # Internal state flags
        self.already_notified = False
        self.first_time = False
        self.hass_booting = False
        self.reading_messages = False
        self.stopping = False

        # Performance Data

        self.bytes_sent = 0
        self.bytes_recv = 0
        self.requests_sent = 0
        self.updates_recv = 0
        self.last_check_ts = 0

        self.logger.info("HASS Plugin initialization complete")

    async def perf_data(self):
        data = {
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "requests_sent": self.requests_sent,
            "updates_recv": self.updates_recv,
            "duration": await self.AD.sched.get_now_ts() - self.last_check_ts,
        }

        self.bytes_sent = 0
        self.bytes_recv = 0
        self.requests_sent = 0
        self.updates_recv = 0
        self.last_check_ts = await self.AD.sched.get_now_ts()

        return data

    def update_perf(self, **kwargs):
        self.bytes_sent += kwargs.get("bytes_sent", 0)
        self.bytes_recv += kwargs.get("bytes_recv", 0)
        self.requests_sent += kwargs.get("requests_sent", 0)
        self.updates_recv += kwargs.get("updates_recv", 0)

    async def am_reading_messages(self):
        return self.reading_messages

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True
        if self.ws is not None:
            self.ws.close()

    #
    # Placeholder for constraints
    #
    def list_constraints(self):
        return []

    #
    # Persistent HTTP Session to HASS instance
    #
    @property
    def session(self):
        if not self._session:
            # ssl None means to use default behavior which check certs for https
            ssl_context = None if self.cert_verify else False
            if self.cert_verify and self.cert_path:
                ssl_context = ssl.create_default_context(capath=self.cert_path)
            conn = aiohttp.TCPConnector(ssl=ssl_context)

            # configure auth
            headers = {}
            if self.token is not None:
                headers["Authorization"] = "Bearer {}".format(self.token)
            elif self.ha_key is not None:
                headers["x-ha-access"] = self.ha_key

            self._session = aiohttp.ClientSession(
                connector=conn,
                headers=headers,
                json_serialize=utils.convert_json,
            )
        return self._session

    #
    # Connect and return a new WebSocket to HASS instance
    #
    async def create_websocket(self):
        # change to websocket protocol
        url = self.ha_url
        if url.startswith("https://"):
            url = url.replace("https", "wss", 1)
        elif url.startswith("http://"):
            url = url.replace("http", "ws", 1)

        # ssl options
        sslopt = {}
        if self.cert_verify is False:
            sslopt = {"cert_reqs": ssl.CERT_NONE}
        if self.cert_path:
            sslopt["ca_certs"] = self.cert_path
        ws = websocket.create_connection("{}/api/websocket".format(url), sslopt=sslopt)

        # wait for successful connection
        res = await utils.run_in_executor(self, ws.recv)
        result = json.loads(res)
        self.logger.info("Connected to Home Assistant %s", result["ha_version"])

        # Check if auth required, if so send password
        if result["type"] == "auth_required":
            if self.token is not None:
                auth = json.dumps({"type": "auth", "access_token": self.token})
            elif self.ha_key is not None:
                auth = json.dumps({"type": "auth", "api_password": self.ha_key})
            else:
                raise ValueError("HASS requires authentication and none provided in plugin config")

            await utils.run_in_executor(self, ws.send, auth)
            result = json.loads(ws.recv())
            if result["type"] != "auth_ok":
                self.logger.warning("Error in authentication")
                raise ValueError("Error in authentication")

        return ws

    #
    # Get initial state
    #
    async def get_complete_state(self):
        hass_state = await self.get_hass_state()
        states = {}
        for state in hass_state:
            states[state["entity_id"]] = state
        self.logger.debug("Got state")
        self.logger.debug("*** Sending Complete State: %s ***", hass_state)
        return states

    #
    # Get HASS Metadata
    #
    async def get_metadata(self):
        return self.metadata

    #
    # Handle state updates
    #
    async def evaluate_started(self, first_time, plugin_booting, event=None):  # noqa: C901
        if first_time is True:
            self.hass_ready = False
            self.state_matched = False

        if plugin_booting is True:
            startup_conditions = self.plugin_startup_conditions
        else:
            startup_conditions = self.appdaemon_startup_conditions

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
            state = await self.get_complete_state()
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
            state = await self.get_complete_state()
            await self.AD.plugins.notify_plugin_started(
                self.name, self.namespace, self.metadata, state, self.first_time
            )
            self.first_time = False
            self.already_notified = False

    #
    # Callback Testing
    #
    # async def state(self, entity, attribute, old, new, kwargs):
    #    self.logger.info("State: %s %s %s %s {}".format(kwargs), entity, attribute, old, new)
    #
    # async def event(self, event, data, kwargs):
    #    self.logger.debug("Event: %s %s %s", kwargs, event, data)

    # async def schedule(self, kwargs):
    #    self.logger.info("Schedule: {}".format(kwargs))
    #
    #
    #

    async def get_updates(self):  # noqa: C901
        _id = 0
        self.already_notified = False
        self.first_time = True

        #
        # Testing
        #
        # await self.AD.state.add_state_callback(self.name, self.namespace, None, self.state, {})

        # listen for service_registered event
        # await self.AD.events.add_event_callback(self.name, self.namespace, self.event, "service_registered")
        # exec_time = await self.AD.sched.get_now() + datetime.timedelta(seconds=1)
        # await self.AD.sched.insert_schedule(
        #    self.name,
        #    exec_time,
        #    self.schedule,
        #    True,
        #    None,
        #    interval=1
        # )
        #
        #
        #

        while not self.stopping:
            _id += 1
            try:
                #
                # Connect to websocket interface
                #
                self.ws = await self.create_websocket()

                #
                # Subscribe to event stream
                #
                sub = json.dumps({"id": _id, "type": "subscribe_events"})
                await utils.run_in_executor(self, self.ws.send, sub)
                result = json.loads(self.ws.recv())
                if not (result["id"] == _id and result["type"] == "result" and result["success"] is True):
                    self.logger.warning("Unable to subscribe to HA events, id = %s", _id)
                    self.logger.warning(result)
                    raise ValueError("Error subscribing to HA Events")

                #
                # Grab Metadata
                #
                self.metadata = await self.get_hass_config()
                #
                # Register Services
                #
                self.services = await self.get_hass_services()
                for hass_service in self.services:
                    domain = hass_service["domain"]
                    for service in hass_service["services"]:
                        self.AD.services.register_service(
                            self.get_namespace(),
                            domain,
                            service,
                            self.call_plugin_service,
                            __silent=True,
                        )

                # Decide if we can start yet
                self.logger.info("Evaluating startup conditions")
                await self.evaluate_started(True, self.hass_booting)

                # state = await self.get_complete_state()
                # self.reading_messages = True

                # await self.AD.plugins.notify_plugin_started(self.name, self.namespace, self.metadata, state,
                # self.first_time)
                # self.first_time = False
                # self.already_notified = False

                #
                # We schedule a task to check for new services over the next 10 minutes
                #
                asyncio.create_task(self.run_hass_service_check())

                #
                # Loop forever consuming events
                #
                while not self.stopping:
                    ret = await utils.run_in_executor(self, self.ws.recv)
                    result = json.loads(ret)

                    self.update_perf(bytes_recv=len(ret), updates_recv=1)

                    if not (result["id"] == _id and result["type"] == "event"):
                        self.logger.warning("Unexpected result from Home Assistant, id = %s", _id)
                        self.logger.warning(result)

                    if self.reading_messages is False:
                        if result["type"] == "event":
                            await self.evaluate_started(False, self.hass_booting, result["event"])
                        else:
                            await self.evaluate_started(False, self.hass_booting)
                    else:
                        metadata = {}
                        metadata["origin"] = result["event"].pop("origin", None)
                        metadata["time_fired"] = result["event"].pop("time_fired", None)
                        metadata["context"] = result["event"].pop("context", None)
                        result["event"]["data"]["metadata"] = metadata

                        await self.AD.events.process_event(self.namespace, result["event"])

                        if result["event"].get("event_type") == "service_registered":
                            data = result["event"]["data"]
                            domain = data.get("domain")
                            service = data.get("service")

                            if domain is None or service is None:
                                continue

                            await self.check_register_service(domain, service)

                self.reading_messages = False

            except Exception:
                self.reading_messages = False
                self.hass_booting = True
                # remove callback from getting local events
                await self.AD.callbacks.clear_callbacks(self.name)

                if not self.already_notified:
                    await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                    self.already_notified = True
                if not self.stopping:
                    self.logger.warning(
                        "Disconnected from Home Assistant, retrying in %s seconds",
                        self.retry_secs,
                    )
                    self.logger.debug("-" * 60)
                    self.logger.debug("Unexpected error:")
                    self.logger.debug("-" * 60)
                    self.logger.debug(traceback.format_exc())
                    self.logger.debug("-" * 60)
                    await asyncio.sleep(self.retry_secs)

        self.logger.info("Disconnecting from Home Assistant")

    def get_namespace(self):
        return self.namespace

    #
    # Utility functions
    #

    def utility(self):
        self.logger.debug("Utility")
        return None

    #
    # Home Assistant Interactions
    #

    #
    # State
    #

    @hass_check
    async def set_plugin_state(self, namespace, entity_id, **kwargs):
        self.logger.debug("set_plugin_state() %s %s %s", namespace, entity_id, kwargs)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        api_url = f"{self.ha_url}/api/states/{entity_id}"

        try:
            r = await self.session.post(api_url, json=kwargs)
            if r.status == 200 or r.status == 201:
                state = await r.json()
                self.logger.debug("return = %s", state)
            else:
                self.logger.warning(
                    "Error setting Home Assistant state %s.%s, %s",
                    namespace,
                    entity_id,
                    kwargs,
                )
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                state = None
                self.update_perf(bytes_sent=len(json.dumps(kwargs)), bytes_recv=len(await r.text()), requests_sent=1)
            return state
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning("Timeout in set_state(%s, %s, %s)", namespace, entity_id, kwargs)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during set_state()")
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during set_plugin_state()")
            self.logger.warning("Arguments: %s = %s", entity_id, kwargs)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return None

    @hass_check  # noqa: C901
    async def call_plugin_service(self, namespace, domain, service, data):
        self.logger.debug(
            "call_plugin_service() namespace=%s domain=%s service=%s data=%s",
            namespace,
            domain,
            service,
            data,
        )

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        #
        # If data is a string just assume it's an entity_id
        #
        if isinstance(data, str):
            data = {"entity_id": data}

        if domain == "template" and service == "render":
            api_url = "/api/template"

        elif domain == "database":
            return await self.get_history(**data)

        else:
            api_url = f"{self.ha_url}/api/services/{domain}/{service}"

        try:
            r = await self.session.post(api_url, json=data)

            if r.status == 200 or r.status == 201:
                if domain == "template":
                    result = await r.text()
                else:
                    result = await r.json()
            else:
                self.logger.warning(
                    "Error calling Home Assistant service %s/%s/%s",
                    namespace,
                    domain,
                    service,
                )
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                result = None

            self.update_perf(bytes_sent=len(json.dumps(data)), bytes_recv=len(await r.text()), requests_sent=1)
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning(
                "Timeout in call_service(%s/%s/%s, %s)",
                namespace,
                domain,
                service,
                data,
            )
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during call_service()")
        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error during call_plugin_service()")
            self.logger.error("Service: %s.%s.%s Arguments: %s", namespace, domain, service, data)
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)
            return None

    async def get_history(self, **kwargs):
        """Used to get HA's History"""

        try:
            api_url = await self.get_history_api(**kwargs)

            r = await self.session.get(api_url)

            if r.status == 200 or r.status == 201:
                self.bytes_recv += len(await r.text())
                self.updates_recv += 1

                result = await r.json()
            else:
                self.logger.warning("Error calling Home Assistant to get_history")
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                result = None

            self.update_perf(bytes_sent=len(json.dumps(api_url)), bytes_recv=len(await r.text()), requests_sent=1)
            return result

        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during get_history()")

        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error during get_history")
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)

        return None

    async def get_history_api(self, **kwargs):
        query = {}
        entity_id = None
        days = None
        start_time = None
        end_time = None

        kwargkeys = set(kwargs.keys())

        if {"days", "start_time"} <= kwargkeys:
            raise ValueError(
                f'Can not have both days and start time. days: {kwargs["days"]} -- start_time: {kwargs["start_time"]}'
            )

        if "end_time" in kwargkeys and {"start_time", "days"}.isdisjoint(kwargkeys):
            raise ValueError("Can not have end_time without start_time or days")

        entity_id = kwargs.get("entity_id", "").strip()
        days = max(0, kwargs.get("days", 0))

        def as_datetime(args, key):
            if key in args:
                if isinstance(args[key], str):
                    return utils.str_to_dt(args(key)).replace(microsecond=0)
                elif isinstance(args[key], datetime.datetime):
                    return self.AD.tz.localize(args[key]).replace(microsecond=0)
                else:
                    raise ValueError(f"Invalid type for {key}")

        start_time = as_datetime(kwargs, "start_time")
        end_time = as_datetime(kwargs, "end_time")

        # end_time default - now
        now = (await self.AD.sched.get_now()).replace(microsecond=0)
        end_time = end_time if end_time else now

        # Days: Calculate start_time (now-days) and end_time (now)
        if days:
            now = (await self.AD.sched.get_now()).replace(microsecond=0)
            start_time = now - datetime.timedelta(days=days)
            end_time = now

        # Build the url
        # /api/history/period/<start_time>?filter_entity_id=<entity_id>&end_time=<end_time>
        apiurl = f"{self.ha_url}/api/history/period"

        if start_time:
            apiurl += "/" + utils.dt_to_str(start_time.replace(microsecond=0), self.AD.tz)

        if entity_id or end_time:
            if entity_id:
                query["filter_entity_id"] = entity_id
            if end_time:
                query["end_time"] = end_time
            apiurl += f"?{urlencode(query)}"

        return apiurl

    async def get_hass_state(self, entity_id=None):
        if entity_id is None:
            api_url = f"{self.ha_url}/api/states"
        else:
            api_url = f"{self.ha_url}/api/states/{entity_id}"
        self.logger.debug("get_ha_state: url is %s", api_url)
        r = await self.session.get(api_url)
        if r.status == 200 or r.status == 201:
            state = await r.json()
        else:
            self.logger.warning("Error getting Home Assistant state for %s", entity_id)
            txt = await r.text()
            self.logger.warning("Code: %s, error: %s", r.status, txt)
            state = None
        self.update_perf(bytes_sent=len(json.dumps(api_url)), bytes_recv=len(await r.text()), requests_sent=1)
        return state

    def validate_meta(self, meta, key):
        if key not in meta:
            self.logger.warning("Value for '%s' not found in metadata for plugin %s", key, self.name)
            raise ValueError
        try:
            float(meta[key])
        except Exception:
            self.logger.warning(
                "Invalid value for '%s' ('%s') in metadata for plugin %s",
                key,
                meta[key],
                self.name,
            )
            raise

    def validate_tz(self, meta):
        if "time_zone" not in meta:
            self.logger.warning("Value for 'time_zone' not found in metadata for plugin %s", self.name)
            raise ValueError
        try:
            pytz.timezone(meta["time_zone"])
        except pytz.exceptions.UnknownTimeZoneError:
            self.logger.warning(
                "Invalid value for 'time_zone' ('%s') in metadata for plugin %s",
                meta["time_zone"],
                self.name,
            )
            raise

    async def get_hass_config(self):
        try:
            self.logger.debug("get_ha_config()")
            api_url = f"{self.ha_url}/api/config"
            self.logger.debug("get_ha_config: url is %s", api_url)
            r = await self.session.get(api_url)
            r.raise_for_status()
            meta = await r.json()
            #
            # Validate metadata is sane
            #
            self.validate_meta(meta, "latitude")
            self.validate_meta(meta, "longitude")
            self.validate_meta(meta, "elevation")
            self.validate_tz(meta)

            self.update_perf(bytes_sent=len(json.dumps(api_url)), bytes_recv=len(await r.text()), requests_sent=1)
            return meta
        except Exception as ex:
            self.logger.warning("Error getting metadata - retrying: %s", str(ex))
            raise

    async def get_hass_services(self) -> dict:
        try:
            self.logger.debug("get_hass_services()")

            api_url = f"{self.ha_url}/api/services"
            self.logger.debug("get_hass_services: url is %s", api_url)
            r = await self.session.get(api_url)

            r.raise_for_status()
            services = await r.json()

            self.update_perf(bytes_sent=len(json.dumps(api_url)), bytes_recv=len(await r.text()), requests_sent=1)

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

            return services

        except Exception:
            self.logger.warning("Error getting services - retrying")
            raise

    async def run_hass_service_check(self) -> None:
        """Used to re-run get hass service, at startup"""

        count = 0
        while count <= 10:  # it runs only a maximum of 10 times
            count += 1
            await asyncio.sleep(60)

            # get hass services
            hass_services = await self.get_hass_services()
            if not isinstance(hass_services, list):
                continue

            # now check if any of the services exists

            for hass_service in hass_services:
                domain = hass_service["domain"]
                services = hass_service["services"]

                await self.check_register_service(domain, services)

    async def check_register_service(self, domain: str, services: Union[dict, str]) -> bool:
        """Used to check and register a service if need be"""

        domain_exists = False
        service_index = -1

        # now to check if it exists already
        for i, registered_services in enumerate(self.services):
            if domain == registered_services["domain"]:
                domain_exists = True
                service_index = i
                break

        if domain_exists is False:  # domain doesn't exist
            self.services.append({"domain": domain, "services": {}})

        domain_services = deepcopy(self.services[service_index])

        if isinstance(services, str):  # its a string
            if services not in domain_services["services"]:
                self.logger.info("Registering new service %s/%s", domain, services)

                self.services[service_index]["services"][services] = {}
                self.AD.services.register_service(
                    self.get_namespace(),
                    domain,
                    services,
                    self.call_plugin_service,
                    __silent=True,
                )

        else:
            for service, service_data in services.items():
                if service not in domain_services["services"]:
                    self.logger.info("Registering new service %s/%s", domain, service)

                    self.services[service_index]["services"][service] = service_data
                    self.AD.services.register_service(
                        self.get_namespace(),
                        domain,
                        service,
                        self.call_plugin_service,
                        __silent=True,
                    )

        return domain_exists

    @hass_check
    async def fire_plugin_event(self, event, namespace, **kwargs):
        self.logger.debug("fire_event: %s, %s %s", event, namespace, kwargs)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        event_clean = quote(event, safe="")
        api_url = f"{self.ha_url}/api/events/{event_clean}"
        try:
            r = await self.session.post(api_url, json=kwargs)
            r.raise_for_status()

            state = await r.json()

            self.update_perf(bytes_sent=len(json.dumps(kwargs)), bytes_recv=len(await r.text()), requests_sent=1)

            return state
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning("Timeout in fire_event(%s, %s, %s)", event, namespace, kwargs)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during fire_event()")
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error fire_plugin_event()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return None

    @hass_check
    async def remove_entity(self, namespace, entity_id):
        self.logger.debug("remove_entity() %s", entity_id)

        # if we get a request for not our namespace something has gone very wrong
        assert namespace == self.namespace

        api_url = f"{self.ha_url}/api/states/{entity_id}"

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
            self.logger.warning("Unexpected error during set_plugin_state()")
            self.logger.warning("Arguments: %s", entity_id)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return None
