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

    #
    # Define an entities class as a descriptor to enable read only access of HASS state
    #

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
    # Apiai
    #

    def get_apiai_intent(self, data):
        if "result" in data and "action" in data["result"]:
            return(data["result"]["action"])
        else:
            return None

    def get_apiai_slot_value(self, data, slot = None):
        if "result" in data and \
                        "contexts" in data["result"]:
            req = data.get('result')
            contexts = req.get('contexts', [{}])
            if contexts:
                parameters = contexts[0].get('parameters')
            else:
                parameters = req.get('parameters')
            if slot == None:
                return(parameters)
            else:
                if slot in parameters:
                    return(parameters[slot])
                else:
                    return None
        else:
            return None

        return response

    def format_apiai_response(self, speech = None):
        speech = \
        {
            "speech": speech,
            "source": "Appdaemon",
            "displayText": speech
        }

        return speech


    #
    # Alexa
    #

    def get_alexa_intent(self, data):
        if "request" in data and "intent" in data["request"] and "name" in data["request"]["intent"]:
            return(data["request"]["intent"]["name"])
        else:
            return None

    def get_alexa_error(self, data):
        if "request" in data and "error" in data["request"] and "message" in data["request"]["error"]:
            return(data["request"]["error"]["message"])
        else:
            return None

    def get_alexa_slot_value(self, data, slot = None):
        if "request" in data and \
                        "intent" in data["request"] and \
                        "slots" in data["request"]["intent"]:
            if slot == None:
                return(data["request"]["intent"]["slots"])
            else:
                if slot in data["request"]["intent"]["slots"] and \
                        "value" in data["request"]["intent"]["slots"][slot]:
                    return(data["request"]["intent"]["slots"][slot]["value"])
                else:
                    return None
        else:
            return None

        return response

    def format_alexa_response(self, speech = None, card = None, title = None):

        response = \
           {
                    "shouldEndSession": True
           }

        if speech is not None:
           response["outputSpeech"] = \
           {
                "type": "PlainText",
                "text": speech
                   }

        if card is not None:
            response["card"] = \
            {
                "type": "Simple",
                "title": title,
                "content": card
            }

        speech = \
        {
            "version": "1.0",
            "response": response,
            "sessionAttributes": {}
        }

        return speech

    #
    # API
    #

    def register_endpoint(self, cb, name = None):

        if name is None:
            ep = self.name
        else:
            ep = name

        handle = uuid.uuid4()

        with conf.endpoints_lock:
            if self.name not in conf.endpoints:
                conf.endpoints[self.name] = {}
            conf.endpoints[self.name][handle] = {"callback": cb, "name": ep}

        return handle

    def unregister_endpoint(self, handle):
        with conf.endpoints_lock:
            if self.name in conf.endpoints and handle in conf.endpoints[self.name]:
                del conf.endpoints[self.name][handle]


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
    # State
    #

    def entity_exists(self, entity_id):
        if "." not in entity_id:
            raise ValueError(
                "{}: Invalid entity ID: {}".format(self.name, entity_id))
        with conf.ha_state_lock:
            if entity_id in conf.ha_state:
                return True
            else:
                return False
    @hass_check
    def get_state(self, entity_id=None, attribute=None):
        utils.log(conf.logger, "DEBUG",
               "get_state: {}.{}".format(entity_id, attribute))
        device = None
        entity = None
        if entity_id is not None and "." in entity_id:
            if not self.entity_exists(entity_id):
                return None
        if entity_id is not None:
            if "." not in entity_id:
                if attribute is not None:
                    raise ValueError(
                        "{}: Invalid entity ID: {}".format(self.name, entity))
                device = entity_id
                entity = None
            else:
                device, entity = entity_id.split(".")
        with conf.ha_state_lock:
            if device is None:
                return conf.ha_state
            elif entity is None:
                devices = {}
                for entity_id in conf.ha_state.keys():
                    thisdevice, thisentity = entity_id.split(".")
                    if device == thisdevice:
                        devices[entity_id] = conf.ha_state[entity_id]
                return devices
            elif attribute is None:
                entity_id = "{}.{}".format(device, entity)
                if entity_id in conf.ha_state:
                    return conf.ha_state[entity_id]["state"]
                else:
                    return None
            else:
                entity_id = "{}.{}".format(device, entity)
                if attribute == "all":
                    if entity_id in conf.ha_state:
                        return conf.ha_state[entity_id]
                    else:
                        return None
                else:
                    if attribute in conf.ha_state[entity_id]:
                        return conf.ha_state[entity_id][attribute]
                    elif attribute in conf.ha_state[entity_id]["attributes"]:
                        return conf.ha_state[entity_id]["attributes"][
                            attribute]
                    else:
                        return None

    def set_app_state(self, entity_id, state):
        utils.log(conf.logger, "DEBUG", "set_app_state: {}".format(entity_id))
        if entity_id is not None and "." in entity_id:
            with conf.ha_state_lock:
                if entity_id in conf.ha_state:
                    old_state = conf.ha_state[entity_id]
                else:
                    old_state = None
                data = {"entity_id": entity_id, "new_state": state, "old_state": old_state}
                args = {"event_type": "state_changed", "data": data}
                conf.appq.put_nowait(args)

    @hass_check
    def set_state(self, entity_id, **kwargs):
        with conf.ha_state_lock:
            self._check_entity(entity_id)
            utils.log(
                conf.logger, "DEBUG",
                "set_state: {}, {}".format(entity_id, kwargs)
            )
            if conf.ha_key != "":
                headers = {'x-ha-access': conf.ha_key}
            else:
                headers = {}
            apiurl = "{}/api/states/{}".format(conf.ha_url, entity_id)

            if entity_id not in conf.ha_state:
                # Its a new state entry
                conf.ha_state[entity_id] = {}
                conf.ha_state[entity_id]["attributes"] = {}

            args = {}

            if "state" in kwargs:
                args["state"] = kwargs["state"]
            else:
                if "state" in conf.ha_state[entity_id]:
                    args["state"] = conf.ha_state[entity_id]["state"]

            if "attributes" in conf.ha_state[entity_id]:
                args["attributes"] = conf.ha_state[entity_id]["attributes"]
                if "attributes" in kwargs:
                    args["attributes"].update(kwargs["attributes"])
            else:
                if "attributes" in kwargs:
                    args["attributes"] = kwargs["attributes"]

            r = requests.post(apiurl, headers=headers, json=args,
                              verify=conf.certpath)
            r.raise_for_status()
            # Update our local copy of state
            state = r.json()
            conf.ha_state[entity_id] = state

            return state

    def listen_state(self, function, entity=None, **kwargs):
        name = self.name
        if entity is not None and "." in entity:
            self._check_entity(entity)
        with conf.callbacks_lock:
            if name not in conf.callbacks:
                conf.callbacks[name] = {}
            handle = uuid.uuid4()
            conf.callbacks[name][handle] = {
                "name": name,
                "id": conf.objects[name]["id"],
                "type": "state",
                "function": function,
                "entity": entity,
                "kwargs": kwargs
            }

        #
        # In the case of a quick_start parameter,
        # start the clock immediately if the device is already in the new state
        #
        if "immediate" in kwargs and kwargs["immediate"] is True:
            if entity is not None and "new" in kwargs and "duration" in kwargs:
                if conf.ha_state[entity]["state"] == kwargs["new"]:
                    exec_time = utils.get_now_ts() + int(kwargs["duration"])
                    kwargs["handle"] = utils.insert_schedule(
                        name, exec_time, function, False, None,
                        entity=entity,
                        attribute=None,
                        old_state=None,
                        new_state=kwargs["new"], **kwargs
                )

        return handle

    def cancel_listen_state(self, handle):
        name = self.name
        utils.log(
            conf.logger, "DEBUG",
            "Canceling listen_state for {}".format(name)
        )
        with conf.callbacks_lock:
            if name in conf.callbacks and handle in conf.callbacks[name]:
                del conf.callbacks[name][handle]
            if name in conf.callbacks and conf.callbacks[name] == {}:
                del conf.callbacks[name]

    def info_listen_state(self, handle):
        name = self.name
        utils.log(
            conf.logger, "DEBUG",
            "Calling info_listen_state for {}".format(name)
        )
        with conf.callbacks_lock:
            if name in conf.callbacks and handle in conf.callbacks[name]:
                callback = conf.callbacks[name][handle]
                return (
                    callback["entity"],
                    callback["kwargs"].get("attribute", None),
                    utils.sanitize_state_kwargs(callback["kwargs"])
                )
            else:
                raise ValueError("Invalid handle: {}".format(handle))
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

    def listen_event(self, function, event=None, **kwargs):
        name = self.name
        with conf.callbacks_lock:
            if name not in conf.callbacks:
                conf.callbacks[name] = {}
            handle = uuid.uuid4()
            conf.callbacks[name][handle] = {
                "name": name,
                "id": conf.objects[name]["id"],
                "type": "event",
                "function": function,
                "event": event,
                "kwargs": kwargs
            }
        return handle

    def cancel_listen_event(self, handle):
        name = self.name
        utils.log(
            conf.logger, "DEBUG",
            "Canceling listen_event for {}".format(name)
        )
        with conf.callbacks_lock:
            if name in conf.callbacks and handle in conf.callbacks[name]:
                del conf.callbacks[name][handle]
            if name in conf.callbacks and conf.callbacks[name] == {}:
                del conf.callbacks[name]

    def info_listen_event(self, handle):
        name = self.name
        utils.log(
            conf.logger, "DEBUG",
            "Calling info_listen_event for {}".format(name)
        )
        with conf.callbacks_lock:
            if name in conf.callbacks and handle in conf.callbacks[name]:
                callback = conf.callbacks[name][handle]
                return callback["event"], callback["kwargs"].copy()
            else:
                raise ValueError("Invalid handle: {}".format(handle))
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

    #
    # Time
    #

    def convert_utc(self, utc):
        return iso8601.parse_date(utc)

    def sun_up(self):
        return conf.sun["next_rising"] > conf.sun["next_setting"]

    def sun_down(self):
        return conf.sun["next_rising"] < conf.sun["next_setting"]

    def sunrise(self):
        return utils.sunrise()

    def sunset(self):
        return utils.sunset()

    def parse_time(self, time_str):
        return utils.parse_time(time_str)

    def now_is_between(self, start_time_str, end_time_str):
        return utils.now_is_between(start_time_str, end_time_str, self.name)

    def time(self):
        return datetime.datetime.fromtimestamp(conf.now).time()

    def datetime(self):
        return datetime.datetime.fromtimestamp(conf.now)

    def date(self):
        return datetime.datetime.fromtimestamp(conf.now).date()

    #
    # Scheduler
    #

    def cancel_timer(self, handle):
        name = self.name
        utils.cancel_timer(name, handle)

    def info_timer(self, handle):
        name = self.name
        utils.log(conf.logger, "DEBUG", "Calling info_timer for {}".format(name))
        with conf.schedule_lock:
            if name in conf.schedule and handle in conf.schedule[name]:
                callback = conf.schedule[name][handle]
                return (
                    datetime.datetime.fromtimestamp(callback["timestamp"]),
                    callback["interval"],
                    utils.sanitize_timer_kwargs(callback["kwargs"])
                )
            else:
                raise ValueError("Invalid handle: {}".format(handle))

    def run_in(self, callback, seconds, **kwargs):
        name = self.name
        utils.log(
            conf.logger, "DEBUG",
            "Registering run_in in {} seconds for {}".format(seconds, name)
        )
        # convert seconds to an int if possible since a common pattern is to
        # pass this through from the config file which is a string
        exec_time = utils.get_now_ts() + int(seconds)
        handle = utils.insert_schedule(
            name, exec_time, callback, False, None, **kwargs
        )
        return handle

    def run_once(self, callback, start, **kwargs):
        name = self.name
        now = utils.get_now()
        today = now.date()
        event = datetime.datetime.combine(today, start)
        if event < now:
            one_day = datetime.timedelta(days=1)
            event = event + one_day
        exec_time = event.timestamp()
        handle = utils.insert_schedule(
            name, exec_time, callback, False, None, **kwargs
        )
        return handle

    def run_at(self, callback, start, **kwargs):
        name = self.name
        now = utils.get_now()
        if start < now:
            raise ValueError(
                "{}: run_at() Start time must be "
                "in the future".format(self.name)
            )
        exec_time = start.timestamp()
        handle = utils.insert_schedule(
            name, exec_time, callback, False, None, **kwargs
        )
        return handle

    def run_daily(self, callback, start, **kwargs):
        name = self.name
        now = utils.get_now()
        today = now.date()
        event = datetime.datetime.combine(today, start)
        if event < now:
            event = event + datetime.timedelta(days=1)
        handle = self.run_every(callback, event, 24 * 60 * 60, **kwargs)
        return handle

    def run_hourly(self, callback, start, **kwargs):
        name = self.name
        now = utils.get_now()
        if start is None:
            event = now + datetime.timedelta(hours=1)
        else:
            event = now
            event = event.replace(minute=start.minute, second=start.second)
            if event < now:
                event = event + datetime.timedelta(hours=1)
        handle = self.run_every(callback, event, 60 * 60, **kwargs)
        return handle

    def run_minutely(self, callback, start, **kwargs):
        name = self.name
        now = utils.get_now()
        if start is None:
            event = now + datetime.timedelta(minutes=1)
        else:
            event = now
            event = event.replace(second=start.second)
            if event < now:
                event = event + datetime.timedelta(minutes=1)
        handle = self.run_every(callback, event, 60, **kwargs)
        return handle

    def run_every(self, callback, start, interval, **kwargs):
        name = self.name
        now = utils.get_now()
        if start < now:
            raise ValueError("start cannot be in the past")
        utils.log(
            conf.logger, "DEBUG",
            "Registering run_every starting {} in {}s intervals for {}".format(
                 start, interval, name
            )
        )
        exec_time = start.timestamp()
        handle = utils.insert_schedule(name, exec_time, callback, True, None,
                                    interval=interval, **kwargs)
        return handle

    def _schedule_sun(self, name, type_, callback, **kwargs):
        event = utils.calc_sun(type_)
        handle = utils.insert_schedule(
            name, event, callback, True, type_, **kwargs
        )
        return handle

    def run_at_sunset(self, callback, **kwargs):
        name = self.name
        utils.log(
            conf.logger, "DEBUG",
            "Registering run_at_sunset with kwargs = {} for {}".format(
                kwargs, name
            )
        )
        handle = self._schedule_sun(name, "next_setting", callback, **kwargs)
        return handle

    def run_at_sunrise(self, callback, **kwargs):
        name = self.name
        utils.log(conf.logger, "DEBUG",
               "Registering run_at_sunrise with kwargs = {} for {}".format(
                   kwargs, name))
        handle = self._schedule_sun(name, "next_rising", callback, **kwargs)
        return handle

    #
    # Other
    #

    def dash_navigate(self, target, timeout = -1, ret = None):
        kwargs = {"command": "navigate", "target": target}

        if timeout != -1:
            kwargs["timeout"] = timeout
        if ret != None:
            kwargs["return"] = ret
        self.fire_event("hadashboard", **kwargs)

    def get_scheduler_entries(self):
        schedule = {}
        for name in conf.schedule.keys():
            schedule[name] = {}
            for entry in sorted(
                    conf.schedule[name].keys(),
                    key=lambda uuid_: conf.schedule[name][uuid_]["timestamp"]
            ):
                schedule[name][entry] = {}
                schedule[name][entry]["timestamp"] = conf.schedule[name][entry]["timestamp"]
                schedule[name][entry]["type"] = conf.schedule[name][entry]["type"]
                schedule[name][entry]["name"] = conf.schedule[name][entry]["name"]
                schedule[name][entry]["basetime"] = conf.schedule[name][entry]["basetime"]
                schedule[name][entry]["repeat"] = conf.schedule[name][entry]["basetime"]
                schedule[name][entry]["offset"] = conf.schedule[name][entry]["basetime"]
                schedule[name][entry]["interval"] = conf.schedule[name][entry]["basetime"]
                schedule[name][entry]["kwargs"] = conf.schedule[name][entry]["basetime"]
                schedule[name][entry]["callback"] = conf.schedule[name][entry]["callback"]
        return (schedule)

    def get_callback_entries(self):
        callbacks = {}
        for name in conf.callbacks.keys():
            callbacks[name] = {}
            utils.log(conf.logger, "INFO", "{}:".format(name))
            for uuid_ in conf.callbacks[name]:
                callbacks[name][uuid_] = {}
                if "entity" in callbacks[name][uuid_]:
                    callbacks[name][uuid_]["entity"] = conf.callbacks[name][uuid_]["entity"]
                else:
                    callbacks[name][uuid_]["entity"] = None
                callbacks[name][uuid_]["type"] = conf.callbacks[name][uuid_]["type"]
                callbacks[name][uuid_]["kwargs"] = conf.callbacks[name][uuid_]["kwargs"]
                callbacks[name][uuid_]["function"] = conf.callbacks[name][uuid_]["function"]
                callbacks[name][uuid_]["name"] = conf.callbacks[name][uuid_]["name"]
        return(callbacks)

