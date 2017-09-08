#!/usr/bin/python3
from pkg_resources import parse_version
import json
import sys
import importlib
import traceback
import configparser
import os
import os.path
from websocket import create_connection
from queue import Queue
from sseclient import SSEClient
import appdaemon.conf as conf
import time
import datetime
import signal
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

q = Queue(maxsize=0)

conf.was_dst = None
conf.last_state = None
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
    now = conf.tz.localize(utils.get_now())
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
    return bool(time.localtime(utils.get_now_ts()).tm_isdst)

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
        utils.log(conf.logger, "INFO", "Keyboard interrupt")
        stopit()

def dump_sun():
    utils.log(conf.logger, "INFO", "--------------------------------------------------")
    utils.log(conf.logger, "INFO", "Sun")
    utils.log(conf.logger, "INFO", "--------------------------------------------------")
    utils.log(conf.logger, "INFO", conf.sun)
    utils.log(conf.logger, "INFO", "--------------------------------------------------")


def dump_schedule():
    if conf.schedule == {}:
        utils.log(conf.logger, "INFO", "Schedule is empty")
    else:
        utils.log(conf.logger, "INFO", "--------------------------------------------------")
        utils.log(conf.logger, "INFO", "Scheduler Table")
        utils.log(conf.logger, "INFO", "--------------------------------------------------")
        for name in conf.schedule.keys():
            utils.log(conf.logger, "INFO", "{}:".format(name))
            for entry in sorted(
                    conf.schedule[name].keys(),
                    key=lambda uuid_: conf.schedule[name][uuid_]["timestamp"]
            ):
                utils.log(
                    conf.logger, "INFO",
                    "  Timestamp: {} - data: {}".format(
                        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(
                            conf.schedule[name][entry]["timestamp"]
                        )),
                        conf.schedule[name][entry]
                    )
                )
        utils.log(conf.logger, "INFO", "--------------------------------------------------")


def dump_callbacks():
    if conf.callbacks == {}:
        utils.log(conf.logger, "INFO", "No callbacks")
    else:
        utils.log(conf.logger, "INFO", "--------------------------------------------------")
        utils.log(conf.logger, "INFO", "Callbacks")
        utils.log(conf.logger, "INFO", "--------------------------------------------------")
        for name in conf.callbacks.keys():
            utils.log(conf.logger, "INFO", "{}:".format(name))
            for uuid_ in conf.callbacks[name]:
                utils.log(conf.logger, "INFO", "  {} = {}".format(uuid_, conf.callbacks[name][uuid_]))
        utils.log(conf.logger, "INFO", "--------------------------------------------------")


def dump_objects():
    utils.log(conf.logger, "INFO", "--------------------------------------------------")
    utils.log(conf.logger, "INFO", "Objects")
    utils.log(conf.logger, "INFO", "--------------------------------------------------")
    for object_ in conf.objects.keys():
        utils.log(conf.logger, "INFO", "{}: {}".format(object_, conf.objects[object_]))
    utils.log(conf.logger, "INFO", "--------------------------------------------------")


def dump_queue():
    utils.log(conf.logger, "INFO", "--------------------------------------------------")
    utils.log(conf.logger, "INFO", "Current Queue Size is {}".format(q.qsize()))
    utils.log(conf.logger, "INFO", "--------------------------------------------------")


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
            if value == "everyone" and not utils.everyone_home():
                unconstrained = False
            elif value == "anyone" and not utils.anyone_home():
                unconstrained = False
            elif value == "noone" and not utils.noone_home():
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
        if not utils.now_is_between(start_time, end_time, name):
            unconstrained = False

    return unconstrained


def dispatch_worker(name, args):
    unconstrained = True
    #
    # Argument Constraints
    #
    for arg in conf.app_config[name].keys():
        if not check_constraint(arg, conf.app_config[name][arg]):
            unconstrained = False
    if not check_time_constraint(conf.app_config[name], name):
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
    day = utils.get_now().weekday()
    daylist = [utils.day_of_week(day) for day in days.split(",")]
    if day in daylist:
        return False
    return True


