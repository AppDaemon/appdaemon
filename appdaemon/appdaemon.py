import traceback
import os
import os.path
import datetime
import uuid
import concurrent.futures
import threading
from copy import deepcopy
import functools
import time
import cProfile
import io
import pstats

import appdaemon.utils as utils
import appdaemon.appq as appq
import appdaemon.utility as utility
import appdaemon.plugin_management as plugins
import appdaemon.threading
import appdaemon.app_management as apps


def _timeit(func):
    @functools.wraps(func)
    def newfunc(*args, **kwargs):
        self = args[0]
        start_time = time.time()
        result = func(self, *args, **kwargs)
        elapsed_time = time.time() - start_time
        self.log("INFO", 'function [{}] finished in {} ms'.format(
            func.__name__, int(elapsed_time * 1000)))
        return result

    return newfunc


def _profile_this(fn):
    def profiled_fn(*args, **kwargs):
        self = args[0]
        self.pr = cProfile.Profile()
        self.pr.enable()

        result = fn(self, *args, **kwargs)

        self.pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(self.pr, stream=s).sort_stats(sortby)
        ps.print_stats()
        self.profile = fn + s.getvalue()

        return result

    return profiled_fn


class AppDaemon:

    def __init__(self, logger, error, diag, loop, **kwargs):

        self.logger = logger
        self.error = error
        self.diagnostic = diag
        self.config = kwargs
        self.booted = datetime.datetime.now()
        self.config["ad_version"] = utils.__version__
        self.check_app_updates_profile = ""

        self.was_dst = False

        self.last_state = None

        self.executor = None
        self.loop = None
        self.srv = None
        self.appd = None
        self.stopping = False
        self.dashboard = None
        self.running_apps = 0

        self.callbacks = {}
        self.callbacks_lock = threading.RLock()

        self.state = {}
        self.state["default"] = {}
        self.state_lock = threading.RLock()

        self.endpoints = {}
        self.endpoints_lock = threading.RLock()

        self.global_vars = {}
        self.global_lock = threading.RLock()

        self.config_file_modified = 0

        self.sched = None
        self.appq = None
        self.utility = None

        # User Supplied/Defaults

        self.load_distribution = "roundrobbin"
        utils.process_arg(self, "load_distribution", kwargs)

        self.app_dir = None
        utils.process_arg(self, "app_dir", kwargs)

        self.starttime = None
        utils.process_arg(self, "starttime", kwargs)

        self.latitude = None
        utils.process_arg(self, "latitude", kwargs)

        self.longitude = None
        utils.process_arg(self, "longitude", kwargs)

        self.elevation = None
        utils.process_arg(self, "elevation", kwargs)

        self.time_zone = None
        utils.process_arg(self, "time_zone", kwargs)

        self.logfile = None
        utils.process_arg(self, "logfile", kwargs)
        if self.logfile is None:
            self.logfile = "STDOUT"

        self.errfile = None
        utils.process_arg(self, "error_file", kwargs)
        if self.errfile is None:
            self.errfile = "STDERR"

        self.config_file = None
        utils.process_arg(self, "config_file", kwargs)

        self.config_dir = None
        utils.process_arg(self, "config_dir", kwargs)

        self.tick = 1
        utils.process_arg(self, "tick", kwargs, float=True)

        self.max_clock_skew = 1
        utils.process_arg(self, "max_clock_skew", kwargs, int=True)

        self.thread_duration_warning_threshold = 10
        utils.process_arg(self, "thread_duration_warning_threshold", kwargs, float=True)

        self.threadpool_workers = 10
        utils.process_arg(self, "threadpool_workers", kwargs, int=True)

        self.endtime = None
        if "endtime" in kwargs:
            self.endtime = datetime.datetime.strptime(kwargs["endtime"], "%Y-%m-%d %H:%M:%S")

        self.interval = 1
        if kwargs["interval"] is None:
            self.interval = self.tick
        else:
            utils.process_arg(self, "interval", kwargs, float=True)

        self.loglevel = "INFO"
        utils.process_arg(self, "loglevel", kwargs)

        self.api_port = None
        utils.process_arg(self, "api_port", kwargs)

        self.utility_delay = 1
        utils.process_arg(self, "utility_delay", kwargs, int=True)

        self.max_utility_skew = self.utility_delay * 0.9
        utils.process_arg(self, "max_utility_skew", kwargs, float=True)

        self.check_app_updates_profile = False
        utils.process_arg(self, "check_app_updates_profile", kwargs)

        self.production_mode = False
        utils.process_arg(self, "production_mode", kwargs)

        self.invalid_yaml_warnings = True
        utils.process_arg(self, "invalid_yaml_warnings", kwargs)

        self.missing_app_warnings = True
        utils.process_arg(self, "missing_app_warnings", kwargs)

        self.log_thread_actions = False
        utils.process_arg(self, "log_thread_actions", kwargs)

        self.qsize_warning_threshold = 50
        utils.process_arg(self, "qsize_warning_threshold", kwargs, int=True)

        self.qsize_warning_step = 60
        utils.process_arg(self, "qsize_warning_step", kwargs, int=True)

        self.exclude_dirs = ["__pycache__"]
        if "exclude_dirs" in kwargs:
            self.exclude_dirs += kwargs["exclude_dirs"]

        self.stop_function = None
        utils.process_arg(self, "stop_function", kwargs)

        if not kwargs.get("cert_verify", True):
            self.certpath = False

        if kwargs.get("disable_apps") is True:
            self.apps = False
            self.log("INFO", "Apps are disabled")
        else:
            self.apps = True

        if self.apps is True:
            if self.app_dir is None:
                if self.config_dir is None:
                    self.app_dir = utils.find_path("apps")
                    self.config_dir = os.path.dirname(self.app_dir)
                else:
                    self.app_dir = os.path.join(self.config_dir, "apps")

            utils.check_path("config_dir", logger, self.config_dir, permissions="rwx")
            utils.check_path("appdir", logger, self.app_dir)

            # Initialize Apps

            self.app_management = apps.AppManagement(self, kwargs.get("app_config_file", None))

            # threading setup

            self.threading = appdaemon.threading.Threading(self, kwargs)
            self.threading.create_initial_threads()


        self.loop = loop

        self.stopping = False

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.threadpool_workers)

        # Initialize Plugins

        if "plugins" in kwargs:
            self.plugins = plugins.Plugins(self, kwargs["plugins"])

        # Create appq Loop

        if self.apps is True:
            self.appq = appq.AppQ(self)
            loop.create_task(self.appq.loop())

        # Create utility loop

        self.log("DEBUG", "Starting utility loop")

        self.utility = utility.Utility(self)
        loop.create_task(self.utility.loop())

    def stop(self):
        self.stopping = True
        if self.sched is not None:
            self.sched.stop()
        if self.utility is not None:
            self.utility.stop()
        if self.appq is not None:
            self.appq.stop()
        if self.plugins is not None:
            self.plugins.stop()
    #
    # Diagnostics
    #

    def dump_callbacks(self):
        if self.callbacks == {}:
            self.diag("INFO", "No callbacks")
        else:
            self.diag("INFO", "--------------------------------------------------")
            self.diag("INFO", "Callbacks")
            self.diag("INFO", "--------------------------------------------------")
            for name in self.callbacks.keys():
                self.diag("INFO", "{}:".format(name))
                for uuid_ in self.callbacks[name]:
                    self.diag( "INFO", "  {} = {}".format(uuid_, self.callbacks[name][uuid_]))
            self.diag("INFO", "--------------------------------------------------")

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
                callbacks[name][uuid_]["pin_app"] = self.callbacks[name][uuid_]["pin_app"]
                callbacks[name][uuid_]["Pin_thread"] = self.callbacks[name][uuid_]["pin_thread"]
        return callbacks

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
        if self.threading.validate_pin(name, kwargs) is True:
            with self.app_management.objects_lock:
                if "pin" in kwargs:
                    pin_app = kwargs["pin"]
                else:
                    pin_app = self.app_management.objects[name]["pin_app"]

                if "pin_thread" in kwargs:
                    pin_thread = kwargs["pin_thread"]
                    pin_app = True
                else:
                    pin_thread = self.app_management.objects[name]["pin_thread"]


            with self.callbacks_lock:
                if name not in self.callbacks:
                    self.callbacks[name] = {}

                handle = uuid.uuid4()
                with self.app_management.objects_lock:
                    self.callbacks[name][handle] = {
                        "name": name,
                        "id": self.app_management.objects[name]["id"],
                        "type": "state",
                        "function": cb,
                        "entity": entity,
                        "namespace": namespace,
                        "pin_app": pin_app,
                        "pin_thread": pin_thread,
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
                            exec_time = self.sched.get_now_ts() + int(kwargs["duration"])
                            kwargs["__duration"] = self.sched.insert_schedule(
                                name, exec_time, cb, False, None,
                                __entity=entity,
                                __attribute=None,
                                __old_state=None,
                                __new_state=kwargs["new"], **kwargs
                        )

            return handle
        else:
            return None

    def cancel_state_callback(self, handle, name):
        with self.callbacks_lock:
            if name not in self.callbacks or handle not in self.callbacks[name]:
                self.log("WARNING", "Invalid callback in cancel_state_callback() from app {}".format(name))

            if name in self.callbacks and handle in self.callbacks[name]:
                del self.callbacks[name][handle]
            if name in self.callbacks and self.callbacks[name] == {}:
                del self.callbacks[name]

    def info_state_callback(self, handle, name):
        with self.callbacks_lock:
            if name in self.callbacks and handle in self.callbacks[name]:
                callback = self.callbacks[name][handle]
                with self.app_management.objects_lock:
                    return (
                        callback["namespace"],
                        callback["entity"],
                        callback["kwargs"].get("attribute", None),
                        self.sanitize_state_kwargs(self.app_management.objects[name]["object"], callback["kwargs"])
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
                            return deepcopy(self.state[namespace][entity_id])
                        else:
                            return None
                    else:
                        if namespace in self.state and entity_id in self.state[namespace]:
                            if attribute in self.state[namespace][entity_id]["attributes"]:
                                return deepcopy(self.state[namespace][entity_id]["attributes"][
                                    attribute])
                            elif attribute in self.state[namespace][entity_id]:
                                return deepcopy(self.state[namespace][entity_id][attribute])
                            else:
                                    return None
                        else:
                            return None

    def set_state(self, namespace, entity, state):
        with self.state_lock:
            self.state[namespace][entity] = state

    def set_namespace_state(self, namespace, state):
        with self.state_lock:
            self.state[namespace] = state

    def update_namespace_state(self, namespace, state):
        with self.state_lock:
            self.state[namespace].update(state)

    #
    # Events
    #
    def add_event_callback(self, _name, namespace, cb, event, **kwargs):
        with self.app_management.objects_lock:
            if "pin" in kwargs:
                pin_app = kwargs["pin_app"]
            else:
                pin_app = self.app_management.objects[_name]["pin_app"]

            if "pin_thread" in kwargs:
                pin_thread = kwargs["pin_thread"]
                pin_app = True
            else:
                pin_thread = self.app_management.objects[_name]["pin_thread"]

        with self.callbacks_lock:
            if _name not in self.callbacks:
                self.callbacks[_name] = {}
            handle = uuid.uuid4()
            with self.app_management.objects_lock:
                self.callbacks[_name][handle] = {
                    "name": _name,
                    "id": self.app_management.objects[_name]["id"],
                    "type": "event",
                    "function": cb,
                    "namespace": namespace,
                    "event": event,
                    "pin_app": pin_app,
                    "pin_thread": pin_thread,
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
    # State Updates
    #

    def check_and_disapatch(self, name, funcref, entity, attribute, new_state,
                            old_state, cold, cnew, kwargs, uuid_, pin_app, pin_thread):
        executed = False
        kwargs["handle"] = uuid_
        if attribute == "all":
            with self.app_management.objects_lock:
                executed = self.threading.dispatch_worker(name, {
                    "name": name,
                    "id": self.app_management.objects[name]["id"],
                    "type": "attr",
                    "function": funcref,
                    "attribute": attribute,
                    "entity": entity,
                    "new_state": new_state,
                    "old_state": old_state,
                    "pin_app": pin_app,
                    "pin_thread": pin_thread,
                    "kwargs": kwargs,
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
                    exec_time = self.sched.get_now_ts() + int(kwargs["duration"])
                    kwargs["__duration"] = self.sched.insert_schedule(
                        name, exec_time, funcref, False, None,
                        __entity=entity,
                        __attribute=attribute,
                        __old_state=old,
                        __new_state=new, **kwargs
                    )
                else:
                    # Do it now
                    with self.app_management.objects_lock:
                        executed = self.threading.dispatch_worker(name, {
                            "name": name,
                            "id": self.app_management.objects[name]["id"],
                            "type": "attr",
                            "function": funcref,
                            "attribute": attribute,
                            "entity": entity,
                            "new_state": new,
                            "old_state": old,
                            "pin_app": pin_app,
                            "pin_thread": pin_thread,
                            "kwargs": kwargs
                        })
            else:
                if "__duration" in kwargs:
                    # cancel timer
                    self.sched.cancel_timer(name, kwargs["__duration"])

        return executed

    def process_state_change(self, namespace, state):
        data = state["data"]
        entity_id = data['entity_id']
        self.log("DEBUG", data)
        device, entity = entity_id.split(".")

        # Process state callbacks

        removes = []
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

                        executed = False
                        if cdevice is None:
                            executed = self.check_and_disapatch(
                                name, callback["function"], entity_id,
                                cattribute,
                                data['new_state'],
                                data['old_state'],
                                cold, cnew,
                                callback["kwargs"],
                                uuid_,
                                callback["pin_app"],
                                callback["pin_thread"]
                            )
                        elif centity is None:
                            if device == cdevice:
                                executed = self.check_and_disapatch(
                                    name, callback["function"], entity_id,
                                    cattribute,
                                    data['new_state'],
                                    data['old_state'],
                                    cold, cnew,
                                    callback["kwargs"],
                                    uuid_,
                                    callback["pin_app"],
                                    callback["pin_thread"]
                                )

                        elif device == cdevice and entity == centity:
                            executed = self.check_and_disapatch(
                                name, callback["function"], entity_id,
                                cattribute,
                                data['new_state'],
                                data['old_state'], cold,
                                cnew,
                                callback["kwargs"],
                                uuid_,
                                callback["pin_app"],
                                callback["pin_thread"]
                            )

                        # Remove the callback if appropriate
                        if executed is True:
                            remove = callback["kwargs"].get("oneshot", False)
                            if remove is True:
                                #print(callback["kwargs"])
                                #removes.append({"name": callback["name"], "uuid": callback["kwargs"]["handle"]})
                                removes.append({"name": callback["name"], "uuid": uuid_})

            for remove in removes:
                self.cancel_state_callback(remove["uuid"], remove["name"])

    async def state_update(self, namespace, data):
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
                await self.dashboard.ws_update(namespace, data)

        except:
            self.log("WARNING", '-' * 60)
            self.log("WARNING", "Unexpected error during state_update()")
            self.log("WARNING", '-' * 60)
            self.log("WARNING", traceback.format_exc())
            self.log("WARNING", '-' * 60)


    #
    # Event Update
    #

    def process_event(self, namespace, data):
        with self.callbacks_lock:
            for name in self.callbacks.keys():
                for uuid_ in self.callbacks[name]:
                    callback = self.callbacks[name][uuid_]
                    if callback["namespace"] == namespace or callback["namespace"] == "global" or namespace == "global":
                        #
                        # Check for either a blank event (for all events)
                        # Or the event is a mtch
                        # But don't allow a global listen for any system events (events that start with __)
                        #
                        if "event" in callback and (
                                (callback["event"] is None and data['event_type'][:2] != "__")
                                or data['event_type'] == callback["event"]):

                            # Filter out log events to general listens

                            # Check any filters

                            _run = True
                            for key in callback["kwargs"]:
                                if key in data["data"] and callback["kwargs"][key] != \
                                        data["data"][key]:
                                    _run = False
                            if _run:
                                with self.app_management.objects_lock:
                                    if name in self.app_management.objects:
                                        self.threading.dispatch_worker(name, {
                                            "name": name,
                                            "id": self.app_management.objects[name]["id"],
                                            "type": "event",
                                            "event": data['event_type'],
                                            "function": callback["function"],
                                            "data": data["data"],
                                            "pin_app": callback["pin_app"],
                                            "pin_thread": callback["pin_thread"],
                                            "kwargs": callback["kwargs"]
                                        })

    #
    # Utilities
    #

    def sanitize_state_kwargs(self, app, kwargs):
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(kwargs_copy, [
            "old", "new", "__attribute", "duration", "state",
            "__entity", "__duration", "__old_state", "__new_state",
            "oneshot", "pin_app", "pin_thread"
        ] + app.list_constraints())

    def log(self, level, message, name="AppDaemon"):
        if self.sched is not None and not self.sched.is_realtime():
            ts = self.sched.get_now_ts()
        else:
            ts = datetime.datetime.now()
        utils.log(self.logger, level, message, name, ts)

        if level != "DEBUG":
            self.process_log_callback(level, message, name, ts, "log")

    def err(self, level, message, name="AppDaemon"):
        if self.sched is not None and not self.sched.is_realtime():
            ts = self.sched.get_now_ts()
        else:
            ts = datetime.datetime.now()
        utils.log(self.error, level, message, name, ts)

        if level != "DEBUG":
            self.process_log_callback(level, message, name, ts, "error")

    def diag(self, level, message, name="AppDaemon"):
        if self.sched is not None and not self.sched.is_realtime():
            ts = self.sched.get_now_ts()
        else:
            ts = None
        utils.log(self.diagnostic, level, message, name, ts)

        if level != "DEBUG":
            self.process_log_callback(level, message, name, ts, "diag")

    def process_log_callback(self, level, message, name, ts, type):
        # Need to check if this log callback belongs to an app that is accepting log events
        # If so, don't generate the event to avoid loops
        has_log_callback = False
        with self.callbacks_lock:
            for callback in self.callbacks:
                for uuid in self.callbacks[callback]:
                    cb = self.callbacks[callback][uuid]
                    if cb["name"] == name and cb["type"] == "event" and cb["event"] == "__AD_LOG_EVENT":
                        has_log_callback = True

        if has_log_callback is False:
            self.process_event("global", {"event_type": "__AD_LOG_EVENT",
                                          "data": {
                                              "level": level,
                                              "app_name": name,
                                              "message": message,
                                              "ts": ts,
                                              "type": type
                                          }})

    def add_log_callback(self, namespace, name, cb, level, **kwargs):
        # Add a separate callback for each log level
        handle = []
        for thislevel in utils.log_levels:
            if utils.log_levels[thislevel] >= utils.log_levels[level] :
                handle.append(self.add_event_callback(name, namespace, cb, "__AD_LOG_EVENT", level=thislevel, **kwargs))

        return handle

    def cancel_log_callback(self, name, handle):
        for h in handle:
            self.cancel_event_callback(name, h)

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

