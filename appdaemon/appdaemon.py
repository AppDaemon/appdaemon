#!/usr/bin/python3
from pkg_resources import parse_version
import json
import sys
import importlib
import traceback
import configparser
import argparse
import logging
import os
import os.path
from websocket import create_connection
from logging.handlers import RotatingFileHandler
from queue import Queue
from sseclient import SSEClient
import threading
import appdaemon.conf as conf
import time
import datetime
import signal
import uuid
import astral
import pytz
import platform
import math
import appdaemon.appdash as appdash
import asyncio
import concurrent
from urllib.parse import urlparse
import yaml
import random

import appdaemon.homeassistant as ha
import appdaemon.appapi as appapi


# Windows does not have Daemonize package so disallow

if platform.system() != "Windows":
    from daemonize import Daemonize

q = Queue(maxsize=0)

config = None
config_file_modified = 0
config_file = ""
was_dst = None
last_state = None
appapi.reading_messages = False
inits = {}
ws = None


def init_sun():
    latitude = conf.latitude
    longitude = conf.longitude

    if -90 > latitude < 90:
        raise ValueError("Latitude needs to be -90 .. 90")

    if -180 > longitude < 180:
        raise ValueError("Longitude needs to be -180 .. 180")

    elevation = conf.elevation

    conf.tz = pytz.timezone(conf.time_zone)

    conf.location = astral.Location((
        '', '', latitude, longitude, conf.tz.zone, elevation
    ))


def update_sun():
    # now = datetime.datetime.now(conf.tz)
    now = conf.tz.localize(ha.get_now())
    mod = -1
    while True:
        try:
            next_rising_dt = conf.location.sunrise(
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
            next_setting_dt = conf.location.sunset(
                now + datetime.timedelta(days=mod), local=False
            )
            if next_setting_dt > now:
                break
        except astral.AstralError:
            pass
        mod += 1

    old_next_rising_dt = conf.sun.get("next_rising")
    old_next_setting_dt = conf.sun.get("next_setting")
    conf.sun["next_rising"] = next_rising_dt
    conf.sun["next_setting"] = next_setting_dt

    if old_next_rising_dt is not None and old_next_rising_dt != conf.sun["next_rising"]:
        # dump_schedule()
        process_sun("next_rising")
        # dump_schedule()
    if old_next_setting_dt is not None and old_next_setting_dt != conf.sun["next_setting"]:
        # dump_schedule()
        process_sun("next_setting")
        # dump_schedule()


def is_dst():
    return bool(time.localtime(ha.get_now_ts()).tm_isdst)

def stopit():
    global ws
    conf.stopping = True
    if ws is not None:
        ws.close()
    conf.appq.put_nowait({"event_type": "ha_stop", "data": None})

# noinspection PyUnusedLocal
def handle_sig(signum, frame):
    if signum == signal.SIGUSR1:
        dump_schedule()
        dump_callbacks()
        dump_objects()
        dump_queue()
        dump_sun()
    if signum == signal.SIGHUP:
        read_apps(True)
    if signum == signal.SIGINT:
        ha.log(conf.logger, "INFO", "Keyboard interrupt")
        stopit()

def dump_sun():
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    ha.log(conf.logger, "INFO", "Sun")
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    ha.log(conf.logger, "INFO", conf.sun)
    ha.log(conf.logger, "INFO", "--------------------------------------------------")


def dump_schedule():
    if conf.schedule == {}:
        ha.log(conf.logger, "INFO", "Schedule is empty")
    else:
        ha.log(conf.logger, "INFO", "--------------------------------------------------")
        ha.log(conf.logger, "INFO", "Scheduler Table")
        ha.log(conf.logger, "INFO", "--------------------------------------------------")
        for name in conf.schedule.keys():
            ha.log(conf.logger, "INFO", "{}:".format(name))
            for entry in sorted(
                    conf.schedule[name].keys(),
                    key=lambda uuid_: conf.schedule[name][uuid_]["timestamp"]
            ):
                ha.log(
                    conf.logger, "INFO",
                    "  Timestamp: {} - data: {}".format(
                        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(
                            conf.schedule[name][entry]["timestamp"]
                        )),
                        conf.schedule[name][entry]
                    )
                )
        ha.log(conf.logger, "INFO", "--------------------------------------------------")


def dump_callbacks():
    if conf.callbacks == {}:
        ha.log(conf.logger, "INFO", "No callbacks")
    else:
        ha.log(conf.logger, "INFO", "--------------------------------------------------")
        ha.log(conf.logger, "INFO", "Callbacks")
        ha.log(conf.logger, "INFO", "--------------------------------------------------")
        for name in conf.callbacks.keys():
            ha.log(conf.logger, "INFO", "{}:".format(name))
            for uuid_ in conf.callbacks[name]:
                ha.log(conf.logger, "INFO", "  {} = {}".format(uuid_, conf.callbacks[name][uuid_]))
        ha.log(conf.logger, "INFO", "--------------------------------------------------")


def dump_objects():
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    ha.log(conf.logger, "INFO", "Objects")
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    for object_ in conf.objects.keys():
        ha.log(conf.logger, "INFO", "{}: {}".format(object_, conf.objects[object_]))
    ha.log(conf.logger, "INFO", "--------------------------------------------------")


def dump_queue():
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    ha.log(conf.logger, "INFO", "Current Queue Size is {}".format(q.qsize()))
    ha.log(conf.logger, "INFO", "--------------------------------------------------")


def check_constraint(key, value):
    unconstrained = True
    with conf.ha_state_lock:
        if key == "constrain_input_boolean":
            values = value.split(",")
            if len(values) == 2:
                entity = values[0]
                state = values[1]
            else:
                entity = value
                state = "on"
            if entity in conf.ha_state and conf.ha_state[entity]["state"] != state:
                unconstrained = False
        if key == "constrain_input_select":
            values = value.split(",")
            entity = values.pop(0)
            if entity in conf.ha_state and conf.ha_state[entity]["state"] not in values:
                unconstrained = False
        if key == "constrain_presence":
            if value == "everyone" and not ha.everyone_home():
                unconstrained = False
            elif value == "anyone" and not ha.anyone_home():
                unconstrained = False
            elif value == "noone" and not ha.noone_home():
                unconstrained = False
        if key == "constrain_days":
            if today_is_constrained(value):
                unconstrained = False

    return unconstrained


