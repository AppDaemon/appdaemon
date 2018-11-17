import os
import os.path
import datetime
import uuid
import concurrent.futures
import threading
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
import appdaemon.callbacks as callbacks
import appdaemon.state as state
import appdaemon.events as events


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

        #
        # Set up events
        #
        self.events = events.Events(self)

        #
        # Set up callbacks
        #
        self.callbacks = callbacks.Callbacks(self)

        #
        # Set up state
        #
        self.state = state.State(self)


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
    # Utilities
    #

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
        with self.callbacks.callbacks_lock:
            for callback in self.callbacks.callbacks:
                for uuid in self.callbacks.callbacks[callback]:
                    cb = self.callbacks.callbacks[callback][uuid]
                    if cb["name"] == name and cb["type"] == "event" and cb["event"] == "__AD_LOG_EVENT":
                        has_log_callback = True

        if has_log_callback is False:
            self.events.process_event("global", {"event_type": "__AD_LOG_EVENT",
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
                handle.append(self.events.add_event_callback(name, namespace, cb, "__AD_LOG_EVENT", level=thislevel, **kwargs))

        return handle

    def cancel_log_callback(self, name, handle):
        for h in handle:
            self.events.cancel_event_callback(name, h)

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

