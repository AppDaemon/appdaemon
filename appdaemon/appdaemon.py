import os
import os.path
import threading
from asyncio import BaseEventLoop
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Union

import appdaemon.utils as utils
from appdaemon.admin_loop import AdminLoop
from appdaemon.app_management import AppManagement
from appdaemon.callbacks import Callbacks
from appdaemon.events import Events
from appdaemon.futures import Futures
from appdaemon.plugin_management import Plugins
from appdaemon.scheduler import Scheduler
from appdaemon.sequences import Sequences
from appdaemon.services import Services
from appdaemon.state import State
from appdaemon.thread_async import ThreadAsync
from appdaemon.threading import Threading
from appdaemon.utility_loop import Utility

if TYPE_CHECKING:
    from appdaemon.http import HTTP
    from appdaemon.logging import Logging


class AppDaemon:
    """Top-level container for the subsystem objects. This gets passed to the subsystem objects and stored in them as the ``self.AD`` attribute.

    Asyncio:

    :class:`~concurrent.futures.ThreadPoolExecutor`

    Subsystems:

    .. list-table::
        :widths: 25, 50
        :header-rows: 1

        * - Attribute
          - Object
        * - ``app_management``
          - :class:`~.app_management.AppManagement`
        * - ``callbacks``
          - :class:`~.callbacks.Callbacks`
        * - ``events``
          - :class:`~.events.Events`
        * - ``futures``
          - :class:`~.futures.Futures`
        * - ``http``
          - :class:`~.http.HTTP`
        * - ``plugins``
          - :class:`~.plugin_management.Plugins`
        * - ``scheduler``
          - :class:`~.scheduler.Scheduler`
        * - ``services``
          - :class:`~.services.Services`
        * - ``sequences``
          - :class:`~.sequences.Sequences`
        * - ``state``
          - :class:`~.state.State`
        * - ``threading``
          - :class:`~.threading.Threading`
        * - ``utility``
          - :class:`~.utility_loop.Utility`


    """

    # asyncio
    loop: BaseEventLoop
    """Main asyncio event loop
    """
    executor: ThreadPoolExecutor
    """Executes functions from a pool of async threads. Configured with the ``threadpool_workers`` key. Defaults to 10.
    """

    # subsystems
    app_management: AppManagement
    callbacks: Callbacks
    events: Events
    futures: Futures
    http: "HTTP"
    logging: "Logging"
    plugins: Plugins
    scheduler: Scheduler
    services: Services
    sequences: Sequences
    state: State
    threading: Threading
    utility: Utility

    # shut down flag
    stopping: bool

    # settings
    app_dir: Union[str, Path]
    """Defined in the main YAML config under ``appdaemon.app_dir``. Defaults to ``./apps``
    """
    config_dir: Union[str, Path]
    """Path to the AppDaemon configuration files. Defaults to the first folder that has ``./apps``

    - ``~/.homeassistant``
    - ``/etc/appdaemon``
    """
    apps: bool
    """Flag for whether ``disable_apps`` was set in the AppDaemon config
    """

    def __init__(self, logging: "Logging", loop: BaseEventLoop, **kwargs):
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

        self.internal_function_timeout = 60
        utils.process_arg(self, "internal_function_timeout", kwargs, int=True)

        self.use_dictionary_unpacking = False
        utils.process_arg(self, "use_dictionary_unpacking", kwargs)

        self.use_stream = False
        utils.process_arg(self, "use_stream", kwargs)

        self.import_paths = []
        utils.process_arg(self, "import_paths", kwargs)

        self.import_method = "normal"
        utils.process_arg(self, "import_method", kwargs)

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
        self.services = Services(self)

        #
        # Set up sequences
        #
        self.sequences = Sequences(self)

        #
        # Set up scheduler
        #
        self.sched = Scheduler(self)

        #
        # Set up state
        #
        self.state = State(self)

        #
        # Set up events
        #
        self.events = Events(self)

        #
        # Set up callbacks
        #
        self.callbacks = Callbacks(self)

        #
        # Set up futures
        #
        self.futures = Futures(self)

        if self.apps is True:
            if self.app_dir is None:
                if self.config_dir is None:
                    self.app_dir = utils.find_path("apps")
                    self.config_dir = os.path.dirname(self.app_dir)
                else:
                    self.app_dir = os.path.join(self.config_dir, "apps")

            utils.check_path("config_dir", self.logger, self.config_dir, permissions="rwx")
            utils.check_path("appdir", self.logger, self.app_dir)

            self.config_dir = os.path.abspath(self.config_dir)
            self.app_dir = os.path.abspath(self.app_dir)

            # Initialize Apps

            self.app_management = AppManagement(self, self.use_toml)

            # threading setup

            self.threading = Threading(self, kwargs)

        self.stopping = False

        #
        # Set up Executor ThreadPool
        #
        if "threadpool_workers" in kwargs:
            self.threadpool_workers = int(kwargs["threadpool_workers"])

        self.executor = ThreadPoolExecutor(max_workers=self.threadpool_workers)

        # Initialize Plugins
        args = kwargs.get("plugins", None)
        self.plugins = Plugins(self, args)

        # Create thread_async Loop
        self.logger.debug("Starting thread_async loop")
        if self.apps is True:
            self.thread_async = ThreadAsync(self)
            loop.create_task(self.thread_async.loop())

        # Create utility loop
        self.logger.debug("Starting utility loop")
        self.utility = Utility(self)
        loop.create_task(self.utility.loop())

    def stop(self):
        """Called by the signal handler to shut AD down.

        Also stops

        - :class:`~.admin_loop.AdminLoop`
        - :class:`~.thread_async.ThreadAsync`
        - :class:`~.scheduler.Scheduler`
        - :class:`~.utility_loop.Utility`
        - :class:`~.plugin_management.Plugins`
        """
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

    def register_http(self, http: "HTTP"):
        """Sets the ``self.http`` attribute with a :class:`~.http.HTTP` object and starts the admin loop."""

        self.http: "HTTP" = http
        # Create admin loop

        if http.old_admin is not None or http.admin is not None:
            self.logger.debug("Starting admin loop")

            self.admin_loop = AdminLoop(self)
            self.loop.create_task(self.admin_loop.loop())