def check_time_constraint(args, name):
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
        if not ha.now_is_between(start_time, end_time, name):
            unconstrained = False

    return unconstrained


def dispatch_worker(name, args):
    unconstrained = True
    #
    # Argument Constraints
    #
    for arg in config[name].keys():
        if not check_constraint(arg, config[name][arg]):
            unconstrained = False
    if not check_time_constraint(config[name], name):
        unconstrained = False
    #
    # Callback level constraints
    #
    if "kwargs" in args:
        for arg in args["kwargs"].keys():
            if not check_constraint(arg, args["kwargs"][arg]):
                unconstrained = False
        if not check_time_constraint(args["kwargs"], name):
            unconstrained = False

    if unconstrained:
        q.put_nowait(args)


def today_is_constrained(days):
    day = ha.get_now().weekday()
    daylist = [ha.day_of_week(day) for day in days.split(",")]
    if day in daylist:
        return False
    return True


def process_sun(action):
    ha.log(
            conf.logger, "DEBUG",
            "Process sun: {}, next sunrise: {}, next sunset: {}".format(
                action, conf.sun["next_rising"], conf.sun["next_setting"]
            )
    )
    with conf.schedule_lock:
        for name in conf.schedule.keys():
            for entry in sorted(
                    conf.schedule[name].keys(),
                    key=lambda uuid_: conf.schedule[name][uuid_]["timestamp"]
            ):
                schedule = conf.schedule[name][entry]
                if schedule["type"] == action and "inactive" in schedule:
                    del schedule["inactive"]
                    c_offset = ha.get_offset(schedule)
                    schedule["timestamp"] = ha.calc_sun(action) + c_offset
                    schedule["offset"] = c_offset


# noinspection PyBroadException
def exec_schedule(name, entry, args):
    try:
        # Locking performed in calling function
        if "inactive" in args:
            return
        # Call function
        if "entity" in args["kwargs"]:
            dispatch_worker(name, {
                "name": name,
                "id": conf.objects[name]["id"],
                "type": "attr",
                "function": args["callback"],
                "attribute": args["kwargs"]["attribute"],
                "entity": args["kwargs"]["entity"],
                "new_state": args["kwargs"]["new_state"],
                "old_state": args["kwargs"]["old_state"],
                "kwargs": args["kwargs"],
            })
        else:
            dispatch_worker(name, {
                "name": name,
                "id": conf.objects[name]["id"],
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
                    c_offset = ha.get_offset(args)
                    args["timestamp"] = ha.calc_sun(args["type"]) + c_offset
                    args["offset"] = c_offset
            else:
                # Not sunrise or sunset so just increment
                # the timestamp with the repeat interval
                args["basetime"] += args["interval"]
                args["timestamp"] = args["basetime"] + ha.get_offset(args)
        else:  # Otherwise just delete
            del conf.schedule[name][entry]

    except:
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(
            conf.error, "WARNING",
            "Unexpected error during exec_schedule() for App: {}".format(name)
        )
        ha.log(conf.error, "WARNING", "Args: {}".format(args))
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", traceback.format_exc())
        ha.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            # When explicitly logging to stdout and stderr, suppress
            # log messages about writing an error (since they show up anyway)
            ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))
        ha.log(conf.error, "WARNING", "Scheduler entry has been deleted")
        ha.log(conf.error, "WARNING", '-' * 60)

        del conf.schedule[name][entry]

@asyncio.coroutine
def do_every(period, f):
    t = math.floor(ha.get_now_ts())
    count = 0
    t_ = math.floor(time.time())
    while not conf.stopping:
        count += 1
        delay = max(t_ + count * period - time.time(), 0)
        yield from asyncio.sleep(delay)
        t += conf.interval
        r = yield from f(t)
        if r is not None and r != t:
            print("r: {}, t: {}".format(r,t))
            t = r
            t_ = r
            count = 0


# noinspection PyBroadException,PyBroadException
def do_every_second(utc):
    global was_dst
    global last_state

    try:

        now = datetime.datetime.fromtimestamp(utc)
        conf.now = utc

        # If we have reached endtime bail out

        if conf.endtime is not None and ha.get_now() >= conf.endtime:
            ha.log(conf.logger, "INFO", "End time reached, exiting")
            stopit()

        if conf.realtime:
            real_now = datetime.datetime.now().timestamp()
            delta = abs(utc - real_now)
            if delta > 1:
                ha.log(conf.logger, "WARNING", "Scheduler clock skew detected - delta = {} - resetting".format(delta))
                return real_now

        # Update sunrise/sunset etc.

        update_sun()

        # Check if we have entered or exited DST - if so, reload apps
        # to ensure all time callbacks are recalculated

        now_dst = is_dst()
        if now_dst != was_dst:
            ha.log(
                conf.logger, "INFO",
                "Detected change in DST from {} to {} -"
                " reloading all modules".format(was_dst, now_dst)
            )
            # dump_schedule()
            ha.log(conf.logger, "INFO", "-" * 40)
            completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, read_apps, True)])
            #read_apps(True)
            # dump_schedule()
        was_dst = now_dst

        # dump_schedule()

        # test code for clock skew
        #if random.randint(1, 10) == 5:
        #    time.sleep(random.randint(1,20))

        # Check to see if any apps have changed but only if we have valid state

        if last_state is not None and appapi.reading_messages:
            completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, read_apps)])
            #read_apps()

        # Check to see if config has changed

        if appapi.reading_messages:
            completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, check_config)])
        #check_config()

        # Call me suspicious, but lets update state form HA periodically
        # in case we miss events for whatever reason
        # Every 10 minutes seems like a good place to start

        if last_state is not None and appapi.reading_messages and now - last_state > datetime.timedelta(minutes=10) and conf.ha_url is not None:
            try:
                completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, get_ha_state)])
                #get_ha_state()
                last_state = now
            except:
                ha.log(conf.logger, "WARNING", "Unexpected error refreshing HA state - retrying in 10 minutes")

        # Check on Queue size

        qsize = q.qsize()
        if qsize > 0 and qsize % 10 == 0:
            conf.logger.warning("Queue size is {}, suspect thread starvation".format(q.qsize()))

        # Process callbacks

        # ha.log(conf.logger, "DEBUG", "Scheduler invoked at {}".format(now))
        with conf.schedule_lock:
            for name in conf.schedule.keys():
                for entry in sorted(
                        conf.schedule[name].keys(),
                        key=lambda uuid_: conf.schedule[name][uuid_]["timestamp"]
                ):

                    if conf.schedule[name][entry]["timestamp"] <= utc:
                        exec_schedule(name, entry, conf.schedule[name][entry])
                    else:
                        break
            for k, v in list(conf.schedule.items()):
                if v == {}:
                    del conf.schedule[k]

        return utc

    except:
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", "Unexpected error during do_every_second()")
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", traceback.format_exc())
        ha.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            # When explicitly logging to stdout and stderr, suppress
            # log messages about writing an error (since they show up anyway)
            ha.log(
                conf.logger, "WARNING",
                "Logged an error to {}".format(conf.errorfile)
            )


