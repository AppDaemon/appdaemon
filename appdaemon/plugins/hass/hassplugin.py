import asyncio
import json
import ssl
import websocket
import traceback
import aiohttp
import pytz

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.plugin_management import PluginBase

def hass_check(func):
    def func_wrapper(*args, **kwargs):
        self = args[0]
        if not self.reading_messages:
            self.logger.warning("Attempt to call Home Assistant while disconnected: %s", func.__name__)
            return lambda *args: None
        else:
            return func(*args, **kwargs)

    return (func_wrapper)


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

        if "app_init_delay" in args:
            self.app_init_delay = args["app_init_delay"]
        else:
            self.app_init_delay = 0
        #
        # Set up HTTP Client
        #
        conn = aiohttp.TCPConnector()
        self.session = aiohttp.ClientSession(connector=conn)

        self.logger.info("HASS Plugin initialization complete")

    async def am_reading_messages(self):
        return(self.reading_messages)

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True
        if self.ws is not None:
            self.ws.close()

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

    async def get_updates(self):

        _id = 0

        already_notified = False
        first_time = True
        while not self.stopping:
            _id += 1
            try:
                #
                # Connect to websocket interface
                #
                url = self.ha_url
                if url.startswith('https://'):
                    url = url.replace('https', 'wss', 1)
                elif url.startswith('http://'):
                    url = url.replace('http', 'ws', 1)

                sslopt = {}
                if self.cert_verify is False:
                    sslopt = {'cert_reqs': ssl.CERT_NONE}
                if self.cert_path:
                    sslopt['ca_certs'] = self.cert_path
                self.ws = websocket.create_connection(
                    "{}/api/websocket".format(url), sslopt=sslopt
                )
                res = await utils.run_in_executor(self, self.ws.recv)
                result = json.loads(res)
                self.logger.info("Connected to Home Assistant %s", result["ha_version"])
                #
                # Check if auth required, if so send password
                #
                if result["type"] == "auth_required":
                    if self.token is not None:
                        auth = json.dumps({
                            "type": "auth",
                            "access_token": self.token
                        })
                    elif self.ha_key is not None:
                        auth = json.dumps({
                            "type": "auth",
                            "api_password": self.ha_key
                        })
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
                sub = json.dumps({
                    "id": _id,
                    "type": "subscribe_events"
                })
                await utils.run_in_executor(self, self.ws.send, sub)
                result = json.loads(self.ws.recv())
                if not (result["id"] == _id and result["type"] == "result" and
                                result["success"] is True):
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
                        self.AD.services.register_service(self.get_namespace(), domain["domain"], service, self.call_plugin_service)
                #
                # Get State
                #
                state = await self.get_complete_state()
                #
                # Wait for app delay
                #
                if self.app_init_delay > 0:
                    self.logger.info("Delaying app initialization for %s seconds", self.app_init_delay)
                    await asyncio.sleep(self.app_init_delay)
                #
                # Fire HA_STARTED Events
                #
                self.reading_messages = True
                await self.AD.plugins.notify_plugin_started(self.name, self.namespace, self.metadata, state, first_time)

                already_notified = False

                #
                # Loop forever consuming events
                #
                while not self.stopping:
                    ret = await utils.run_in_executor(self, self.ws.recv)
                    result = json.loads(ret)

                    if not (result["id"] == _id and result["type"] == "event"):
                        self.logger.warning("Unexpected result from Home Assistant, id = %s", _id)
                        self.logger.warning(result)

                    await self.AD.events.process_event(self.namespace, result["event"])

                self.reading_messages = False

            except:
                self.reading_messages = False
                first_time = False
                if not already_notified:
                    await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                    already_notified = True
                if not self.stopping:
                    self.logger.warning("Disconnected from Home Assistant, retrying in 5 seconds")
                    self.logger.debug('-' * 60)
                    self.logger.debug("Unexpected error:")
                    self.logger.debug('-' * 60)
                    self.logger.debug(traceback.format_exc())
                    self.logger.debug('-' * 60)
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
        if "cert_path" in config:
            cert_path = config["cert_path"]
        else:
            cert_path = False

        if "token" in config:
            headers = {'Authorization': "Bearer {}".format(config["token"])}
        elif "ha_key"  in config:
            headers = {'x-ha-access': config["ha_key"]}
        else:
            headers = {}
            r = None
        apiurl = "{}/api/states/{}".format(config["ha_url"], entity_id)
        try:
            r = await self.session.post(apiurl, headers=headers, json=kwargs, verify_ssl=self.cert_verify)
            if r.status == 200 or r.status == 201:
                state = await r.json()
                self.logger.debug("return = %s", state)
            else:
                self.logger.warning("Error setting Home Assistant state %s.%s, %s", namespace, entity_id, kwargs )
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                state = None
            return state
        except asyncio.TimeoutError:
            self.logger.warning("Timeout in set_state(%s, %s, %s)", namespace, entity_id, kwargs)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during set_state()")
        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error during set_plugin_state()")
            self.logger.warning("Arguments: %s = %s", entity_id, kwargs)
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)
            return None

    @hass_check
    async def call_plugin_service(self, namespace, domain, service, data):

        config = (await self.AD.plugins.get_plugin_object(namespace)).config
        if "token" in config:
            headers = {'Authorization': "Bearer {}".format(config["token"])}
        elif "ha_key" in config:
            headers = {'x-ha-access': config["ha_key"]}
        else:
            headers = {}

        apiurl = "{}/api/services/{}/{}".format(config["ha_url"], domain, service)
        try:
            r = await self.session.post(apiurl, headers=headers, json=data, verify_ssl=self.cert_verify)
            if r.status == 200 or r.status == 201:
                result = await r.json()
            else:
                self.logger.warning("Error calling Home Assistant service %s/%s/%s", namespace, domain, service)
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                result = None
            return result
        except asyncio.TimeoutError:
            self.logger.warning("Timeout in call_service(%s/%s/%s, %s)", namespace, domain, service, data)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during call_service()")
        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error during call_plugin_service()")
            self.logger.warning("Service: %s.%s.%s Arguments: %s", namespace, domain, service, data)
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)
            return None

    async def get_hass_state(self, entity_id=None):
        if self.token is not None:
            headers = {'Authorization': "Bearer {}".format(self.token)}
        elif self.ha_key is not None:
            headers = {'x-ha-access': self.ha_key}
        else:
            headers = {}

        if entity_id is None:
            apiurl = "{}/api/states".format(self.ha_url)
        else:
            apiurl = "{}/api/states/{}".format(self.ha_url, entity_id)
        self.logger.debug("get_ha_state: url is %s", apiurl)
        r = await self.session.get(apiurl, headers=headers, verify_ssl=self.cert_verify)
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
            value = float(meta[key])
        except:
            self.logger.warning("Invalid value for '%s' ('%s') in metadata for plugin %s", key, meta[key], self.name)
            raise

    def validate_tz(self, meta):
        if "time_zone" not in meta:
            self.logger.warning("Value for 'time_zone' not found in metadata for plugin %s", self.name)
            raise ValueError
        try:
            tz = pytz.timezone(meta["time_zone"])
        except pytz.exceptions.UnknownTimeZoneError:
            self.logger.warning("Invalid value for 'time_zone' ('%s') in metadata for plugin %s", meta["time_zone"], self.name)
            raise

    async def get_hass_config(self):
        try:
            self.logger.debug("get_ha_config()")
            if self.token is not None:
                headers = {'Authorization': "Bearer {}".format(self.token)}
            elif self.ha_key is not None:
                headers = {'x-ha-access': self.ha_key}
            else:
                headers = {}

            apiurl = "{}/api/config".format(self.ha_url)
            self.logger.debug("get_ha_config: url is %s", apiurl)
            r = await self.session.get(apiurl, headers=headers, verify_ssl=self.cert_verify)
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
        except:
            self.logger.warning("Error getting metadata - retrying")
            raise

    async def get_hass_services(self):
        try:
            self.logger.debug("get_hass_services()")
            if self.token is not None:
                headers = {'Authorization': "Bearer {}".format(self.token)}
            elif self.ha_key is not None:
                headers = {'x-ha-access': self.ha_key}
            else:
                headers = {}

            apiurl = "{}/api/services".format(self.ha_url)
            self.logger.debug("get_hass_services: url is %s", apiurl)
            r = await self.session.get(apiurl, headers=headers, verify_ssl=self.cert_verify)
            r.raise_for_status()
            services = await r.json()

            return services
        except:
            self.logger.warning("Error getting services - retrying")
            raise

    @hass_check
    async def fire_plugin_event(self, event, namespace, **kwargs):
        self.logger.debug("fire_event: %s, %s %s", event, namespace, kwargs)

        config = (await self.AD.plugins.get_plugin_object(namespace)).config

        if "token" in config:
            headers = {'Authorization': "Bearer {}".format(config["token"])}
        elif "ha_key" in config:
            headers = {'x-ha-access': config["ha_key"]}
        else:
            headers = {}

        apiurl = "{}/api/events/{}".format(config["ha_url"], event)
        try:
            r = await self.session.post(apiurl, headers=headers, json=kwargs, verify_ssl=self.cert_verify)
            r.raise_for_status()
            state = await r.json()
            return state
        except asyncio.TimeoutError:
            self.logger.warning("Timeout in fire_event(%s, %s, %s)", event, namespace, kwargs)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("HASS Disconnected unexpectedly during fire_event()")
        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error fire_plugin_event()")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)
            return None
