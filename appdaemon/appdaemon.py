import os
import threading
from asyncio import BaseEventLoop
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Optional


from appdaemon.admin_loop import AdminLoop
from appdaemon.app_management import AppManagement
from appdaemon.callbacks import Callbacks
from appdaemon.events import Events
from appdaemon.futures import Futures
from appdaemon.models.config import AppDaemonConfig
from appdaemon.plugin_management import PluginManagement
from appdaemon.scheduler import Scheduler
from appdaemon.sequences import Sequences
from appdaemon.services import Services
from appdaemon.state import State
from appdaemon.thread_async import ThreadAsync
from appdaemon.threads import Threading
from appdaemon.utility_loop import Utility

from .utils import Singleton

if TYPE_CHECKING:
    from appdaemon.http import HTTP
    from appdaemon.logging import Logging


class AppDaemon(metaclass=Singleton):
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
    callbacks: Callbacks = None
    events: Events = None
    futures: Futures
    logging: "Logging"
    plugins: PluginManagement
    scheduler: Scheduler
    services: Services
    sequences: Sequences
    state: State
    threading: Threading
    thread_async: ThreadAsync = None
    utility: Utility

    # settings
    app_dir: Path
    """Defined in the main YAML config under ``appdaemon.app_dir``. Defaults to ``./apps``
    """
    config_dir: Path
    """Path to the AppDaemon configuration files. Defaults to the first folder that has ``./apps``

    - ``~/.homeassistant``
    - ``/etc/appdaemon``
    """
    apps: bool
    """Flag for whether ``disable_apps`` was set in the AppDaemon config
    """

    admin_loop: AdminLoop | None = None
    http: Optional["HTTP"] = None
    global_lock: RLock = RLock()

    # shut down flag
    stopping: bool = False

    def __init__(self, logging: "Logging", loop: BaseEventLoop, ad_config_model: AppDaemonConfig):
        self.logging = logging
        self.loop = loop
        self.config = ad_config_model
        self.booted = "booting"
        self.logger = logging.get_logger()
        self.logging.register_ad(self) # needs to go last to reference the config object

        self.global_vars = {}
        self.main_thread_id = threading.current_thread().ident

        if not self.apps:
            self.logging.log("INFO", "Apps are disabled")

        # Initialize subsystems
        self.callbacks = Callbacks(self)
        self.events = Events(self)
        self.services = Services(self)
        self.sequences = Sequences(self)
        self.sched = Scheduler(self)
        self.state = State(self)
        self.futures = Futures(self)

        if self.apps is True:
            assert self.config_dir is not None, "Config_dir not set. This is a development problem"
            assert self.config_dir.exists(), f"{self.config_dir} does not exist"
            assert os.access(
                self.config_dir, os.R_OK | os.X_OK
            ), f"{self.config_dir} does not have the right permissions"

            # this will always be None because it never gets set in ad_kwargs in __main__.py
            if self.app_dir is None:
                self.app_dir = self.config_dir / "apps"
                if not self.app_dir.exists():
                    self.app_dir.mkdir()
                assert os.access(
                    self.app_dir, os.R_OK | os.W_OK | os.X_OK
                ), f"{self.app_dir} does not have the right permissions"

            self.logger.info(f"Using {self.app_dir} as app_dir")

            self.app_management = AppManagement(self)
            self.threading = Threading(self)

            # Create ThreadAsync loop
            self.logger.debug("Starting thread_async loop")
            self.thread_async = ThreadAsync(self)
            loop.create_task(self.thread_async.loop())

        self.executor = ThreadPoolExecutor(max_workers=self.threadpool_workers)

        # Initialize Plugins
        self.plugins = PluginManagement(self, self.config.plugins)

        # Create utility loop
        self.logger.debug("Starting utility loop")
        self.utility = Utility(self)
        loop.create_task(self.utility.loop())

    #
    # Property definitions
    #
    @property
    def admin_delay(self):
        return self.config.admin_delay

    @property
    def api_port(self):
        return self.config.api_port

    @property
    def app_dir(self):
        return self.config.app_dir

    @property
    def apps(self):
        return not self.config.disable_apps

    @property
    def certpath(self):
        return self.config.cert_verify

    @property
    def check_app_updates_profile(self):
        return self.config.check_app_updates_profile

    @property
    def config_dir(self):
        return self.config.config_dir

    @property
    def config_file(self):
        return self.config.config_file

    @property
    def elevation(self):
        return self.config.elevation

    @property
    def endtime(self):
        return self.config.endtime

    @property
    def exclude_dirs(self):
        return self.config.exclude_dirs

    @property
    def import_paths(self):
        return self.config.import_paths

    @property
    def invalid_config_warnings(self):
        return self.config.invalid_config_warnings

    @property
    def latitude(self):
        return self.config.latitude

    @property
    def load_distribution(self):
        return self.config.load_distribution

    @property
    def log_thread_actions(self):
        return self.config.log_thread_actions

    @property
    def loglevel(self):
        return self.config.loglevel

    @property
    def longitude(self):
        return self.config.longitude

    @property
    def max_clock_skew(self):
        return self.config.max_clock_skew

    @property
    def max_utility_skew(self):
        return self.config.max_utility_skew

    @property
    def missing_app_warnings(self):
        return self.config.invalid_config_warnings

    @property
    def module_debug(self):
        return self.config.module_debug

    @property
    def namespaces(self):
        return self.config.namespaces

    @property
    def production_mode(self):
        return self.config.production_mode

    @production_mode.setter
    def production_mode(self, mode: bool):
        self.config.production_mode = mode
        action = "activated" if mode else "deactivated"
        self.logger.info("AD Production Mode %s", action)

    @property
    def qsize_warning_iterations(self):
        return self.config.qsize_warning_iterations

    @property
    def qsize_warning_step(self):
        return self.config.qsize_warning_step

    @property
    def qsize_warning_threshold(self):
        return self.config.qsize_warning_threshold

    @property
    def starttime(self):
        return self.config.starttime

    @property
    def stop_function(self):
        return self.config.stop_function or self.stop

    @property
    def thread_duration_warning_threshold(self):
        return self.config.thread_duration_warning_threshold

    @property
    def threadpool_workers(self):
        return self.config.threadpool_workers

    @property
    def time_zone(self):
        return self.config.time_zone

    @property
    def timewarp(self):
        return self.config.timewarp

    @property
    def tz(self):
        return self.config.time_zone

    @property
    def use_stream(self):
        return self.config.use_stream

    @property
    def write_toml(self):
        return self.config.write_toml

    @property
    def utility_delay(self):
        return self.config.utility_delay

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