# noinspection PyBroadException
def worker():
    while True:
        args = q.get()
        _type = args["type"]
        function = args["function"]
        _id = args["id"]
        name = args["name"]
        if name in conf.objects and conf.objects[name]["id"] == _id:
            try:
                if _type == "initialize":
                    ha.log(conf.logger, "DEBUG", "Calling initialize() for {}".format(name))
                    function()
                    ha.log(conf.logger, "DEBUG", "{} initialize() done".format(name))
                elif _type == "timer":
                    function(ha.sanitize_timer_kwargs(args["kwargs"]))
                elif _type == "attr":
                    entity = args["entity"]
                    attr = args["attribute"]
                    old_state = args["old_state"]
                    new_state = args["new_state"]
                    function(entity, attr, old_state, new_state,
                             ha.sanitize_state_kwargs(args["kwargs"]))
                elif _type == "event":
                    data = args["data"]
                    function(args["event"], data, args["kwargs"])

            except:
                ha.log(conf.error, "WARNING", '-' * 60)
                ha.log(conf.error, "WARNING", "Unexpected error in worker for App {}:".format(name))
                ha.log(conf.error, "WARNING", "Worker Ags: {}".format(args))
                ha.log(conf.error, "WARNING", '-' * 60)
                ha.log(conf.error, "WARNING", traceback.format_exc())
                ha.log(conf.error, "WARNING", '-' * 60)
                if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
                    ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))
        else:
            conf.logger.warning("Found stale callback for {} - discarding".format(name))

        if inits.get(name):
            inits.pop(name)

        q.task_done()


def term_file(name):
    global config
    for key in config:
        if "module" in config[key] and config[key]["module"] == name:
            term_object(key)


def clear_file(name):
    global config
    for key in config:
        if "module" in config[key] and config[key]["module"] == name:
            clear_object(key)
            if key in conf.objects:
                del conf.objects[key]


def clear_object(object_):
    ha.log(conf.logger, "DEBUG", "Clearing callbacks for {}".format(object_))
    with conf.callbacks_lock:
        if object_ in conf.callbacks:
            del conf.callbacks[object_]
    with conf.schedule_lock:
        if object_ in conf.schedule:
            del conf.schedule[object_]


def term_object(name):
    if name in conf.objects and hasattr(conf.objects[name]["object"], "terminate"):
        ha.log(conf.logger, "INFO", "Terminating Object {}".format(name))
        # Call terminate directly rather than via worker thread
        # so we know terminate has completed before we move on
        conf.objects[name]["object"].terminate()


def init_object(name, class_name, module_name, args):
    ha.log(conf.logger, "INFO", "Loading Object {} using class {} from module {}".format(name, class_name, module_name))
    module = __import__(module_name)
    app_class = getattr(module, class_name)
    conf.objects[name] = {
        "object": app_class(
            name, conf.logger, conf.error, args, conf.global_vars
        ),
        "id": uuid.uuid4()
    }

    # Call it's initialize function

    conf.objects[name]["object"].initialize()

    # with conf.threads_busy_lock:
    #     inits[name] = 1
    #     conf.threads_busy += 1
    #     q.put_nowait({
    #         "type": "initialize",
    #         "name": name,
    #         "id": conf.objects[name]["id"],
    #         "function": conf.objects[name]["object"].initialize
    #     })


