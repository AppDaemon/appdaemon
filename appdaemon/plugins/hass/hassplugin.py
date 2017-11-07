import yaml
import asyncio

import appdaemon.utils as utils

class HassPlugin:

    def __init__(self, name, logger, error, args):

        self.logger = logger
        self.error = error
        self.stopping = False
        self.config = args

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

        utils.log(self.logger, "INFO", "HASS Plugin initialization complete")

    def log(self, text):
        if self.verbose:
            utils.log(self.logger, "INFO", text)


    def stop(self):
        self.log("*** Stopping ***")
        self.stopping = True

    #
    # Get initial state
    #

    def get_complete_state(self):
        self.log("*** Sending Complete State: {} ***".format(self.state))
        return {}

    #
    # Handle state updates
    #

    @asyncio.coroutine
    def get_next_update(self):
        pass

    #
    # Set State
    #

    def set_state(self, entity, state):
        self.log("*** Setting State: {} = {} ***".format(entity, state))

    #
    # Call Service
    #

    def call_service(self, service, args):
        pass

    #
    # Fire Event
    #

    def fire_event(self, event, args):
        pass


def get_ha_state(entity_id=None):
    if conf.ha_key != "":
        headers = {'x-ha-access': conf.ha_key}
    else:
        headers = {}
    if entity_id is None:
        apiurl = "{}/api/states".format(conf.ha_url)
    else:
        apiurl = "{}/api/states/{}".format(conf.ha_url, entity_id)
    log(conf.logger, "DEBUG", "get_ha_state: url is {}".format(apiurl))
    r = requests.get(apiurl, headers=headers, verify=conf.certpath)
    r.raise_for_status()
    return r.json()


def get_ha_config():
    log(conf.logger, "DEBUG", "get_ha_config()")
    if conf.ha_key != "":
        headers = {'x-ha-access': conf.ha_key}
    else:
        headers = {}
    apiurl = "{}/api/config".format(conf.ha_url)
    log(conf.logger, "DEBUG", "get_ha_config: url is {}".format(apiurl))
    r = requests.get(apiurl, headers=headers, verify=conf.certpath)
    r.raise_for_status()
    return r.json()


def _check_service(service):
    if service.find("/") == -1:
        raise ValueError("Invalid Service Name: {}".format(service))


def call_service(service, **kwargs):
    _check_service(service)
    d, s = service.split("/")
    log(
        conf.logger, "DEBUG",
        "call_service: {}/{}, {}".format(d, s, kwargs)
    )
    if conf.ha_key != "":
        headers = {'x-ha-access': conf.ha_key}
    else:
        headers = {}
    apiurl = "{}/api/services/{}/{}".format(conf.ha_url, d, s)
    r = requests.post(
        apiurl, headers=headers, json=kwargs, verify=conf.certpath
    )
    r.raise_for_status()
    return r.json()
