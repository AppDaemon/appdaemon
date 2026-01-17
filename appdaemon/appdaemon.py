import asyncio
import os
import threading
from asyncio import AbstractEventLoop
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from appdaemon.http import HTTP
    from appdaemon.logging import Logging


class AppDaemon:
    """Top-level container for the subsystem objects. This gets passed to the subsystem objects and stored in them as
    the ``self.AD`` attribute.

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
    loop: AbstractEventLoop
    """Main asyncio event loop
    """
    executor: ThreadPoolExecutor
    """Executes functions from a pool of async threads. Configured with the ``threadpool_workers`` key. Defaults to 10.
    """
    exit_stack: ExitStack

    # subsystems
    app_management: AppManagement
    callbacks: Callbacks
    events: Events
    futures: Futures
    logging: "Logging"
    plugins: PluginManagement
    scheduler: Scheduler
    services: Services
    sequences: Sequences
    state: State
    threading: Threading
    thread_async: ThreadAsync
    utility: Utility

    admin_loop: "AdminLoop | None" = None
    http: "HTTP | None" = None
    global_lock: RLock = RLock()

    stop_event: asyncio.Event
    """Flag to indicate that AppDaemon is stopping. Set by :meth:`~.appdaemon.AppDaemon.stop` and checked by subsystems."""
    stop_time: float = 0.0
    """Stores the value of perf_counter() when self.stop is first called."""

    def __init__(
        self,
        logging: "Logging",
        loop: AbstractEventLoop,
        ad_config_model: AppDaemonConfig,
        exit_stack: ExitStack | None = None,
    ) -> None:
        self.logging = logging
        self.loop = loop
        self.exit_stack = exit_stack if exit_stack is not None else ExitStack()
        self.config = ad_config_model
        self.booted = "booting"
        self.logger = logging.get_logger()
        self.logging.register_ad(self)  # needs to go last to reference the config object
        self._shutdown_logger = self.logging.get_child("_shutdown")
        self.stop_event = asyncio.Event()

        self.global_vars: Any = {}
        self.main_thread_id = threading.current_thread().ident

        # Initialize subsystems
        self.callbacks = Callbacks(self)
        self.events = Events(self)
        self.services = Services(self)
        self.sequences = Sequences(self)
        self.sched = Scheduler(self)
        self.state = State(self)
        self.thread_async = ThreadAsync(self)
        self.futures = Futures(self)

        if not self.apps_enabled:
            self.logger.info("Apps are disabled, skipping app management initialization")
        else:
            assert self.config_dir is not None, "Config_dir not set. This is a development problem"
            assert self.config_dir.exists(), f"{self.config_dir} does not exist"
            assert os.access(
                self.config_dir,
                os.R_OK | os.X_OK,
            ), f"{self.config_dir} does not have the right permissions"

            # this will always be None because it never gets set in ad_kwargs in __main__.py
            if self.app_dir is None:
                self.app_dir = self.config_dir / "apps"
                if not self.app_dir.exists():
                    self.app_dir.mkdir()
                assert os.access(
                    self.app_dir,
                    os.R_OK | os.W_OK | os.X_OK,
                ), f"{self.app_dir} does not have the right permissions"

            self.logger.info(f"Using {self.app_dir} as app_dir")

            self.app_management = AppManagement(self)

        self.threading = Threading(self)
        self.executor = ThreadPoolExecutor(max_workers=self.threadpool_workers)
        self.utility = Utility(self)
        self.plugins = PluginManagement(self, self.config.plugins)

    #
    # Property definitions
    #

    @property
    def api_port(self) -> int | None:
        return self.config.api_port

    @property
    def app_dir(self) -> Path:
        """Defined in the main YAML config under ``appdaemon.app_dir``. Defaults to ``./apps``"""
        return self.config.app_dir

    @app_dir.setter
    def app_dir(self, path: os.PathLike) -> None:
        self.config.app_dir = Path(path)

    @property
    def apps_enabled(self):
        """Flag for whether ``disable_apps`` was set in the AppDaemon config"""
        return not self.config.disable_apps

    @apps_enabled.setter
    def apps_enabled(self, value: bool) -> None:
        """Set whether apps are enabled or disabled"""
        self.config.disable_apps = not value
        action = "enabled" if value else "disabled"
        self.logger.info(f"Apps {action}")

    @property
    def certpath(self):
        return self.config.cert_verify

    @property
    def check_app_updates_profile(self):
        return self.config.check_app_updates_profile

    @property
    def config_dir(self):
        """Path to the AppDaemon configuration files. Defaults to the first folder that has ``./apps``

        - ``~/.homeassistant``
        - ``/etc/appdaemon``
        """
        return self.config.config_dir

    @config_dir.setter
    def config_dir(self, path: os.PathLike) -> None:
        self.config.config_dir = Path(path)

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
    def real_time(self) -> bool:
        """Flag for whether the AppDaemon instance is running in real time or not."""
        return self.config.timewarp == 1

    @real_time.setter
    def real_time(self, value: bool) -> None:
        """Set the AppDaemon instance to run in real time or not."""
        if value:
            self.timewarp = 1.0
        else:
            raise NotImplementedError("Setting real_time to False is not supported. Set timewarp to a value other than 1.0 instead.")

    @property
    def starttime(self):
        return self.config.starttime

    @property
    def stopping(self) -> bool:
        """Check if the AppDaemon instance is stopping."""
        return self.stop_event.is_set()

    @stopping.setter
    def stopping(self, value: bool) -> None:
        """Set the stopping state of the AppDaemon instance."""
        if value:
            self.stop_event.set()
            self.logger.debug("Set stop event")
        else:
            self.stop_event.clear()

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

    @timewarp.setter
    def timewarp(self, value: float):
        """Set the timewarp value for the AppDaemon instance."""
        if not isinstance(value, (int, float)):
            raise TypeError("Timewarp must be a number.")
        self.config.timewarp = value
        self.logger.info(f"Timewarp set to {value}")

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

    def start(self) -> None:
        """Start AppDaemon, which also starts all the component subsystems like the scheduler, etc.

        - :meth:`ThreadAsync <appdaemon.thread_async.ThreadAsync.start>`
        - :meth:`Utility <appdaemon.utility_loop.Utility.start>`

        Note: The scheduler is started by the utility loop after plugins are ready.
        """
        self.logger.debug("Starting AppDaemon")
        self.thread_async.start()
        self.utility.start()
        self.state.start()

    async def stop(self) -> None:
        """Stop AppDaemon by calling the stop method of the subsystems.

        This does not stop the event loop, but waits for all the existings tasks to finish before returning, which has a 3s timeout.

        - :meth:`AppManagement <appdaemon.app_management.AppManagement.stop>`
        - :meth:`ThreadAsync <appdaemon.thread_async.ThreadAsync.stop>`
        - :meth:`Plugins <appdaemon.plugin_management.Plugins.stop>`
        - :meth:`Scheduler <appdaemon.scheduler.Scheduler.stop>`
        - :meth:`State <appdaemon.state.State.stop>`
        """
        self._shutdown_logger.info("Stopping AppDaemon")
        self.stopping = True

        # Subsystems are able to create tasks during their stop methods
        if self.apps_enabled:
            try:
                await asyncio.wait_for(self.app_management.stop(), timeout=3)
            except asyncio.TimeoutError:
                self._shutdown_logger.warning("AppManagement stop timed out, continuing shutdown")
        if self.thread_async is not None:
            self.thread_async.stop()
        if self.plugins is not None:
            try:
                await asyncio.wait_for(self.plugins.stop(), timeout=1)
            except asyncio.TimeoutError:
                self._shutdown_logger.warning("Timed out stopping plugins, continuing shutdown")
        self.sched.stop()
        self.state.stop()
        self.threading.stop()

        self.executor.shutdown(wait=True)

        # This creates a task that will wait for all the ones that were running when stop() was called to finish
        # before stopping the event loop. This allows subsystems to create tasks during their own stop methods
        current_task = asyncio.current_task()
        running_tasks = [task for task in asyncio.all_tasks() if task is not current_task]
        if running_tasks:
            all_coro = asyncio.wait(running_tasks, return_when=asyncio.ALL_COMPLETED, timeout=3)
            gather_task = asyncio.create_task(all_coro, name="appdaemon_stop_tasks")
            gather_task.add_done_callback(lambda _: self.logger.debug("All tasks finished"))
            self._shutdown_logger.debug("Waiting for tasks %s to finish...", len(running_tasks))

            # These is left here for future debugging purposes
            # await asyncio.sleep(2.0)
            # still_running = [
            #     task
            #     for task in asyncio.all_tasks()
            #     if task is not current_task and task is not gather_task and not task.done()
            # ]
            # self._shutdown_logger.debug("%s tasks still running after 2 seconds", len(still_running))
            # if still_running:
            #     for task in still_running:
            #         self._shutdown_logger.debug("Still running: %s", task.get_name())

            await gather_task

    #
    # Utilities
    #

    def register_http(self, http: "HTTP"):
        """Sets the ``self.http`` attribute with a :class:`~.http.HTTP` object and starts the admin loop."""

        self.http = http
        # Create admin loop

        if http.old_admin is not None or http.admin is not None:
            self.logger.debug("Starting admin loop")

            self.admin_loop = AdminLoop(self)
            self.loop.create_task(self.admin_loop.loop(), name="admin loop")