def check_and_disapatch(name, function, entity, attribute, new_state,
                        old_state, cold, cnew, kwargs):
    if attribute == "all":
        dispatch_worker(name, {
            "name": name,
            "id": conf.objects[name]["id"],
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
                exec_time = ha.get_now_ts() + int(kwargs["duration"])
                kwargs["handle"] = ha.insert_schedule(
                    name, exec_time, function, False, None,
                    entity=entity,
                    attribute=attribute,
                    old_state=old,
                    new_state=new, **kwargs
                )
            else:
                # Do it now
                dispatch_worker(name, {
                    "name": name,
                    "id": conf.objects[name]["id"],
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
                ha.cancel_timer(name, kwargs["handle"])


def process_state_change(data):
    entity_id = data['data']['entity_id']
    ha.log(conf.logger, "DEBUG", "Entity ID:{}:".format(entity_id))
    device, entity = entity_id.split(".")

    # Process state callbacks

    with conf.callbacks_lock:
        for name in conf.callbacks.keys():
            for uuid_ in conf.callbacks[name]:
                callback = conf.callbacks[name][uuid_]
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
                        check_and_disapatch(
                            name, callback["function"], entity_id,
                            cattribute,
                            data['data']['new_state'],
                            data['data']['old_state'],
                            cold, cnew,
                            callback["kwargs"]
                        )
                    elif centity is None:
                        if device == cdevice:
                            check_and_disapatch(
                                name, callback["function"], entity_id,
                                cattribute,
                                data['data']['new_state'],
                                data['data']['old_state'],
                                cold, cnew,
                                callback["kwargs"]
                            )
                    elif device == cdevice and entity == centity:
                        check_and_disapatch(
                            name, callback["function"], entity_id,
                            cattribute,
                            data['data']['new_state'],
                            data['data']['old_state'], cold,
                            cnew,
                            callback["kwargs"]
                        )


def process_event(data):
    with conf.callbacks_lock:
        for name in conf.callbacks.keys():
            for uuid_ in conf.callbacks[name]:
                callback = conf.callbacks[name][uuid_]
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
                        dispatch_worker(name, {
                            "name": name,
                            "id": conf.objects[name]["id"],
                            "type": "event",
                            "event": data['event_type'],
                            "function": callback["function"],
                            "data": data["data"],
                            "kwargs": callback["kwargs"]
                        })


# noinspection PyBroadException
def process_message(data):
    try:
        ha.log(
            conf.logger, "DEBUG",
            "Event type:{}:".format(data['event_type'])
        )
        ha.log(conf.logger, "DEBUG", data["data"])

        if data['event_type'] == "state_changed":
            entity_id = data['data']['entity_id']

            # First update our global state
            with conf.ha_state_lock:
                conf.ha_state[entity_id] = data['data']['new_state']

        if conf.apps is True:
            # Process state changed message
            if data['event_type'] == "state_changed":
                process_state_change(data)

            # Process non-state callbacks
            process_event(data)

        # Update dashboards

        if conf.dashboard is True:
            appdash.ws_update(data)

    except:
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", "Unexpected error during process_message()")
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", traceback.format_exc())
        ha.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))


# noinspection PyBroadException
def check_config():
    global config_file_modified
    global config

    new_config = None
    try:
        modified = os.path.getmtime(config_file)
        if modified > config_file_modified:
            ha.log(conf.logger, "INFO", "{} modified".format(config_file))
            config_file_modified = modified
            root, ext = os.path.splitext(config_file)
            if ext == ".yaml":
                with open(config_file, 'r') as yamlfd:
                    config_file_contents = yamlfd.read()
                try:
                    new_config = yaml.load(config_file_contents)
                except yaml.YAMLError as exc:
                    print(conf.dash, "WARNING", "Error loading configuration")
                    if hasattr(exc, 'problem_mark'):
                        if exc.context is not None:
                            ha.log(conf.dash, "WARNING", "parser says")
                            ha.log(conf.dash, "WARNING", str(exc.problem_mark))
                            ha.log(conf.dash, "WARNING", str(exc.problem) + " " + str(exc.context))
                        else:
                            ha.log(conf.dash, "WARNING", "parser says")
                            ha.log(conf.dash, "WARNING", str(exc.problem_mark))
                            ha.log(conf.dash, "WARNING", str(exc.problem))
            else:
                new_config = configparser.ConfigParser()
                new_config.read_file(open(config_file))

            if new_config is None:
                ha.log(conf.dash, "WARNING", "New config not applied")
                return


            # Check for changes

            for name in config:
                if name == "DEFAULT" or name == "AppDaemon":
                    continue
                if name in new_config:
                    if config[name] != new_config[name]:
                        # Something changed, clear and reload

                        ha.log(conf.logger, "INFO", "App '{}' changed - reloading".format(name))
                        term_object(name)
                        clear_object(name)
                        init_object(
                            name, new_config[name]["class"],
                            new_config[name]["module"], new_config[name]
                        )
                else:

                    # Section has been deleted, clear it out

                    ha.log(conf.logger, "INFO", "App '{}' deleted - removing".format(name))
                    clear_object(name)

            for name in new_config:
                if name == "DEFAULT" or name == "AppDaemon":
                    continue
                if name not in config:
                    #
                    # New section added!
                    #
                    ha.log(conf.logger, "INFO", "App '{}' added - running".format(name))
                    init_object(
                        name, new_config[name]["class"],
                        new_config[name]["module"], new_config[name]
                    )

            config = new_config
    except:
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", "Unexpected error:")
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", traceback.format_exc())
        ha.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))


# noinspection PyBroadException
def read_app(file, reload=False):
    global config
    name = os.path.basename(file)
    module_name = os.path.splitext(name)[0]
    # Import the App
    try:
        if reload:
            ha.log(conf.logger, "INFO", "Reloading Module: {}".format(file))

            file, ext = os.path.splitext(name)

            #
            # Clear out callbacks and remove objects
            #
            term_file(file)
            clear_file(file)
            #
            # Reload
            #
            try:
                importlib.reload(conf.modules[module_name])
            except KeyError:
                if name not in sys.modules:
                    # Probably failed to compile on initial load
                    # so we need to re-import
                    read_app(file)
                else:
                    # A real KeyError!
                    raise
        else:
            ha.log(conf.logger, "INFO", "Loading Module: {}".format(file))
            conf.modules[module_name] = importlib.import_module(module_name)

        # Instantiate class and Run initialize() function

        for name in config:
            if name == "DEFAULT" or name == "AppDaemon" or name == "HASS" or name == "HADashboard":
                continue
            if module_name == config[name]["module"]:
                class_name = config[name]["class"]

                init_object(name, class_name, module_name, config[name])

    except:
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", "Unexpected error during loading of {}:".format(name))
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", traceback.format_exc())
        ha.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))


def get_module_dependencies(file):
    global config
    module_name = get_module_from_path(file)
    for key in config:
        if "module" in config[key] and config[key]["module"] == module_name:
            if "dependencies" in config[key]:
                return config[key]["dependencies"].split(",")
            else:
                return None

    return None


def in_previous_dependencies(dependencies, load_order):
    for dependency in dependencies:
        dependency_found = False
        for batch in load_order:
            for module in batch:
                module_name = get_module_from_path(module["name"])
                # print(dependency, module_name)
                if dependency == module_name:
                    # print("found {}".format(module_name))
                    dependency_found = True
        if not dependency_found:
            return False

    return True


def dependencies_are_satisfied(module, load_order):
    dependencies = get_module_dependencies(module)

    if dependencies is None:
        return True

    if in_previous_dependencies(dependencies, load_order):
        return True

    return False


def get_module_from_path(path):
    name = os.path.basename(path)
    module_name = os.path.splitext(name)[0]
    return module_name


def find_dependent_modules(module):
    global config
    module_name = get_module_from_path(module["name"])
    dependents = []
    for mod in config:
        if "dependencies" in config[mod]:
            for dep in config[mod]["dependencies"].split(","):
                if dep == module_name:
                    dependents.append(config[mod]["module"])
    return dependents


def get_file_from_module(module):
    for file in conf.monitored_files:
        module_name = get_module_from_path(file)
        if module_name == module:
            return file

    return None


def file_in_modules(file, modules):
    for mod in modules:
        if mod["name"] == file:
            return True
    return False


