import datetime
import inspect
import iso8601
import re
from datetime import timedelta

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon


class ADAPI:
    #
    # Internal
    #

    def __init__(self, ad: AppDaemon, name, logging_obj, args, config, app_config, global_vars):
        # Store args

        self._AD = ad
        self.name = name
        self._logging = logging_obj
        self.config = config
        self.app_config = app_config
        self.args = args
        self.global_vars = global_vars
        self._namespace = "default"
        self.logger = self._logging.get_child(name)
        self.err = self._logging.get_error().getChild(name)
        self.user_logs = {}
        if "log_level" in args:
            self.logger.setLevel(args["log_level"])
            self.err.setLevel(args["log_level"])
        if "log" in args:
            self.logger = self.get_user_log(args["log"])


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

    def _get_namespace(self, **kwargs):
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]
            del kwargs["namespace"]
        else:
            namespace = self._namespace

        return namespace

    #
    # Logging
    #

    def _log(self, logger, msg, *args, **kwargs):
        msg = self._sub_stack(msg)
        if "level" in kwargs:
            level = kwargs.get("level", "INFO")
            kwargs.pop("level")
        else:
            level = "INFO"
        ascii_encode = kwargs.get("ascii_encode", True)
        if ascii_encode is True:
            safe_enc = lambda s: str(s).encode("utf-8", "replace").decode("ascii", "replace")
            msg = safe_enc(msg)

        logger.log(self._logging.log_levels[level], msg, *args, **kwargs)

    def log(self, msg, *args, **kwargs):
        if "log" in kwargs:
            # Its a user defined log
            logger = self.get_user_log(kwargs["log"])
            kwargs.pop("log")
        else:
            logger = self.logger
        self._log(logger, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._log(self.err, msg, *args, **kwargs)

    def listen_log(self, cb, level="INFO", **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
        return self._AD.logging.add_log_callback(namespace, self.name, cb, level, **kwargs)

    def cancel_listen_log(self, handle):
        self.logger.debug("Canceling listen_log for %s", self.name)
        self._AD.logging.cancel_log_callback(self.name, handle)

    def get_main_log(self):
        return self.logger

    def get_error_log(self):
        return self.err

    def get_user_log(self, log):
        if log in self.user_logs:
            # Did we use it already?
            logger = self.user_logs[log]
        else:
            # Build it on the fly
            logger = self._AD.logging.get_user_log(self.name, log).getChild(self.name)
            self.user_logs[log] = logger
            if "log_level" in self.args:
                logger.setLevel(self.args["log_level"])

        return logger

    def set_log_level(self, level):
        self.logger.setLevel(self._logging.log_levels[level])
        self.err.setLevel(self._logging.log_levels[level])
        for log in self.user_logs:
            self.user_logs[log].setLevel(self._logging.log_levels[level])

    def set_error_level(self, level):
        self.err.setLevel(self._logging.log_levels[level])
    #
    # Threading
    #

    def set_app_pin(self, pin):
        self._AD.threading.set_app_pin(self.name, pin)

    def get_app_pin(self):
        return self._AD.threading.get_app_pin(self.name)

    def set_pin_thread(self, thread):
        self._AD.threading.set_pin_thread(self.name, thread)

    def get_pin_thread(self):
        return self._AD.threading.get_pin_thread(self.name)

    #
    # Namespace
    #

    def set_namespace(self, namespace):
        self._namespace = namespace

    def get_namespace(self):
        return self._namespace

    def list_namespaces(self):
        return self._AD.state.list_namespaces()

    def save_namespace(self, namespace):
        self._AD.state.save_namespace(namespace)

    #
    # Utility
    #

    def get_app(self, name):
        return self._AD.app_management.get_app(name)

    def _check_entity(self, namespace, entity):
        if "." not in entity:
            raise ValueError(
                "{}: Invalid entity ID: {}".format(self.name, entity))
        if not self._AD.state.entity_exists(namespace, entity):
            self.logger.warning("%s: Entity %s not found in namespace %s", self.name, entity, namespace)

    def get_ad_version(self):
        return utils.__version__

    def entity_exists(self, entity_id, **kwargs):
        namespace = self._get_namespace(**kwargs)
        return self._AD.state.entity_exists(namespace, entity_id)

    def split_entity(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(**kwargs), entity_id)
        return entity_id.split(".")

    def split_device_list(self, list_):
        return list_.split(",")

    def get_plugin_config(self, **kwargs):
        namespace = self._get_namespace(**kwargs)
        return self._AD.plugins.get_plugin_meta(namespace)

    def friendly_name(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(**kwargs), entity_id)
        state = self.get_state(**kwargs)
        if entity_id in state:
            if "friendly_name" in state[entity_id]["attributes"]:
                return state[entity_id]["attributes"]["friendly_name"]
            else:
                return entity_id
        return None

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
        if self._AD.http is not None:
            return self._AD.http.register_endpoint(cb, ep)
        else:
            self.logger.warning("register_endpoint for %s filed - HTTP component is not configured", name)


    def unregister_endpoint(self, handle):
        self._AD.http.unregister_endpoint(handle, self.name)

    #
    # State
    #

    def listen_state(self, cb, entity=None, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
        name = self.name
        if entity is not None and "." in entity:
            self._check_entity(namespace, entity)
        return self._AD.state.add_state_callback(name, namespace, entity, cb, kwargs)

    def cancel_listen_state(self, handle):
        self.logger.debug("Canceling listen_state for %s", self.name)
        self._AD.state.cancel_state_callback(handle, self.name)

    def info_listen_state(self, handle):
        self.logger.debug("Calling info_listen_state for %s",self.name)
        return self._AD.state.info_state_callback(handle, self.name)

    def get_state(self, entity_id=None, attribute=None, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        return self._AD.state.get_state(self.name, namespace, entity_id, attribute, **kwargs)

        #
        # Service
        #

    @staticmethod
    def _check_service(service):
        if service.find("/") == -1:
            raise ValueError("Invalid Service Name: {}".format(service))

    def call_service(self, service, **kwargs):
        self._check_service(service)
        d, s = service.split("/")
        self.logger.debug("call_service: %s/%s, %s", d, s, kwargs)

        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        return self._AD.services.call_service(namespace, d, s, kwargs)

    def set_state(self, entity_id, **kwargs):
        self.logger.debug("set state: %s, %s", entity_id, kwargs)
        namespace = self._get_namespace(**kwargs)
        self._check_entity(namespace, entity_id)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        old_state = self._AD.state.get_state(self.name, namespace, entity_id)
        new_state = self._AD.state.parse_state(entity_id, namespace, **kwargs)

        self._AD.state.set_state_simple(namespace, entity_id, new_state)

        # Fire the plugin's state update if it has one

        plugin = self._AD.plugins.get_plugin_object(namespace)

        if hasattr(plugin, "set_plugin_state"):
            # We assume that the state change will come back to us via the plugin
            plugin.set_plugin_state(namespace, entity_id, new_state, **kwargs)
        else:
            # Just fire the event locally

            data = \
                        {
                            "event_type": "state_changed",
                            "data":
                                {
                                    "entity_id": entity_id,
                                    "new_state": new_state,
                                    "old_state": old_state
                                }
                        }

            self._AD.thread_async.call_async_no_wait(self._AD.events.process_event, namespace, data)

        return new_state

    #
    # Events
    #

    def listen_event(self, cb, event=None, **kwargs):
        namespace = self._get_namespace(**kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        _name = self.name
        self.logger.debug("Calling listen_event for %s", self.name)
        return self._AD.events.add_event_callback(_name, namespace, cb, event, **kwargs)

    def cancel_listen_event(self, handle):
        self.logger.debug("Canceling listen_event for %s", self.name)
        self._AD.events.cancel_event_callback(self.name, handle)

    def info_listen_event(self, handle):
        self.logger.debug("Calling info_listen_event for %s", self.name)
        return self._AD.events.info_event_callback(self.name, handle)

    def fire_event(self, event, **kwargs):
        namespace = self._get_namespace(**kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        # Fire the plugin's state update if it has one

        plugin = self._AD.plugins.get_plugin_object(namespace)

        if hasattr(plugin, "fire_plugin_event"):
            # We assume that the event will come back to us via the plugin
            plugin.fire_plugin_event(event, namespace, **kwargs)
        else:
            # Just fire the event locally
            self._AD.thread_async.call_async_no_wait(self._AD.events.process_event, namespace, {"event_type": event, "data": kwargs})


    #
    # Time
    #

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
        return self._AD.sched.sun_up()

    def sun_down(self):
        return self._AD.sched.sun_down()

    def parse_time(self, time_str, name=None, aware=False):
        return self._AD.sched.parse_time(time_str, name, aware)

    def parse_datetime(self, time_str, name=None, aware=False):
        return self._AD.sched.parse_datetime(time_str, name, aware)

    def get_now(self):
        return self._AD.sched.get_now()

    def get_now_ts(self):
        return self._AD.sched.get_now_ts()

    def now_is_between(self, start_time_str, end_time_str, name=None):
        return self._AD.sched.now_is_between(start_time_str, end_time_str, name)

    def sunrise(self, aware=False):
        return self._AD.sched.sunrise(aware)

    def sunset(self, aware=False):
        return self._AD.sched.sunset(aware)

    def time(self):
        return self._AD.sched.get_now().astimezone(self._AD.tz).time()


    def datetime(self, aware=False):
        if aware is True:
            return self._AD.sched.get_now().astimezone(self._AD.tz)
        else:
            return self._AD.sched.get_now_naive()

    def date(self):
        return self._AD.sched.get_now().astimezone(self._AD.tz).date()

    def get_timezone(self):
        return self._AD.time_zone

    #
    # Scheduler
    #

    def cancel_timer(self, handle):
        name = self.name
        self._AD.sched.cancel_timer(name, handle)

    def info_timer(self, handle):
        return self._AD.sched.info_timer(handle, self.name)

    def run_in(self, callback, seconds, **kwargs):
        name = self.name
        self.logger.debug("Registering run_in in %s seconds for %s", seconds, name)
        # convert seconds to an int if possible since a common pattern is to
        # pass this through from the config file which is a string
        exec_time = self.get_now() + timedelta(seconds=int(seconds))
        handle = self._AD.sched.insert_schedule(
            name, exec_time, callback, False, None, **kwargs
        )
        return handle

    def run_once(self, callback, start, **kwargs):
        if type(start) == datetime.time:
            when = start
        elif type(start) == str:
            when = self._AD.sched._parse_time(start, self.name, True)["datetime"].time()
        else:
            raise ValueError("Invalid type for start")
        name = self.name
        now = self.get_now()
        today = now.date()
        event = datetime.datetime.combine(today, when)
        if event < now:
            one_day = datetime.timedelta(days=1)
            event = event + one_day
        exec_time = event.timestamp()
        handle = self._AD.sched.insert_schedule(
            name, exec_time, callback, False, None, **kwargs
        )
        return handle

    def run_at(self, callback, start, **kwargs):
        if type(start) == datetime.datetime:
            when = start
        elif type(start) == str:
            when = self._AD.sched._parse_time(start, self.name)["datetime"]
        else:
            raise ValueError("Invalid type for start")
        aware_when = self._AD.sched.convert_naive(when)
        name = self.name
        now = self.get_now()
        if aware_when < now:
            raise ValueError(
                "{}: run_at() Start time must be "
                "in the future".format(self.name)
            )
        handle = self._AD.sched.insert_schedule(
            name, aware_when, callback, False, None, **kwargs
        )
        return handle

    def run_daily(self, callback, start, **kwargs):
        info = None
        when = None
        if type(start) == datetime.time:
            when = start
        elif type(start) == str:
            info = self._AD.sched._parse_time(start, self.name)
        else:
            raise ValueError("Invalid type for start")

        if info is None or info["sun"] is None:
            if when is None:
                when = info["datetime"].time()
            now = self._AD.sched.make_naive(self.get_now())
            today = now.date()
            event = datetime.datetime.combine(today, when)
            if event < now:
                event = event + datetime.timedelta(days=1)
            handle = self.run_every(callback, event, 24 * 60 * 60, **kwargs)
        elif info["sun"] == "sunrise":
            kwargs["offset"] = info["offset"]
            handle = self.run_at_sunrise(callback, **kwargs)
        else:
            kwargs["offset"] = info["offset"]
            handle = self.run_at_sunset(callback, **kwargs)
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
        aware_start = self._AD.sched.convert_naive(start)
        if aware_start < now:
            raise ValueError("start cannot be in the past")

        self.logger.debug("Registering run_every starting %s in %ss intervals for %s", aware_start, interval, name)

        handle = self._AD.sched.insert_schedule(name, aware_start, callback, True, None,
                                                interval=interval, **kwargs)
        return handle

    def _schedule_sun(self, name, type_, callback, **kwargs):
        event = self._AD.sched.sun[type_]
        handle = self._AD.sched.insert_schedule(
            name, event, callback, True, type_, **kwargs
        )
        return handle

    def run_at_sunset(self, callback, **kwargs):
        name = self.name
        self.logger.debug("Registering run_at_sunset with kwargs = %s for %s", kwargs, name)
        handle = self._schedule_sun(name, "next_setting", callback, **kwargs)
        return handle

    def run_at_sunrise(self, callback, **kwargs):
        name = self.name
        self.logger.debug("Registering run_at_sunrise with kwargs = %s for %s", kwargs, name)
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
        self.fire_event("__HADASHBOARD_EVENT", **kwargs)
    #
    # Other
    #
    def run_in_thread(self, callback, thread):
        self.run_in(callback, 0, pin=False, pin_thread=thread)

    def get_thread_info(self):
        return self._AD.threading.get_thread_info()

    def get_scheduler_entries(self):
        return self._AD.sched.get_scheduler_entries()

    def get_callback_entries(self):
        return self._AD.callbacks.get_callback_entries()

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
        if "request" in data and "err" in data["request"] and "message" in data["request"]["err"]:
            return data["request"]["err"]["message"]
        else:
            return None

    @staticmethod
    def get_alexa_intent(data):
        if "request" in data and "intent" in data["request"] and "name" in data["request"]["intent"]:
            return data["request"]["intent"]["name"]
        else:
            return None
