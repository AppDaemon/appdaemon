#!/usr/bin/python3
import sys
import importlib
import traceback
import configparser
import os
import os.path
from queue import Queue
import time
import datetime
import uuid
import astral
import pytz
import math
import appdaemon.rundash as appdash
import asyncio
import yaml
import concurrent
import threading

import appdaemon.utils as utils
import appdaemon.appapi as appapi


class AppDaemon:

    def __init__(self, logger, error, **kwargs):

        self.logger = logger
        self.error = error

        self.q = Queue(maxsize=0)

        self.was_dst = False

        self.last_state = None
        #appapi.reading_messages = False
        self.inits = {}
        #ws = None

        self.monitored_files = {}
        self.modules = {}
        self.appq = None
        self.executor = None
        self.loop = None
        self.srv = None
        self.appd = None
        self.stopping = False

        # Will require object based locking if implemented
        self.objects = {}

        self.schedule = {}
        self.schedule_lock = threading.RLock()

        self.callbacks = {}
        self.callbacks_lock = threading.RLock()

        self.ha_state = {}
        self.ha_state_lock = threading.RLock()

        self.endpoints = {}
        self.endpoints_lock = threading.RLock()

        # No locking yet
        self.global_vars = {}

        self.sun = {}

        self.config_file_modified = 0
        self.tz = None
        self.ad_time_zone = None
        self.now = 0
        self.realtime = True
        self.version = 0
        self.config = None
        self.app_config_file_modified = 0
        self.app_config = None

        self.app_config_file = None
        self._process_arg("app_config_file", kwargs)

        # User Supplied/Defaults
        self.threads = 0
        self._process_arg("threads", kwargs)

        self.app_dir = None
        self._process_arg("app_dir", kwargs)

        self.apps = False
        self._process_arg("apps", kwargs)

        self.start_time = None
        self._process_arg("start_time", kwargs)

        self.logfile = None
        self._process_arg("logfile", kwargs)

        self.latitude = None
        self._process_arg("latitude", kwargs)

        self.longitude = None
        self._process_arg("longitude", kwargs)

        self.elevation = None
        self._process_arg("elevation", kwargs)

        self.time_zone = None
        self._process_arg("time_zone", kwargs)

        self.errorfile = None
        self._process_arg("error_file", kwargs)

        self.config_file = None
        self._process_arg("config_file", kwargs)

        self.location = None
        self._process_arg("location", kwargs)

        self.tick = 1
        self._process_arg("tick", kwargs)

        self.endtime = None
        self._process_arg("endtime", kwargs)

        self.interval = 1
        self._process_arg("interval", kwargs)

        self.loglevel = "INFO"
        self._process_arg("loglevel", kwargs)

        self.config_dir = None
        self._process_arg("config_dir", kwargs)

        self.api_port = None
        self._process_arg("api_port", kwargs)

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

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
                    now + datetime.timedelta(days=mod), local=False
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
                    now + datetime.timedelta(days=mod), local=False
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

    def is_dst(self):
        return bool(time.localtime(self.get_now_ts()).tm_isdst)

    def stopit(self):
        global ws
        self.stopping = True
        if ws is not None:
            ws.close()
        self.appq.put_nowait({"event_type": "ha_stop", "data": None})

    def get_now(self):
        return datetime.datetime.fromtimestamp(self.now)

    def get_now_ts(self):
        return self.now

    def dump_sun(self):
        utils.log(self.logger, "INFO", "--------------------------------------------------")
        utils.log(self.logger, "INFO", "Sun")
        utils.log(self.logger, "INFO", "--------------------------------------------------")
        utils.log(self.logger, "INFO", self.sun)
        utils.log(self.logger, "INFO", "--------------------------------------------------")

    def dump_schedule(self):
        if self.schedule == {}:
            utils.log(self.logger, "INFO", "Schedule is empty")
        else:
            utils.log(self.logger, "INFO", "--------------------------------------------------")
            utils.log(self.logger, "INFO", "Scheduler Table")
            utils.log(self.logger, "INFO", "--------------------------------------------------")
            for name in self.schedule.keys():
                utils.log(self.logger, "INFO", "{}:".format(name))
                for entry in sorted(
                        self.schedule[name].keys(),
                        key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
                ):
                    utils.log(
                        self.logger, "INFO",
                        "  Timestamp: {} - data: {}".format(
                            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(
                                self.schedule[name][entry]["timestamp"]
                            )),
                            self.schedule[name][entry]
                        )
                    )
            utils.log(self.logger, "INFO", "--------------------------------------------------")


    def dump_callbacks(self):
        if self.callbacks == {}:
            utils.log(self.logger, "INFO", "No callbacks")
        else:
            utils.log(self.logger, "INFO", "--------------------------------------------------")
            utils.log(self.logger, "INFO", "Callbacks")
            utils.log(self.logger, "INFO", "--------------------------------------------------")
            for name in self.callbacks.keys():
                utils.log(self.logger, "INFO", "{}:".format(name))
                for uuid_ in self.callbacks[name]:
                    utils.log(self.logger, "INFO", "  {} = {}".format(uuid_, self.callbacks[name][uuid_]))
            utils.log(self.logger, "INFO", "--------------------------------------------------")


    def dump_objects(self):
        utils.log(self.logger, "INFO", "--------------------------------------------------")
        utils.log(self.logger, "INFO", "Objects")
        utils.log(self.logger, "INFO", "--------------------------------------------------")
        for object_ in self.objects.keys():
            utils.log(self.logger, "INFO", "{}: {}".format(object_, self.objects[object_]))
        utils.log(self.logger, "INFO", "--------------------------------------------------")


    def dump_queue(self):
        utils.log(self.logger, "INFO", "--------------------------------------------------")
        utils.log(self.logger, "INFO", "Current Queue Size is {}".format(self.q.qsize()))
        utils.log(self.logger, "INFO", "--------------------------------------------------")


    #TODO: Pull this into the API
    def check_constraint(self, key, value):
        unconstrained = True
        with self.ha_state_lock:
            if key == "constrain_input_boolean":
                values = value.split(",")
                if len(values) == 2:
                    entity = values[0]
                    state = values[1]
                else:
                    entity = value
                    state = "on"
                if entity in self.ha_state and self.ha_state[entity]["state"] != state:
                    unconstrained = False
            if key == "constrain_input_select":
                values = value.split(",")
                entity = values.pop(0)
                if entity in self.ha_state and self.ha_state[entity]["state"] not in values:
                    unconstrained = False
            if key == "constrain_presence":
                if value == "everyone" and not utils.everyone_home():
                    unconstrained = False
                elif value == "anyone" and not utils.anyone_home():
                    unconstrained = False
                elif value == "noone" and not utils.noone_home():
                    unconstrained = False
            if key == "constrain_days":
                if self.today_is_constrained(value):
                    unconstrained = False

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
            if not utils.now_is_between(start_time, end_time, name):
                unconstrained = False

        return unconstrained


    def dispatch_worker(self, name, args):
        unconstrained = True
        #
        # Argument Constraints
        #
        for arg in self.app_config[name].keys():
            if not self.check_constraint(arg, self.app_config[name][arg]):
                unconstrained = False
        if not self.check_time_constraint(self.app_config[name], name):
            unconstrained = False
        #
        # Callback level constraints
        #
        if "kwargs" in args:
            for arg in args["kwargs"].keys():
                if not self.check_constraint(arg, args["kwargs"][arg]):
                    unconstrained = False
            if not self.check_time_constraint(args["kwargs"], name):
                unconstrained = False

        if unconstrained:
            self.q.put_nowait(args)

    def today_is_constrained(self, days):
        day = utils.get_now().weekday()
        daylist = [utils.day_of_week(day) for day in days.split(",")]
        if day in daylist:
            return False
        return True


    def process_sun(self, action):
        utils.log(
                self.logger, "DEBUG",
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
                        c_offset = utils.get_offset(schedule)
                        schedule["timestamp"] = utils.calc_sun(action) + c_offset
                        schedule["offset"] = c_offset


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
                        c_offset = utils.get_offset(args)
                        args["timestamp"] = utils.calc_sun(args["type"]) + c_offset
                        args["offset"] = c_offset
                else:
                    # Not sunrise or sunset so just increment
                    # the timestamp with the repeat interval
                    args["basetime"] += args["interval"]
                    args["timestamp"] = args["basetime"] + utils.get_offset(args)
            else:  # Otherwise just delete
                del self.schedule[name][entry]

        except:
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(
                self.error, "WARNING",
                "Unexpected error during exec_schedule() for App: {}".format(name)
            )
            utils.log(self.error, "WARNING", "Args: {}".format(args))
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", traceback.format_exc())
            utils.log(self.error, "WARNING", '-' * 60)
            if self.errorfile != "STDERR" and self.logfile != "STDOUT":
                # When explicitly logging to stdout and stderr, suppress
                # log messages about writing an error (since they show up anyway)
                utils.log(self.logger, "WARNING", "Logged an error to {}".format(self.errorfile))
            utils.log(self.error, "WARNING", "Scheduler entry has been deleted")
            utils.log(self.error, "WARNING", '-' * 60)

            del self.schedule[name][entry]

    @asyncio.coroutine
    def do_every(self, period, f):
        t = math.floor(utils.get_now_ts())
        count = 0
        t_ = math.floor(time.time())
        while not self.stopping:
            count += 1
            delay = max(t_ + count * period - time.time(), 0)
            yield from asyncio.sleep(delay)
            t += self.interval
            r = yield from f(t)
            if r is not None and r != t:
                #print("r: {}, t: {}".format(r,t))
                t = r
                t_ = r
                count = 0


    # noinspection PyBroadException,PyBroadException
    def do_every_second(self, utc):

        try:
            start_time = datetime.datetime.now().timestamp()
            now = datetime.datetime.fromtimestamp(utc)
            self.now = utc

            # If we have reached endtime bail out

            if self.endtime is not None and utils.get_now() >= self.endtime:
                utils.log(self.logger, "INFO", "End time reached, exiting")
                self.stopit()

            if self.realtime:
                real_now = datetime.datetime.now().timestamp()
                delta = abs(utc - real_now)
                if delta > 1:
                    utils.log(self.logger, "WARNING", "Scheduler clock skew detected - delta = {} - resetting".format(delta))
                    return real_now

            # Update sunrise/sunset etc.

            self.update_sun()

            # Check if we have entered or exited DST - if so, reload apps
            # to ensure all time callbacks are recalculated

            now_dst = self.is_dst()
            if now_dst != self.was_dst:
                utils.log(
                    self.logger, "INFO",
                    "Detected change in DST from {} to {} -"
                    " reloading all modules".format(self.was_dst, now_dst)
                )
                # dump_schedule()
                utils.log(self.logger, "INFO", "-" * 40)
                yield from utils.run_in_executor(self.loop, self.executor, self.read_apps, True)
                # dump_schedule()
            self.was_dst = now_dst

            # dump_schedule()

            # test code for clock skew
            #if random.randint(1, 10) == 5:
            #    time.sleep(random.randint(1,20))

            # Check to see if any apps have changed but only if we have valid state

            if self.last_state is not None and appapi.reading_messages:
                yield from utils.run_in_executor(self.loop, self.executor, self.read_apps)

            # Check to see if config has changed

            if appapi.reading_messages:
                yield from utils.run_in_executor(self.loop, self.executor, self.check_config)

            # Call me suspicious, but lets update state form HA periodically
            # in case we miss events for whatever reason
            # Every 10 minutes seems like a good place to start

            #if self.last_state is not None and appapi.reading_messages and now - self.last_state > datetime.timedelta(minutes=10) and self.ha_url is not None:
            #    try:
            #        yield from utils.run_in_executor(self.loop, self.executor, get_ha_state)
            #        self.last_state = now
            #    except:
            #        utils.log(self.logger, "WARNING", "Unexpected error refreshing HA state - retrying in 10 minutes")

            # Check on Queue size

            qsize = self.q.qsize()
            if qsize > 0 and qsize % 10 == 0:
                self.logger.warning("Queue size is {}, suspect thread starvation".format(self.q.qsize()))

            # Process callbacks

            # utils.log(self.logger, "DEBUG", "Scheduler invoked at {}".format(now))
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

            loop_duration = (int((end_time - start_time)*1000) / 1000) * 1000
            utils.log(self.logger, "DEBUG", "Main loop compute time: {}ms".format(loop_duration))

            if loop_duration > 900:
                utils.log(self.logger, "WARNING", "Excessive time spent in scheduler loop: {}ms".format(loop_duration))

            return utc

        except:
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", "Unexpected error during do_every_second()")
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", traceback.format_exc())
            utils.log(self.error, "WARNING", '-' * 60)
            if self.errorfile != "STDERR" and self.logfile != "STDOUT":
                # When explicitly logging to stdout and stderr, suppress
                # log messages about writing an error (since they show up anyway)
                utils.log(
                    self.logger, "WARNING",
                    "Logged an error to {}".format(self.errorfile)
                )

    # noinspection PyBroadException
    def worker(self):
        while True:
            args = self.q.get()
            _type = args["type"]
            function = args["function"]
            _id = args["id"]
            name = args["name"]
            if name in self.objects and self.objects[name]["id"] == _id:
                try:
                    if _type == "initialize":
                        utils.log(self.logger, "DEBUG", "Calling initialize() for {}".format(name))
                        function()
                        utils.log(self.logger, "DEBUG", "{} initialize() done".format(name))
                    elif _type == "timer":
                        function(utils.sanitize_timer_kwargs(args["kwargs"]))
                    elif _type == "attr":
                        entity = args["entity"]
                        attr = args["attribute"]
                        old_state = args["old_state"]
                        new_state = args["new_state"]
                        function(entity, attr, old_state, new_state,
                                 utils.sanitize_state_kwargs(args["kwargs"]))
                    elif _type == "event":
                        data = args["data"]
                        function(args["event"], data, args["kwargs"])

                except:
                    utils.log(self.error, "WARNING", '-' * 60)
                    utils.log(self.error, "WARNING", "Unexpected error in worker for App {}:".format(name))
                    utils.log(self.error, "WARNING", "Worker Ags: {}".format(args))
                    utils.log(self.error, "WARNING", '-' * 60)
                    utils.log(self.error, "WARNING", traceback.format_exc())
                    utils.log(self.error, "WARNING", '-' * 60)
                    if self.errorfile != "STDERR" and self.logfile != "STDOUT":
                        utils.log(self.logger, "WARNING", "Logged an error to {}".format(self.errorfile))
            else:
                self.logger.warning("Found stale callback for {} - discarding".format(name))

            if self.inits.get(name):
                self.inits.pop(name)

            self.q.task_done()


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
        utils.log(self.logger, "DEBUG", "Clearing callbacks for {}".format(object_))
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
            utils.log(self.logger, "INFO", "Terminating Object {}".format(name))
            # Call terminate directly rather than via worker thread
            # so we know terminate has completed before we move on
            self.objects[name]["object"].terminate()


    def init_object(self, name, class_name, module_name, args):
        utils.log(self.logger, "INFO", "Loading Object {} using class {} from module {}".format(name, class_name, module_name))
        module = __import__(module_name)
        app_class = getattr(module, class_name)
        self.objects[name] = {
            "object": app_class(
                name, self.logger, self.error, args, self.global_vars
            ),
            "id": uuid.uuid4()
        }

        # Call it's initialize function

        self.objects[name]["object"].initialize()

        # with self.threads_busy_lock:
        #     inits[name] = 1
        #     self.threads_busy += 1
        #     q.put_nowait({
        #         "type": "initialize",
        #         "name": name,
        #         "id": self.objects[name]["id"],
        #         "function": self.objects[name]["object"].initialize
        #     })


    def check_and_disapatch(self, name, function, entity, attribute, new_state,
                            old_state, cold, cnew, kwargs):
        if attribute == "all":
            self.dispatch_worker(name, {
                "name": name,
                "id": self.objects[name]["id"],
                "type": "attr",
                "function": function,
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
                elif attribute in old_state['attributes']:
                    old = old_state['attributes'][attribute]
                else:
                    old = None
            if new_state is None:
                new = None
            else:
                if attribute in 'new_state':
                    new = new_state[attribute]
                elif attribute in new_state['attributes']:
                    new = new_state['attributes'][attribute]
                else:
                    new = None

            if (cold is None or cold == old) and (cnew is None or cnew == new):
                if "duration" in kwargs:
                    # Set a timer
                    exec_time = utils.get_now_ts() + int(kwargs["duration"])
                    kwargs["handle"] = utils.insert_schedule(
                        name, exec_time, function, False, None,
                        entity=entity,
                        attribute=attribute,
                        old_state=old,
                        new_state=new, **kwargs
                    )
                else:
                    # Do it now
                    self.dispatch_worker(name, {
                        "name": name,
                        "id": self.objects[name]["id"],
                        "type": "attr",
                        "function": function,
                        "attribute": attribute,
                        "entity": entity,
                        "new_state": new,
                        "old_state": old,
                        "kwargs": kwargs
                    })
            else:
                if "handle" in kwargs:
                    # cancel timer
                    utils.cancel_timer(name, kwargs["handle"])

    def process_state_change(self, data):
        entity_id = data['data']['entity_id']
        utils.log(self.logger, "DEBUG", "Entity ID:{}:".format(entity_id))
        device, entity = entity_id.split(".")

        # Process state callbacks

        with self.callbacks_lock:
            for name in self.callbacks.keys():
                for uuid_ in self.callbacks[name]:
                    callback = self.callbacks[name][uuid_]
                    if callback["type"] == "state":
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
                                data['data']['new_state'],
                                data['data']['old_state'],
                                cold, cnew,
                                callback["kwargs"]
                            )
                        elif centity is None:
                            if device == cdevice:
                                self.check_and_disapatch(
                                    name, callback["function"], entity_id,
                                    cattribute,
                                    data['data']['new_state'],
                                    data['data']['old_state'],
                                    cold, cnew,
                                    callback["kwargs"]
                                )
                        elif device == cdevice and entity == centity:
                            self.check_and_disapatch(
                                name, callback["function"], entity_id,
                                cattribute,
                                data['data']['new_state'],
                                data['data']['old_state'], cold,
                                cnew,
                                callback["kwargs"]
                            )

    def process_event(self,data):
        with self.callbacks_lock:
            for name in self.callbacks.keys():
                for uuid_ in self.callbacks[name]:
                    callback = self.callbacks[name][uuid_]
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


    # noinspection PyBroadException
    def process_message(self, data):
        try:
            utils.log(
                self.logger, "DEBUG",
                "Event type:{}:".format(data['event_type'])
            )
            utils.log(self.logger, "DEBUG", data["data"])

            if data['event_type'] == "state_changed":
                entity_id = data['data']['entity_id']

                # First update our global state
                with self.ha_state_lock:
                    self.ha_state[entity_id] = data['data']['new_state']

            if self.apps is True:
                # Process state changed message
                if data['event_type'] == "state_changed":
                    self.process_state_change(data)

                # Process non-state callbacks
                    self.process_event(data)

            # Update dashboards

            if self.dashboard is True:
                appdash.ws_update(data)

        except:
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", "Unexpected error during process_message()")
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", traceback.format_exc())
            utils.log(self.error, "WARNING", '-' * 60)
            if self.errorfile != "STDERR" and self.logfile != "STDOUT":
                utils.log(self.logger, "WARNING", "Logged an error to {}".format(self.errorfile))

    def read_config(self):
        root, ext = os.path.splitext(self.app_config_file)
        if ext == ".yaml":
            with open(self.app_config_file, 'r') as yamlfd:
                config_file_contents = yamlfd.read()
            try:
                new_config = yaml.load(config_file_contents)
            except yaml.YAMLError as exc:
                utils.log(self.logger, "WARNING", "Error loading configuration")
                if hasattr(exc, 'problem_mark'):
                    if exc.context is not None:
                        utils.log(self.error, "WARNING", "parser says")
                        utils.log(self.error, "WARNING", str(exc.problem_mark))
                        utils.log(self.error, "WARNING", str(exc.problem) + " " + str(exc.context))
                    else:
                        utils.log(self.error, "WARNING", "parser says")
                        utils.log(self.error, "WARNING", str(exc.problem_mark))
                        utils.log(self.error, "WARNING", str(exc.problem))
        else:
            new_config = configparser.ConfigParser()
            new_config.read_file(open(self.app_config_file))

        return new_config

# noinspection PyBroadException
    def check_config(self):

        new_config = None
        try:
            modified = os.path.getmtime(self.app_config_file)
            if modified > self.app_config_file_modified:
                utils.log(self.logger, "INFO", "{} modified".format(self.app_config_file))
                self.app_config_file_modified = modified
                new_config = self.read_config()

                if new_config is None:
                    utils.log(self.error, "WARNING", "New config not applied")
                    return


                # Check for changes

                for name in self.app_config:
                    if name == "DEFAULT" or name == "AppDaemon" or name == "HADashboard":
                        continue
                    if name in new_config:
                        if self.app_config[name] != new_config[name]:
                            # Something changed, clear and reload

                            utils.log(self.logger, "INFO", "App '{}' changed - reloading".format(name))
                            self.term_object(name)
                            self.clear_object(name)
                            self.init_object(
                                name, new_config[name]["class"],
                                new_config[name]["module"], new_config[name]
                            )
                    else:

                        # Section has been deleted, clear it out

                        utils.log(self.logger, "INFO", "App '{}' deleted - removing".format(name))
                        self.clear_object(name)

                for name in new_config:
                    if name == "DEFAULT" or name == "AppDaemon":
                        continue
                    if name not in self.app_config:
                        #
                        # New section added!
                        #
                        utils.log(self.logger, "INFO", "App '{}' added - running".format(name))
                        self.init_object(
                            name, new_config[name]["class"],
                            new_config[name]["module"], new_config[name]
                        )

                self.app_config = new_config
        except:
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", "Unexpected error:")
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", traceback.format_exc())
            utils.log(self.error, "WARNING", '-' * 60)
            if self.errorfile != "STDERR" and self.logfile != "STDOUT":
                utils.log(self.logger, "WARNING", "Logged an error to {}".format(self.errorfile))


    # noinspection PyBroadException
    def read_app(self, file, reload=False):
        name = os.path.basename(file)
        module_name = os.path.splitext(name)[0]
        # Import the App
        try:
            if reload:
                utils.log(self.logger, "INFO", "Reloading Module: {}".format(file))

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
                utils.log(self.logger, "INFO", "Loading Module: {}".format(file))
                self.modules[module_name] = importlib.import_module(module_name)

            # Instantiate class and Run initialize() function

            if self.app_config is not None:
                for name in self.app_config:
                    if name == "DEFAULT" or name == "AppDaemon" or name == "HASS" or name == "HADashboard":
                        continue
                    if module_name == self.app_config[name]["module"]:
                        class_name = self.app_config[name]["class"]

                        self.init_object(name, class_name, module_name, self.app_config[name])

        except:
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", "Unexpected error during loading of {}:".format(name))
            utils.log(self.error, "WARNING", '-' * 60)
            utils.log(self.error, "WARNING", traceback.format_exc())
            utils.log(self.error, "WARNING", '-' * 60)
            if self.errorfile != "STDERR" and self.logfile != "STDOUT":
                utils.log(self.logger, "WARNING", "Logged an error to {}".format(self.errorfile))

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
                for module in batch:
                    module_name = self.get_module_from_path(module["name"])
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
            return True

        if self.in_previous_dependencies(dependencies, load_order):
            return True

        return False


    def get_module_from_path(self, path):
        name = os.path.basename(path)
        module_name = os.path.splitext(name)[0]
        return module_name


    def find_dependent_modules(self, module):
        module_name = self.get_module_from_path(module["name"])
        dependents = []
        if self.app_config is not None:
            for mod in self.app_config:
                if "dependencies" in self.app_config[mod]:
                    for dep in self.app_config[mod]["dependencies"].split(","):
                        if dep == module_name:
                            dependents.append(self.app_config[mod]["module"])
        return dependents


    def get_file_from_module(self, module):
        for file in self.monitored_files:
            module_name = self.get_module_from_path(file)
            if module_name == module:
                return file

        return None

    def file_in_modules(self, file, modules):
        for mod in modules:
            if mod["name"] == file:
                return True
        return False


    # noinspection PyBroadException
    def read_apps(self, all_=False):
        # Check if the apps are disabled in config
        if not self.apps:
            return

        found_files = []
        modules = []
        for root, subdirs, files in os.walk(self.app_dir):
            if root[-11:] != "__pycache__":
                for file in files:
                    if file[-3:] == ".py":
                        found_files.append(os.path.join(root, file))
        for file in found_files:
            if file == os.path.join(self.app_dir, "__init__.py"):
                continue
            if file == os.path.join(self.app_dir, "__pycache__"):
                continue
            modified = os.path.getmtime(file)
            if file in self.monitored_files:
                if self.monitored_files[file] < modified or all_:
                    # read_app(file, True)
                    module = {"name": file, "reload": True, "load": True}
                    modules.append(module)
                    self.monitored_files[file] = modified
            else:
                # read_app(file)
                modules.append({"name": file, "reload": False, "load": True})
                self.monitored_files[file] = modified

        # Add any required dependent files to the list

        if modules:
            more_modules = True
            while more_modules:
                module_list = modules.copy()
                for module in module_list:
                    dependent_modules = self.find_dependent_modules(module)
                    if not dependent_modules:
                        more_modules = False
                    else:
                        for mod in dependent_modules:
                            file = self.get_file_from_module(mod)

                            if file is None:
                                utils.log(self.logger, "ERROR", "Unable to resolve dependencies due to incorrect references")
                                utils.log(self.logger, "ERROR", "The following modules have unresolved dependencies:")
                                utils.log(self.logger, "ERROR",  self.get_module_from_path(module["file"]))
                                raise ValueError("Unresolved dependencies")

                            mod_def = {"name": file, "reload": True, "load": True}
                            if not self.file_in_modules(file, modules):
                                # print("Appending {} ({})".format(mod, file))
                                modules.append(mod_def)

        # Loading order algorithm requires full population of modules
        # so we will add in any missing modules but mark them for not loading

        for file in self.monitored_files:
            if not self.file_in_modules(file, modules):
                modules.append({"name": file, "reload": False, "load": False})

        # Figure out loading order

        # for mod in modules:
        #  print(mod["name"], mod["load"])

        load_order = []

        while modules:
            batch = []
            module_list = modules.copy()
            for module in module_list:
                # print(module)
                if self.dependencies_are_satisfied(module["name"], load_order):
                    batch.append(module)
                    modules.remove(module)

            if not batch:
                utils.log(self.logger, "ERROR",  "Unable to resolve dependencies due to incorrect or circular references")
                utils.log(self.logger, "ERROR",  "The following modules have unresolved dependencies:")
                for module in modules:
                    module_name = self.get_module_from_path(module["name"])
                    utils.log(self.logger, "ERROR", module_name)
                raise ValueError("Unresolved dependencies")

            load_order.append(batch)

        try:
            for batch in load_order:
                for module in batch:
                    if module["load"]:
                        self.read_app(module["name"], module["reload"])

        except:
            utils.log(self.logger, "WARNING", '-' * 60)
            utils.log(self.logger, "WARNING", "Unexpected error loading file")
            utils.log(self.logger, "WARNING", '-' * 60)
            utils.log(self.logger, "WARNING", traceback.format_exc())
            utils.log(self.logger, "WARNING", '-' * 60)

    def run_ad(self, loop, tasks):
        self.appq = asyncio.Queue(maxsize=0)

        self.loop = loop

        first_time = True

        self.stopping = False

        utils.log(self.logger, "DEBUG", "Entering run()")

        self.init_sun()

        # Load App Config

        self.app_config = self.read_config()

        # Save start time

        self.start_time = datetime.datetime.now()

        # Take a note of DST

        self.was_dst = self.is_dst()

        # Setup sun

        self.update_sun()

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

        utils.log(self.logger, "DEBUG", "Creating worker threads ...")

        # Create Worker Threads
        for i in range(self.threads):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()

        utils.log(self.logger, "DEBUG", "Done")


        """
        if self.ha_url is not None:
            # Read apps and get HA State before we start the timer thread
            utils.log(self.logger, "DEBUG", "Calling HA for initial state with key: {} and url: {}".format(self.ha_key, self.ha_url))
    
            while self.last_state is None:
                try:
                    get_ha_state()
                    self.last_state = utils.get_now()
                except:
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
                    time.sleep(5)
    
            utils.log(self.logger, "INFO", "Got initial state")
    
            # Initialize appdaemon loop
            tasks.append(asyncio.async(appdaemon_loop()))
    
        else:
           self.last_state = utils.get_now()
    
        # Load apps
    
        # Let other parts know we are in business,
        appapi.reading_messages = True
    
        """

        utils.log(self.logger, "DEBUG", "Reading Apps")

        self.read_apps(True)

        utils.log(self.logger, "INFO", "App initialization complete")

        # Create timer loop

        # First, update "now" for less chance of clock skew error
        if self.realtime:
            self.now = datetime.datetime.now().timestamp()

        utils.log(self.logger, "DEBUG", "Starting timer loop")

            #tasks.append(asyncio.async(self.appstate_loop()))

        tasks.append(asyncio.async(self.do_every(self.tick, self.do_every_second)))