def process_sun(action):
    utils.log(
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
                    c_offset = utils.get_offset(schedule)
                    schedule["timestamp"] = utils.calc_sun(action) + c_offset
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
                    c_offset = utils.get_offset(args)
                    args["timestamp"] = utils.calc_sun(args["type"]) + c_offset
                    args["offset"] = c_offset
            else:
                # Not sunrise or sunset so just increment
                # the timestamp with the repeat interval
                args["basetime"] += args["interval"]
                args["timestamp"] = args["basetime"] + utils.get_offset(args)
        else:  # Otherwise just delete
            del conf.schedule[name][entry]

    except:
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(
            conf.error, "WARNING",
            "Unexpected error during exec_schedule() for App: {}".format(name)
        )
        utils.log(conf.error, "WARNING", "Args: {}".format(args))
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", traceback.format_exc())
        utils.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            # When explicitly logging to stdout and stderr, suppress
            # log messages about writing an error (since they show up anyway)
            utils.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))
        utils.log(conf.error, "WARNING", "Scheduler entry has been deleted")
        utils.log(conf.error, "WARNING", '-' * 60)

        del conf.schedule[name][entry]

@asyncio.coroutine
def do_every(period, f):
    t = math.floor(utils.get_now_ts())
    count = 0
    t_ = math.floor(time.time())
    while not conf.stopping:
        count += 1
        delay = max(t_ + count * period - time.time(), 0)
        yield from asyncio.sleep(delay)
        t += conf.interval
        r = yield from f(t)
        if r is not None and r != t:
            #print("r: {}, t: {}".format(r,t))
            t = r
            t_ = r
            count = 0


# noinspection PyBroadException,PyBroadException
def do_every_second(utc):

    try:
        start_time = datetime.datetime.now().timestamp()
        now = datetime.datetime.fromtimestamp(utc)
        conf.now = utc

        # If we have reached endtime bail out

        if conf.endtime is not None and utils.get_now() >= conf.endtime:
            utils.log(conf.logger, "INFO", "End time reached, exiting")
            stopit()

        if conf.realtime:
            real_now = datetime.datetime.now().timestamp()
            delta = abs(utc - real_now)
            if delta > 1:
                utils.log(conf.logger, "WARNING", "Scheduler clock skew detected - delta = {} - resetting".format(delta))
                return real_now

        # Update sunrise/sunset etc.

        update_sun()

        # Check if we have entered or exited DST - if so, reload apps
        # to ensure all time callbacks are recalculated

        now_dst = is_dst()
        if now_dst != conf.was_dst:
            utils.log(
                conf.logger, "INFO",
                "Detected change in DST from {} to {} -"
                " reloading all modules".format(conf.was_dst, now_dst)
            )
            # dump_schedule()
            utils.log(conf.logger, "INFO", "-" * 40)
            yield from utils.run_in_executor(conf.loop, conf.executor, read_apps, True)
            # dump_schedule()
        conf.was_dst = now_dst

        # dump_schedule()

        # test code for clock skew
        #if random.randint(1, 10) == 5:
        #    time.sleep(random.randint(1,20))

        # Check to see if any apps have changed but only if we have valid state

        if conf.last_state is not None and appapi.reading_messages:
            yield from utils.run_in_executor(conf.loop, conf.executor, read_apps)

        # Check to see if config has changed

        if appapi.reading_messages:
            yield from utils.run_in_executor(conf.loop, conf.executor, check_config)

        # Call me suspicious, but lets update state form HA periodically
        # in case we miss events for whatever reason
        # Every 10 minutes seems like a good place to start

        if conf.last_state is not None and appapi.reading_messages and now - conf.last_state > datetime.timedelta(minutes=10) and conf.ha_url is not None:
            try:
                yield from utils.run_in_executor(conf.loop, conf.executor, get_ha_state)
                conf.last_state = now
            except:
                utils.log(conf.logger, "WARNING", "Unexpected error refreshing HA state - retrying in 10 minutes")

        # Check on Queue size

        qsize = q.qsize()
        if qsize > 0 and qsize % 10 == 0:
            conf.logger.warning("Queue size is {}, suspect thread starvation".format(q.qsize()))

        # Process callbacks

        # utils.log(conf.logger, "DEBUG", "Scheduler invoked at {}".format(now))
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

        end_time = datetime.datetime.now().timestamp()

        loop_duration = (int((end_time - start_time)*1000) / 1000) * 1000
        utils.log(conf.logger, "DEBUG", "Main loop compute time: {}ms".format(loop_duration))

        if loop_duration > 900:
            utils.log(conf.logger, "WARNING", "Excessive time spent in scheduler loop: {}ms".format(loop_duration))

        return utc

    except:
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", "Unexpected error during do_every_second()")
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", traceback.format_exc())
        utils.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            # When explicitly logging to stdout and stderr, suppress
            # log messages about writing an error (since they show up anyway)
            utils.log(
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
                    utils.log(conf.logger, "DEBUG", "Calling initialize() for {}".format(name))
                    function()
                    utils.log(conf.logger, "DEBUG", "{} initialize() done".format(name))
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
                utils.log(conf.error, "WARNING", '-' * 60)
                utils.log(conf.error, "WARNING", "Unexpected error in worker for App {}:".format(name))
                utils.log(conf.error, "WARNING", "Worker Ags: {}".format(args))
                utils.log(conf.error, "WARNING", '-' * 60)
                utils.log(conf.error, "WARNING", traceback.format_exc())
                utils.log(conf.error, "WARNING", '-' * 60)
                if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
                    utils.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))
        else:
            conf.logger.warning("Found stale callback for {} - discarding".format(name))

        if inits.get(name):
            inits.pop(name)

        q.task_done()


