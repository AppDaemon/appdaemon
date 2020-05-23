import asyncio
import json
import ssl
import websocket
import traceback
import aiohttp
import pytz
from deepdiff import DeepDiff
import datetime
from urllib.parse import quote

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

        self.stopping = False
        self.ws = None
        self.reading_messages = False
        self.metadata = None
        self.hass_booting = False

        self.logger.info("HASS Plugin Initializing")

        self.name = name

        if "namespace" in args:
            self.namespace = args["namespace"]
        else:
            self.namespace = "default"

        if "ha_key" in args:
            self.ha_key = args["ha_key"]
            self.logger.warning("ha_key is deprecated please use HASS Long Lived Tokens instead")
        else:
            self.ha_key = None

        if "token" in args:
            self.token = args["token"]
        else:
            self.token = None

        if "ha_url" in args:
            self.ha_url = args["ha_url"]
        else:
            self.logger.warning("ha_url not found in HASS configuration - module not initialized")

        if "cert_path" in args:
            self.cert_path = args["cert_path"]
        else:
            self.cert_path = None

        if "timeout" in args:
            self.timeout = args["timeout"]
        else:
            self.timeout = None

        if "cert_verify" in args:
            self.cert_verify = args["cert_verify"]
        else:
            self.cert_verify = True

        if "commtype" in args:
            self.commtype = args["commtype"]
        else:
            self.commtype = "WS"

        if "appdaemon_startup_conditions" in args:
            self.appdaemon_startup_conditions = args["appdaemon_startup_conditions"]
        else:
            self.appdaemon_startup_conditions = None

        if "plugin_startup_conditions" in args:
            self.plugin_startup_conditions = args["plugin_startup_conditions"]
        else:
            self.plugin_startup_conditions = None

        self.session = None
        self.first_time = False
        self.already_notified = False
        self.services = None

        self.logger.info("HASS Plugin initialization complete")

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

    async def evaluate_started(self, delay_done, plugin_booting, event=None):

        if plugin_booting is True:
            startup_conditions = self.plugin_startup_conditions
        else:
            startup_conditions = self.appdaemon_startup_conditions

        state_start = False
        event_start = False
        if startup_conditions is None:
            state_start = True
            event_start = True
        else:
            if "delay" in startup_conditions:
                if delay_done is False:
                    self.logger.info("Delaying startup for %s seconds", startup_conditions["delay"])
                    await asyncio.sleep(int(startup_conditions["delay"]))

            if "state" in startup_conditions:
                state = await self.get_complete_state()
                entry = startup_conditions["state"]
                if "value" in entry:
                    # print(entry["value"], state[entry["entity"]])
                    # print(DeepDiff(state[entry["entity"]], entry["value"]))
                    if entry["entity"] in state and "values_changed" not in DeepDiff(
                        entry["value"], state[entry["entity"]]
                    ):
                        self.logger.info(
                            "Startup condition met: %s=%s", entry["entity"], entry["value"],
                        )
                        state_start = True
                elif entry["entity"] in state:
                    self.logger.info("Startup condition met: %s exists", entry["entity"])
                    state_start = True
            else:
                state_start = True

            if "event" in startup_conditions:
                if event is not None:
                    entry = startup_conditions["event"]
                    if "data" not in entry:
                        if entry["event_type"] == event["event_type"]:
                            event_start = True
                            self.logger.info(
                                "Startup condition met: event type %s fired", event["event_type"],
                            )
                    else:
                        if entry["event_type"] == event["event_type"]:
                            if "values_changed" not in DeepDiff(event["data"], entry["data"]):
                                event_start = True
                                self.logger.info(
                                    "Startup condition met: event type %s, data = %s fired",
                                    event["event_type"],
                                    entry["data"],
                                )

            else:
                event_start = True

        if state_start is True and event_start is True:
            # We are good to go
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

    async def event(self, event, data, kwargs):
        self.logger.debug("Event: %s %s %s", kwargs, event, data)

        if event == "service_registered":  # hass just registered a service
            domain = data["domain"]
            service = data["service"]
            self.AD.services.register_service(
                self.get_namespace(), domain, service, self.call_plugin_service,
            )

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
        await self.AD.events.add_event_callback(self.name, self.namespace, self.event, "service_registered")
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
                url = self.ha_url
                if url.startswith("https://"):
                    url = url.replace("https", "wss", 1)
                elif url.startswith("http://"):
                    url = url.replace("http", "ws", 1)

                sslopt = {}
                if self.cert_verify is False:
                    sslopt = {"cert_reqs": ssl.CERT_NONE}
                if self.cert_path:
                    sslopt["ca_certs"] = self.cert_path
                self.ws = websocket.create_connection("{}/api/websocket".format(url), sslopt=sslopt)
                res = await utils.run_in_executor(self, self.ws.recv)
                result = json.loads(res)
                self.logger.info("Connected to Home Assistant %s", result["ha_version"])
                #
                # Check if auth required, if so send password
                #
                if result["type"] == "auth_required":
                    if self.token is not None:
                        auth = json.dumps({"type": "auth", "access_token": self.token})
                    elif self.ha_key is not None:
                        auth = json.dumps({"type": "auth", "api_password": self.ha_key})
                    else:
                        raise ValueError("HASS requires authentication and none provided in plugin config")

                    await utils.run_in_executor(self, self.ws.send, auth)
                    result = json.loads(self.ws.recv())
                    if result["type"] != "auth_ok":
                        self.logger.warning("Error in authentication")
                        raise ValueError("Error in authentication")
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
                for domain in self.services:
                    for service in domain["services"]:
                        self.AD.services.register_service(
                            self.get_namespace(), domain["domain"], service, self.call_plugin_service, __silent=True
                        )

                # Decide if we can start yet
                self.logger.info("Evaluating startup conditions")
                await self.evaluate_started(False, self.hass_booting)

                # state = await self.get_complete_state()
                # self.reading_messages = True

                # await self.AD.plugins.notify_plugin_started(self.name, self.namespace, self.metadata, state,
                # self.first_time)
                # self.first_time = False
                # self.already_notified = False

                #
                # Loop forever consuming events
                #
                while not self.stopping:
                    ret = await utils.run_in_executor(self, self.ws.recv)
                    result = json.loads(ret)

                    if not (result["id"] == _id and result["type"] == "event"):
                        self.logger.warning("Unexpected result from Home Assistant, id = %s", _id)
                        self.logger.warning(result)

                    if self.reading_messages is False:
                        if result["type"] == "event":
                            await self.evaluate_started(True, self.hass_booting, result["event"])
                        else:
                            await self.evaluate_started(True, self.hass_booting)
                    else:
                        await self.AD.events.process_event(self.namespace, result["event"])

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
                    self.logger.warning("Disconnected from Home Assistant, retrying in 5 seconds")
                    self.logger.debug("-" * 60)
                    self.logger.debug("Unexpected error:")
                    self.logger.debug("-" * 60)
                    self.logger.debug(traceback.format_exc())
                    print(traceback.format_exc())
                    self.logger.debug("-" * 60)
                    await asyncio.sleep(5)

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
        config = (await self.AD.plugins.get_plugin_object(namespace)).config

        # TODO cert_path is not used
        if "cert_path" in config:
            cert_path = config["cert_path"]
        else:
            cert_path = False  # noqa: F841

        if "token" in config:
            headers = {"Authorization": "Bearer {}".format(config["token"])}
        elif "ha_key" in config:
            headers = {"x-ha-access": config["ha_key"]}
        else:
            headers = {}
        api_url = "{}/api/states/{}".format(config["ha_url"], entity_id)

        try:
            r = await self.session.post(api_url, headers=headers, json=kwargs, verify_ssl=self.cert_verify)
            if r.status == 200 or r.status == 201:
                state = await r.json()
                self.logger.debug("return = %s", state)
            else:
                self.logger.warning(
                    "Error setting Home Assistant state %s.%s, %s", namespace, entity_id, kwargs,
                )
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                state = None
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
            "call_plugin_service() namespace=%s domain=%s service=%s data=%s", namespace, domain, service, data,
        )

        #
        # If data is a string just assume it's an entity_id
        #
        if isinstance(data, str):
            data = {"entity_id": data}

        config = (await self.AD.plugins.get_plugin_object(namespace)).config
        if "token" in config:
            headers = {"Authorization": "Bearer {}".format(config["token"])}
        elif "ha_key" in config:
            headers = {"x-ha-access": config["ha_key"]}
        else:
            headers = {}

        if domain == "template":
            api_url = "{}/api/template".format(config["ha_url"])
        
        elif domain == "database":
            return await self.get_history(**data)

        else:
            api_url = "{}/api/services/{}/{}".format(config["ha_url"], domain, service)

        try:

            r = await self.session.post(api_url, headers=headers, json=data, verify_ssl=self.cert_verify)

            if r.status == 200 or r.status == 201:
                if domain == "template":
                    result = await r.text()
                else:
                    result = await r.json()
            else:
                self.logger.warning(
                    "Error calling Home Assistant service %s/%s/%s", namespace, domain, service,
                )
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                result = None

            return result
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning(
                "Timeout in call_service(%s/%s/%s, %s)", namespace, domain, service, data,
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

        # TODO cert_path is not used
        if "cert_path" in self.config:
            cert_path = self.config["cert_path"]
        else:
            cert_path = False  # noqa: F841

        if "token" in self.config:
            headers = {"Authorization": "Bearer {}".format(self.config["token"])}
        elif "ha_key" in self.config:
            headers = {"x-ha-access": self.config["ha_key"]}
        else:
            headers = {}

        try:
            if "entity_id" in kwargs and kwargs["entity_id"] != "":
                filter_entity_id = "?filter_entity_id={}".format(kwargs["entity_id"])
            else:
                filter_entity_id = ""
            start_time = ""
            end_time = ""
            if "days" in kwargs:
                days = kwargs["days"]
                if days - 1 < 0:
                    days = 1
            else:
                days = 1
            if "start_time" in kwargs:
                if isinstance(kwargs["start_time"], str):
                    start_time = utils.str_to_dt(kwargs["start_time"]).replace(microsecond=0)
                elif isinstance(kwargs["start_time"], datetime.datetime):
                    start_time = self.AD.tz.localize(kwargs["start_time"]).replace(microsecond=0)
                else:
                    raise ValueError("Invalid type for start time")

            if "end_time" in kwargs:
                if isinstance(kwargs["end_time"], str):
                    end_time = utils.str_to_dt(kwargs["end_time"]).replace(microsecond=0)
                elif isinstance(kwargs["end_time"], datetime.datetime):
                    end_time = self.AD.tz.localize(kwargs["end_time"]).replace(microsecond=0)
                else:
                    raise ValueError("Invalid type for end time")

            # if both are declared, it can't process entity_id
            if start_time != "" and end_time != "":
                filter_entity_id = ""

            # if starttime is not declared and entity_id is declared, and days specified
            elif (filter_entity_id != "" and start_time == "") and "days" in kwargs:
                start_time = (await self.AD.sched.get_now()).replace(microsecond=0) - datetime.timedelta(days=days)

            # if starttime is declared and entity_id is not declared, and days specified
            elif filter_entity_id == "" and start_time != "" and end_time == "" and "days" in kwargs:
                end_time = start_time + datetime.timedelta(days=days)

            # if endtime is declared and entity_id is not declared, and days specified
            elif filter_entity_id == "" and end_time != "" and start_time == "" and "days" in kwargs:
                start_time = end_time - datetime.timedelta(days=days)

            if start_time != "":
                timestamp = "/{}".format(utils.dt_to_str(start_time.replace(microsecond=0), self.AD.tz))

                if filter_entity_id != "":  # if entity_id is specified, end_time cannot be used
                    end_time = ""

                if end_time != "":
                    end_time = "?end_time={}".format(
                        quote(utils.dt_to_str(end_time.replace(microsecond=0), self.AD.tz))
                    )

            # if no start_time is specified, other parameters are invalid
            else:
                timestamp = ""
                end_time = ""

            api_url = "{}/api/history/period{}{}{}".format(self.config["ha_url"], timestamp, filter_entity_id, end_time)

            r = await self.session.get(api_url, headers=headers, verify_ssl=self.cert_verify)

            if r.status == 200 or r.status == 201:
                result = await r.json()
            else:
                self.logger.warning(
                    "Error calling Home Assistant to get_history"
                    )
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                result = None

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

    async def get_hass_state(self, entity_id=None):

        if self.token is not None:
            headers = {"Authorization": "Bearer {}".format(self.token)}
        elif self.ha_key is not None:
            headers = {"x-ha-access": self.ha_key}
        else:
            headers = {}

        if entity_id is None:
            api_url = "{}/api/states".format(self.ha_url)
        else:
            api_url = "{}/api/states/{}".format(self.ha_url, entity_id)
        self.logger.debug("get_ha_state: url is %s", api_url)
        r = await self.session.get(api_url, headers=headers, verify_ssl=self.cert_verify)
        if r.status == 200 or r.status == 201:
            state = await r.json()
        else:
            self.logger.warning("Error getting Home Assistant state for %s", entity_id)
            txt = await r.text()
            self.logger.warning("Code: %s, error: %s", r.status, txt)
            state = None
        return state

    def validate_meta(self, meta, key):
        if key not in meta:
            self.logger.warning("Value for '%s' not found in metadata for plugin %s", key, self.name)
            raise ValueError
        try:
            float(meta[key])
        except Exception:
            self.logger.warning(
                "Invalid value for '%s' ('%s') in metadata for plugin %s", key, meta[key], self.name,
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
                "Invalid value for 'time_zone' ('%s') in metadata for plugin %s", meta["time_zone"], self.name,
            )
            raise

    async def get_hass_config(self):
        try:
            if self.session is None:
                #
                # Set up HTTP Client
                #
                conn = aiohttp.TCPConnector()
                self.session = aiohttp.ClientSession(connector=conn, json_serialize=utils.convert_json)

            self.logger.debug("get_ha_config()")
            if self.token is not None:
                headers = {"Authorization": "Bearer {}".format(self.token)}
            elif self.ha_key is not None:
                headers = {"x-ha-access": self.ha_key}
            else:
                headers = {}

            api_url = "{}/api/config".format(self.ha_url)
            self.logger.debug("get_ha_config: url is %s", api_url)
            r = await self.session.get(api_url, headers=headers, verify_ssl=self.cert_verify)
            r.raise_for_status()
            meta = await r.json()
            #
            # Validate metadata is sane
            #
            self.validate_meta(meta, "latitude")
            self.validate_meta(meta, "longitude")
            self.validate_meta(meta, "elevation")
            self.validate_tz(meta)

            return meta
        except Exception:
            self.logger.warning("Error getting metadata - retrying")
            raise

    async def get_hass_services(self):
        try:
            self.logger.debug("get_hass_services()")
            if self.token is not None:
                headers = {"Authorization": "Bearer {}".format(self.token)}
            elif self.ha_key is not None:
                headers = {"x-ha-access": self.ha_key}
            else:
                headers = {}

            api_url = "{}/api/services".format(self.ha_url)
            self.logger.debug("get_hass_services: url is %s", api_url)
            r = await self.session.get(api_url, headers=headers, verify_ssl=self.cert_verify)
            r.raise_for_status()
            services = await r.json()
            # manually added HASS history service
            services.append({"domain": "database", "services": ["history"]})
            services.append({"domain": "template", "services": ["render"]})

            return services
        except Exception:
            self.logger.warning("Error getting services - retrying")
            raise

    @hass_check
    async def fire_plugin_event(self, event, namespace, **kwargs):
        self.logger.debug("fire_event: %s, %s %s", event, namespace, kwargs)

        config = (await self.AD.plugins.get_plugin_object(namespace)).config

        if "token" in config:
            headers = {"Authorization": "Bearer {}".format(config["token"])}
        elif "ha_key" in config:
            headers = {"x-ha-access": config["ha_key"]}
        else:
            headers = {}

        event_clean = quote(event, safe="")
        api_url = "{}/api/events/{}".format(config["ha_url"], event_clean)
        try:
            r = await self.session.post(api_url, headers=headers, json=kwargs, verify_ssl=self.cert_verify)
            r.raise_for_status()
            state = await r.json()
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
        config = (await self.AD.plugins.get_plugin_object(namespace)).config

        # TODO cert_path is not used
        if "cert_path" in config:
            cert_path = config["cert_path"]
        else:
            cert_path = False  # noqa: F841

        if "token" in config:
            headers = {"Authorization": "Bearer {}".format(config["token"])}
        elif "ha_key" in config:
            headers = {"x-ha-access": config["ha_key"]}
        else:
            headers = {}

        api_url = "{}/api/states/{}".format(config["ha_url"], entity_id)

        try:
            r = await self.session.delete(api_url, headers=headers, verify_ssl=self.cert_verify)
            if r.status == 200 or r.status == 201:
                state = await r.json()
                self.logger.debug("return = %s", state)
            else:
                self.logger.warning("Error Removing Home Assistant entity %s", entity_id)
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                state = None
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
