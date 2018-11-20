import os
import os.path
import datetime
import concurrent.futures
import threading
import pytz

class AppDaemon:

    def __init__(self, logging, loop, **kwargs):

        #
        # Import various AppDaemon bits and pieces now to avoid circular import
        #

        import appdaemon.utils as utils
        import appdaemon.appq as appq
        import appdaemon.utility_loop as utility
        import appdaemon.plugin_management as plugins
        import appdaemon.threading
        import appdaemon.app_management as apps
        import appdaemon.callbacks as callbacks
        import appdaemon.state as state
        import appdaemon.events as events

        self.logging = logging
        self.logging.register_ad(self)

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
        self.api = None
        self.running_apps = 0

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

        self.tz = None

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
        utils.process_arg(self, "endtime", kwargs)

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
            self.logging.log("INFO", "Apps are disabled")
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

            utils.check_path("config_dir", logging, self.config_dir, permissions="rwx")
            utils.check_path("appdir", logging, self.app_dir)

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
            args = kwargs["plugins"]
        else:
            args = None

        self.plugins = plugins.Plugins(self, args)

        # Create appq Loop

        if self.apps is True:
            self.appq = appq.AppQ(self)
            loop.create_task(self.appq.loop())

        # Create utility loop

        self.logging.log("DEBUG", "Starting utility loop")

        self.utility = utility.Utility(self)
        loop.create_task(self.utility.loop())

    def stop(self):
        self.stopping = True
        if self.appq is not None:
            self.appq.stop()
        if self.sched is not None:
            self.sched.stop()
        if self.utility is not None:
            self.utility.stop()
        if self.plugins is not None:
            self.plugins.stop()

    #
    # Utilities
    #

    def register_dashboard(self, dash):
        self.dashboard = dash

    def register_api(self, api):
        self.api = api