def term_file(name):
    for key in conf.app_config:
        if "module" in conf.app_config[key] and conf.app_config[key]["module"] == name:
            term_object(key)


def clear_file(name):
    for key in conf.app_config:
        if "module" in conf.app_config[key] and conf.app_config[key]["module"] == name:
            clear_object(key)
            if key in conf.objects:
                del conf.objects[key]


def clear_object(object_):
    utils.log(conf.logger, "DEBUG", "Clearing callbacks for {}".format(object_))
    with conf.callbacks_lock:
        if object_ in conf.callbacks:
            del conf.callbacks[object_]
    with conf.schedule_lock:
        if object_ in conf.schedule:
            del conf.schedule[object_]
    with conf.endpoints_lock:
        if object_ in conf.endpoints:
            del conf.endpoints[object_]


def term_object(name):
    if name in conf.objects and hasattr(conf.objects[name]["object"], "terminate"):
        utils.log(conf.logger, "INFO", "Terminating Object {}".format(name))
        # Call terminate directly rather than via worker thread
        # so we know terminate has completed before we move on
        conf.objects[name]["object"].terminate()


def init_object(name, class_name, module_name, args):
    utils.log(conf.logger, "INFO", "Loading Object {} using class {} from module {}".format(name, class_name, module_name))
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
                utils.cancel_timer(name, kwargs["handle"])


def process_state_change(data):
    entity_id = data['data']['entity_id']
    utils.log(conf.logger, "DEBUG", "Entity ID:{}:".format(entity_id))
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
        utils.log(
            conf.logger, "DEBUG",
            "Event type:{}:".format(data['event_type'])
        )
        utils.log(conf.logger, "DEBUG", data["data"])

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
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", "Unexpected error during process_message()")
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", traceback.format_exc())
        utils.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            utils.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))


def read_config():
    root, ext = os.path.splitext(conf.app_config_file)
    if ext == ".yaml":
        with open(conf.app_config_file, 'r') as yamlfd:
            config_file_contents = yamlfd.read()
        try:
            new_config = yaml.load(config_file_contents)
        except yaml.YAMLError as exc:
            utils.log(conf.logger, "WARNING", "Error loading configuration")
            if hasattr(exc, 'problem_mark'):
                if exc.context is not None:
                    utils.log(conf.error, "WARNING", "parser says")
                    utils.log(conf.error, "WARNING", str(exc.problem_mark))
                    utils.log(conf.error, "WARNING", str(exc.problem) + " " + str(exc.context))
                else:
                    utils.log(conf.error, "WARNING", "parser says")
                    utils.log(conf.error, "WARNING", str(exc.problem_mark))
                    utils.log(conf.error, "WARNING", str(exc.problem))
    else:
        new_config = configparser.ConfigParser()
        new_config.read_file(open(conf.app_config_file))

    return new_config