# noinspection PyBroadException
def read_apps(all_=False):
    global config
    # Check if the apps are disabled in config
    if not conf.apps:
        return
    found_files = []
    modules = []
    for root, subdirs, files in os.walk(conf.app_dir):
        if root[-11:] != "__pycache__":
            for file in files:
                if file[-3:] == ".py":
                    found_files.append(os.path.join(root, file))
    for file in found_files:
        if file == os.path.join(conf.app_dir, "__init__.py"):
            continue
        if file == os.path.join(conf.app_dir, "__pycache__"):
            continue
        modified = os.path.getmtime(file)
        if file in conf.monitored_files:
            if conf.monitored_files[file] < modified or all_:
                # read_app(file, True)
                module = {"name": file, "reload": True, "load": True}
                modules.append(module)
                conf.monitored_files[file] = modified
        else:
            # read_app(file)
            modules.append({"name": file, "reload": False, "load": True})
            conf.monitored_files[file] = modified

    # Add any required dependent files to the list

    if modules:
        more_modules = True
        while more_modules:
            module_list = modules.copy()
            for module in module_list:
                dependent_modules = find_dependent_modules(module)
                if not dependent_modules:
                    more_modules = False
                else:
                    for mod in dependent_modules:
                        file = get_file_from_module(mod)

                        if file is None:
                            ha.log(conf.logger, "ERROR", "Unable to resolve dependencies due to incorrect references")
                            ha.log(conf.logger, "ERROR", "The following modules have unresolved dependencies:")
                            ha.log(conf.logger, "ERROR",  get_module_from_path(module["file"]))
                            raise ValueError("Unresolved dependencies")

                        mod_def = {"name": file, "reload": True, "load": True}
                        if not file_in_modules(file, modules):
                            # print("Appending {} ({})".format(mod, file))
                            modules.append(mod_def)

    # Loading order algorithm requires full population of modules
    # so we will add in any missing modules but mark them for not loading

    for file in conf.monitored_files:
        if not file_in_modules(file, modules):
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
            if dependencies_are_satisfied(module["name"], load_order):
                batch.append(module)
                modules.remove(module)

        if not batch:
            ha.log(conf.logger, "ERROR",  "Unable to resolve dependencies due to incorrect or circular references")
            ha.log(conf.logger, "ERROR",  "The following modules have unresolved dependencies:")
            for module in modules:
                module_name = get_module_from_path(module["name"])
                ha.log(conf.logger, "ERROR", module_name)
            raise ValueError("Unresolved dependencies")

        load_order.append(batch)

    try:
        for batch in load_order:
            for module in batch:
                if module["load"]:
                    read_app(module["name"], module["reload"])

    except:
        ha.log(conf.logger, "WARNING", '-' * 60)
        ha.log(conf.logger, "WARNING", "Unexpected error loading file")
        ha.log(conf.logger, "WARNING", '-' * 60)
        ha.log(conf.logger, "WARNING", traceback.format_exc())
        ha.log(conf.logger, "WARNING", '-' * 60)


def get_ha_state():
    ha.log(conf.logger, "DEBUG", "Refreshing HA state")
    states = ha.get_ha_state()
    with conf.ha_state_lock:
        for state in states:
            conf.ha_state[state["entity_id"]] = state


# noinspection PyBroadException,PyBroadException
def run():
    global was_dst
    global last_state

    conf.appq = asyncio.Queue(maxsize=0)

    first_time = True

    conf.stopping = False

    ha.log(conf.logger, "DEBUG", "Entering run()")

    conf.loop = asyncio.get_event_loop()

    # Save start time

    conf.start_time = datetime.datetime.now()

    # Take a note of DST

    was_dst = is_dst()

    # Setup sun

    update_sun()

    conf.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
    tasks = []

    if conf.apps is True:
        ha.log(conf.logger, "DEBUG", "Creating worker threads ...")

        # Create Worker Threads
        for i in range(conf.threads):
            t = threading.Thread(target=worker)
            t.daemon = True
            t.start()

            ha.log(conf.logger, "DEBUG", "Done")


    if conf.ha_url is not None:
        # Read apps and get HA State before we start the timer thread
        ha.log(conf.logger, "DEBUG", "Calling HA for initial state")

        while last_state is None:
            try:
                get_ha_state()
                last_state = ha.get_now()
            except:
                ha.log(
                    conf.logger, "WARNING",
                    "Disconnected from Home Assistant, retrying in 5 seconds"
                )
                if conf.loglevel == "DEBUG":
                    ha.log(conf.logger, "WARNING", '-' * 60)
                    ha.log(conf.logger, "WARNING", "Unexpected error:")
                    ha.log(conf.logger, "WARNING", '-' * 60)
                    ha.log(conf.logger, "WARNING", traceback.format_exc())
                    ha.log(conf.logger, "WARNING", '-' * 60)
                time.sleep(5)

        ha.log(conf.logger, "INFO", "Got initial state")

        # Initialize appdaemon loop
        tasks.append(asyncio.async(appdaemon_loop()))

    else:
       last_state = ha.get_now()

    if conf.apps is True:
        # Load apps

        # Let other parts know we are in business,
        appapi.reading_messages = True

        ha.log(conf.logger, "DEBUG", "Reading Apps")

        read_apps(True)

        ha.log(conf.logger, "INFO", "App initialization complete")


        # Create timer loop

        # First, update "now" for less chance of clock skew error
        if conf.realtime:
            conf.now = datetime.datetime.now().timestamp()

            ha.log(conf.logger, "DEBUG", "Starting timer loop")

            tasks.append(asyncio.async(appstate_loop()))

        tasks.append(asyncio.async(do_every(conf.tick, do_every_second)))
        appapi.reading_messages = True

    else:
        ha.log(conf.logger, "INFO", "Apps are disabled")


    # Initialize Dashboard

    if conf.dashboard is True:
        ha.log(conf.logger, "INFO", "Starting dashboard")
        #tasks.append(appdash.run_dash(conf.loop))
        appdash.run_dash(conf.loop)
    else:
        ha.log(conf.logger, "INFO", "Dashboards are disabled")

    conf.loop.run_until_complete(asyncio.wait(tasks))

    while not conf.stopping:
        asyncio.sleep(1)


    ha.log(conf.logger, "INFO", "AppDeamon Exited")


@asyncio.coroutine
def appstate_loop():
    while not conf.stopping:
        args = yield from conf.appq.get()
        process_message(args)
        conf.appq.task_done()


