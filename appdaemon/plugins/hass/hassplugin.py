import asyncio
import requests
import json
import ssl
from websocket import create_connection
from pkg_resources import parse_version
from sseclient import SSEClient
import traceback
import copy

import appdaemon.utils as utils

class HassPlugin:

    def __init__(self, ad, name, logger, error, loglevel, args):

        self.AD = ad
        self.logger = logger
        self.error = error
        self.stopping = False
        self.config = args
        self.loglevel = loglevel
        self.ws = None
        self.reading_messages = False

        utils.log(self.logger, "INFO", "HASS Plugin Initializing")

        self.name = name

        if "namespace" in args:
            self.namespace = args["namespace"]
        else:
            self.namespace = "hass"

        if "verbose" in args:
            self.verbose = args["verbose"]
        else:
            self.verbose = False

        if "ha_key" in args:
            self.ha_key = args["ha_key"]
        else:
            self.ha_key = ""

        if "ha_url" in args:
            self.ha_url = args["ha_url"]
        else:
            utils.log(self.logger, "WARN", "ha_url not found in HASS configuration - module not initialized")

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
            self.cert_path = False

        if "commtype" in args:
            self.commtype = args["commtype"]
        else:
            self.commtype = "WS"

        utils.log(self.logger, "INFO", "HASS Plugin initialization complete")

    def verbose_log(self, text):
        if self.verbose:
            utils.log(self.logger, "INFO", text)

    def stop(self):
        self.verbose_log("*** Stopping ***")
        self.stopping = True
        if self.ws is not None:
            self.ws.close()

    #
    # Get initial state
    #

    def get_complete_state(self):
        hass_state = self.get_hass_state()
        states = {}
        for state in hass_state:
            states[state["entity_id"]] = state
        utils.log(self.logger, "INFO", "Got initial state")
        self.verbose_log("*** Sending Complete State: {} ***".format(hass_state))
        return states

    #
    # Handle state updates
    #

    async def get_updates(self):
        disconnected_event = False

        _id = 0

        while not self.stopping:
            _id += 1
            try:

                #
                # Fire HA_STARTED Events
                #

                self.AD.process_event({"event_type": "ha_started", "data": {}})

                if parse_version(utils.__version__) < parse_version('0.34') or self.commtype == "SSE":
                    #
                    # Older version of HA - connect using SSEClient
                    #
                    if self.commtype == "SSE":
                        utils.log(self.logger, "INFO", "Using SSE")
                    else:
                        utils.log(
                            self.logger, "INFO",
                            "Home Assistant version < 0.34.0 - "
                            "falling back to SSE"
                        )
                    headers = {'x-ha-access': self.ha_key}
                    if self.timeout is None:
                        messages = SSEClient(
                            "{}/api/stream".format(self.ha_url),
                            verify=False, headers=headers, retry=3000
                        )
                        utils.log(
                            self.logger, "INFO",
                            "Connected to Home Assistant".format(self.timeout)
                        )
                    else:
                        messages = SSEClient(
                            "{}/api/stream".format(self.ha_url),
                            verify=False, headers=headers, retry=3000,
                            timeout=int(self.timeout)
                        )
                        utils.log(
                            self.logger, "INFO",
                            "Connected to Home Assistant with timeout = {}".format(
                                self.timeout
                            )
                        )
                    self.reading_messages = True
                    while not self.stopping:
                        msg = await utils.run_in_executor(self.AD.loop, self.AD.executor, messages.__next__)
                        if msg.data != "ping":
                            self.AD.state_update(self.namespace, json.loads(msg.data))
                    self.reading_messages = False
                else:
                    #
                    # Connect to websocket interface
                    #
                    url = self.ha_url
                    if url.startswith('https://'):
                        url = url.replace('https', 'wss', 1)
                    elif url.startswith('http://'):
                        url = url.replace('http', 'ws', 1)

                    sslopt = {'cert_reqs': ssl.CERT_NONE}
                    if self.cert_path:
                        sslopt['ca_certs'] = self.cert_path
                    self.ws = create_connection(
                        "{}/api/websocket".format(url), sslopt=sslopt
                    )
                    result = json.loads(self.ws.recv())
                    utils.log(self.logger, "INFO",
                              "Connected to Home Assistant {}".format(
                                  result["ha_version"]))
                    #
                    # Check if auth required, if so send password
                    #
                    if result["type"] == "auth_required":
                        auth = json.dumps({
                            "type": "auth",
                            "api_password": self.ha_key
                        })
                        self.ws.send(auth)
                        result = json.loads(self.ws.recv())
                        if result["type"] != "auth_ok":
                            utils.log(self.logger, "WARNING",
                                      "Error in authentication")
                            raise ValueError("Error in authentication")
                    #
                    # Subscribe to event stream
                    #
                    sub = json.dumps({
                        "id": _id,
                        "type": "subscribe_events"
                    })
                    self.ws.send(sub)
                    result = json.loads(self.ws.recv())
                    if not (result["id"] == _id and result["type"] == "result" and
                                    result["success"] is True):
                        utils.log(
                            self.logger, "WARNING",
                            "Unable to subscribe to HA events, id = {}".format(_id)
                        )
                        utils.log(self.logger, "WARNING", result)
                        raise ValueError("Error subscribing to HA Events")

                    #
                    # Loop forever consuming events
                    #
                    self.reading_messages = True
                    while not self.stopping:
                        ret = await utils.run_in_executor(self.AD.loop, self.AD.executor, self.ws.recv)
                        result = json.loads(ret)

                        if not (result["id"] == _id and result["type"] == "event"):
                            utils.log(
                                self.logger, "WARNING",
                                "Unexpected result from Home Assistant, "
                                "id = {}".format(_id)
                            )
                            utils.log(self.logger, "WARNING", result)
                            raise ValueError(
                                "Unexpected result from Home Assistant"
                            )

                        self.AD.state_update(self.namespace, result["event"])
                    self.reading_messages = False

            except:
                self.reading_messages = False
                if not self.stopping:
                    if disconnected_event == False:
                        self.AD.state_update(self.namespace, {"event_type": "ha_disconnected", "data": {}})
                        disconnected_event = True
                    utils.log(
                        self.logger, "WARNING",
                        "Disconnected from Home Assistant, retrying in 5 seconds"
                    )
                    if self.loglevel == "DEBUG":
                        utils.log(self.logger, "WARNING", '-' * 60)
                        utils.log(self.logger, "WARNING", "Unexpected error:")
                        utils.log(self.logger, "WARNING", '-' * 60)
                        utils.log(self.logger, "WARNING", traceback.format_exc())
                        utils.log(self.logger, "WARNING", '-' * 60)
                    await asyncio.sleep(5)

        utils.log(self.logger, "INFO", "Disconnecting from Home Assistant")

    def get_namespace(self):
        return self.namespace

    #
    # Utility functions
    #

    def utility(self):
       return None

    #
    # Home Assistant Interactions
    #


    #
    # Set State
    #

    def set_state(self, entity, state):
        self.verbose_log("*** Setting State: {} = {} ***".format(entity, state))

    #
    # Call Service
    #

    def call_hass_service(self, service, args):
        pass

    #
    # Fire Event
    #

    def fire_hass_event(self, event, args):
        pass

    def get_hass_state(self, entity_id=None):
        if self.ha_key != "":
            headers = {'x-ha-access': self.ha_key}
        else:
            headers = {}
        if entity_id is None:
            apiurl = "{}/api/states".format(self.ha_url)
        else:
            apiurl = "{}/api/states/{}".format(self.ha_url, entity_id)
        utils.log(self.logger, "DEBUG", "get_ha_state: url is {}".format(apiurl))
        r = requests.get(apiurl, headers=headers, verify=self.cert_path)
        r.raise_for_status()
        return r.json()


    def get_ha_config(self):
        utils.log(self.logger, "DEBUG", "get_ha_config()")
        if self.ha_key != "":
            headers = {'x-ha-access': self.ha_key}
        else:
            headers = {}
        apiurl = "{}/api/config".format(self.ha_url)
        utils.log(self.logger, "DEBUG", "get_ha_config: url is {}".format(apiurl))
        r = requests.get(apiurl, headers=headers, verify=self.cert_path)
        r.raise_for_status()
        return r.json()


    def _check_service(self, service):
        if service.find("/") == -1:
            raise ValueError("Invalid Service Name: {}".format(service))


    def call_service(self, service, **kwargs):
        self._check_service(service)
        d, s = service.split("/")
        utils.log(
            self.logger, "DEBUG",
            "call_service: {}/{}, {}".format(d, s, kwargs)
        )
        if self.ha_key != "":
            headers = {'x-ha-access': self.ha_key}
        else:
            headers = {}
        apiurl = "{}/api/services/{}/{}".format(self.ha_url, d, s)
        r = requests.post(
            apiurl, headers=headers, json=kwargs, verify=self.cert_path
        )
        r.raise_for_status()
        return r.json()