# noinspection PyBroadException
def check_config():

    new_config = None
    try:
        modified = os.path.getmtime(conf.app_config_file)
        if modified > conf.app_config_file_modified:
            utils.log(conf.logger, "INFO", "{} modified".format(conf.app_config_file))
            conf.app_config_file_modified = modified
            new_config = read_config()

            if new_config is None:
                utils.log(conf.error, "WARNING", "New config not applied")
                return


            # Check for changes

            for name in conf.app_config:
                if name == "DEFAULT" or name == "AppDaemon" or name == "HADashboard":
                    continue
                if name in new_config:
                    if conf.app_config[name] != new_config[name]:
                        # Something changed, clear and reload

                        utils.log(conf.logger, "INFO", "App '{}' changed - reloading".format(name))
                        term_object(name)
                        clear_object(name)
                        init_object(
                            name, new_config[name]["class"],
                            new_config[name]["module"], new_config[name]
                        )
                else:

                    # Section has been deleted, clear it out

                    utils.log(conf.logger, "INFO", "App '{}' deleted - removing".format(name))
                    clear_object(name)

            for name in new_config:
                if name == "DEFAULT" or name == "AppDaemon":
                    continue
                if name not in conf.app_config:
                    #
                    # New section added!
                    #
                    utils.log(conf.logger, "INFO", "App '{}' added - running".format(name))
                    init_object(
                        name, new_config[name]["class"],
                        new_config[name]["module"], new_config[name]
                    )

            conf.app_config = new_config
    except:
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", "Unexpected error:")
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", traceback.format_exc())
        utils.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            utils.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))


# noinspection PyBroadException
def read_app(file, reload=False):
    name = os.path.basename(file)
    module_name = os.path.splitext(name)[0]
    # Import the App
    try:
        if reload:
            utils.log(conf.logger, "INFO", "Reloading Module: {}".format(file))

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
            utils.log(conf.logger, "INFO", "Loading Module: {}".format(file))
            conf.modules[module_name] = importlib.import_module(module_name)

        # Instantiate class and Run initialize() function

        if conf.app_config is not None:
            for name in conf.app_config:
                if name == "DEFAULT" or name == "AppDaemon" or name == "HASS" or name == "HADashboard":
                    continue
                if module_name == conf.app_config[name]["module"]:
                    class_name = conf.app_config[name]["class"]

                    init_object(name, class_name, module_name, conf.app_config[name])

    except:
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", "Unexpected error during loading of {}:".format(name))
        utils.log(conf.error, "WARNING", '-' * 60)
        utils.log(conf.error, "WARNING", traceback.format_exc())
        utils.log(conf.error, "WARNING", '-' * 60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            utils.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))


def get_module_dependencies(file):
    module_name = get_module_from_path(file)
    if conf.app_config is not None:
        for key in conf.app_config:
            if "module" in conf.app_config[key] and conf.app_config[key]["module"] == module_name:
                if "dependencies" in conf.app_config[key]:
                    return conf.app_config[key]["dependencies"].split(",")
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
    module_name = get_module_from_path(module["name"])
    dependents = []
    if conf.app_config is not None:
        for mod in conf.app_config:
            if "dependencies" in conf.app_config[mod]:
                for dep in conf.app_config[mod]["dependencies"].split(","):
                    if dep == module_name:
                        dependents.append(conf.app_config[mod]["module"])
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
                            utils.log(conf.logger, "ERROR", "Unable to resolve dependencies due to incorrect references")
                            utils.log(conf.logger, "ERROR", "The following modules have unresolved dependencies:")
                            utils.log(conf.logger, "ERROR",  get_module_from_path(module["file"]))
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
            utils.log(conf.logger, "ERROR",  "Unable to resolve dependencies due to incorrect or circular references")
            utils.log(conf.logger, "ERROR",  "The following modules have unresolved dependencies:")
            for module in modules:
                module_name = get_module_from_path(module["name"])
                utils.log(conf.logger, "ERROR", module_name)
            raise ValueError("Unresolved dependencies")

        load_order.append(batch)

    try:
        for batch in load_order:
            for module in batch:
                if module["load"]:
                    read_app(module["name"], module["reload"])

    except:
        utils.log(conf.logger, "WARNING", '-' * 60)
        utils.log(conf.logger, "WARNING", "Unexpected error loading file")
        utils.log(conf.logger, "WARNING", '-' * 60)
        utils.log(conf.logger, "WARNING", traceback.format_exc())
        utils.log(conf.logger, "WARNING", '-' * 60)