@asyncio.coroutine
def appdaemon_loop():
    first_time = True
    disconnected_event = False
    global ws

    conf.stopping = False

    _id = 0

    while not conf.stopping:
        _id += 1
        try:
            if first_time is False:
                # Get initial state
                get_ha_state()
                last_state = ha.get_now()
                ha.log(conf.logger, "INFO", "Got initial state")

                disconnected_event = False

                # Let other parts know we are in business,
                appapi.reading_messages = True

                # Load apps
                read_apps(True)

                ha.log(conf.logger, "INFO", "App initialization complete")

            #
            # Fire HA_STARTED and APPD_STARTED Events
            #
            if first_time is True:
                process_event({"event_type": "appd_started", "data": {}})
                first_time = False
            elif conf.ha_url is not None:

                process_event({"event_type": "ha_started", "data": {}})

            if conf.version < parse_version('0.34') or conf.commtype == "SSE":
                #
                # Older version of HA - connect using SSEClient
                #
                if conf.commtype == "SSE":
                    ha.log(conf.logger, "INFO", "Using SSE")
                else:
                    ha.log(
                        conf.logger, "INFO",
                        "Home Assistant version < 0.34.0 - "
                        "falling back to SSE"
                    )
                headers = {'x-ha-access': conf.ha_key}
                if conf.timeout is None:
                    messages = SSEClient(
                        "{}/api/stream".format(conf.ha_url),
                        verify=False, headers=headers, retry=3000
                    )
                    ha.log(
                        conf.logger, "INFO",
                        "Connected to Home Assistant".format(conf.timeout)
                    )
                else:
                    messages = SSEClient(
                        "{}/api/stream".format(conf.ha_url),
                        verify=False, headers=headers, retry=3000,
                        timeout=int(conf.timeout)
                    )
                    ha.log(
                        conf.logger, "INFO",
                        "Connected to Home Assistant with timeout = {}".format(
                            conf.timeout
                        )
                    )
                while True:
                    completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, messages.__next__)])
                    msg = list(completed)[0].result()
                    if msg.data != "ping":
                        process_message(json.loads(msg.data))
            else:
                #
                # Connect to websocket interface
                #
                url = conf.ha_url
                if url.startswith('https://'):
                    url = url.replace('https', 'wss', 1)
                elif url.startswith('http://'):
                    url = url.replace('http', 'ws', 1)

                sslopt = {}
                if conf.certpath:
                    sslopt['ca_certs'] = conf.certpath
                ws = create_connection(
                    "{}/api/websocket".format(url), sslopt=sslopt
                )
                result = json.loads(ws.recv())
                ha.log(conf.logger, "INFO",
                       "Connected to Home Assistant {}".format(
                           result["ha_version"]))
                #
                # Check if auth required, if so send password
                #
                if result["type"] == "auth_required":
                    auth = json.dumps({
                        "type": "auth",
                        "api_password": conf.ha_key
                    })
                    ws.send(auth)
                    result = json.loads(ws.recv())
                    if result["type"] != "auth_ok":
                        ha.log(conf.logger, "WARNING",
                               "Error in authentication")
                        raise ValueError("Error in authentication")
                #
                # Subscribe to event stream
                #
                sub = json.dumps({
                    "id": _id,
                    "type": "subscribe_events"
                })
                ws.send(sub)
                result = json.loads(ws.recv())
                if not (result["id"] == _id and result["type"] == "result" and
                                result["success"] is True):
                    ha.log(
                        conf.logger, "WARNING",
                        "Unable to subscribe to HA events, id = {}".format(_id)
                    )
                    ha.log(conf.logger, "WARNING", result)
                    raise ValueError("Error subscribing to HA Events")

                #
                # Loop forever consuming events
                #

                while not conf.stopping:
                    completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, ws.recv)])
                    result = json.loads(list(completed)[0].result())

                    if not (result["id"] == _id and result["type"] == "event"):
                        ha.log(
                            conf.logger, "WARNING",
                            "Unexpected result from Home Assistant, "
                            "id = {}".format(_id)
                        )
                        ha.log(conf.logger, "WARNING", result)
                        raise ValueError(
                            "Unexpected result from Home Assistant"
                        )

                    process_message(result["event"])

        except:
            appapi.reading_messages = False
            if not conf.stopping:
                if disconnected_event == False:
                    process_event({"event_type": "ha_disconnected", "data": {}})
                    disconnected_event = True
                ha.log(
                    conf.logger, "WARNING",
                    "Disconnected from Home Assistant, retrying in 5 seconds"
                )
                if conf.loglevel == "DEBUG":
                    ha.log(conf.logger, "WARNING", '-' * 60)
                    ha.log(conf.logger, "WARNING", "Unexpected error:")
                    ha.log(conf.logger, "WARNING", '-' * 60)
                    ha.log(conf.logger, "WARNING", traceback.format_exc())
                    ha.log(conf.logger, "WARNING", '-' * 60)
                yield from asyncio.sleep(5)

    ha.log(conf.logger, "INFO", "Disconnecting from Home Assistant")


def find_path(name):
    for path in [os.path.join(os.path.expanduser("~"), ".homeassistant"),
                 os.path.join(os.path.sep, "etc", "appdaemon")]:
        _file = os.path.join(path, name)
        if os.path.isfile(_file) or os.path.isdir(_file):
            return _file
    return None


