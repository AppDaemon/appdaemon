import sys
import importlib
import traceback
import os
import os.path
from queue import Queue
import time
import datetime
import uuid
import astral
import pytz
import math
import asyncio
import yaml
import concurrent
import threading
import random
import re
from copy import deepcopy

import appdaemon.utils as utils


class AppDaemon:

    required_meta = ["latitude", "longitude", "elevation", "time_zone"]

    def __init__(self, logger, error, loop, **kwargs):

        self.logger = logger
        self.error = error
        self.config = kwargs
        self.q = Queue(maxsize=0)

        self.was_dst = False

        self.last_state = None
        self.inits = {}
        self.last_plugin_state = {}

        self.monitored_files = {}
        self.modules = {}
        self.appq = None
        self.executor = None
        self.loop = None
        self.srv = None
        self.appd = None
        self.stopping = False
        self.dashboard = None

        self.now = datetime.datetime.now().timestamp()

        self.objects = {}

        self.schedule = {}
        self.schedule_lock = threading.RLock()

        self.callbacks = {}
        self.callbacks_lock = threading.RLock()

        self.state = {}
        self.state["default"] = {}
        self.state_lock = threading.RLock()

        self.endpoints = {}
        self.endpoints_lock = threading.RLock()

        self.plugin_meta = {}
        self.plugin_objs = {}

        # No locking yet
        self.global_vars = {}

        self.sun = {}

        self.config_file_modified = 0
        self.tz = None
        self.ad_time_zone = None

        self.realtime = True
        self.version = 0
        self.app_config_file_modified = 0
        self.app_config = None

        self.app_config_file = None
        self._process_arg("app_config_file", kwargs)

        self.plugin_params = kwargs["plugins"]

        # User Supplied/Defaults
        self.threads = 10
        self._process_arg("threads", kwargs)

        self.app_dir = None
        self._process_arg("app_dir", kwargs)

        self.starttime = None
        self._process_arg("starttime", kwargs)

        self._process_arg("now", kwargs)

        self.logfile = None
        self._process_arg("logfile", kwargs)
        if self.logfile == None:
            self.logfile = "STDOUT"

        self.latitude = None
        self._process_arg("latitude", kwargs)

        self.longitude = None
        self._process_arg("longitude", kwargs)

        self.elevation = None
        self._process_arg("elevation", kwargs)

        self.time_zone = None
        self._process_arg("time_zone", kwargs)

        self.errfile = None
        self._process_arg("error_file", kwargs)
        if self.errfile == None:
            self.errfile  = "STDERR"

        self.config_file = None
        self._process_arg("config_file", kwargs)

        self.config_dir = None
        self._process_arg("config_dir", kwargs)

        self.plugins = {}
        self._process_arg("plugins", kwargs)

        self.tick = 1
        self._process_arg("tick", kwargs)

        self.max_skew = 1
        self._process_arg("max_skew", kwargs)

        self.endtime = None
        if "endtime" in kwargs:
            self.endtime = datetime.datetime.strptime(kwargs["endtime"], "%Y-%m-%d %H:%M:%S")

        self.interval = 1
        self._process_arg("interval", kwargs)

        self.loglevel = "INFO"
        self._process_arg("loglevel", kwargs)

        self.config_dir = None
        self._process_arg("config_dir", kwargs)

        self.api_port = None
        self._process_arg("api_port", kwargs)

        self.utility_delay = 1
        self._process_arg("utility_delay", kwargs)

        self.exclude_dirs = ["__pycache__"]
        if "exclude_dirs" in kwargs:
            self.exclude_dirs += kwargs["exclude_dirs"]

        self.stop_function = None
        self.stop_function = None
        self._process_arg("stop_function", kwargs)

        if self.tick != 1 or self.interval != 1 or self.starttime is not None:
            self.realtime = False

        if kwargs.get("cert_verify", True) == False:
            self.certpath = False

        if kwargs.get("disable_apps") is True:
            self.apps = False
            self.log("INFO", "Apps are disabled")
        else:
            self.apps = True
            self.log("INFO", "Starting Apps")

        # Add appdir and subdirs to path
        if self.apps is True:
            if self.app_dir is None:
                if self.config_dir is None:
                    self.app_dir = utils.find_path("apps")
                else:
                    self.app_dir = os.path.join(self.config_dir, "apps")

            if os.path.isdir(self.app_dir) is False:
                self.log("ERROR", "Invalid value for app_dir: {}".format(self.app_dir))
                return


            file, self.app_config_file_modified = self.check_latest_app_config()

            for root, subdirs, files in os.walk(self.app_dir):
                if root[-11:] != "__pycache__":
                    sys.path.insert(0, root)
        else:
            self.app_config_file_modified = 0

        #
        # Initial Setup
        #

        self.appq = asyncio.Queue(maxsize=0)

        self.loop = loop

        self.stopping = False

        self.log("DEBUG", "Entering run()")

        # Load App Config

        self.app_config = self.read_config()

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

        self.log("DEBUG", "Creating worker threads ...")

        # Create Worker Threads
        for i in range(self.threads):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()

        self.log("DEBUG", "Done")

        # Load Plugins

        if self.plugins is not None:
            for name in self.plugins:
                basename = self.plugins[name]["type"]
                module_name = "{}plugin".format(basename)
                class_name = "{}Plugin".format(basename.capitalize())
                basepath = "appdaemon.plugins"

                self.log("INFO",
                          "Loading Plugin {} using class {} from module {}".format(name, class_name, module_name))
                full_module_name = "{}.{}.{}".format(basepath, basename, module_name)
                mod = __import__(full_module_name, globals(), locals(), [module_name], 0)
                app_class = getattr(mod, class_name)

                plugin = app_class(self, name, self.logger, self.err, self.loglevel, self.plugins[name])

                namespace = plugin.get_namespace()

                if namespace in self.plugin_objs:
                    raise ValueError("Duplicate namespace: {}".format(namespace))

                self.plugin_objs[namespace] = plugin

                loop.create_task(plugin.get_updates())

        # Create utility loop

        self.log("DEBUG", "Starting utility loop")

        loop.create_task(self.utility())



    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    def stop(self):
        self.stopping = True
        # if ws is not None:
        #    ws.close()
        self.appq.put_nowait({"event_type": "ha_stop", "data": None})
        for plugin in self.plugin_objs:
            self.plugin_objs[plugin].stop()

    #
    # Diagnostics
    #

    def dump_callbacks(self):
        if self.callbacks == {}:
            self.log("INFO", "No callbacks")
        else:
            self.log("INFO", "--------------------------------------------------")
            self.log("INFO", "Callbacks")
            self.log("INFO", "--------------------------------------------------")
            for name in self.callbacks.keys():
                self.log("INFO", "{}:".format(name))
                for uuid_ in self.callbacks[name]:
                    self.log( "INFO", "  {} = {}".format(uuid_, self.callbacks[name][uuid_]))
            self.log("INFO", "--------------------------------------------------")

    def dump_objects(self):
        self.log("INFO", "--------------------------------------------------")
        self.log("INFO", "Objects")
        self.log("INFO", "--------------------------------------------------")
        for object_ in self.objects.keys():
            self.log("INFO", "{}: {}".format(object_, self.objects[object_]))
        self.log("INFO", "--------------------------------------------------")

    def dump_queue(self):
        self.log("INFO", "--------------------------------------------------")
        self.log("INFO", "Current Queue Size is {}".format(self.q.qsize()))
        self.log("INFO", "--------------------------------------------------")

    def get_callback_entries(self):
        callbacks = {}
        for name in self.callbacks.keys():
            callbacks[name] = {}
            for uuid_ in self.callbacks[name]:
                callbacks[name][uuid_] = {}
                if "entity" in callbacks[name][uuid_]:
                    callbacks[name][uuid_]["entity"] = self.callbacks[name][uuid_]["entity"]
                else:
                    callbacks[name][uuid_]["entity"] = None
                callbacks[name][uuid_]["type"] = self.callbacks[name][uuid_]["type"]
                callbacks[name][uuid_]["kwargs"] = self.callbacks[name][uuid_]["kwargs"]
                callbacks[name][uuid_]["function"] = self.callbacks[name][uuid_]["function"]
                callbacks[name][uuid_]["name"] = self.callbacks[name][uuid_]["name"]
        return callbacks

    #
    # Constraints
    #
    def check_constraint(self, key, value, app):
        unconstrained = True
        if key in app.list_constraints():
            method = getattr(app, key)
            unconstrained = method(value)

        return unconstrained

    def check_time_constraint(self, args, name):
        unconstrained = True
        if "constrain_start_time" in args or "constrain_end_time" in args:
            if "constrain_start_time" not in args:
                start_time = "00:00:00"
            else:
                start_time = args["constrain_start_time"]
            if "constrain_end_time" not in args:
                end_time = "23:59:59"
            else:
                end_time = args["constrain_end_time"]
            if not self.now_is_between(start_time, end_time, name):
                unconstrained = False

        return unconstrained

    #
    # Thread Management
    #

    def dispatch_worker(self, name, args):
        unconstrained = True
        #
        # Argument Constraints
        #
        for arg in self.app_config[name].keys():
            constrained = self.check_constraint(arg, self.app_config[name][arg], self.objects[name]["object"])
            if not constrained:
                unconstrained = False
        if not self.check_time_constraint(self.app_config[name], name):
            unconstrained = False
        #
        # Callback level constraints
        #
        if "kwargs" in args:
            for arg in args["kwargs"].keys():
                constrained = self.check_constraint(arg, args["kwargs"][arg], self.objects[name]["object"])
                if not constrained:
                    unconstrained = False
            if not self.check_time_constraint(args["kwargs"], name):
                unconstrained = False

        if unconstrained:
            self.q.put_nowait(args)


    # noinspection PyBroadException
    def worker(self):
        while True:
            args = self.q.get()
            _type = args["type"]
            funcref = args["function"]
            _id = args["id"]
            name = args["name"]
            if name in self.objects and self.objects[name]["id"] == _id:
                app = self.objects[name]["object"]
                try:
                    if _type == "initialize":
                        self.log("DEBUG", "Calling initialize() for {}".format(name))
                        funcref()
                        self.log("DEBUG", "{} initialize() done".format(name))
                    elif _type == "timer":
                        funcref(self.sanitize_timer_kwargs(app, args["kwargs"]))
                    elif _type == "attr":
                        entity = args["entity"]
                        attr = args["attribute"]
                        old_state = args["old_state"]
                        new_state = args["new_state"]
                        funcref(entity, attr, old_state, new_state,
                                self.sanitize_state_kwargs(app, args["kwargs"]))
                    elif _type == "event":
                        data = args["data"]
                        funcref(args["event"], data, args["kwargs"])

                except:
                    self.err("WARNING", '-' * 60)
                    self.err("WARNING", "Unexpected error in worker for App {}:".format(name))
                    self.err("WARNING", "Worker Ags: {}".format(args))
                    self.err("WARNING", '-' * 60)
                    self.err("WARNING", traceback.format_exc())
                    self.err("WARNING", '-' * 60)
                    if self.errfile != "STDERR" and self.logfile != "STDOUT":
                        self.log("WARNING", "Logged an error to {}".format(self.errfile))
            else:
                self.log("WARNING", "Found stale callback for {} - discarding".format(name))

            if self.inits.get(name):
                self.inits.pop(name)

            self.q.task_done()

    #
    # State
    #

    def entity_exists(self, namespace, entity):
        with self.state_lock:
            if namespace in self.state and entity in self.state[namespace]:
                return True
            else:
                return False


    def add_state_callback(self, name, namespace, entity, cb, kwargs):
        with self.callbacks_lock:
            if name not in self.callbacks:
                self.callbacks[name] = {}
            handle = uuid.uuid4()
            self.callbacks[name][handle] = {
                "name": name,
                "id": self.objects[name]["id"],
                "type": "state",
                "function": cb,
                "entity": entity,
                "namespace": namespace,
                "kwargs": kwargs
            }

        #
        # In the case of a quick_start parameter,
        # start the clock immediately if the device is already in the new state
        #
        if "immediate" in kwargs and kwargs["immediate"] is True:
            if entity is not None and "new" in kwargs and "duration" in kwargs:
                with self.state_lock:
                    if self.state[namespace][entity]["state"] == kwargs["new"]:
                        exec_time = self.get_now_ts() + int(kwargs["duration"])
                        kwargs["handle"] = self.insert_schedule(
                            name, exec_time, cb, False, None,
                            entity=entity,
                            attribute=None,
                            old_state=None,
                            new_state=kwargs["new"], **kwargs
                    )

        return handle

    def cancel_state_callback(self, handle, name):
        with self.callbacks_lock:
            if name in self.callbacks and handle in self.callbacks[name]:
                del self.callbacks[name][handle]
            if name in self.callbacks and self.callbacks[name] == {}:
                del self.callbacks[name]

    def info_state_callback(self, handle, name):
        with self.callbacks_lock:
            if name in self.callbacks and handle in self.callbacks[name]:
                callback = self.callbacks[name][handle]
                return (
                    callback["namespace"],
                    callback["entity"],
                    callback["kwargs"].get("attribute", None),
                    self.sanitize_state_kwargs(self.objects[name]["object"], callback["kwargs"])
                )
            else:
                raise ValueError("Invalid handle: {}".format(handle))

    def get_entity(self, namespace, entity_id):
            with self.state_lock:
                if namespace in self.state:
                    if entity_id in self.state[namespace]:
                        return self.state[namespace][entity_id]
                    else:
                        return None
                else:
                    self.log("WARNING", "Unknown namespace: {}".format(namespace))
                    return None

    def get_state(self, namespace, device, entity, attribute):
            with self.state_lock:
                if device is None:
                    return deepcopy(self.state[namespace])
                elif entity is None:
                    devices = {}
                    for entity_id in self.state[namespace].keys():
                        thisdevice, thisentity = entity_id.split(".")
                        if device == thisdevice:
                            devices[entity_id] = self.state[namespace][entity_id]
                    return deepcopy(devices)
                elif attribute is None:
                    entity_id = "{}.{}".format(device, entity)
                    if entity_id in self.state[namespace]:
                        return deepcopy(self.state[namespace][entity_id]["state"])
                    else:
                        return None
                else:
                    entity_id = "{}.{}".format(device, entity)
                    if attribute == "all":
                        if entity_id in self.state[namespace]:
                            return deepcopy(self.state[namespace][entity_id]["attributes"])
                        else:
                            return None
                    else:
                        if attribute in self.state[namespace][entity_id]:
                            return deepcopy(self.state[namespace][entity_id][attribute])
                        elif attribute in self.state[namespace][entity_id]["attributes"]:
                            return deepcopy(self.state[namespace][entity_id]["attributes"][
                                attribute])
                        else:
                            return None

    def set_state(self, namespace, entity, state):
        with self.state_lock:
            self.state[namespace][entity] = state

    def set_app_state(self, entity_id, state):
        self.log("DEBUG", "set_app_state: {}".format(entity_id))
        if entity_id is not None and "." in entity_id:
            with self.state_lock:
                if entity_id in self.state:
                    old_state = self.state[entity_id]
                else:
                    old_state = None
                data = {"entity_id": entity_id, "new_state": state, "old_state": old_state}
                args = {"event_type": "state_changed", "data": data}
                self.appq.put_nowait(args)

    #
    # Events
    #
    def add_event_callback(self, name, namespace, cb, event, **kwargs):
        with self.callbacks_lock:
            if name not in self.callbacks:
                self.callbacks[name] = {}
            handle = uuid.uuid4()
            self.callbacks[name][handle] = {
                "name": name,
                "id": self.objects[name]["id"],
                "type": "event",
                "function": cb,
                "namespace": namespace,
                "event": event,
                "kwargs": kwargs
            }
        return handle

    def cancel_event_callback(self, name, handle):
        with self.callbacks_lock:
            if name in self.callbacks and handle in self.callbacks[name]:
                del self.callbacks[name][handle]
            if name in self.callbacks and self.callbacks[name] == {}:
                del self.callbacks[name]

    def info_event_callback(self, name, handle):
        with self.callbacks_lock:
            if name in self.callbacks and handle in self.callbacks[name]:
                callback = self.callbacks[name][handle]
                return callback["event"], callback["kwargs"].copy()
            else:
                raise ValueError("Invalid handle: {}".format(handle))

    #
    # Scheduler
    #

    def cancel_timer(self, name, handle):
        self.log("DEBUG", "Canceling timer for {}".format(name))
        with self.schedule_lock:
            if name in self.schedule and handle in self.schedule[name]:
                del self.schedule[name][handle]
            if name in self.schedule and self.schedule[name] == {}:
                del self.schedule[name]

    # noinspection PyBroadException
    def exec_schedule(self, name, entry, args):
        try:
            # Locking performed in calling function
            if "inactive" in args:
                return
            # Call function
            if "entity" in args["kwargs"]:
                self.dispatch_worker(name, {
                    "name": name,
                    "id": self.objects[name]["id"],
                    "type": "attr",
                    "function": args["callback"],
                    "attribute": args["kwargs"]["attribute"],
                    "entity": args["kwargs"]["entity"],
                    "new_state": args["kwargs"]["new_state"],
                    "old_state": args["kwargs"]["old_state"],
                    "kwargs": args["kwargs"],
                })
            else:
                self.dispatch_worker(name, {
                    "name": name,
                    "id": self.objects[name]["id"],
                    "type": "timer",
                    "function": args["callback"],
                    "kwargs": args["kwargs"],
                })
            # If it is a repeating entry, rewrite with new timestamp
            if args["repeat"]:
                if args["type"] == "next_rising" or args["type"] == "next_setting":
                    # Its sunrise or sunset - if the offset is negative we
                    # won't know the next rise or set time yet so mark as inactive
                    # So we can adjust with a scan at sun rise/set
                    if args["offset"] < 0:
                        args["inactive"] = 1
                    else:
                        # We have a valid time for the next sunrise/set so use it
                        c_offset = self.get_offset(args)
                        args["timestamp"] = self.calc_sun(args["type"]) + c_offset
                        args["offset"] = c_offset
                else:
                    # Not sunrise or sunset so just increment
                    # the timestamp with the repeat interval
                    args["basetime"] += args["interval"]
                    args["timestamp"] = args["basetime"] + self.get_offset(args)
            else:  # Otherwise just delete
                del self.schedule[name][entry]

        except:
            self.err("WARNING", '-' * 60)
            self.err(
                "WARNING",
                "Unexpected error during exec_schedule() for App: {}".format(name)
            )
            self.err("WARNING", "Args: {}".format(args))
            self.err("WARNING", '-' * 60)
            self.err("WARNING", traceback.format_exc())
            self.err("WARNING", '-' * 60)
            if self.errfile != "STDERR" and self.logfile != "STDOUT":
                # When explicitly logging to stdout and stderr, suppress
                # verbose_log messages about writing an error (since they show up anyway)
                self.log("WARNING", "Logged an error to {}".format(self.errfile))
            self.err("WARNING", "Scheduler entry has been deleted")
            self.err("WARNING", '-' * 60)

            del self.schedule[name][entry]

    def process_sun(self, action):
        self.log(
            "DEBUG",
            "Process sun: {}, next sunrise: {}, next sunset: {}".format(
                action, self.sun["next_rising"], self.sun["next_setting"]
            )
        )
        with self.schedule_lock:
            for name in self.schedule.keys():
                for entry in sorted(
                        self.schedule[name].keys(),
                        key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
                ):
                    schedule = self.schedule[name][entry]
                    if schedule["type"] == action and "inactive" in schedule:
                        del schedule["inactive"]
                        c_offset = self.get_offset(schedule)
                        schedule["timestamp"] = self.calc_sun(action) + c_offset
                        schedule["offset"] = c_offset

    def calc_sun(self, type_):
        # convert to a localized timestamp
        return self.sun[type_].timestamp()

    def info_timer(self, handle, name):
        with self.schedule_lock:
            if name in self.schedule and handle in self.schedule[name]:
                callback = self.schedule[name][handle]
                return (
                    datetime.datetime.fromtimestamp(callback["timestamp"]),
                    callback["interval"],
                    self.sanitize_timer_kwargs(self.objects[name]["object"], callback["kwargs"])
                )
            else:
                raise ValueError("Invalid handle: {}".format(handle))

    def init_sun(self):
        latitude = self.latitude
        longitude = self.longitude

        if -90 > latitude < 90:
            raise ValueError("Latitude needs to be -90 .. 90")

        if -180 > longitude < 180:
            raise ValueError("Longitude needs to be -180 .. 180")

        elevation = self.elevation

        self.tz = pytz.timezone(self.time_zone)

        self.location = astral.Location((
            '', '', latitude, longitude, self.tz.zone, elevation
        ))

    def update_sun(self):
        # now = datetime.datetime.now(self.tz)
        now = self.tz.localize(self.get_now())
        mod = -1
        while True:
            try:
                next_rising_dt = self.location.sunrise(
                    (now + datetime.timedelta(days=mod)).date(), local=False
                )
                if next_rising_dt > now:
                    break
            except astral.AstralError:
                pass
            mod += 1

        mod = -1
        while True:
            try:
                next_setting_dt = self.location.sunset(
                    (now + datetime.timedelta(days=mod)).date(), local=False
                )
                if next_setting_dt > now:
                    break
            except astral.AstralError:
                pass
            mod += 1

        old_next_rising_dt = self.sun.get("next_rising")
        old_next_setting_dt = self.sun.get("next_setting")
        self.sun["next_rising"] = next_rising_dt
        self.sun["next_setting"] = next_setting_dt

        if old_next_rising_dt is not None and old_next_rising_dt != self.sun["next_rising"]:
            # dump_schedule()
            self.process_sun("next_rising")
            # dump_schedule()
        if old_next_setting_dt is not None and old_next_setting_dt != self.sun["next_setting"]:
            # dump_schedule()
            self.process_sun("next_setting")
            # dump_schedule()

    @staticmethod
    def get_offset(kwargs):
        if "offset" in kwargs["kwargs"]:
            if "random_start" in kwargs["kwargs"] \
                    or "random_end" in kwargs["kwargs"]:
                raise ValueError(
                    "Can't specify offset as well as 'random_start' or "
                    "'random_end' in 'run_at_sunrise()' or 'run_at_sunset()'"
                )
            else:
                offset = kwargs["kwargs"]["offset"]
        else:
            rbefore = kwargs["kwargs"].get("random_start", 0)
            rafter = kwargs["kwargs"].get("random_end", 0)
            offset = random.randint(rbefore, rafter)
        # verbose_log(conf.logger, "INFO", "sun: offset = {}".format(offset))
        return offset

    def insert_schedule(self, name, utc, callback, repeat, type_, **kwargs):
        with self.schedule_lock:
            if name not in self.schedule:
                self.schedule[name] = {}
            handle = uuid.uuid4()
            utc = int(utc)
            c_offset = self.get_offset({"kwargs": kwargs})
            ts = utc + c_offset
            interval = kwargs.get("interval", 0)

            self.schedule[name][handle] = {
                "name": name,
                "id": self.objects[name]["id"],
                "callback": callback,
                "timestamp": ts,
                "interval": interval,
                "basetime": utc,
                "repeat": repeat,
                "offset": c_offset,
                "type": type_,
                "kwargs": kwargs
            }
            # verbose_log(conf.logger, "INFO", conf.schedule[name][handle])
        return handle

    def get_scheduler_entries(self):
        schedule = {}
        for name in self.schedule.keys():
            schedule[name] = {}
            for entry in sorted(
                    self.schedule[name].keys(),
                    key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
            ):
                schedule[name][entry] = {}
                schedule[name][entry]["timestamp"] = self.schedule[name][entry]["timestamp"]
                schedule[name][entry]["type"] = self.schedule[name][entry]["type"]
                schedule[name][entry]["name"] = self.schedule[name][entry]["name"]
                schedule[name][entry]["basetime"] = self.schedule[name][entry]["basetime"]
                schedule[name][entry]["repeat"] = self.schedule[name][entry]["basetime"]
                schedule[name][entry]["offset"] = self.schedule[name][entry]["basetime"]
                schedule[name][entry]["interval"] = self.schedule[name][entry]["basetime"]
                schedule[name][entry]["kwargs"] = self.schedule[name][entry]["basetime"]
                schedule[name][entry]["callback"] = self.schedule[name][entry]["callback"]
        return schedule

    def is_dst(self):
        return bool(time.localtime(self.get_now_ts()).tm_isdst)

    def get_now(self):
        return datetime.datetime.fromtimestamp(self.now)

    def get_now_ts(self):
        return self.now

    def now_is_between(self, start_time_str, end_time_str, name=None):
        start_time = self.parse_time(start_time_str, name)
        end_time = self.parse_time(end_time_str, name)
        now = self.get_now()
        start_date = now.replace(
            hour=start_time.hour, minute=start_time.minute,
            second=start_time.second
        )
        end_date = now.replace(
            hour=end_time.hour, minute=end_time.minute, second=end_time.second
        )
        if end_date < start_date:
            # Spans midnight
            if now < start_date and now < end_date:
                now = now + datetime.timedelta(days=1)
            end_date = end_date + datetime.timedelta(days=1)
        return start_date <= now <= end_date

    def sunset(self):
        return datetime.datetime.fromtimestamp(self.calc_sun("next_setting"))

    def sunrise(self):
        return datetime.datetime.fromtimestamp(self.calc_sun("next_rising"))

    def parse_time(self, time_str, name=None):
        parsed_time = None
        parts = re.search('^(\d+):(\d+):(\d+)', time_str)
        if parts:
            parsed_time = datetime.time(
                int(parts.group(1)), int(parts.group(2)), int(parts.group(3))
            )
        else:
            if time_str == "sunrise":
                parsed_time = self.sunrise().time()
            elif time_str == "sunset":
                parsed_time = self.sunset().time()
            else:
                parts = re.search(
                    '^sunrise\s*([+-])\s*(\d+):(\d+):(\d+)', time_str
                )
                if parts:
                    if parts.group(1) == "+":
                        parsed_time = (self.sunrise() + datetime.timedelta(
                            hours=int(parts.group(2)), minutes=int(parts.group(3)),
                            seconds=int(parts.group(4))
                        )).time()
                    else:
                        parsed_time = (self.sunrise() - datetime.timedelta(
                            hours=int(parts.group(2)), minutes=int(parts.group(3)),
                            seconds=int(parts.group(4))
                        )).time()
                else:
                    parts = re.search(
                        '^sunset\s*([+-])\s*(\d+):(\d+):(\d+)', time_str
                    )
                    if parts:
                        if parts.group(1) == "+":
                            parsed_time = (self.sunset() + datetime.timedelta(
                                hours=int(parts.group(2)),
                                minutes=int(parts.group(3)),
                                seconds=int(parts.group(4))
                            )).time()
                        else:
                            parsed_time = (self.sunset() - datetime.timedelta(
                                hours=int(parts.group(2)),
                                minutes=int(parts.group(3)),
                                seconds=int(parts.group(4))
                            )).time()
        if parsed_time is None:
            if name is not None:
                raise ValueError(
                    "{}: invalid time string: {}".format(name, time_str))
            else:
                raise ValueError("invalid time string: {}".format(time_str))
        return parsed_time

    def dump_sun(self):
        self.log("INFO", "--------------------------------------------------")
        self.log("INFO", "Sun")
        self.log("INFO", "--------------------------------------------------")
        self.log("INFO", self.sun)
        self.log("INFO", "--------------------------------------------------")

    def dump_schedule(self):
        if self.schedule == {}:
            self.log("INFO", "Schedule is empty")
        else:
            self.log("INFO", "--------------------------------------------------")
            self.log("INFO", "Scheduler Table")
            self.log("INFO", "--------------------------------------------------")
            for name in self.schedule.keys():
                self.log( "INFO", "{}:".format(name))
                for entry in sorted(
                        self.schedule[name].keys(),
                        key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
                ):
                    self.log(
                        "INFO",
                        "  Timestamp: {} - data: {}".format(
                            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(
                                self.schedule[name][entry]["timestamp"]
                            )),
                            self.schedule[name][entry]
                        )
                    )
            self.log("INFO", "--------------------------------------------------")

    async def do_every(self, period, f):
        #
        # We already set self.now for DST calculation and initial sunset,
        # but lets reset it at the start of the timer loop to avoid an initial clock skew
        #
        if self.starttime:
            self.now = datetime.datetime.strptime(self.starttime, "%Y-%m-%d %H:%M:%S").timestamp()
        else:
            self.now = datetime.datetime.now().timestamp()

        t = math.floor(self.now)
        count = 0
        t_ = math.floor(time.time())
        while not self.stopping:
            count += 1
            delay = max(t_ + count * period - time.time(), 0)
            await asyncio.sleep(delay)
            t += self.interval
            r = await f(t)
            if r is not None and r != t:
                # print("r: {}, t: {}".format(r,t))
                t = r
                t_ = r
                count = 0

    #
    # Scheduler Loop
    #

    # noinspection PyBroadException,PyBroadException

    async def do_every_tick(self, utc):
        try:
            start_time = datetime.datetime.now().timestamp()
            self.now = utc

            # If we have reached endtime bail out

            if self.endtime is not None and self.get_now() >= self.endtime:
                self.log("INFO", "End time reached, exiting")
                if self.stop_function is not None:
                    self.stop_function()
                else:
                    #
                    # We aren't in a standalone environment so the best we can do is terminate the AppDaemon parts
                    #
                    self.stop()

            if self.realtime:
                real_now = datetime.datetime.now().timestamp()
                delta = abs(utc - real_now)
                if delta > self.max_skew:
                    self.log("WARNING",
                              "Scheduler clock skew detected - delta = {} - resetting".format(delta))
                    return real_now

            # Update sunrise/sunset etc.

            self.update_sun()

            # Check if we have entered or exited DST - if so, reload apps
            # to ensure all time callbacks are recalculated

            now_dst = self.is_dst()
            if now_dst != self.was_dst:
                self.log(
                    "INFO",
                    "Detected change in DST from {} to {} -"
                    " reloading all modules".format(self.was_dst, now_dst)
                )
                # dump_schedule()
                self.log("INFO", "-" * 40)
                await utils.run_in_executor(self.loop, self.executor, self.read_apps, True)
                # dump_schedule()
            self.was_dst = now_dst

            # dump_schedule()

            # test code for clock skew
            # if random.randint(1, 10) == 5:
            #    time.sleep(random.randint(1,20))


            # Process callbacks

            # self.log("DEBUG", "Scheduler invoked at {}".format(now))
            with self.schedule_lock:
                for name in self.schedule.keys():
                    for entry in sorted(
                            self.schedule[name].keys(),
                            key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
                    ):

                        if self.schedule[name][entry]["timestamp"] <= utc:
                            self.exec_schedule(name, entry, self.schedule[name][entry])
                        else:
                            break
                for k, v in list(self.schedule.items()):
                    if v == {}:
                        del self.schedule[k]

            end_time = datetime.datetime.now().timestamp()

            loop_duration = (int((end_time - start_time) * 1000) / 1000) * 1000
            self.log("DEBUG", "Scheduler loop compute time: {}ms".format(loop_duration))

            if loop_duration > 900:
                self.log("WARNING", "Excessive time spent in scheduler loop: {}ms".format(loop_duration))

            return utc

        except:
            self.err("WARNING", '-' * 60)
            self.err("WARNING", "Unexpected error during do_every_tick()")
            self.err("WARNING", '-' * 60)
            self.err( "WARNING", traceback.format_exc())
            self.err("WARNING", '-' * 60)
            if self.errfile != "STDERR" and self.logfile != "STDOUT":
                # When explicitly logging to stdout and stderr, suppress
                # verbose_log messages about writing an error (since they show up anyway)
                self.log(
                    "WARNING",
                    "Logged an error to {}".format(self.errfile)
                )

    def process_meta(self, meta, namespace):

        for key in self.required_meta:
            if getattr(self, key) == None:
                if key in meta:
                    # We have a value so override
                    setattr(self, key, meta[key])

    async def notify_plugin_started(self, namespace, first_time=False):

        self.last_plugin_state[namespace] = datetime.datetime.now()

        meta = await self.plugin_objs[namespace].get_metadata()
        self.process_meta(meta, namespace)

        if not self.stopping:
            self.plugin_meta[namespace] = meta

            state = await self.plugin_objs[namespace].get_complete_state()

            with self.state_lock:
                self.state[namespace] = state

            if not first_time:
                await utils.run_in_executor(self.loop, self.executor, self.read_apps, True)
            else:
                self.log("INFO", "Got initial state from namespace {}".format(namespace))

            self.process_event("global", {"event_type": "plugin_started".format(namespace), "data": {"name": namespace}})

    def notify_plugin_stopped(self, namespace):

        self.process_event("global", {"event_type": "plugin_stopped".format(namespace), "data": {"name": namespace}})


    #
    # Utility Loop
    #

    async def utility(self):

        #
        # Wait for all plugins to initialize
        #
        initialized = False
        while not initialized:
            initialized = True
            for plugin in self.plugin_objs:
                if not self.plugin_objs[plugin].active():
                    initialized = False
                    break
            await asyncio.sleep(1)

        # Check if we need to bail due to missing metadata

        for key in self.required_meta:
            if getattr(self, key) == None:
               # No value so bail
                self.err("ERROR", "Required attribute not set or obtainable from any plugin: {}".format(key))
                self.err("ERROR", "AppDaemon is terminating")
                self.stop()


        if not self.stopping:

            #
            # All plugins are loaded and we have initial state
            #

            if self.starttime:
                new_now = datetime.datetime.strptime(self.starttime, "%Y-%m-%d %H:%M:%S")
                self.log("INFO", "Starting time travel ...")
                self.log("INFO", "Setting clocks to {}".format(new_now))
                self.now = new_now.timestamp()
            else:
                self.now = datetime.datetime.now().timestamp()

            # Take a note of DST

            self.was_dst = self.is_dst()

            # Setup sun

            self.init_sun()

            self.update_sun()

            # Create timer loop

            self.log("DEBUG", "Starting timer loop")

            self.loop.create_task(self.do_every(self.tick, self.do_every_tick))

            self.log("DEBUG", "Reading Apps")

            self.app_config_file_modified = datetime.datetime.now().timestamp()
            await utils.run_in_executor(self.loop, self.executor,self.read_apps, True)

            self.log("INFO", "App initialization complete")
            #
            # Fire APPD Started Event
            #
            self.process_event("global", {"event_type": "appd_started", "data": {}})

            while not self.stopping:
                start_time = datetime.datetime.now().timestamp()

                try:

                    await utils.run_in_executor(self.loop, self.executor, self.read_apps)

                    # Check to see if config has changed

                    await utils.run_in_executor(self.loop, self.executor, self.check_config)

                    # Call me suspicious, but lets update state from the plugins periodically
                    # in case we miss events for whatever reason
                    # Every 10 minutes seems like a good place to start

                    for plugin in self.plugin_objs:
                        if self.plugin_objs[plugin].active():
                            if  datetime.datetime.now() - self.last_plugin_state[plugin] > datetime.timedelta(
                            minutes=10):
                                try:
                                    self.log("DEBUG",
                                             "Refreshing {} state".format(plugin))

                                    state = await self.plugin_objs[plugin].get_complete_state()

                                    with self.state_lock:
                                        self.state[plugin] = state

                                    self.last_plugin_state[plugin] = datetime.datetime.now()
                                except:
                                    self.log("WARNING",
                                          "Unexpected error refreshing {} state - retrying in 10 minutes".format(plugin))

                    # Check for thread starvation

                    qsize = self.q.qsize()
                    if qsize > 0 and qsize % 10 == 0:
                        self.log("WARNING", "Queue size is {}, suspect thread starvation".format(self.q.qsize()))

                    # Plugins

                    for plugin in self.plugin_objs:
                        self.plugin_objs[plugin].utility()

                except:
                    self.err("WARNING", '-' * 60)
                    self.err("WARNING", "Unexpected error during utility()")
                    self.err("WARNING", '-' * 60)
                    self.err("WARNING", traceback.format_exc())
                    self.err("WARNING", '-' * 60)
                    if self.errfile != "STDERR" and self.logfile != "STDOUT":
                        # When explicitly logging to stdout and stderr, suppress
                        # verbose_log messages about writing an error (since they show up anyway)
                        self.log(
                            "WARNING",
                            "Logged an error to {}".format(self.errfile)
                        )

                end_time = datetime.datetime.now().timestamp()

                loop_duration = (int((end_time - start_time) * 1000) / 1000) * 1000

                self.log("DEBUG", "Util loop compute time: {}ms".format(loop_duration))

                if loop_duration > (self.utility_delay * 1000 * 0.9):
                    self.log("WARNING", "Excessive time spent in utility loop: {}ms".format(loop_duration))

                await asyncio.sleep(self.utility_delay)

    #
    # AppDaemon API
    #

    def register_endpoint(self, cb, name):

        handle = uuid.uuid4()

        with self.endpoints_lock:
            if name not in self.endpoints:
                self.endpoints[name] = {}
            self.endpoints[name][handle] = {"callback": cb, "name": name}

        return handle

    def unregister_endpoint(self, handle, name):
        with self.endpoints_lock:
            if name in self.endpoints and handle in self.endpoints[name]:
                del self.endpoints[name][handle]

    #
    # App Management
    #

    def get_app(self, name):
        if name in self.objects:
            return self.objects[name]["object"]
        else:
            return None

    def term_file(self, name):
        for key in self.app_config:
            if "module" in self.app_config[key] and self.app_config[key]["module"] == name:
                self.term_object(key)

    def clear_file(self, name):
        for key in self.app_config:
            if "module" in self.app_config[key] and self.app_config[key]["module"] == name:
                self.clear_object(key)
                if key in self.objects:
                    del self.objects[key]

    def clear_object(self, object_):
        self.log("DEBUG", "Clearing callbacks for {}".format(object_))
        with self.callbacks_lock:
            if object_ in self.callbacks:
                del self.callbacks[object_]
        with self.schedule_lock:
            if object_ in self.schedule:
                del self.schedule[object_]
        with self.endpoints_lock:
            if object_ in self.endpoints:
                del self.endpoints[object_]

    def term_object(self, name):
        if name in self.objects and hasattr(self.objects[name]["object"], "terminate"):
            self.log("INFO", "Terminating Object {}".format(name))
            # Call terminate directly rather than via worker thread
            # so we know terminate has completed before we move on
            self.objects[name]["object"].terminate()

    def init_object(self, name, class_name, module_name, app_args):
        self.log("INFO",
                  "Loading Object {} using class {} from module {}".format(name, class_name, module_name))
        modname = __import__(module_name)
        app_class = getattr(modname, class_name)
        self.objects[name] = {
            "object": app_class(
                self, name, self.logger, self.err, app_args[name], self.config, app_args, self.global_vars
            ),
            "id": uuid.uuid4()
        }

        # Call it's initialize function

        self.objects[name]["object"].initialize()

    def read_config(self):

        new_config = None

        if os.path.isfile(self.app_config_file):
            self.log("WARNING", "apps.yaml in the Config directory is deprecated. Please move apps.yaml to the apps directory.")
            new_config = self.read_config_file(self.app_config_file)
        else:
            for root, subdirs, files in os.walk(self.app_dir):
                if root[-11:] != "__pycache__":
                    for file in files:
                        if file[-5:] == ".yaml":
                            #root, ext = os.path.splitext(file)
                            config = self.read_config_file(os.path.join(root, file))

                            if new_config is None:
                                new_config = {}
                            new_config = {**new_config, **config}

        return new_config

    def check_latest_app_config(self):
        if os.path.isfile(self.app_config_file):
            return self.app_config_file, os.path.getmtime(self.app_config_file)
        else:
            latest = 0
            file = None
            for root, subdirs, files in os.walk(self.app_dir):
                if root[-11:] != "__pycache__":
                    for file in files:
                        if file[-5:] == ".yaml":
                            ts = os.path.getmtime(os.path.join(root, file))
                            if ts > latest:
                                latest = ts
                                file = os.path.join(root, file)
            return file, latest

    def read_config_file(self, file):

        new_config = None
        with open(file, 'r') as yamlfd:
            config_file_contents = yamlfd.read()
        try:
            new_config = yaml.load(config_file_contents)

        except yaml.YAMLError as exc:
            self.log("WARNING", "Error loading configuration")
            if hasattr(exc, 'problem_mark'):
                if exc.context is not None:
                    self.log("WARNING", "parser says")
                    self.log("WARNING", str(exc.problem_mark))
                    self.log("WARNING", str(exc.problem) + " " + str(exc.context))
                else:
                    self.log("WARNING", "parser says")
                    self.log("WARNING", str(exc.problem_mark))
                    self.log("WARNING", str(exc.problem))

        return new_config

    # noinspection PyBroadException
    def check_config(self):

        try:
            filename, modified = self.check_latest_app_config()
            if modified > self.app_config_file_modified:
                self.log("INFO", "{} modified".format(self.app_config_file))
                self.app_config_file_modified = modified
                new_config = self.read_config()

                if new_config is None:
                    self.log("WARNING", "New config not applied")
                    return

                # Check for changes

                for name in self.app_config:
                    # if name == "DEFAULT" or name == "AppDaemon" or name == "HADashboard":
                    #    continue
                    if name in new_config:
                        if self.app_config[name] != new_config[name]:
                            # Something changed, clear and reload

                            self.log("INFO", "App '{}' changed - reloading".format(name))
                            self.term_object(name)
                            self.clear_object(name)
                            #TODO: This should force a reload for all dependant apps too
                            self.init_object(
                                name, new_config[name]["class"],
                                new_config[name]["module"], new_config
                            )
                    else:

                        # Section has been deleted, clear it out

                        self.log("INFO", "App '{}' deleted - removing".format(name))
                        self.clear_object(name)

                for name in new_config:
                    if name not in self.app_config:
                        #
                        # New section added!
                        #
                        self.log("INFO", "App '{}' added - running".format(name))
                        self.init_object(
                            name, new_config[name]["class"],
                            new_config[name]["module"], new_config
                        )

                self.app_config = new_config
        except:
            self.err("WARNING", '-' * 60)
            self.err("WARNING", "Unexpected error:")
            self.err("WARNING", '-' * 60)
            self.err("WARNING", traceback.format_exc())
            self.err("WARNING", '-' * 60)
            if self.errfile != "STDERR" and self.logfile != "STDOUT":
                self.log("WARNING", "Logged an error to {}".format(self.errfile))

    # noinspection PyBroadException
    def read_app(self, file, reload=False):
        name = os.path.basename(file)
        module_name = os.path.splitext(name)[0]
        # Import the App
        try:
            if reload:
                self.log("INFO", "Reloading Module: {}".format(file))

                file, ext = os.path.splitext(name)

                #
                # Clear out callbacks and remove objects
                #
                self.term_file(file)
                self.clear_file(file)
                #
                # Reload
                #
                try:
                    importlib.reload(self.modules[module_name])
                except KeyError:
                    if name not in sys.modules:
                        # Probably failed to compile on initial load
                        # so we need to re-import
                        self.read_app(file)
                    else:
                        # A real KeyError!
                        raise
            else:
                self.log("INFO", "Loading Module: {}".format(file))
                self.modules[module_name] = importlib.import_module(module_name)

            # Instantiate class and Run initialize() function

            if self.app_config is not None:
                for name in self.app_config:
                    if module_name == self.app_config[name]["module"]:
                        class_name = self.app_config[name]["class"]

                        self.init_object(name, class_name, module_name, self.app_config)

        except:
            self.err( "WARNING", '-' * 60)
            self.err("WARNING", "Unexpected error during loading of {}:".format(name))
            self.err( "WARNING", '-' * 60)
            self.err( "WARNING", traceback.format_exc())
            self.err("WARNING", '-' * 60)
            if self.errfile != "STDERR" and self.logfile != "STDOUT":
                self.log("WARNING", "Logged an error to {}".format(self.errfile))

    def get_module_dependencies(self, file):
        module_name = self.get_module_from_path(file)
        if self.app_config is not None:
            for key in self.app_config:
                if "module" in self.app_config[key] and self.app_config[key]["module"] == module_name:
                    if "dependencies" in self.app_config[key]:
                        return self.app_config[key]["dependencies"].split(",")
                    else:
                        return None

        return None

    def in_previous_dependencies(self, dependencies, load_order):
        for dependency in dependencies:
            dependency_found = False
            for batch in load_order:
                for mod in batch:
                    module_name = self.get_module_from_path(mod["name"])
                    # print(dependency, module_name)
                    if dependency == module_name:
                        # print("found {}".format(module_name))
                        dependency_found = True
            if not dependency_found:
                return False

        return True

    def dependencies_are_satisfied(self, _module, load_order):
        dependencies = self.get_module_dependencies(_module)

        if dependencies is None:
            return None

        if self.in_previous_dependencies(dependencies, load_order):
            return True

        return False

    @staticmethod
    def get_module_from_path(path):
        name = os.path.basename(path)
        module_name = os.path.splitext(name)[0]
        return module_name

    def find_dependent_modules(self, mod):
        module_name = self.get_module_from_path(mod["name"])
        dependents = []
        if self.app_config is not None:
            for mod in self.app_config:
                if "dependencies" in self.app_config[mod]:
                    for dep in self.app_config[mod]["dependencies"].split(","):
                        if dep == module_name:
                            dependents.append(self.app_config[mod]["module"])
        return dependents

    def get_file_from_module(self, mod):
        for file in self.monitored_files:
            module_name = self.get_module_from_path(file)
            if module_name == mod:
                return file

        return None

    @staticmethod
    def file_in_modules(file, modules):
        for mod in modules:
            if mod["name"] == file:
                return True
        return False

    def get_app_priority(self, file):
        # Set to highest priority
        prio = sys.float_info.max
        mod = self.get_module_from_path(file)
        for name in self.app_config:
            if "module" in self.app_config[name] and self.app_config[name]["module"] == mod:
                if "priority" in self.app_config[name]:
                    modprio = float(self.app_config[name]["priority"])
                    # if any apps have this file at a lower priority set it accordingly
                    if modprio < prio:
                        prio = modprio

        # If priority is still at 100, this app has no priority so set it to the middle
        if prio == sys.float_info.max:
            prio = float(50.0)

        return prio

    # noinspection PyBroadException
    def read_apps(self, all_=False):
        # Check if the apps are disabled in config
        if not self.apps:
            return

        found_files = []
        modules = []
        for root, subdirs, files in os.walk(self.app_dir, topdown=True):
            #print(root, subdirs, files)
            #
            # Prune dir list
            #
            subdirs[:] = [d for d in subdirs if d not in self.exclude_dirs]

            for file in files:
                if file[-3:] == ".py":
                    found_files.append(os.path.join(root, file))

        for file in found_files:
            if file == os.path.join(self.app_dir, "__init__.py"):
                continue
            try:

                #check we can actually open the file the first time
                if all_ is True:
                    fh = open(file)
                    fh.close()

                modified = os.path.getmtime(file)
                if file in self.monitored_files:
                    if self.monitored_files[file] < modified or all_:
                        # read_app(file, True)
                        thismod = {"name": file, "reload": True, "load": True}
                        modules.append(thismod)
                        self.monitored_files[file] = modified
                else:
                    # read_app(file)
                    modules.append({"name": file, "reload": False, "load": True})
                    self.monitored_files[file] = modified
            except IOError as err:
                self.log("WARNING",
                         "Unable to read app {}: {} - skipping".format(file, err))

        # Add any required dependent files to the list
        if modules:
            more_modules = True
            while more_modules:
                module_list = modules.copy()
                for mod in module_list:
                    dependent_modules = self.find_dependent_modules(mod)
                    if not dependent_modules:
                        more_modules = False
                    else:
                        for thismod in dependent_modules:
                            file = self.get_file_from_module(thismod)
                            if file is None:
                                self.log( "ERROR",
                                          "Unable to resolve dependencies due to incorrect references")
                                self.log("ERROR", "The following modules have unresolved dependencies:")
                                self.log("ERROR", self.get_module_from_path(mod["file"]))
                                raise ValueError("Unresolved dependencies")

                            mod_def = {"name": file, "reload": True, "load": True}
                            if not self.file_in_modules(file, modules):
                                # Give each dependency tree module an incremented priority to maintain order for later sort
                                # This will break if anyone has more than 99,999,999 apps that depend on other apps :(
                                # print("Appending {} ({})".format(mod, file))
                                modules.append(mod_def)

        # Loading order algorithm requires full population of modules
        # so we will add in any missing modules but mark them for not loading

        for file in self.monitored_files:
            if not self.file_in_modules(file, modules):
                name = self.get_module_from_path(file)
                modules.append({"name": file, "reload": False, "load": False, "priority": self.get_app_priority(file)})

        # Figure out loading order

        # for mod in modules:
        #  print(mod["name"], mod["load"])

        depends_load_order = []

        prio = float(50.1)
        while modules:
            batch = []
            module_list = modules.copy()
            for mod in module_list:
                if self.dependencies_are_satisfied(mod["name"], depends_load_order) is True:
                    prio += float(0.0001)
                    mod ["priority"] = prio
                    batch.append(mod)
                    modules.remove(mod)
                elif self.dependencies_are_satisfied(mod["name"], depends_load_order) is None:
                    mod["priority"] = self.get_app_priority(mod["name"])
                    batch.append(mod)
                    modules.remove(mod)

            if not batch:
                self.log("ERROR",
                          "Unable to resolve dependencies due to incorrect or circular references")
                self.log("ERROR", "The following modules have unresolved dependencies:")
                for mod in modules:
                    module_name = self.get_module_from_path(mod["name"])
                    self.log("ERROR", module_name)
                raise ValueError("Unresolved dependencies")

            depends_load_order.append(batch)

        final_load_order = []

        for batch in depends_load_order:
            for mod in batch:
                final_load_order.append(mod)

        final_load_order.sort(key = lambda mod: mod["priority"])

        try:
            for mod in final_load_order:
                if mod["load"]:
                    self.read_app(mod["name"], mod["reload"])

        except:
            self.log("WARNING", '-' * 60)
            self.log("WARNING", "Unexpected error loading file")
            self.log("WARNING", '-' * 60)
            self.log("WARNING", traceback.format_exc())
            self.log("WARNING", '-' * 60)

    #
    # State Updates
    #

    def check_and_disapatch(self, name, funcref, entity, attribute, new_state,
                            old_state, cold, cnew, kwargs):
        if attribute == "all":
            self.dispatch_worker(name, {
                "name": name,
                "id": self.objects[name]["id"],
                "type": "attr",
                "function": funcref,
                "attribute": attribute,
                "entity": entity,
                "new_state": new_state,
                "old_state": old_state,
                "kwargs": kwargs
            })
        else:
            if old_state is None:
                old = None
            else:
                if attribute in old_state:
                    old = old_state[attribute]
                elif 'attributes' in old_state and attribute in old_state['attributes']:
                    old = old_state['attributes'][attribute]
                else:
                    old = None
            if new_state is None:
                new = None
            else:
                if attribute in new_state:
                    new = new_state[attribute]
                elif 'attributes' in new_state and attribute in new_state['attributes']:
                    new = new_state['attributes'][attribute]
                else:
                    new = None

            if (cold is None or cold == old) and (cnew is None or cnew == new):
                if "duration" in kwargs:
                    # Set a timer
                    exec_time = self.get_now_ts() + int(kwargs["duration"])
                    kwargs["handle"] = self.insert_schedule(
                        name, exec_time, funcref, False, None,
                        entity=entity,
                        attribute=attribute,
                        old_state=old,
                        new_state=new, **kwargs
                    )
                # Do it now
                self.dispatch_worker(name, {
                    "name": name,
                    "id": self.objects[name]["id"],
                    "type": "attr",
                    "function": funcref,
                    "attribute": attribute,
                    "entity": entity,
                    "new_state": new,
                    "old_state": old,
                    "kwargs": kwargs
                })
            else:
                if "handle" in kwargs:
                    # cancel timer
                    self.cancel_timer(name, kwargs["handle"])

    def process_state_change(self, namespace, state):
        data = state["data"]
        entity_id = data['entity_id']
        self.log("DEBUG", data)
        device, entity = entity_id.split(".")

        # Process state callbacks

        with self.callbacks_lock:
            for name in self.callbacks.keys():
                for uuid_ in self.callbacks[name]:
                    callback = self.callbacks[name][uuid_]
                    if callback["type"] == "state" and (callback["namespace"] == namespace or callback["namespace"] == "global" or namespace == "global"):
                        cdevice = None
                        centity = None
                        if callback["entity"] is not None:
                            if "." not in callback["entity"]:
                                cdevice = callback["entity"]
                                centity = None
                            else:
                                cdevice, centity = callback["entity"].split(".")
                        if callback["kwargs"].get("attribute") is None:
                            cattribute = "state"
                        else:
                            cattribute = callback["kwargs"].get("attribute")

                        cold = callback["kwargs"].get("old")
                        cnew = callback["kwargs"].get("new")

                        if cdevice is None:
                            self.check_and_disapatch(
                                name, callback["function"], entity_id,
                                cattribute,
                                data['new_state'],
                                data['old_state'],
                                cold, cnew,
                                callback["kwargs"]
                            )
                        elif centity is None:
                            if device == cdevice:
                                self.check_and_disapatch(
                                    name, callback["function"], entity_id,
                                    cattribute,
                                    data['new_state'],
                                    data['old_state'],
                                    cold, cnew,
                                    callback["kwargs"]
                                )
                        elif device == cdevice and entity == centity:
                            self.check_and_disapatch(
                                name, callback["function"], entity_id,
                                cattribute,
                                data['new_state'],
                                data['old_state'], cold,
                                cnew,
                                callback["kwargs"]
                            )

    def state_update(self, namespace, data):
        try:
            self.log(
                "DEBUG",
                "Event type:{}:".format(data['event_type'])
            )
            self.log( "DEBUG", data["data"])

            if data['event_type'] == "state_changed":
                entity_id = data['data']['entity_id']

                # First update our global state
                with self.state_lock:
                    self.state[namespace][entity_id] = data['data']['new_state']

            if self.apps is True:
                # Process state changed message
                if data['event_type'] == "state_changed":
                    self.process_state_change(namespace, data)
                else:
                    # Process non-state callbacks
                    self.process_event(namespace, data)

            # Update dashboards

            if self.dashboard is not None:
                self.dashboard.ws_update(namespace, data)

        except:
            self.err("WARNING", '-' * 60)
            self.err("WARNING", "Unexpected error during state_update()")
            self.err("WARNING", '-' * 60)
            self.err("WARNING", traceback.format_exc())
            self.err("WARNING", '-' * 60)
            if self.errfile != "STDERR" and self.logfile != "STDOUT":
                self.log("WARNING", "Logged an error to {}".format(self.errfile))


    #
    # Event Update
    #

    def process_event(self, namespace, data):
        with self.callbacks_lock:
            for name in self.callbacks.keys():
                for uuid_ in self.callbacks[name]:
                    callback = self.callbacks[name][uuid_]
                    if callback["namespace"] == namespace or callback["namespace"] == "global" or namespace == "global":
                        if "event" in callback and (
                                        callback["event"] is None
                                or data['event_type'] == callback["event"]):
                            # Check any filters
                            _run = True
                            for key in callback["kwargs"]:
                                if key in data["data"] and callback["kwargs"][key] != \
                                        data["data"][key]:
                                    _run = False
                            if _run:
                                self.dispatch_worker(name, {
                                    "name": name,
                                    "id": self.objects[name]["id"],
                                    "type": "event",
                                    "event": data['event_type'],
                                    "function": callback["function"],
                                    "data": data["data"],
                                    "kwargs": callback["kwargs"]
                                })

    #
    # Plugin Management
    #

    def get_plugin(self, name):
        if name in self.plugin_objs:
            return self.plugin_objs[name]
        else:
            return None

    def get_plugin_meta(self, namespace):
        for name in self.plugins:
            if "namespace" not in self.plugins[name] and namespace == "default":
                return self.plugin_meta[namespace]
            elif "namespace" in self.plugins[name] and self.plugins[name]["namespace"] == namespace:
                return self.plugin_meta[namespace]
            else:
                return None


    #
    # Utilities
    #

    def sanitize_state_kwargs(self, app, kwargs):
        kwargs_copy = kwargs.copy()
        return self._sanitize_kwargs(kwargs_copy, [
            "old", "new", "attribute", "duration", "state",
            "entity", "handle", "old_state", "new_state",
        ] + app.list_constraints())

    def sanitize_timer_kwargs(self, app, kwargs):
        kwargs_copy = kwargs.copy()
        return self._sanitize_kwargs(kwargs_copy, [
            "interval", "constrain_days", "constrain_input_boolean",
        ] + app.list_constraints())

    def _sanitize_kwargs(self, kwargs, keys):
        for key in keys:
            if key in kwargs:
                del kwargs[key]
        return kwargs

    def log(self, level, message, name="AppDaemon"):
        if not self.realtime:
            ts = self.get_now()
        else:
            ts = None
        utils.log(self.logger, level, message, name, ts)

    def err(self, level, message, name="AppDaemon"):
        if not self.realtime:
            ts = self.get_now()
        else:
            ts = None
        utils.log(self.error, level, message, name, ts)

    def register_dashboard(self, dash):
        self.dashboard = dash

    async def dispatch_app_by_name(self, name, args):
        with self.endpoints_lock:
            callback = None
            for app in self.endpoints:
                for handle in self.endpoints[app]:
                    if self.endpoints[app][handle]["name"] == name:
                        callback = self.endpoints[app][handle]["callback"]
        if callback is not None:
            return await utils.run_in_executor(self.loop, self.executor, callback, args)
        else:
            return '', 404

