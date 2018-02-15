import datetime
import inspect
import iso8601
import re

import appdaemon.utils as utils

class Entities:

    def __get__(self, instance, owner):
        stateattrs = utils.StateAttrs(instance.get_state())
        return stateattrs



class AppDaemon:
    #
    # Internal
    #

    entities = Entities()

    def __init__(self, ad, name, logger, error, args, config, app_config, global_vars):
        self.AD = ad
        self.name = name
        self._logger = logger
        self._error = error
        self.config = config
        self.app_config = app_config
        self.args = args
        self.global_vars = global_vars
        self.constraints = []

    @staticmethod
    def _sub_stack(msg):
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

    def log(self, msg, level="INFO"):
        msg = self._sub_stack(msg)
        self.AD.log(level, msg, self.name)

    def error(self, msg, level="WARNING"):
        msg = self._sub_stack(msg)
        self.AD.err(level, msg, self.name)

    def get_app(self, name):
        return self.AD.get_app(name)

    def _check_entity(self, namespace, entity):
        if "." not in entity:
            raise ValueError(
                "{}: Invalid entity ID: {}".format(self.name, entity))
        if not self.AD.entity_exists(namespace, entity):
            self.AD.log("WARNING",
                      "{}: Entity {} not found in AppDaemon".format(
                          self.name, entity))

    def get_main_log(self):
        return self._logger

    def get_error_log(self):
        return self._error

    def get_ad_version(self):
        return utils.__version__

    #
    # Apiai
    #

    @staticmethod
    def get_apiai_intent(data):
        if "result" in data and "action" in data["result"]:
            return data["result"]["action"]
        else:
            return None

    @staticmethod
    def get_apiai_slot_value(data, slot=None):
        if "result" in data and \
                        "contexts" in data["result"]:
            req = data.get('result')
            contexts = req.get('contexts', [{}])
            if contexts:
                parameters = contexts[0].get('parameters')
            else:
                parameters = req.get('parameters')
            if slot is None:
                return parameters
            else:
                if slot in parameters:
                    return parameters[slot]
                else:
                    return None
        else:
            return None

    @staticmethod
    def format_apiai_response(speech=None):
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

    @staticmethod
    def format_alexa_response(speech=None, card=None, title=None):

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

    def register_endpoint(self, cb, name=None):
        if name is None:
            ep = self.name
        else:
            ep = name
        return self.AD.register_endpoint(cb, ep)

    def unregister_endpoint(self, handle):
        self.AD.unregister_endpoint(handle, self.name)

    #
    # State
    #

    def listen_state(self, namespace, cb, entity, **kwargs):
        name = self.name
        if entity is not None and "." in entity:
            self._check_entity(namespace, entity)
        return self.AD.add_state_callback(name, namespace, entity, cb, kwargs)

    def cancel_listen_state(self, handle):
        self.AD.log(
            "DEBUG",
            "Canceling listen_state for {}".format(self.name)
        )
        self.AD.cancel_state_callback(handle, self.name)

    def info_listen_state(self, handle):
        self.AD.log(
            "DEBUG",
            "Calling info_listen_state for {}".format(self.name)
        )
        return self.AD.info_state_callback(handle, self.name)

    def get_state(self, namespace, entity_id=None, attribute=None):
        self.AD.log("DEBUG",
               "get_state: {}.{}".format(entity_id, attribute))
        device = None
        entity = None
        if entity_id is not None and "." in entity_id:
            if not self.AD.entity_exists(namespace, entity_id):
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

        return self.AD.get_state(namespace, device, entity, attribute)

    #
    # Events
    #

    def listen_event(self, namespace, cb, event=None, **kwargs):
        name = self.name
        self.AD.log(
            "DEBUG",
            "Calling listen_event for {}".format(self.name)
        )
        return self.AD.add_event_callback(name, namespace, cb, event, **kwargs)

    def cancel_listen_event(self, handle):
        self.AD.log(
            "DEBUG",
            "Canceling listen_event for {}".format(self.name)
        )
        self.AD.cancel_event_callback(self.name, handle)

    def info_listen_event(self, handle):
        self.AD.log(
            "DEBUG",
            "Calling info_listen_event for {}".format(self.name)
        )
        return self.AD.info_event_callback(self.name, handle)

    #
    # Time
    #

    def calc_sun(self, type_):
        return self.AD.calc_sun(type_)

    def parse_utc_string(self, s):
        return datetime.datetime(*map(
            int, re.split('[^\d]', s)[:-1]
        )).timestamp() + self.get_tz_offset() * 60

    @staticmethod
    def get_tz_offset():
        utc_offset_min = int(round(
            (datetime.datetime.now()
             - datetime.datetime.utcnow()).total_seconds())
        ) / 60  # round for taking time twice
        utc_offset_h = utc_offset_min / 60

        # we do not handle 1/2 h timezone offsets
        assert utc_offset_min == utc_offset_h * 60
        return utc_offset_min

    @staticmethod
    def convert_utc(utc):
        return iso8601.parse_date(utc)

    def sun_up(self):
        return self.AD.sun["next_rising"] > self.AD.sun["next_setting"]

    def sun_down(self):
        return self.AD.sun["next_rising"] < self.AD.sun["next_setting"]

    def parse_time(self, time_str, name=None):
        return self.AD.parse_time(time_str, name)

    def get_now(self):
        return self.AD.get_now()

    def get_now_ts(self):
        return self.AD.get_now_ts()

    def now_is_between(self, start_time_str, end_time_str, name=None):
        return self.AD.now_is_between(start_time_str, end_time_str, name)

    def sunrise(self):
        return self.AD.sunrise()

    def sunset(self):
        return self.AD.sunset()

    def time(self):
        return datetime.datetime.fromtimestamp(self.get_now_ts()).time()

    def datetime(self):
        return datetime.datetime.fromtimestamp(self.get_now_ts())

    def date(self):
        return datetime.datetime.fromtimestamp(self.get_now_ts()).date()

    #
    # Scheduler
    #

    def cancel_timer(self, handle):
        name = self.name
        self.AD.cancel_timer(name, handle)

    def info_timer(self, handle):
        return self.AD.info_timer(handle, self.name)

    def run_in(self, callback, seconds, **kwargs):
        name = self.name
        self.AD.log(
            "DEBUG",
            "Registering run_in in {} seconds for {}".format(seconds, name)
        )
        # convert seconds to an int if possible since a common pattern is to
        # pass this through from the config file which is a string
        exec_time = self.get_now_ts() + int(seconds)
        handle = self.AD.insert_schedule(
            name, exec_time, callback, False, None, **kwargs
        )
        return handle

    def run_once(self, callback, start, **kwargs):
        name = self.name
        now = self.get_now()
        today = now.date()
        event = datetime.datetime.combine(today, start)
        if event < now:
            one_day = datetime.timedelta(days=1)
            event = event + one_day
        exec_time = event.timestamp()
        handle = self.AD.insert_schedule(
            name, exec_time, callback, False, None, **kwargs
        )
        return handle

    def run_at(self, callback, start, **kwargs):
        name = self.name
        now = self.get_now()
        if start < now:
            raise ValueError(
                "{}: run_at() Start time must be "
                "in the future".format(self.name)
            )
        exec_time = start.timestamp()
        handle = self.AD.insert_schedule(
            name, exec_time, callback, False, None, **kwargs
        )
        return handle

    def run_daily(self, callback, start, **kwargs):
        now = self.get_now()
        today = now.date()
        event = datetime.datetime.combine(today, start)
        if event < now:
            event = event + datetime.timedelta(days=1)
        handle = self.run_every(callback, event, 24 * 60 * 60, **kwargs)
        return handle

    def run_hourly(self, callback, start, **kwargs):
        now = self.get_now()
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
        now = self.get_now()
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
        now = self.get_now()
        if start < now:
            raise ValueError("start cannot be in the past")
        self.AD.log(
            "DEBUG",
            "Registering run_every starting {} in {}s intervals for {}".format(
                start, interval, name
            )
        )
        exec_time = start.timestamp()
        handle = self.AD.insert_schedule(name, exec_time, callback, True, None,
                                         interval=interval, **kwargs)
        return handle

    def _schedule_sun(self, name, type_, callback, **kwargs):
        event = self.calc_sun(type_)
        handle = self.AD.insert_schedule(
            name, event, callback, True, type_, **kwargs
        )
        return handle

    def run_at_sunset(self, callback, **kwargs):
        name = self.name
        self.AD.log(
            "DEBUG",
            "Registering run_at_sunset with kwargs = {} for {}".format(
                kwargs, name
            )
        )
        handle = self._schedule_sun(name, "next_setting", callback, **kwargs)
        return handle

    def run_at_sunrise(self, callback, **kwargs):
        name = self.name
        self.AD.log("DEBUG",
                  "Registering run_at_sunrise with kwargs = {} for {}".format(
                      kwargs, name))
        handle = self._schedule_sun(name, "next_rising", callback, **kwargs)
        return handle

    #
    # Dashboard
    #

    def dash_navigate(self, target, timeout=-1, ret=None, sticky=0):
        kwargs = {"command": "navigate", "target": target, "sticky": sticky}

        if timeout != -1:
            kwargs["timeout"] = timeout
        if ret is not None:
            kwargs["return"] = ret
        self.fire_event("hadashboard", **kwargs)
    #
    # Constraints
    #

    def register_constraint(self, name):
        self.constraints.append(name)

    def deregister_constraint(self, name):
        self.constraints.remove(name)

    def list_constraints(self):
        return self.constraints


    #
    # Other
    #

    def get_thread_info(self):
        return self.AD.get_thread_info()

    def get_scheduler_entries(self):
        return self.AD.get_scheduler_entries()

    def get_callback_entries(self):
        return self.AD.get_callback_entries()

    @staticmethod
    def get_alexa_slot_value(data, slot=None):
        if "request" in data and \
                        "intent" in data["request"] and \
                        "slots" in data["request"]["intent"]:
            if slot is None:
                return data["request"]["intent"]["slots"]
            else:
                if slot in data["request"]["intent"]["slots"] and \
                                "value" in data["request"]["intent"]["slots"][slot]:
                    return data["request"]["intent"]["slots"][slot]["value"]
                else:
                    return None
        else:
            return None

    @staticmethod
    def get_alexa_error(data):
        if "request" in data and "error" in data["request"] and "message" in data["request"]["error"]:
            return data["request"]["error"]["message"]
        else:
            return None

    @staticmethod
    def get_alexa_intent(data):
        if "request" in data and "intent" in data["request"] and "name" in data["request"]["intent"]:
            return data["request"]["intent"]["name"]
        else:
            return None
