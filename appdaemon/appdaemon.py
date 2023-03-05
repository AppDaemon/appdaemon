import os
import os.path
import concurrent.futures
import threading


class AppDaemon:
    def __init__(self, logging, loop, **kwargs):
        #
        # Import various AppDaemon bits and pieces now to avoid circular import
        #

        import appdaemon.utils as utils
        import appdaemon.thread_async as appq
        import appdaemon.utility_loop as utility
        import appdaemon.plugin_management as plugins
        import appdaemon.threading
        import appdaemon.app_management as apps
        import appdaemon.callbacks as callbacks
        import appdaemon.futures as futures
        import appdaemon.state as state
        import appdaemon.events as events
        import appdaemon.services as services
        import appdaemon.sequences as sequences
        import appdaemon.scheduler as scheduler

        self.logging = logging
        self.logging.register_ad(self)
        self.logger = logging.get_logger()
        self.threading = None
        self.callbacks = None
        self.futures = None
        self.state = None

        self.config = kwargs
        self.booted = "booting"
        self.config["ad_version"] = utils.__version__
        self.check_app_updates_profile = ""

        self.was_dst = False

        self.last_state = None

        self.executor = None
        self.loop = None
        self.srv = None
        self.appd = None
        self.stopping = False
        self.http = None
        self.admin_loop = None

        self.global_vars = {}
        self.global_lock = threading.RLock()

        self.config_file_modified = 0

        self.sched = None
        self.thread_async = None
        self.utility = None
        self.module_debug = kwargs["module_debug"]

        # User Supplied/Defaults

        self.load_distribution = "roundrobbin"
        utils.process_arg(self, "load_distribution", kwargs)

        self.app_dir = None
        utils.process_arg(self, "app_dir", kwargs)

        self.starttime = None
        utils.process_arg(self, "starttime", kwargs)

        self.latitude = None
        utils.process_arg(self, "latitude", kwargs, float=True)

        self.longitude = None
        utils.process_arg(self, "longitude", kwargs, float=True)

        self.elevation = None
        utils.process_arg(self, "elevation", kwargs, int=True)

        self.time_zone = None
        utils.process_arg(self, "time_zone", kwargs)

        self.tz = None
        self.loop = loop

        self.logfile = None
        self.errfile = None

        self.config_file = None
        utils.process_arg(self, "config_file", kwargs)

        self.config_dir = None
        utils.process_arg(self, "config_dir", kwargs)

        self.timewarp = 1
        utils.process_arg(self, "timewarp", kwargs, float=True)

        self.max_clock_skew = 1
        utils.process_arg(self, "max_clock_skew", kwargs, int=True)

        self.thread_duration_warning_threshold = 10
        utils.process_arg(self, "thread_duration_warning_threshold", kwargs, float=True)

        self.threadpool_workers = 10
        utils.process_arg(self, "threadpool_workers", kwargs, int=True)

        self.endtime = None
        utils.process_arg(self, "endtime", kwargs)

        self.loglevel = "INFO"
        utils.process_arg(self, "loglevel", kwargs)

        self.api_port = None
        utils.process_arg(self, "api_port", kwargs)

        self.utility_delay = 1
        utils.process_arg(self, "utility_delay", kwargs, int=True)

        self.admin_delay = 1
        utils.process_arg(self, "admin_delay", kwargs, int=True)

        self.max_utility_skew = self.utility_delay * 2
        utils.process_arg(self, "max_utility_skew", kwargs, float=True)

        self.check_app_updates_profile = False
        utils.process_arg(self, "check_app_updates_profile", kwargs)

        self.production_mode = False
        utils.process_arg(self, "production_mode", kwargs)

        self.invalid_config_warnings = True
        utils.process_arg(self, "invalid_config_warnings", kwargs)

        self.use_toml = False
        utils.process_arg(self, "use_toml", kwargs)

        self.missing_app_warnings = True
        utils.process_arg(self, "missing_app_warnings", kwargs)

        self.log_thread_actions = False
        utils.process_arg(self, "log_thread_actions", kwargs)

        self.qsize_warning_threshold = 50
        utils.process_arg(self, "qsize_warning_threshold", kwargs, int=True)

        self.qsize_warning_step = 60
        utils.process_arg(self, "qsize_warning_step", kwargs, int=True)

        self.qsize_warning_iterations = 10
        utils.process_arg(self, "qsize_warning_iterations", kwargs, int=True)

        self.internal_function_timeout = 10
        utils.process_arg(self, "internal_function_timeout", kwargs, int=True)

        self.namespaces = {}
        utils.process_arg(self, "namespaces", kwargs)

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
        # Set up services
        #
        self.services = services.Services(self)

        #
        # Set up sequences
        #
        self.sequences = sequences.Sequences(self)

        #
        # Set up scheduler
        #
        self.sched = scheduler.Scheduler(self)

        #
        # Set up state
        #
        self.state = state.State(self)

        #
        # Set up events
        #
        self.events = events.Events(self)

        #
        # Set up callbacks
        #
        self.callbacks = callbacks.Callbacks(self)

        #
        # Set up futures
        #
        self.futures = futures.Futures(self)

        if self.apps is True:
            if self.app_dir is None:
                if self.config_dir is None:
                    self.app_dir = utils.find_path("apps")
                    self.config_dir = os.path.dirname(self.app_dir)
                else:
                    self.app_dir = os.path.join(self.config_dir, "apps")

            utils.check_path("config_dir", self.logger, self.config_dir, permissions="rwx")
            utils.check_path("appdir", self.logger, self.app_dir)

            # Initialize Apps

            self.app_management = apps.AppManagement(self, self.use_toml)

            # threading setup

            self.threading = appdaemon.threading.Threading(self, kwargs)

        self.stopping = False

        #
        # Set up Executor ThreadPool
        #
        if "threadpool_workers" in kwargs:
            self.threadpool_workers = int(kwargs["threadpool_workers"])

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.threadpool_workers)

        # Initialize Plugins

        if "plugins" in kwargs:
            args = kwargs["plugins"]
        else:
            args = None

        self.plugins = plugins.Plugins(self, args)

        # Create thread_async Loop

        self.logger.debug("Starting thread_async loop")

        if self.apps is True:
            self.thread_async = appq.ThreadAsync(self)
            loop.create_task(self.thread_async.loop())

        # Create utility loop

        self.logger.debug("Starting utility loop")

        self.utility = utility.Utility(self)
        loop.create_task(self.utility.loop())

    def stop(self):
        self.stopping = True
        if self.admin_loop is not None:
            self.admin_loop.stop()
        if self.thread_async is not None:
            self.thread_async.stop()
        if self.sched is not None:
            self.sched.stop()
        if self.utility is not None:
            self.utility.stop()
        if self.plugins is not None:
            self.plugins.stop()

    def terminate(self):
        if self.state is not None:
            self.state.terminate()

    #
    # Utilities
    #

    def register_http(self, http):
        import appdaemon.admin_loop as admin_loop

        self.http = http
        # Create admin loop

        if http.old_admin is not None or http.admin is not None:
            self.logger.debug("Starting admin loop")

            self.admin_loop = admin_loop.AdminLoop(self)
            self.loop.create_task(self.admin_loop.loop())