def get_ha_state():
    utils.log(conf.logger, "DEBUG", "Refreshing HA state")
    states = utils.get_ha_state()
    with conf.ha_state_lock:
        for state in states:
            conf.ha_state[state["entity_id"]] = state


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
                conf.last_state = utils.get_now()
                utils.log(conf.logger, "INFO", "Got initial state")

                disconnected_event = False

                # Let other parts know we are in business,
                appapi.reading_messages = True

                # Load apps
                read_apps(True)

                utils.log(conf.logger, "INFO", "App initialization complete")

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
                    utils.log(conf.logger, "INFO", "Using SSE")
                else:
                    utils.log(
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
                    utils.log(
                        conf.logger, "INFO",
                        "Connected to Home Assistant".format(conf.timeout)
                    )
                else:
                    messages = SSEClient(
                        "{}/api/stream".format(conf.ha_url),
                        verify=False, headers=headers, retry=3000,
                        timeout=int(conf.timeout)
                    )
                    utils.log(
                        conf.logger, "INFO",
                        "Connected to Home Assistant with timeout = {}".format(
                            conf.timeout
                        )
                    )
                while True:
                    msg = yield from utils.run_in_executor(conf.loop, conf.executor, messages.__next__)
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
                utils.log(conf.logger, "INFO",
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
                        utils.log(conf.logger, "WARNING",
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
                    utils.log(
                        conf.logger, "WARNING",
                        "Unable to subscribe to HA events, id = {}".format(_id)
                    )
                    utils.log(conf.logger, "WARNING", result)
                    raise ValueError("Error subscribing to HA Events")

                #
                # Loop forever consuming events
                #

                while not conf.stopping:
                    ret = yield from utils.run_in_executor(conf.loop, conf.executor, ws.recv)
                    result = json.loads(ret)
                    result = json.loads(ret)

                    if not (result["id"] == _id and result["type"] == "event"):
                        utils.log(
                            conf.logger, "WARNING",
                            "Unexpected result from Home Assistant, "
                            "id = {}".format(_id)
                        )
                        utils.log(conf.logger, "WARNING", result)
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
                utils.log(
                    conf.logger, "WARNING",
                    "Disconnected from Home Assistant, retrying in 5 seconds"
                )
                if conf.loglevel == "DEBUG":
                    utils.log(conf.logger, "WARNING", '-' * 60)
                    utils.log(conf.logger, "WARNING", "Unexpected error:")
                    utils.log(conf.logger, "WARNING", '-' * 60)
                    utils.log(conf.logger, "WARNING", traceback.format_exc())
                    utils.log(conf.logger, "WARNING", '-' * 60)
                yield from asyncio.sleep(5)

    utils.log(conf.logger, "INFO", "Disconnecting from Home Assistant")

def run_ad(loop, tasks):
    conf.appq = asyncio.Queue(maxsize=0)

    conf.loop = loop

    first_time = True

    conf.stopping = False

    utils.log(conf.logger, "DEBUG", "Entering run()")

    # Load App Config

    conf.app_config = read_config()

    # Save start time

    conf.start_time = datetime.datetime.now()

    # Take a note of DST

    conf.was_dst = is_dst()

    # Setup sun

    update_sun()

    conf.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

    utils.log(conf.logger, "DEBUG", "Creating worker threads ...")

    # Create Worker Threads
    for i in range(conf.threads):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    utils.log(conf.logger, "DEBUG", "Done")


    if conf.ha_url is not None:
        # Read apps and get HA State before we start the timer thread
        utils.log(conf.logger, "DEBUG", "Calling HA for initial state with key: {} and url: {}".format(conf.ha_key, conf.ha_url))

        while conf.last_state is None:
            try:
                get_ha_state()
                conf.last_state = utils.get_now()
            except:
                utils.log(
                    conf.logger, "WARNING",
                    "Disconnected from Home Assistant, retrying in 5 seconds"
                )
                if conf.loglevel == "DEBUG":
                    utils.log(conf.logger, "WARNING", '-' * 60)
                    utils.log(conf.logger, "WARNING", "Unexpected error:")
                    utils.log(conf.logger, "WARNING", '-' * 60)
                    utils.log(conf.logger, "WARNING", traceback.format_exc())
                    utils.log(conf.logger, "WARNING", '-' * 60)
                time.sleep(5)

        utils.log(conf.logger, "INFO", "Got initial state")

        # Initialize appdaemon loop
        tasks.append(asyncio.async(appdaemon_loop()))

    else:
       conf.last_state = utils.get_now()

    # Load apps

    # Let other parts know we are in business,
    appapi.reading_messages = True

    utils.log(conf.logger, "DEBUG", "Reading Apps")

    read_apps(True)

    utils.log(conf.logger, "INFO", "App initialization complete")

    # Create timer loop

    # First, update "now" for less chance of clock skew error
    if conf.realtime:
        conf.now = datetime.datetime.now().timestamp()

        utils.log(conf.logger, "DEBUG", "Starting timer loop")

        tasks.append(asyncio.async(appstate_loop()))

    tasks.append(asyncio.async(do_every(conf.tick, do_every_second)))
    appapi.reading_messages = True