# noinspection PyBroadException
def main():
    global config
    global config_file
    global config_file_modified

    # import appdaemon.stacktracer
    # appdaemon.stacktracer.trace_start("/tmp/trace.html")

    # Windows does not support SIGUSR1 or SIGUSR2
    if platform.system() != "Windows":
        signal.signal(signal.SIGUSR1, handle_sig)
        signal.signal(signal.SIGINT, handle_sig)
        signal.signal(signal.SIGHUP, handle_sig)

    # Get command line args

    parser = argparse.ArgumentParser()

    parser.add_argument("-c", "--config", help="full path to config directory", type=str, default=None)
    parser.add_argument("-p", "--pidfile", help="full path to PID File", default="/tmp/hapush.pid")
    parser.add_argument("-t", "--tick", help="time that a tick in the schedular lasts (seconds)", default=1, type=float)
    parser.add_argument("-s", "--starttime", help="start time for scheduler <YYYY-MM-DD HH:MM:SS>", type=str)
    parser.add_argument("-e", "--endtime", help="end time for scheduler <YYYY-MM-DD HH:MM:SS>", type=str, default=None)
    parser.add_argument("-i", "--interval", help="multiplier for scheduler tick", type=float, default=1)
    parser.add_argument("-D", "--debug", help="debug level", default="INFO", choices=
                        [
                            "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
                        ])
    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + conf.__version__)
    parser.add_argument('--commtype', help="Communication Library to use", default="WEBSOCKETS", choices=
                        [
                            "SSE",
                            "WEBSOCKETS"
                        ])
    parser.add_argument('--profiledash', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('--convertcfg', help="Convert existing .cfg file to yaml", action='store_true')

    # Windows does not have Daemonize package so disallow
    if platform.system() != "Windows":
        parser.add_argument("-d", "--daemon", help="run as a background process", action="store_true")

    args = parser.parse_args()

    conf.tick = args.tick
    conf.interval = args.interval
    conf.loglevel = args.debug
    conf.profile_dashboard = args.profiledash

    if args.starttime is not None:
        conf.now = datetime.datetime.strptime(args.starttime, "%Y-%m-%d %H:%M:%S").timestamp()
    else:
        conf.now = datetime.datetime.now().timestamp()

    if args.endtime is not None:
        conf.endtime = datetime.datetime.strptime(args.endtime, "%Y-%m-%d %H:%M:%S")

    if conf.tick != 1 or conf.interval != 1 or args.starttime is not None:
        conf.realtime = False

    config_dir = args.config

    conf.commtype = args.commtype

    if platform.system() != "Windows":
        isdaemon = args.daemon
    else:
        isdaemon = False


    if config_dir is None:
        config_file_conf = find_path("appdaemon.cfg")
        config_file_yaml = find_path("appdaemon.yaml")
    else:
        config_file_conf = os.path.join(config_dir, "appdaemon.cfg")
        if not os.path.isfile(config_file_conf):
            config_file_conf = None
        config_file_yaml = os.path.join(config_dir, "appdaemon.yaml")
        if not os.path.isfile(config_file_yaml):
            config_file_yaml = None

    config = None
    config_from_yaml = False

    if config_file_yaml is not None and args.convertcfg is False:
        config_from_yaml = True
        config_file = config_file_yaml
        with open(config_file_yaml, 'r') as yamlfd:
            config_file_contents = yamlfd.read()
        try:
            config = yaml.load(config_file_contents)
        except yaml.YAMLError as exc:
            print("ERROR", "Error loading configuration")
            if hasattr(exc, 'problem_mark'):
                if exc.context is not None:
                    print("ERROR", "parser says")
                    print("ERROR", str(exc.problem_mark))
                    print("ERROR", str(exc.problem) + " " + str(exc.context))
                else:
                    print("ERROR", "parser says")
                    print("ERROR", str(exc.problem_mark))
                    print("ERROR", str(exc.problem))
            sys.exit()
    else:

        # Read Config File
        config_file = config_file_conf
        config = configparser.ConfigParser()
        config.read_file(open(config_file_conf))

        if args.convertcfg is True:
            yaml_file = os.path.join(os.path.dirname(config_file_conf), "appdaemon.yaml")
            print("Converting {} to {}".format(config_file_conf, yaml_file))
            new_config = {}
            for section in config:
                if section != "DEFAULT":
                    if section == "AppDaemon":
                        new_config["AppDaemon"] = {}
                        new_config["HADashboard"] = {}
                        new_config["HASS"] = {}
                        new_section = ""
                        for var in config[section]:
                            if var in ("dash_compile_on_start", "dash_dir", "dash_force_compile", "dash_url"):
                                new_section = "HADashboard"
                            elif var in ("ha_key", "ha_url", "timeout"):
                                new_section = "HASS"
                            else:
                                new_section = "AppDaemon"
                            new_config[new_section][var] = config[section][var]
                    else:
                        new_config[section] = {}
                        for var in config[section]:
                            new_config[section][var] = config[section][var]
            with open(yaml_file, "w") as outfile:
                yaml.dump(new_config, outfile, default_flow_style=False)
            sys.exit()


    conf.config_dir = os.path.dirname(config_file)
    conf.config = config
    conf.logfile = config['AppDaemon'].get("logfile")
    conf.errorfile = config['AppDaemon'].get("errorfile")
    conf.threads = int(config['AppDaemon'].get('threads'))
    conf.certpath = config['AppDaemon'].get("cert_path")
    conf.app_dir = config['AppDaemon'].get("app_dir")
    conf.latitude = config['AppDaemon'].get("latitude")
    conf.longitude = config['AppDaemon'].get("longitude")
    conf.elevation = config['AppDaemon'].get("elevation")
    conf.time_zone = config['AppDaemon'].get("time_zone")
    conf.rss_feeds = config['AppDaemon'].get("rss_feeds")
    conf.rss_update = config['AppDaemon'].get("rss_update")

    if config_from_yaml is True:

        conf.timeout = config['HASS'].get("timeout")
        conf.ha_url = config['HASS'].get('ha_url')
        conf.ha_key = config['HASS'].get('ha_key', "")

        if 'HADashboard' in config:
            conf.dash_url = config['HADashboard'].get("dash_url")
            conf.dashboard_dir = config['HADashboard'].get("dash_dir")

            if config['HADashboard'].get("dash_force_compile") == "1":
                conf.dash_force_compile = True
            else:
                conf.dash_force_compile = False

            if config['HADashboard'].get("dash_compile_on_start") == "1":
                conf.dash_compile_on_start = True
            else:
                conf.dash_compile_on_start = False
    else:
        conf.timeout = config['AppDaemon'].get("timeout")
        conf.ha_url = config['AppDaemon'].get('ha_url')
        conf.ha_key = config['AppDaemon'].get('ha_key', "")
        conf.dash_url = config['AppDaemon'].get("dash_url")
        conf.dashboard_dir = config['AppDaemon'].get("dash_dir")

        if config['AppDaemon'].get("dash_force_compile") == "1":
            conf.dash_force_compile = True
        else:
            conf.dash_force_compile = False

        if config['AppDaemon'].get("dash_compile_on_start") == "1":
            conf.dash_compile_on_start = True
        else:
            conf.dash_compile_on_start = False



    if config['AppDaemon'].get("disable_apps") == "1":
        conf.apps = False
    else:
        conf.apps = True

    if config['AppDaemon'].get("cert_verify", True) == False:
        conf.certpath = False

    if conf.dash_url is not None:
        conf.dashboard = True
        url = urlparse(conf.dash_url)

        if url.scheme != "http":
            raise ValueError("Invalid scheme for 'dash_url' - only HTTP is supported")

        dash_net = url.netloc.split(":")
        conf.dash_host = dash_net[0]
        try:
            conf.dash_port = dash_net[1]
        except IndexError:
            conf.dash_port = 80

        if conf.dash_host == "":
            raise ValueError("Invalid host for 'dash_url'")

    if conf.threads is None:
        conf.threads = 10

    if conf.logfile is None:
        conf.logfile = "STDOUT"

    if conf.errorfile is None:
        conf.errorfile = "STDERR"

    if isdaemon and (
                        conf.logfile == "STDOUT" or conf.errorfile == "STDERR"
                        or conf.logfile == "STDERR" or conf.errorfile == "STDOUT"
                    ):
        raise ValueError("STDOUT and STDERR not allowed with -d")

    # Setup Logging

    conf.logger = logging.getLogger("log1")
    numeric_level = getattr(logging, args.debug, None)
    conf.logger.setLevel(numeric_level)
    conf.logger.propagate = False
    # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

    # Send to file if we are daemonizing, else send to console

    fh = None
    if conf.logfile != "STDOUT":
        fh = RotatingFileHandler(conf.logfile, maxBytes=1000000, backupCount=3)
        fh.setLevel(numeric_level)
        # fh.setFormatter(formatter)
        conf.logger.addHandler(fh)
    else:
        # Default for StreamHandler() is sys.stderr
        ch = logging.StreamHandler(stream=sys.stdout)
        ch.setLevel(numeric_level)
        # ch.setFormatter(formatter)
        conf.logger.addHandler(ch)

    # Setup compile output

    conf.error = logging.getLogger("log2")
    numeric_level = getattr(logging, args.debug, None)
    conf.error.setLevel(numeric_level)
    conf.error.propagate = False
    # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

    if conf.errorfile != "STDERR":
        efh = RotatingFileHandler(
            conf.errorfile, maxBytes=1000000, backupCount=3
        )
    else:
        efh = logging.StreamHandler()

    efh.setLevel(numeric_level)
    # efh.setFormatter(formatter)
    conf.error.addHandler(efh)

    # Setup dash output

    if config['AppDaemon'].get("accessfile") is not None:
        conf.dash = logging.getLogger("log3")
        numeric_level = getattr(logging, args.debug, None)
        conf.dash.setLevel(numeric_level)
        conf.dash.propagate = False
        # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        efh = RotatingFileHandler(
            config['AppDaemon'].get("accessfile"), maxBytes=1000000, backupCount=3
        )

        efh.setLevel(numeric_level)
        # efh.setFormatter(formatter)
        conf.dash.addHandler(efh)
    else:
        conf.dash = conf.logger

    # Startup message

    ha.log(conf.logger, "INFO", "AppDaemon Version {} starting".format(conf.__version__))
    ha.log(conf.logger, "INFO", "Configuration read from: {}".format(config_file))

    # Check with HA to get various info

    ha_config = None
    if conf.ha_url is not None:
        while ha_config is None:
            try:
                ha_config = ha.get_ha_config()
            except:
                ha.log(
                    conf.logger, "WARNING", "Unable to connect to Home Assistant, retrying in 5 seconds")
                if conf.loglevel == "DEBUG":
                    ha.log(conf.logger, "WARNING", '-' * 60)
                    ha.log(conf.logger, "WARNING", "Unexpected error:")
                    ha.log(conf.logger, "WARNING", '-' * 60)
                    ha.log(conf.logger, "WARNING", traceback.format_exc())
                    ha.log(conf.logger, "WARNING", '-' * 60)
                time.sleep(5)

        conf.version = parse_version(ha_config["version"])

        conf.ha_config = ha_config

        conf.latitude = ha_config["latitude"]
        conf.longitude = ha_config["longitude"]
        conf.time_zone = ha_config["time_zone"]

        if "elevation" in ha_config:
            conf.elevation = ha_config["elevation"]
            if "elevation" in config['AppDaemon']:
                ha.log(conf.logger, "WARNING",  "'elevation' directive is deprecated, please remove")
        else:
            conf.elevation = config['AppDaemon']["elevation"]

    # Use the supplied timezone
    if "time_zone" in config['AppDaemon']:
        os.environ['TZ'] = config['AppDaemon']['time_zone']
    else:
        os.environ['TZ'] = conf.time_zone



    # Now we have logging, warn about deprecated directives
    #if "latitude" in config['AppDaemon']:
    #    ha.log(conf.logger, "WARNING", "'latitude' directive is deprecated, please remove")

    #if "longitude" in config['AppDaemon']:
    #    ha.log(conf.logger, "WARNING", "'longitude' directive is deprecated, please remove")

    #if "timezone" in config['AppDaemon']:
    #    ha.log(conf.logger, "WARNING", "'timezone' directive is deprecated, please remove")

    #if "time_zone" in config['AppDaemon']:
    #    ha.log(conf.logger, "WARNING", "'time_zone' directive is deprecated, please remove")

    init_sun()

    config_file_modified = os.path.getmtime(config_file)

    # Add appdir  and subdirs to path
    if conf.apps:
        if conf.app_dir is None:
            if config_dir is None:
                conf.app_dir = find_path("apps")
            else:
                conf.app_dir = os.path.join(config_dir, "apps")
        for root, subdirs, files in os.walk(conf.app_dir):
            if root[-11:] != "__pycache__":
                sys.path.insert(0, root)

    # find dashboard dir

    if conf.dashboard:
        if conf.dashboard_dir is None:
            if config_dir is None:
                conf.dashboard_dir = find_path("dashboards")
            else:
                conf.dashboard_dir = os.path.join(config_dir, "dashboards")

        #
        # Figure out where our data files are
        #
        conf.dash_dir = os.path.dirname(__file__)

        #
        # Setup compile directories
        #
        if config_dir is None:
            conf.compile_dir = find_path("compiled")
        else:
            conf.compile_dir = os.path.join(config_dir, "compiled")

    # Start main loop

    if isdaemon:
        keep_fds = [fh.stream.fileno(), efh.stream.fileno()]
        pid = args.pidfile
        daemon = Daemonize(app="appdaemon", pid=pid, action=run,
                           keep_fds=keep_fds)
        daemon.start()
        while True:
            time.sleep(1)
    else:
        run()


if __name__ == "__main__":
    main()
