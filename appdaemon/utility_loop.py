"""Module to handle utility functions within AppDaemon."""

import asyncio
import datetime
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from logging import Logger
from time import perf_counter
from typing import TYPE_CHECKING

from . import exceptions as ade
from . import utils

if TYPE_CHECKING:
    from .appdaemon import AppDaemon


@dataclass
class LoopTiming:
    """Wrapper object for recording the timing of operations in the utility loop."""

    _start_time: float = field(default_factory=perf_counter)
    times: dict[str, float] = field(default_factory=dict)

    def record_time(self, name: str):
        """Record the current time for a specific operation."""
        self.times[name] = perf_counter() - self._start_time

    def timedelta(self, name: str) -> timedelta:
        """Get the recorded time as a timedelta."""
        return utils.parse_timedelta(self.times.get(name, 0.0))

    def get_time_strs(self) -> tuple[str, str, str]:
        assert "total" in self.times, "Total time must be recorded first"
        total = self.times["total"]
        check_app_updates = self.times.get("check_app_updates", 0.0)
        other = total - check_app_updates
        return (
            utils.format_timedelta(total),
            utils.format_timedelta(check_app_updates),
            utils.format_timedelta(other),
        )


class Utility:
    """Subsystem container for managing the utility loop

    Checks for file changes, overdue threads, thread starvation, and schedules regular state refreshes.
    """

    AD: "AppDaemon"
    """Reference to the AppDaemon container object
    """

    logger: Logger
    name: str = "_utility"
    loop_task: asyncio.Task
    """The task for the :meth:`~.utility_loop.Utility.loop` method"""
    app_update_event: asyncio.Event
    """Event that gets set and cleared :meth:`~.utility_loop.Utility._loop_iteration_context` method, which wraps each
    iteration of the while loop in :meth:`~.utility_loop.Utility.loop`"""

    def __init__(self, ad: "AppDaemon"):
        """Constructor.

        Args:
            ad: Reference to the AppDaemon object
        """
        self.AD = ad
        self.logger = ad.logging.get_child(self.name)
        self.booted = None

        self.app_update_event = asyncio.Event()

    def start(self) -> None:
        """Starts the utility loop by creating the async task for the :meth:`~.utility_loop.Utility.loop` method."""
        self.loop_task = self.AD.loop.create_task(self.loop(), name="utility_loop")
        self.loop_task.add_done_callback(self._loop_final_status)

    def _loop_final_status(self, task: asyncio.Task) -> None:
        """Used only to log how the utility loop ended."""
        if task.cancelled():
            self.logger.debug("Utility loop was cancelled")
        elif task.exception():
            self.logger.error("Utility loop encountered an error", exc_info=task.exception())
        else:
            self.logger.debug("Utility loop completed gracefully")

    async def get_uptime(self) -> timedelta:
        """Get the uptime of AppDaemon as a timedelta."""
        if self.booted is not None:
            uptime = (await self.AD.sched.get_now()) - self.booted
            uptime = utils.parse_timedelta(round(uptime.total_seconds()))
            return uptime
        else:
            return timedelta()

    async def _init_stats(self):
        # This method was originally part of self.loop
        await self.AD.threading.init_admin_stats()
        if self.AD.apps_enabled:
            await self.AD.threading.create_initial_threads()
            await self.AD.app_management.init_admin_stats()
        else:
            # Apps are disabled, so just create a single thread
            await self.AD.threading.add_thread(silent=True)
            self.total_threads = 1

        self.booted = await self.AD.sched.get_now()
        boot_time_str = self.booted.replace(microsecond=0).isoformat()
        await self.AD.state.add_entity("admin", "sensor.appdaemon_version", utils.__version__)
        await self.AD.state.add_entity("admin", "sensor.appdaemon_uptime", str(datetime.timedelta(0)))
        await self.AD.state.add_entity("admin", "sensor.appdaemon_booted", boot_time_str)

    async def _register_services(self):
        """Register core AppDaemon services for state management, events, sequences, and admin functions."""
        # Register state services
        for ns in self.AD.state.list_namespaces():
            if ns in ("admin", "appdaemon", "global"):
                continue  # Don't allow admin/appdaemon/global namespaces
            self.AD.state.register_state_services(ns)

            # Register fire_event services
            self.AD.services.register_service(ns, "event", "fire", self.AD.events.event_services)

        # Register run_sequence service
        self.AD.services.register_service("rules", "sequence", "run", self.AD.sequences.run_sequence_service)
        self.AD.services.register_service("rules", "sequence", "cancel", self.AD.sequences.run_sequence_service)

        # Register production_mode service
        self.AD.services.register_service("admin", "production_mode", "set", self.production_mode_service)

        # Register logging services
        self.AD.services.register_service("admin", "logs", "get_admin", self.AD.logging.manage_services)

    async def _init_loop(self):
        """Initialize the utility loop components.

        * Sets up stats
        * Starts the web server if configured
        * Waits for all plugins to initialize
        * Registers services
        * Starts the scheduler
        * Initializes apps if apps are enabled
        """
        self.logger.debug("Starting utility loop")

        # Setup
        await self._init_stats()

        # Start the web server
        if self.AD.http is not None and not self.AD.http.has_been_started:
            http_start_event = self.AD.exit_stack.enter_context(self.AD.http)
            await http_start_event.wait()

        # Wait for all plugins to initialize
        await self.AD.plugins.wait_for_plugins()

        if self.AD.stopping:
            self.logger.debug("AppDaemon already stopping before starting utility loop")
            return

        await self._register_services()

        # Start the scheduler
        self.AD.sched.start()

        if self.AD.apps_enabled:
            await self.AD.app_management.start()

            # Fire APPD Started Event
            await self.AD.events.process_event("global", {"event_type": "appd_started", "data": {}})

    async def loop(self):
        """Run the utility loop, which handles the following:

        * Checking for file changes to update/reload apps if necessary with :py:meth:`~.app_management.AppManagement.check_app_updates`
        * Checking for thread starvation
        * Checking for overdue threads
        * Save hybrid namespaces
        * Gives the plugins a chance to run their own utility functions
        * Updates performance entities
        """

        if not self.AD.stopping:
            await self._init_loop()
        else:
            self.logger.debug("AppDaemon already stopping before starting utility loop")

        if self.AD.stopping:
            # Debug message will have already been logged
            return

        warning_step = 0
        warning_iterations = 0

        # Start the loop proper
        self.logger.debug("Starting timer loop")
        while not self.AD.stopping:
            # _loop_iteration_context handles warnings, errors, and timing the loop
            async with self._loop_iteration_context() as timing:
                if self.AD.apps_enabled and not self.AD.production_mode:
                    # Check to see if config has changed
                    await self.AD.app_management.check_app_updates()
                    timing.record_time("check_app_updates")

                # Call me suspicious, but lets update state from the plugins periodically
                await self.AD.plugins.update_plugin_state()

                # Check for thread starvation
                (
                    warning_step,
                    warning_iterations,
                ) = await self.AD.threading.check_q_size(warning_step, warning_iterations)

                # Check for any overdue threads
                await self.AD.threading.check_overdue_and_dead_threads()

                # Save any hybrid namespaces
                # self.AD.state.save_hybrid_namespaces()

                # Run utility for each plugin
                self.AD.plugins.run_plugin_utility()

                # Update perf data
                await self.AD.plugins.get_plugin_perf_data()

                # Update uptime sensor
                await self.AD.state.set_state(
                    "_utility",
                    "admin",
                    "sensor.appdaemon_uptime",
                    state=str(await self.get_uptime()),
                )

    @asynccontextmanager
    async def _loop_iteration_context(self) -> AsyncGenerator[LoopTiming]:
        """Async context manager for running the utility :meth:`~.utility_loop.Utility.loop`.

        * Contains logic for warnings

            - Exceptions are logged with tracebacks, but not raised
            - Warnings are logged if the utility loop takes too long

        * Handles the timing of the utility loop

        Yields:
            LoopTiming: Timing object for recording operation timestamps.
        """
        try:
            self.app_update_event.clear()
            timing = LoopTiming()
            yield timing
        except ade.AppDaemonException as exc:
            ade.user_exception_block(self.AD.logging.error, exc, self.AD.app_dir)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during utility()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
        finally:
            self.app_update_event.set()
            timing.record_time("total")

            self.logger.debug(
                "Util loop compute time: %s, check_app_updates: %s, other: %s",
                timing.get_time_strs(),
            )
            if self.AD.real_time and timing.timedelta("total") > self.AD.config.max_utility_skew:
                self.logger.warning(
                    "Excessive time spent in utility loop: %s, %s in check_app_updates(), %s in other",
                    *timing.get_time_strs(),
                )
                if self.AD.check_app_updates_profile:
                    self.logger.info("Profile information for Utility Loop")
                    self.logger.info(self.AD.app_management.check_app_updates_profile_stats)
            else:
                if not self.AD.stopping:
                    await self.sleep(self.AD.config.utility_delay.total_seconds(), timeout_ok=True)

    async def production_mode_service(self, ns, domain, service, kwargs):
        match kwargs:
            case {"mode": bool(mode)}:
                self.AD.production_mode = mode
                self.logger.info(f"Production mode set to {mode}")
            case _:
                if "mode" in kwargs:
                    self.logger.warning(f"Invalid production mode: {kwargs.get('mode')}")
                else:
                    self.logger.warning("No production mode specified, use True or False")

    async def sleep(self, delay: float, *, timeout_ok: bool):
        """Sleep for a specified number of seconds.

        The purpose of this method is to make sleeping easily and quickly interruptible. This is done by using
        :py:func:`asyncio.wait_for` to wait for the stop event to be set, and (usually) ignoring the timeout.

        Args:
            seconds (float): Number of seconds to sleep.
            timeout_ok (bool): If True, does not raise TimeoutError if the sleep is interrupted by stop_event.
        """
        if not self.AD.stopping:
            try:
                await asyncio.wait_for(self.AD.stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                if not timeout_ok:
                    raise
