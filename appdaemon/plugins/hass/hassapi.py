import appdaemon.conf as conf
import datetime
import uuid
import requests
import inspect
import json
import iso8601

import appdaemon.utils as utils

reading_messages = False


def hass_check(func):
    def func_wrapper(*args, **kwargs):
        if not reading_messages:
            utils.log(conf.logger, "WARNING", "Attempt to call Home Assistant while disconnected: {}".format(func))
            return (lambda *args: None)
        else:
            return(func(*args, **kwargs))

    return (func_wrapper)


#
# Define an entities class as a descriptor to enable read only access of HASS state
#

class Entities:

    def __get__(self, instance, owner):
        with conf.ha_state_lock:
            state = utils.StateAttrs(conf.ha_state)
        return state


class AppDaemon:
    #
    # Internal
    #

    entities = Entities()

    def __init__(self, name, logger, error, args, global_vars):
        self.name = name
        self._logger = logger
        self._error = error
        self.args = args
        self.global_vars = global_vars
        self.config = conf.config
        self.ha_config = conf.ha_config


    def _check_entity(self, entity):
        if "." not in entity:
            raise ValueError(
                "{}: Invalid entity ID: {}".format(self.name, entity))
        with conf.ha_state_lock:
            if entity not in conf.ha_state:
                utils.log(conf.logger, "WARNING",
                       "{}: Entity {} not found in Home Assistant".format(
                           self.name, entity))

    def _sub_stack(self, msg):
        # If msg is a data structure of some type, don't sub
        if type(msg) is str:
            stack = inspect.stack()
            if msg.find("__module__") != -1:
                msg = msg.replace("__module__", stack[2][1])
            if msg.find("__line__") != -1:
                msg = msg.replace("__line__", str(stack[2][2]))
            if msg.find("__function__") != -1:
                msg = msg.replace("__function__", stack[2][3])
        return msg

    #
    # Utility
    #

    def split_entity(self, entity_id):
        self._check_entity(entity_id)
        return entity_id.split(".")

    def split_device_list(self, list_):
        return list_.split(",")

    def log(self, msg, level="INFO"):
        msg = self._sub_stack(msg)
        utils.log(self._logger, level, msg, self.name)

    def error(self, msg, level="WARNING"):
        msg = self._sub_stack(msg)
        utils.log(self._error, level, msg, self.name)

    def get_app(self, name):
        if name in conf.objects:
            return conf.objects[name]["object"]
        else:
            return None

    def friendly_name(self, entity_id):
        self._check_entity(entity_id)
        with conf.ha_state_lock:
            if entity_id in conf.ha_state:
                if "friendly_name" in conf.ha_state[entity_id]["attributes"]:
                    return conf.ha_state[entity_id][
                        "attributes"]["friendly_name"]
                else:
                    return entity_id
            return None

    #
    # Device Trackers
    #

    def get_trackers(self):
        return (key for key, value in self.get_state("device_tracker").items())

    def get_tracker_details(self):
        return (self.get_state("device_tracker"))

    def get_tracker_state(self, entity_id):
        self._check_entity(entity_id)
        return self.get_state(entity_id)

    def anyone_home(self):
        return utils.anyone_home()

    def everyone_home(self):
        return utils.everyone_home()

    def noone_home(self):
        return utils.noone_home()

        #
        # Event
        #

    @hass_check
    def fire_event(self, event, **kwargs):
        utils.log(conf.logger, "DEBUG",
                  "fire_event: {}, {}".format(event, kwargs))
        if conf.ha_key != "":
            headers = {'x-ha-access': conf.ha_key}
        else:
            headers = {}
        apiurl = "{}/api/events/{}".format(conf.ha_url, event)
        r = requests.post(
            apiurl, headers=headers, json=kwargs, verify=conf.certpath
        )
        r.raise_for_status()
        return r.json()

    #
    # Service
    #


    @hass_check
    def call_service(self, service, **kwargs):
        return utils.call_service(service, **kwargs)

    @hass_check
    def turn_on(self, entity_id, **kwargs):
        self._check_entity(entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
        self.call_service("homeassistant/turn_on", **rargs)

    @hass_check
    def turn_off(self, entity_id, **kwargs):
        self._check_entity(entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
        
        device, entity = self.split_entity(entity_id)
        if device == "scene":
            self.call_service("homeassistant/turn_on", **rargs)
        else:
            self.call_service("homeassistant/turn_off", **rargs)

    @hass_check
    def toggle(self, entity_id):
        self._check_entity(entity_id)
        self.call_service("homeassistant/toggle", entity_id=entity_id)

    @hass_check
    def select_value(self, entity_id, value):
        self._check_entity(entity_id)
        rargs = {"entity_id": entity_id, "value": value}
        self.call_service("input_slider/select_value", **rargs)

    @hass_check
    def select_option(self, entity_id, option):
        self._check_entity(entity_id)
        rargs = {"entity_id": entity_id, "option": option}
        self.call_service("input_select/select_option", **rargs)

    @hass_check
    def notify(self, message, **kwargs):
        args = {"message": message}
        if "title" in kwargs:
            args["title"] = kwargs["title"]
        if "name" in kwargs:
            service = "notify/{}".format(kwargs["name"])
        else:
            service = "notify/notify"

        self.call_service(service, **args)

    @hass_check
    def persistent_notification(self, message, title=None, id=None):
        args = {"message": message}
        if title is not None:
            args["title"] = title
        if id is not None:
            args["notification_id"] = id
        self.call_service("persistent_notification/create", **args)

