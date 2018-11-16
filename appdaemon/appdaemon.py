import sys
import importlib
import traceback
import os
import os.path
from queue import Queue
import datetime
import uuid
import asyncio
import yaml
import concurrent.futures
import threading
import re
from copy import deepcopy, copy
import subprocess
import functools
import time
import cProfile
import io
import pstats
from random import randint
import inspect

import appdaemon.utils as utils
import appdaemon.appq as appq
import appdaemon.utility as utility

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

    required_meta = ["latitude", "longitude", "elevation", "time_zone"]

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
        self.last_plugin_state = {}

        self.monitored_files = {}
        self.filter_files = {}
        self.modules = {}

        self.executor = None
        self.loop = None
        self.srv = None
        self.appd = None
        self.stopping = False
        self.dashboard = None
        self.running_apps = 0

        self.objects = {}
        self.objects_lock = threading.RLock()

        self.callbacks = {}
        self.callbacks_lock = threading.RLock()

        self.thread_info = {}
        self.thread_info_lock = threading.RLock()
        self.thread_info["threads"] = {}
        self.thread_info["current_busy"] = 0
        self.thread_info["max_busy"] = 0
        self.thread_info["max_busy_time"] = 0
        self.thread_info["last_action_time"] = 0

        self.state = {}
        self.state["default"] = {}
        self.state_lock = threading.RLock()

        self.endpoints = {}
        self.endpoints_lock = threading.RLock()

        self.plugin_meta = {}
        self.plugin_objs = {}

        self.global_vars = {}
        self.global_lock = threading.RLock()

        self.config_file_modified = 0

        self.sched = None
        self.appq = None
        self.utility = None

        self.version = 0
        self.app_config_file_modified = 0
        self.app_config = {}

        self.app_config_file = None
        utils.process_arg(self, "app_config_file", kwargs)

        if "plugins" in kwargs:
            self.plugin_params = kwargs["plugins"]
        else:
            self.plugin_params = None

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

        self.plugins = {}
        utils.process_arg(self, "plugins", kwargs)

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

        # Initialize config file tracking

        self.app_config_file_modified = 0
        self.app_config_files = {}
        self.module_dirs = []

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
            #if os.path.isdir(self.app_dir) is False:
            #    self.log("ERROR", "Invalid value for app_dir: {}".format(self.app_dir))
            #    return


            # threading setup

            self.auto_pin = True

            if "threads" in kwargs:
                self.log("WARNING",
                         "Threads directive is deprecated apps - will be pinned. Use total_threads if you want to unpin your apps")

            if "total_threads" in kwargs:
                self.total_threads = kwargs["total_threads"]
                self.auto_pin = False
            else:
                self.total_threads = int(self.check_config(True, False)["total"])

            self.pin_apps = True
            utils.process_arg(self, "pin_apps", kwargs)

            if self.pin_apps is True:
                self.pin_threads = self.total_threads
            else:
                self.auto_pin = False
                self.pin_threads = 0
                if "total_threads" not in kwargs:
                    self.total_threads = 10

            utils.process_arg(self, "pin_threads", kwargs, int=True)

            if self.pin_threads > self.total_threads:
                raise ValueError("pin_threads cannot be > threads")

            if self.pin_threads < 0:
                raise ValueError("pin_threads cannot be < 0")

            self.log("INFO", "Starting Apps with {} workers and {} pins".format(self.total_threads, self.pin_threads))

            self.next_thread = self.pin_threads

            # Create Worker Threads
            self.threads = 0
            for i in range(self.total_threads):
                self.add_thread(True)

            if self.apps is True:
                self.process_filters()

            self.log("DEBUG", "Done")

        self.loop = loop

        self.stopping = False

        self.log("DEBUG", "Entering run()")

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.threadpool_workers)

        # Load Plugins

        # Add Path for adbase

        sys.path.insert(0, os.path.dirname(__file__))

        # Add built in plugins to path

        moddir = "{}/plugins".format(os.path.dirname(__file__))

        plugins = [f.path for f in os.scandir(moddir) if f.is_dir(follow_symlinks=True)]

        for plugin in plugins:
            sys.path.insert(0, plugin)

        # Now custom plugins

        plugins = []

        if os.path.isdir(os.path.join(self.config_dir, "custom_plugins")):
            plugins = [f.path for f in os.scandir(os.path.join(self.config_dir, "custom_plugins")) if f.is_dir(follow_symlinks=True)]

            for plugin in plugins:
                sys.path.insert(0, plugin)

        if self.plugins is not None:
            for name in self.plugins:
                basename = self.plugins[name]["type"]
                type = self.plugins[name]["type"]
                module_name = "{}plugin".format(basename)
                class_name = "{}Plugin".format(basename.capitalize())

                full_module_name = None
                for plugin in plugins:
                    if os.path.basename(plugin) == type:
                        full_module_name = "{}".format(module_name)
                        self.log("INFO",
                                 "Loading Custom Plugin {} using class {} from module {}".format(name, class_name,
                                                                                          module_name))
                        break

                if full_module_name is None:
                    #
                    # Not a custom plugin, assume it's a built in
                    #
                    full_module_name = "{}".format(module_name)
                    self.log("INFO",
                                "Loading Plugin {} using class {} from module {}".format(name, class_name,
                                                                                         module_name))
                try:

                    mod = __import__(full_module_name, globals(), locals(), [module_name], 0)

                    app_class = getattr(mod, class_name)

                    plugin = app_class(self, name, self.logger, self.err, self.loglevel, self.plugins[name])

                    namespace = plugin.get_namespace()

                    if namespace in self.plugin_objs:
                        raise ValueError("Duplicate namespace: {}".format(namespace))

                    self.plugin_objs[namespace] = {"object": plugin, "active": False}

                    loop.create_task(plugin.get_updates())
                except:
                    self.log("WARNING", "error loading plugin: {} - ignoring".format(name))
                    self.log("WARNING", '-' * 60)
                    self.log("WARNING", traceback.format_exc())
                    self.log("WARNING", '-' * 60)


        # Create appq Loop

        if self.apps is True:
            self.appq = appq.AppQ(self)
            loop.create_task(self.appq.loop())

        # Create utility loop

        self.log("DEBUG", "Starting utility loop")

        self.utility = utility.Utility(self)
        loop.create_task(self.utility.loop())

    def add_thread(self, silent=False):
        id = self.threads
        if silent is False:
            self.log("INFO", "Adding thread {}".format(id))
        t = threading.Thread(target=self.worker)
        t.daemon = True
        t.setName("thread-{}".format(id))
        with self.thread_info_lock:
            self.thread_info["threads"][t.getName()] = \
                {"callback": "idle",
                 "time_called": 0,
                 "q": Queue(maxsize=0),
                 "id": id,
                 "thread": t}
        t.start()
        self.threads += 1

    def stop(self):
        self.stopping = True
        if self.sched is not None:
            self.sched.stop()
        if self.utility is not None:
            self.utility.stop()
        if self.appq is not None:
            self.appq.stop()
        for plugin in self.plugin_objs:
            self.plugin_objs[plugin]["object"].stop()

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

    def dump_objects(self):
        self.diag("INFO", "--------------------------------------------------")
        self.diag("INFO", "Objects")
        self.diag("INFO", "--------------------------------------------------")
        with self.objects_lock:
            for object_ in self.objects.keys():
                self.diag("INFO", "{}: {}".format(object_, self.objects[object_]))
        self.diag("INFO", "--------------------------------------------------")

    def q_info(self):
        qsize = 0
        with self.thread_info_lock:
            thread_info = self.get_thread_info()

        for thread in thread_info["threads"]:
            qsize += self.thread_info["threads"][thread]["q"].qsize()
        return {"qsize": qsize, "thread_info": thread_info}

    def min_q_id(self):
        id = 0
        i = 0
        qsize = sys.maxsize
        with self.thread_info_lock:
            for thread in self.thread_info["threads"]:
                if self.thread_info["threads"][thread]["q"].qsize() < qsize:
                    qsize = self.thread_info["threads"][thread]["q"].qsize()
                    id = i
                i += 1
        return id

    @staticmethod
    def atoi(text):
        return int(text) if text.isdigit() else text

    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split('(\d+)', text)]

    def get_pinned_apps(self, thread):
        id = int(thread.split("-")[1])
        apps = []
        with self.objects_lock:
            for obj in self.objects:
                if self.objects[obj]["pin_thread"] == id:
                    apps.append(obj)
        return apps

    def get_thread_info(self):
        info = {}
        # Make a copy without the thread objects
        with self.thread_info_lock:
            info["max_busy_time"] = copy(self.thread_info["max_busy_time"])
            info["last_action_time"] = copy(self.thread_info["last_action_time"])
            info["current_busy"] = copy(self.thread_info["current_busy"])
            info["max_busy"] = copy(self.thread_info["max_busy"])
            info["threads"] = {}
            for thread in self.thread_info["threads"]:
                if thread not in info["threads"]:
                    info["threads"][thread] = {}
                info["threads"][thread]["time_called"] = copy(self.thread_info["threads"][thread]["time_called"])
                info["threads"][thread]["callback"] = copy(self.thread_info["threads"][thread]["callback"])
                info["threads"][thread]["is_alive"] = copy(self.thread_info["threads"][thread]["thread"].is_alive())
                info["threads"][thread]["pinned_apps"] = copy(self.get_pinned_apps(thread))
                info["threads"][thread]["qsize"] = copy(self.thread_info["threads"][thread]["q"].qsize())
        return info

    def dump_threads(self, qinfo):
        thread_info = qinfo["thread_info"]
        self.diag("INFO", "--------------------------------------------------")
        self.diag("INFO", "Threads")
        self.diag("INFO", "--------------------------------------------------")
        max_ts = datetime.datetime.fromtimestamp(thread_info["max_busy_time"])
        last_ts = datetime.datetime.fromtimestamp(thread_info["last_action_time"])
        self.diag("INFO", "Currently busy threads: {}".format(thread_info["current_busy"]))
        self.diag("INFO", "Most used threads: {} at {}".format(thread_info["max_busy"], max_ts))
        self.diag("INFO", "Last activity: {}".format(last_ts))
        self.diag("INFO", "Total Q Entries: {}".format(qinfo["qsize"]))
        self.diag("INFO", "--------------------------------------------------")
        for thread in sorted(thread_info["threads"], key=self.natural_keys):
            ts = datetime.datetime.fromtimestamp(thread_info["threads"][thread]["time_called"])
            self.diag("INFO",
                     "{} - qsize: {} | current callback: {} | since {}, | alive: {}, | pinned apps: {}".format(
                         thread,
                         thread_info["threads"][thread]["qsize"],
                         thread_info["threads"][thread]["callback"],
                         ts,
                         thread_info["threads"][thread]["is_alive"],
                         self.get_pinned_apps(thread)
                     ))
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
            if not self.sched.now_is_between(start_time, end_time, name):
                unconstrained = False

        return unconstrained

    #
    # Thread Management
    #

    def dispatch_worker(self, name, args):
        with self.objects_lock:
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
            self.select_q(args)
            return True
        else:
            return False

    def select_q(self, args):
        #
        # Select Q based on distribution method:
        #   Round Robin
        #   Random
        #   Load distribution
        #

        # Check for pinned app and if so figure correct thread for app

        if args["pin_app"] is True:
            thread = args["pin_thread"]
            # Handle the case where an App is unpinned but selects a pinned callback without specifying a thread
            # If this happens a lot, thread 0 might get congested but the alternatives are worse!
            if thread == -1:
                self.log("WARNING", "Invalid thread ID for pinned thread in app: {} - assigning to thread 0".format(args["name"]))
                thread = 0
        else:
            if self.threads == self.pin_threads:
                raise ValueError("pin_threads must be set lower than threads if unpinned_apps are in use")
            if self.load_distribution == "load":
                thread = self.min_q_id()
            elif self.load_distribution == "random":
                thread = randint(self.pin_threads, self.threads - 1)
            else:
                # Round Robin is the catch all
                thread = self.next_thread
                self.next_thread += 1
                if self.next_thread == self.threads:
                    self.next_thread = self.pin_threads

        if thread < 0 or thread >= self.threads:
            raise ValueError("invalid thread id: {} in app {}".format(thread, args["name"]))

        with self.thread_info_lock:
            id = "thread-{}".format(thread)
            q = self.thread_info["threads"][id]["q"]
            q.put_nowait(args)

    def check_overdue_threads(self):
        if self.thread_duration_warning_threshold != 0:
            for thread_id in self.thread_info["threads"]:
                if self.thread_info["threads"][thread_id]["callback"] != "idle":
                    start = self.thread_info["threads"][thread_id]["time_called"]
                    dur = self.sched.get_now_ts() - start
                    if dur >= self.thread_duration_warning_threshold and dur % self.thread_duration_warning_threshold == 0:
                        self.log("WARNING", "Excessive time spent in callback: {} - {}s".format
                        (self.thread_info["threads"][thread_id]["callback"], dur))

    def check_q_size(self, warning_step):
        qinfo = self.q_info()
        if qinfo["qsize"] > self.qsize_warning_threshold:
            if warning_step == 0:
                self.log("WARNING", "Queue size is {}, suspect thread starvation".format(qinfo["qsize"]))
                self.dump_threads(qinfo)
            warning_step += 1
            if warning_step >= self.qsize_warning_step:
                warning_step = 0
        else:
            warning_step = 0

        return warning_step

    #
    # Pinning
    #

    def calculate_pin_threads(self):

        if self.pin_threads == 0:
            return

        thread_pins = [0] * self.pin_threads
        with self.objects_lock:
            for name in self.objects:
                # Looking for apps that already have a thread pin value
                if self.get_app_pin(name) and self.get_pin_thread(name) != -1:
                    thread = self.get_pin_thread(name)
                    if thread >= self.threads:
                        raise ValueError("Pinned thread out of range - check apps.yaml for 'pin_thread' or app code for 'set_pin_thread()'")
                    # Ignore anything outside the pin range as it will have been set by the user
                    if thread < self.pin_threads:
                        thread_pins[thread] += 1

            # Now we know the numbers, go fill in the gaps

            for name in self.objects:
                if self.get_app_pin(name) and self.get_pin_thread(name) == -1:
                    thread = thread_pins.index(min(thread_pins))
                    self.set_pin_thread(name, thread)
                    thread_pins[thread] += 1

    def app_should_be_pinned(self, name):
        # Check apps.yaml first - allow override
        app = self.app_config[name]
        if "pin_app" in app:
            return app["pin_app"]

        # if not, go with the global default
        return self.pin_apps

    def get_app_pin(self, name):
        with self.objects_lock:
            return self.objects[name]["pin_app"]

    def set_app_pin(self, name, pin):
        with self.objects_lock:
            self.objects[name]["pin_app"] = pin
        if pin is True:
            # May need to set this app up with a pinned thread
            self.calculate_pin_threads()

    def get_pin_thread(self, name):
        with self.objects_lock:
            return self.objects[name]["pin_thread"]

    def set_pin_thread(self, name, thread):
        with self.objects_lock:
            self.objects[name]["pin_thread"] = thread

    def validate_pin(self, name, kwargs):
        if "pin_thread" in kwargs:
            if kwargs["pin_thread"] < 0 or kwargs["pin_thread"] >= self.threads:
                self.log("WARNING", "Invalid value for pin_thread ({}) in app: {} - discarding callback".format(kwargs["pin_thread"], name))
                return False
        else:
            return True

    def update_thread_info(self, thread_id, callback, type = None):
        if self.log_thread_actions:
            if callback == "idle":
                self.diag("INFO",
                         "{} done".format(thread_id, type, callback))
            else:
                self.diag("INFO",
                         "{} calling {} callback {}".format(thread_id, type, callback))

        with self.thread_info_lock:
            ts = self.sched.get_now_ts()
            if callback == "idle":
                start = self.thread_info["threads"][thread_id]["time_called"]
                if ts - start >= self.thread_duration_warning_threshold:
                    self.log("WARNING", "callback {} has now completed".format(self.thread_info["threads"][thread_id]["callback"]))
            self.thread_info["threads"][thread_id]["callback"] = callback
            self.thread_info["threads"][thread_id]["time_called"] = ts
            if callback == "idle":
                self.thread_info["current_busy"] -= 1
            else:
                self.thread_info["current_busy"] += 1

            if self.thread_info["current_busy"] > self.thread_info["max_busy"]:
                self.thread_info["max_busy"] = self.thread_info["current_busy"]
                self.thread_info["max_busy_time"] = ts

            self.thread_info["last_action_time"] = ts

    # noinspection PyBroadException
    def worker(self):
        while True:
            thread_id = threading.current_thread().name
            with self.thread_info_lock:
                q = self.thread_info["threads"][thread_id]["q"]
            args = q.get()
            _type = args["type"]
            funcref = args["function"]
            _id = args["id"]
            name = args["name"]
            args["kwargs"]["__thread_id"] = thread_id
            callback = "{}() in {}".format(funcref.__name__, name)
            app = None
            with self.objects_lock:
                if name in self.objects and self.objects[name]["id"] == _id:
                    app = self.objects[name]["object"]
            if app is not None:
                try:
                    if _type == "timer":
                        if self.validate_callback_sig(name, "timer", funcref):
                            self.update_thread_info(thread_id, callback, _type)
                            funcref(self.sched.sanitize_timer_kwargs(app, args["kwargs"]))
                    elif _type == "attr":
                        if self.validate_callback_sig(name, "attr", funcref):
                            entity = args["entity"]
                            attr = args["attribute"]
                            old_state = args["old_state"]
                            new_state = args["new_state"]
                            self.update_thread_info(thread_id, callback, _type)
                            funcref(entity, attr, old_state, new_state,
                                    self.sanitize_state_kwargs(app, args["kwargs"]))
                    elif _type == "event":
                        data = args["data"]
                        if args["event"] == "__AD_LOG_EVENT":
                            if self.validate_callback_sig(name, "log_event", funcref):
                                self.update_thread_info(thread_id, callback, _type)
                                funcref(data["app_name"], data["ts"], data["level"], data["type"], data["message"], args["kwargs"])
                        else:
                            if self.validate_callback_sig(name, "event", funcref):
                                self.update_thread_info(thread_id, callback, _type)
                                funcref(args["event"], data, args["kwargs"])
                except:
                    self.err("WARNING", '-' * 60, name=name)
                    self.err("WARNING", "Unexpected error in worker for App {}:".format(name), name=name)
                    self.err("WARNING", "Worker Ags: {}".format(args), name=name)
                    self.err("WARNING", '-' * 60, name=name)
                    self.err("WARNING", traceback.format_exc(), name=name)
                    self.err("WARNING", '-' * 60, name=name)
                    if self.errfile != "STDERR" and self.logfile != "STDOUT":
                        self.log("WARNING", "Logged an error to {}".format(self.errfile), name=name)
                finally:
                    self.update_thread_info(thread_id, "idle")
            else:
                self.log("WARNING", "Found stale callback for {} - discarding".format(name), name=name)

            q.task_done()

    def validate_callback_sig(self, name, type, funcref):

        callback_args = {
            "timer": {"count": 1, "signature": "f(self, kwargs)"},
            "attr": {"count": 5, "signature": "f(self, entity, attribute, old, new, kwargs)"},
            "event": {"count": 3, "signature": "f(self, event, data, kwargs)"},
            "log_event": {"count": 6, "signature": "f(self, name, ts, level, type, message, kwargs)"},
            "initialize": {"count": 0, "signature": "initialize()"}
        }

        sig = inspect.signature(funcref)

        if type in callback_args:
            if len(sig.parameters) != callback_args[type]["count"]:
                self.log("WARNING", "Incorrect signature type for callback {}(), should be {} - discarding".format(funcref.__name__, callback_args[type]["signature"]), name=name)
                return False
            else:
                return True
        else:
            self.log("ERROR", "Unknown callback type: {}".format(type), name=name)

        return False
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
        if self.validate_pin(name, kwargs) is True:
            with self.objects_lock:
                if "pin" in kwargs:
                    pin_app = kwargs["pin"]
                else:
                    pin_app = self.objects[name]["pin_app"]

                if "pin_thread" in kwargs:
                    pin_thread = kwargs["pin_thread"]
                    pin_app = True
                else:
                    pin_thread = self.objects[name]["pin_thread"]


            with self.callbacks_lock:
                if name not in self.callbacks:
                    self.callbacks[name] = {}

                handle = uuid.uuid4()
                with self.objects_lock:
                    self.callbacks[name][handle] = {
                        "name": name,
                        "id": self.objects[name]["id"],
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
                with self.objects_lock:
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

    #
    # Events
    #
    def add_event_callback(self, _name, namespace, cb, event, **kwargs):
        with self.objects_lock:
            if "pin" in kwargs:
                pin_app = kwargs["pin_app"]
            else:
                pin_app = self.objects[_name]["pin_app"]

            if "pin_thread" in kwargs:
                pin_thread = kwargs["pin_thread"]
                pin_app = True
            else:
                pin_thread = self.objects[_name]["pin_thread"]

        with self.callbacks_lock:
            if _name not in self.callbacks:
                self.callbacks[_name] = {}
            handle = uuid.uuid4()
            with self.objects_lock:
                self.callbacks[_name][handle] = {
                    "name": _name,
                    "id": self.objects[_name]["id"],
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
    # Plugin Stuff
    #

    def run_plugin_utility(self):
        for plugin in self.plugin_objs:
            self.plugin_objs[plugin]["object"].utility()

    def process_meta(self, meta, namespace):

        if meta is not None:
            for key in self.required_meta:
                if getattr(self, key) == None:
                    if key in meta:
                        # We have a value so override
                        setattr(self, key, meta[key])

    def get_plugin_from_namespace(self, namespace):
        if self.plugins is not None:
            for name in self.plugins:
                if "namespace" in self.plugins[name] and self.plugins[name]["namespace"] == namespace:
                    return name
                if "namespace" not in self.plugins[name] and namespace == "default":
                    return name
        else:
            return None

    async def notify_plugin_started(self, name, namespace, meta, state, first_time=False):
        self.log("DEBUG", "Plugin started: {}".format(name))
        try:
            self.last_plugin_state[namespace] = datetime.datetime.now()

            self.log("DEBUG", "Plugin started meta: {} = {}".format(name, meta))

            self.process_meta(meta, namespace)

            if not self.stopping:
                self.plugin_meta[namespace] = meta

                with self.state_lock:
                    self.state[namespace]= state

                if not first_time:
                    await utils.run_in_executor(self.loop, self.executor, self.check_app_updates, self.get_plugin_from_namespace(namespace))
                else:
                    self.log("INFO", "Got initial state from namespace {}".format(namespace))

                self.plugin_objs[namespace]["active"] = True
                self.process_event(namespace, {"event_type": "plugin_started", "data": {"name": name}})
        except:
            self.err("WARNING", '-' * 60)
            self.err("WARNING", "Unexpected error during notify_plugin_started()")
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

    def notify_plugin_stopped(self, name, namespace):
        self.plugin_objs[namespace]["active"] = False
        self.process_event(namespace, {"event_type": "plugin_stopped", "data": {"name": name}})


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
        with self.objects_lock:
            if name in self.objects:
                return self.objects[name]["object"]
            else:
                return None

    def initialize_app(self, name):
        with self.objects_lock:
            if name in self.objects:
                init = getattr(self.objects[name]["object"], "initialize", None)
                if init == None:
                    self.log("WARNING", "Unable to find initialize() function in module {} - skipped".format(name))
                    return
            else:
                self.log("WARNING", "Unable to find module {} - initialize() skipped".format(name))
                return
        # Call its initialize function

        try:
            if self.validate_callback_sig(name, "initialize", init):
                init()
        except:
            self.err("WARNING", '-' * 60)
            self.err("WARNING", "Unexpected error running initialize() for {}".format(name))
            self.err("WARNING", '-' * 60)
            self.err("WARNING", traceback.format_exc())
            self.err("WARNING", '-' * 60)
            if self.errfile != "STDERR" and self.logfile != "STDOUT":
                self.log("WARNING", "Logged an error to {}".format(self.errfile))

    def term_object(self, name):
        with self.objects_lock:
            term = None
            if name in self.objects and hasattr(self.objects[name]["object"], "terminate"):
                self.log("INFO", "Calling terminate() for {}".format(name))
                # Call terminate directly rather than via worker thread
                # so we know terminate has completed before we move on

                term = self.objects[name]["object"].terminate

        if term is not None:
            try:
                term()
            except:
                self.err("WARNING", '-' * 60)
                self.err("WARNING", "Unexpected error running terminate() for {}".format(name))
                self.err("WARNING", '-' * 60)
                self.err("WARNING", traceback.format_exc())
                self.err("WARNING", '-' * 60)
                if self.errfile != "STDERR" and self.logfile != "STDOUT":
                    self.log("WARNING", "Logged an error to {}".format(self.errfile))

        with self.objects_lock:
            if name in self.objects:
                del self.objects[name]

        self.log("DEBUG", "Clearing callbacks for {}".format(name))
        with self.callbacks_lock:
            if name in self.callbacks:
                del self.callbacks[name]

        self.sched.term_object(name)

        with self.endpoints_lock:
            if name in self.endpoints:
                del self.endpoints[name]

    def init_object(self, name):
        app_args = self.app_config[name]
        self.log("INFO",
                  "Initializing app {} using class {} from module {}".format(name, app_args["class"], app_args["module"]))

        if self.get_file_from_module(app_args["module"]) is not None:

            with self.objects_lock:
                if "pin_thread" in app_args:
                    if app_args["pin_thread"] < 0 or app_args["pin_thread"] >= self.threads:
                        self.log("WARNING", "pin_thread out of range ({}) in app definition for {} - app will be discarded".format(app_args["pin_thread"], name))
                        return
                    else:
                        pin = app_args["pin_thread"]
                else:
                    pin = -1

                modname = __import__(app_args["module"])
                app_class = getattr(modname, app_args["class"])
                self.objects[name] = {
                    "object": app_class(
                        self, name, self.logger, self.error, app_args, self.config, self.app_config, self.global_vars
                    ),
                    "id": uuid.uuid4(),
                    "pin_app": self.app_should_be_pinned(name),
                    "pin_thread": pin
                }

        else:
            self.log("WARNING", "Unable to find module module {} - {} is not initialized".format(app_args["module"], name))

    def read_config(self):

        new_config = None

        if os.path.isfile(self.app_config_file):
            self.log("WARNING", "apps.yaml in the Config directory is deprecated. Please move apps.yaml to the apps directory.")
            new_config = self.read_config_file(self.app_config_file)
        else:
            for root, subdirs, files in os.walk(self.app_dir):
                subdirs[:] = [d for d in subdirs if d not in self.exclude_dirs]
                if root[-11:] != "__pycache__":
                    for file in files:
                        if file[-5:] == ".yaml":
                            self.log("DEBUG", "Reading {}".format(os.path.join(root, file)))
                            config = self.read_config_file(os.path.join(root, file))
                            valid_apps = {}
                            if type(config).__name__ == "dict":
                                for app in config:
                                    if config[app] is not None:
                                        if app == "global_modules":
                                            valid_apps[app] = config[app]
                                        elif "class" in config[app] and "module" in config[app]:
                                            valid_apps[app] = config[app]
                                        else:
                                            if self.invalid_yaml_warnings:
                                                self.log("WARNING",
                                                         "App '{}' missing 'class' or 'module' entry - ignoring".format(app))
                            else:
                                if self.invalid_yaml_warnings:
                                    self.log("WARNING",
                                             "File '{}' invalid structure - ignoring".format(os.path.join(root, file)))

                            if new_config is None:
                                new_config = {}
                            for app in valid_apps:
                                if app in new_config:
                                    self.log("WARNING",
                                             "File '{}' duplicate app: {} - ignoring".format(os.path.join(root, file), app))
                                else:
                                    new_config[app] = valid_apps[app]

        return new_config

    def check_later_app_configs(self, last_latest):
        if os.path.isfile(self.app_config_file):
            ts = os.path.getmtime(self.app_config_file)
            return {"latest": ts, "files": [{"name": self.app_config_file, "ts": os.path.getmtime(self.app_config_file)}]}
        else:
            later_files = {}
            app_config_files = []
            later_files["files"] = []
            later_files["latest"] = last_latest
            later_files["deleted"] = []
            for root, subdirs, files in os.walk(self.app_dir):
                subdirs[:] = [d for d in subdirs if d not in self.exclude_dirs]
                if root[-11:] != "__pycache__":
                    for file in files:
                        if file[-5:] == ".yaml":
                            path = os.path.join(root, file)
                            app_config_files.append(path)
                            ts = os.path.getmtime(path)
                            if ts > last_latest:
                                later_files["files"].append(path)
                            if ts > later_files["latest"]:
                                later_files["latest"] = ts

            for file in self.app_config_files:
                if file not in app_config_files:
                    later_files["deleted"].append(file)

            if self.app_config_files != {}:
                for file in app_config_files:
                    if file not in self.app_config_files:
                        later_files["files"].append(file)

            self.app_config_files = app_config_files

            return later_files

    def read_config_file(self, file):

        new_config = None
        try:
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

        except:
            self.err("WARNING", '-' * 60)
            self.err("WARNING", "Unexpected error loading config file: {}".format(file))
            self.err("WARNING", '-' * 60)
            self.err("WARNING", traceback.format_exc())
            self.err("WARNING", '-' * 60)
            if self.errfile != "STDERR" and self.logfile != "STDOUT":
                self.log("WARNING", "Logged an error to {}".format(self.errfile))

    # noinspection PyBroadException
    def check_config(self, silent=False, add_threads=True):

        terminate_apps = {}
        initialize_apps = {}
        new_config = {}
        total_apps = len(self.app_config)

        try:
            latest = self.check_later_app_configs(self.app_config_file_modified)
            self.app_config_file_modified = latest["latest"]

            if latest["files"] or latest["deleted"]:
                if silent is False:
                    self.log("INFO", "Reading config")
                new_config = self.read_config()
                if new_config is None:
                    if silent is False:
                        self.log("WARNING", "New config not applied")
                    return

                for file in latest["deleted"]:
                    if silent is False:
                        self.log("INFO", "{} deleted".format(file))

                for file in latest["files"]:
                    if silent is False:
                        self.log("INFO", "{} added or modified".format(file))

                # Check for changes

                for name in self.app_config:
                    if name in new_config:
                        if self.app_config[name] != new_config[name]:
                            # Something changed, clear and reload

                            if silent is False:
                                self.log("INFO", "App '{}' changed".format(name))
                            terminate_apps[name] = 1
                            initialize_apps[name] = 1
                    else:

                        # Section has been deleted, clear it out

                        if silent is False:
                            self.log("INFO", "App '{}' deleted".format(name))
                        #
                        # Since the entry has been deleted we can't sensibly determine dependencies
                        # So just immediately terminate it
                        #
                        self.term_object(name)

                for name in new_config:
                    if name not in self.app_config:
                        #
                        # New section added!
                        #
                        if "class" in new_config[name] and "module" in new_config[name]:
                            self.log("INFO", "App '{}' added".format(name))
                            initialize_apps[name] = 1
                        elif name == "global_modules":
                            pass
                        else:
                            if self.invalid_yaml_warnings:
                                if silent is False:
                                    self.log("WARNING", "App '{}' missing 'class' or 'module' entry - ignoring".format(name))

                self.app_config = new_config
                total_apps = len(self.app_config)

                if silent is False:
                    self.log("INFO", "Running {} apps".format(total_apps))

            # Now we know if we have any new apps we can create new threads if pinning

            if add_threads is True and self.auto_pin is True:
                if total_apps > self.threads:
                    for i in range(total_apps - self.threads):
                        self.add_thread(False)
                    self.pin_threads = self.threads

            return {"init": initialize_apps, "term": terminate_apps, "total": total_apps}
        except:
            self.err("WARNING", '-' * 60)
            self.err("WARNING", "Unexpected error:")
            self.err("WARNING", '-' * 60)
            self.err("WARNING", traceback.format_exc())
            self.err("WARNING", '-' * 60)
            if self.errfile != "STDERR" and self.logfile != "STDOUT":
                self.log("WARNING", "Logged an error to {}".format(self.errfile))

    def get_app_from_file(self, file):
        module = self.get_module_from_path(file)
        for app in self.app_config:
            if "module" in self.app_config[app] and self.app_config[app]["module"] == module:
                return app
        return None

    # noinspection PyBroadException
    def read_app(self, file, reload=False):
        name = os.path.basename(file)
        module_name = os.path.splitext(name)[0]
        # Import the App
        if reload:
            self.log("INFO", "Reloading Module: {}".format(file))

            file, ext = os.path.splitext(name)
            #
            # Reload
            #
            try:
                importlib.reload(self.modules[module_name])
            except KeyError:
                if name not in sys.modules:
                    # Probably failed to compile on initial load
                    # so we need to re-import not reload
                    self.read_app(file)
                else:
                    # A real KeyError!
                    raise
        else:
            app = self.get_app_from_file(file)
            if app is not None:
                self.log("INFO", "Loading App Module: {}".format(file))
                if module_name not in self.modules:
                    self.modules[module_name] = importlib.import_module(module_name)
                else:
                    # We previously imported it so we need to reload to pick up any potential changes
                    importlib.reload(self.modules[module_name])

            elif "global_modules" in self.app_config and module_name in self.app_config["global_modules"]:
                self.log("INFO", "Loading Global Module: {}".format(file))
                self.modules[module_name] = importlib.import_module(module_name)
            else:
                if self.missing_app_warnings:
                    self.log("WARNING", "No app description found for: {} - ignoring".format(file))


    @staticmethod
    def get_module_from_path(path):
        name = os.path.basename(path)
        module_name = os.path.splitext(name)[0]
        return module_name

    def get_file_from_module(self, mod):
        for file in self.monitored_files:
            module_name = self.get_module_from_path(file)
            if module_name == mod:
                return file

        return None

    def process_filters(self):
        if "filters" in self.config:
            for filter in self.config["filters"]:

                for root, subdirs, files in os.walk(self.app_dir, topdown=True):
                    # print(root, subdirs, files)
                    #
                    # Prune dir list
                    #
                    subdirs[:] = [d for d in subdirs if d not in self.exclude_dirs]

                    ext = filter["input_ext"]
                    extlen = len(ext) * -1

                    for file in files:
                        run = False
                        if file[extlen:] == ext:
                            infile = os.path.join(root, file)
                            modified = os.path.getmtime(infile)
                            if infile in self.filter_files:
                                if self.filter_files[infile] < modified:
                                    run = True
                            else:
                                self.log("INFO", "Found new filter file {}".format(infile))
                                run = True

                            if run is True:
                                self.log("INFO", "Running filter on {}".format(infile))
                                self.filter_files[infile] = modified

                                # Run the filter

                                outfile = utils.rreplace(infile, ext, filter["output_ext"], 1)
                                command_line = filter["command_line"].replace("$1", infile)
                                command_line = command_line.replace("$2", outfile)
                                try:
                                    p = subprocess.Popen(command_line, shell=True)
                                except:
                                    self.log("WARNING", '-' * 60)
                                    self.log("WARNING", "Unexpected running filter on: {}:".format(infile))
                                    self.log("WARNING", '-' * 60)
                                    self.log("WARNING", traceback.format_exc())
                                    self.log("WARNING", '-' * 60)

    @staticmethod
    def file_in_modules(file, modules):
        for mod in modules:
            if mod["name"] == file:
                return True
        return False

    #@_timeit
    def check_app_updates(self, plugin=None, exit=False):

        if self.apps is False:
            return

        # Lets add some profiling
        pr = None
        if self.check_app_updates_profile is True:
            pr = cProfile.Profile()
            pr.enable()

        # Process filters

        self.process_filters()

        # Get list of apps we need to terminate and/or initialize

        apps = self.check_config()

        found_files = []
        modules = []
        for root, subdirs, files in os.walk(self.app_dir, topdown=True):
            # print(root, subdirs, files)
            #
            # Prune dir list
            #
            subdirs[:] = [d for d in subdirs if d not in self.exclude_dirs]

            if root[-11:] != "__pycache__":
                if root not in self.module_dirs:
                    self.log("INFO", "Adding {} to module import path".format(root))
                    sys.path.insert(0, root)
                    self.module_dirs.append(root)

            for file in files:
                if file[-3:] == ".py":
                    found_files.append(os.path.join(root, file))

        for file in found_files:
            if file == os.path.join(self.app_dir, "__init__.py"):
                continue
            try:

                # check we can actually open the file

                fh = open(file)
                fh.close()

                modified = os.path.getmtime(file)
                if file in self.monitored_files:
                    if self.monitored_files[file] < modified:
                        modules.append({"name": file, "reload": True})
                        self.monitored_files[file] = modified
                else:
                    self.log("DEBUG", "Found module {}".format(file))
                    modules.append({"name": file, "reload": False})
                    self. monitored_files[file] = modified
            except IOError as err:
                self.log("WARNING",
                         "Unable to read app {}: {} - skipping".format(file, err))

        # Check for deleted modules and add them to the terminate list
        deleted_modules = []
        for file in self.monitored_files:
            if file not in found_files or exit is True:
                deleted_modules.append(file)
                self.log("INFO", "Removing module {}".format(file))

        for file in deleted_modules:
            del self.monitored_files[file]
            for app in self.apps_per_module(self.get_module_from_path(file)):
                apps["term"][app] = 1

        # Add any apps we need to reload because of file changes

        for module in modules:
            for app in self.apps_per_module(self.get_module_from_path(module["name"])):
                if module["reload"]:
                    apps["term"][app] = 1
                apps["init"][app] = 1

            if "global_modules" in self.app_config:
                for gm in utils.single_or_list(self.app_config["global_modules"]):
                    if gm == self.get_module_from_path(module["name"]):
                        for app in self.apps_per_global_module(gm):
                            if module["reload"]:
                                apps["term"][app] = 1
                            apps["init"][app] = 1

        if plugin is not None:
            self.log("INFO", "Processing restart for {}".format(plugin))
            # This is a restart of one of the plugins so check which apps need to be restarted
            for app in self.app_config:
                reload = False
                if app == "global_modules":
                    continue
                if "plugin" in self.app_config[app]:
                    for this_plugin in utils.single_or_list(self.app_config[app]["plugin"]):
                        if this_plugin == plugin:
                            # We got a match so do the reload
                            reload = True
                            break
                        elif plugin == "__ALL__":
                            reload = True
                            break
                else:
                    # No plugin dependency specified, reload to err on the side of caution
                    reload = True

                if reload is True:
                    apps["term"][app] = 1
                    apps["init"][app] = 1

        # Terminate apps

        if apps is not None and apps["term"]:

            prio_apps = self.get_app_deps_and_prios(apps["term"])

            for app in sorted(prio_apps, key=prio_apps.get, reverse=True):
                try:
                    self.log("INFO", "Terminating {}".format(app))
                    self.term_object(app)
                except:
                    self.err("WARNING", '-' * 60)
                    self.err("WARNING", "Unexpected error terminating app: {}:".format(app))
                    self.err("WARNING", '-' * 60)
                    self.err("WARNING", traceback.format_exc())
                    self.err("WARNING", '-' * 60)
                    if self.errfile != "STDERR" and self.logfile != "STDOUT":
                        self.log("WARNING", "Logged an error to {}".format(self.errfile))


        # Load/reload modules

        for mod in modules:
            try:
                self.read_app(mod["name"], mod["reload"])
            except:
                self.err("WARNING", '-' * 60)
                self.err("WARNING", "Unexpected error loading module: {}:".format(mod["name"]))
                self.err("WARNING", '-' * 60)
                self.err("WARNING", traceback.format_exc())
                self.err("WARNING", '-' * 60)
                if self.errfile != "STDERR" and self.logfile != "STDOUT":
                    self.log("WARNING", "Unexpected error loading module: {}:".format(mod["name"]))
                self.log("WARNING", "Removing associated apps:")
                module = self.get_module_from_path(mod["name"])
                for app in self.app_config:
                    if self.app_config[app]["module"] == module:
                        if apps["init"] and app in apps["init"]:
                            del apps["init"][app]
                            self.log("WARNING", "{}".format(app))

        if apps is not None and apps["init"]:

            prio_apps = self.get_app_deps_and_prios(apps["init"])

            # Load Apps

            for app in sorted(prio_apps, key=prio_apps.get):
                try:
                    self.init_object(app)
                except:
                    self.err("WARNING", '-' * 60)
                    self.err("WARNING", "Unexpected error initializing app: {}:".format(app))
                    self.err("WARNING", '-' * 60)
                    self.err("WARNING", traceback.format_exc())
                    self.err("WARNING", '-' * 60)
                    if self.errfile != "STDERR" and self.logfile != "STDOUT":
                        self.log("WARNING", "Logged an error to {}".format(self.errfile))

            self.calculate_pin_threads()

            # Call initialize() for apps

            for app in sorted(prio_apps, key=prio_apps.get):
                self.initialize_app(app)

        if self.check_app_updates_profile is True:
            pr.disable()

        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats()
        self.check_app_updates_profile_stats = s.getvalue()

    def get_app_deps_and_prios(self, applist):

        # Build a list of modules and their dependencies

        deplist = []
        for app in applist:
            if app not in deplist:
                deplist.append(app)
            self.get_dependent_apps(app, deplist)

        # Need to gove the topological sort a full list of apps or it will fail
        full_list = list(self.app_config.keys())

        deps = []

        for app in full_list:
            dependees = []
            if "dependencies" in self.app_config[app]:
                for dep in utils.single_or_list(self.app_config[app]["dependencies"]):
                    if dep in self.app_config:
                        dependees.append(dep)
                    else:
                        self.log("WARNING", "Unable to find app {} in dependencies for {}".format(dep, app))
                        self.log("WARNING", "Ignoring app {}".format(app))
            deps.append((app, dependees))

        prio_apps = {}
        prio = float(50.1)
        try:
            for app in self.topological_sort(deps):
                if "dependencies" in self.app_config[app] or self.app_has_dependents(app):
                    prio_apps[app] = prio
                    prio += float(0.0001)
                else:
                    if "priority" in self.app_config[app]:
                        prio_apps[app] = float(self.app_config[app]["priority"])
                    else:
                        prio_apps[app] = float(50)
        except ValueError:
            pass

        # now we remove the ones we aren't interested in

        final_apps = {}
        for app in prio_apps:
            if app in deplist:
                final_apps[app] = prio_apps[app]

        return final_apps

    def app_has_dependents(self, name):
        for app in self.app_config:
            if "dependencies" in self.app_config[app]:
                for dep in utils.single_or_list(self.app_config[app]["dependencies"]):
                    if dep == name:
                        return True
        return False

    def get_dependent_apps(self, dependee, deps):
        for app in self.app_config:
            if "dependencies" in self.app_config[app]:
                for dep in utils.single_or_list(self.app_config[app]["dependencies"]):
                    #print("app= {} dep = {}, dependee = {} deps = {}".format(app, dep, dependee, deps))
                    if dep == dependee and app not in deps:
                        deps.append(app)
                        new_deps = self.get_dependent_apps(app, deps)
                        if new_deps is not None:
                            deps.append(new_deps)

    def topological_sort(self, source):

        pending = [(name, set(deps)) for name, deps in source]  # copy deps so we can modify set in-place
        emitted = []
        while pending:
            next_pending = []
            next_emitted = []
            for entry in pending:
                name, deps = entry
                deps.difference_update(emitted)  # remove deps we emitted last pass
                if deps:  # still has deps? recheck during next pass
                    next_pending.append(entry)
                else:  # no more deps? time to emit
                    yield name
                    emitted.append(name)  # <-- not required, but helps preserve original ordering
                    next_emitted.append(name)  # remember what we emitted for difference_update() in next pass
            if not next_emitted:
                # all entries have unmet deps, we have cyclic redundancies
                # since we already know all deps are correct
                self.log("WARNING", "Cyclic or missing app dependencies detected")
                for pend in next_pending:
                    deps = ""
                    for dep in pend[1]:
                        deps += "{} ".format(dep)
                    self.log("WARNING", "{} depends on {}".format(pend[0], deps))
                raise ValueError("cyclic dependancy detected")
            pending = next_pending
            emitted = next_emitted

    def apps_per_module(self, module):
        apps = []
        for app in self.app_config:
            if app != "global_modules" and self.app_config[app]["module"] == module:
                apps.append(app)

        return apps

    def apps_per_global_module(self, module):
        apps = []
        for app in self.app_config:
            if "global_dependencies" in self.app_config[app]:
                for gm in utils.single_or_list(self.app_config[app]["global_dependencies"]):
                    if gm == module:
                        apps.append(app)

        return apps
    #
    # State Updates
    #

    def check_and_disapatch(self, name, funcref, entity, attribute, new_state,
                            old_state, cold, cnew, kwargs, uuid_, pin_app, pin_thread):
        executed = False
        kwargs["handle"] = uuid_
        if attribute == "all":
            with self.objects_lock:
                executed = self.dispatch_worker(name, {
                    "name": name,
                    "id": self.objects[name]["id"],
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
                    with self.objects_lock:
                        executed = self.dispatch_worker(name, {
                            "name": name,
                            "id": self.objects[name]["id"],
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
                                with self.objects_lock:
                                    if name in self.objects:
                                        self.dispatch_worker(name, {
                                            "name": name,
                                            "id": self.objects[name]["id"],
                                            "type": "event",
                                            "event": data['event_type'],
                                            "function": callback["function"],
                                            "data": data["data"],
                                            "pin_app": callback["pin_app"],
                                            "pin_thread": callback["pin_thread"],
                                            "kwargs": callback["kwargs"]
                                        })

    #
    # Plugin Management
    #

    def get_plugin(self, name):
        if name in self.plugin_objs:
            return self.plugin_objs[name]["object"]
        else:
            return None

    def get_plugin_meta(self, namespace):
        for name in self.plugins:
            if "namespace" not in self.plugins[name] and namespace == "default":
                return self.plugin_meta[namespace]
            elif "namespace" in self.plugins[name] and self.plugins[name]["namespace"] == namespace:
                return self.plugin_meta[namespace]

        return None

    async def wait_for_plugins(self):
        initialized = False
        while not initialized and self.stopping is False:
            initialized = True
            for plugin in self.plugin_objs:
                if self.plugin_objs[plugin]["active"] is False:
                    initialized = False
                    break
            await asyncio.sleep(1)

    async def update_plugin_state(self):
        for plugin in self.plugin_objs:
            if self.plugin_objs[plugin]["active"] is True:
                if datetime.datetime.now() - self.last_plugin_state[plugin] > datetime.timedelta(
                        minutes=10):
                    try:
                        self.log("DEBUG",
                                 "Refreshing {} state".format(plugin))

                        state = await self.plugin_objs[plugin]["object"].get_complete_state()

                        if state is not None:
                            with self.state_lock:
                                self.state[plugin].update(state)

                        self.last_plugin_state[plugin] = datetime.datetime.now()
                    except:
                        self.log("WARNING",
                                 "Unexpected error refreshing {} state - retrying in 10 minutes".format(plugin))

    def required_meta_check(self):
        OK = True
        for key in self.required_meta:
            if getattr(self, key) == None:
                # No value so bail
                self.err("ERROR", "Required attribute not set or obtainable from any plugin: {}".format(key))
                OK = False
        return OK



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

