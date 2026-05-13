import asyncio
import datetime
import functools
import inspect
import logging
import re
import threading
import traceback
from collections import deque
from collections.abc import Callable, Generator, Iterable
from itertools import cycle
from logging import Logger
from queue import Queue
from random import randint
from threading import Thread
from typing import TYPE_CHECKING, Any

from . import exceptions as ade
from .models.config.app import AppConfig
from .models.internal.app_management import ManagedObject
from .utils import parse
from .utils.datetime import day_of_week
from .utils.functools import has_expanded_kwargs
from .utils.misc import deepcopy as ad_deepcopy
from .utils.state import check_state
from .utils.str import dt_to_str, format_timedelta, str_to_dt
from .utils.threading import run_async_sync_func, run_coroutine_threadsafe, run_in_executor

if TYPE_CHECKING:
    from .adbase import ADBase
    from .appdaemon import AppDaemon


class Threading:
    """Subsystem container for managing :class:`~threading.Thread` objects"""

    AD: "AppDaemon"
    """Reference to the AppDaemon container object
    """
    logger: Logger
    """Standard python logger named ``AppDaemon._threading``
    """
    name: str = "_threading"
    log_lock: threading.Lock
    """Threadsafe lock that helps prevent blocks of log output from different threads being mixed together
    """
    diag: Logger
    """Standard python logger named ``Diag``
    """
    threads: dict[str, dict[str, Thread | Queue]]
    """Dictionary with keys of the thread ID (string beginning with `thread-`) and values of
    another dictionary with `thread` and `queue` keys that have values of
    :class:`~threading.Thread` and :class:`~queue.Queue` objects respectively.
    """

    last_stats_time: datetime.datetime = datetime.datetime.min
    last_callbacks: deque[dict[str, Any]]

    _roundrobin_cycle: Iterable[str]
    """Iterator that produces the name of the next thread when using the round robin load distribition method."""

    current_callbacks_executed: int = 0
    current_callbacks_fired: int = 0

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child(self.name)
        self.log_lock = threading.Lock()
        self.diag = ad.logging.get_diag()

        self.threads = {}

        # A few shortcuts
        self.add_entity = functools.partial(ad.state.add_entity, "admin")
        self.get_state = functools.partial(ad.state.get_state, self.name, "admin")
        self.set_state = functools.partial(ad.state.set_state, self.name, "admin")
        self.add_to_state = functools.partial(ad.state.add_to_state, self.name, "admin")
        self.add_to_attr = functools.partial(ad.state.add_to_attr, self.name, "admin")

        self.last_callbacks = deque(maxlen=10)

    @property
    def thread_count(self) -> int:
        """The number of threads that have actually been created. This is calculated from the length of the internal
        `threads` dictionary, so it can't be set directly."""
        return len(self.threads)

    def stop(self):
        """Stop all threads."""
        for thread_name, thread in self.threads.items():
            match thread:
                case {"queue": Queue() as q, "thread": Thread() as t}:
                    self.logger.debug("Stopping %s", thread_name)
                    q.put_nowait(None)
                    try:
                        t.join(timeout=1)
                        self.logger.debug("Joined %s", thread_name)
                    except RuntimeError as exc:
                        self.logger.error("Error joining thread %s: %s", thread_name, exc)

    def _pin_settings(self):
        return {
            name: {'pinned': obj.pin_app, 'pin_thread': obj.pin_thread}
            for name, obj in self.AD.app_management.objects.items()
        }

    async def get_q_update(self):
        """Updates queue sizes"""
        for thread in self.threads:
            qsize = self.get_q(thread).qsize()
            await self.set_state(f"thread.{thread}", q=qsize)

    async def get_callback_update(self):
        """Updates the sensors with information about how many callbacks have been fired. Called by the :class:`~appdaemon.admin_loop.AdminLoop`

        - ``sensor.callbacks_average_fired``
        - ``sensor.callbacks_average_executed``
        """
        now = await self.AD.sched.get_now()
        self.last_callbacks.append(
            {"fired": self.current_callbacks_fired, "executed": self.current_callbacks_executed, "ts": now}
        )

        fired_total = sum(item["fired"] for item in self.last_callbacks)
        executed_total = sum(item["executed"] for item in self.last_callbacks)
        total_duration = (self.last_callbacks[-1]["ts"] - self.last_callbacks[0]["ts"]).total_seconds()

        if total_duration == 0:
            fired_avg = 0
            executed_avg = 0
        else:
            fired_avg = round(fired_total / total_duration, 1)
            executed_avg = round(executed_total / total_duration, 1)

        await self.set_state("sensor.callbacks_average_fired", state=fired_avg, _silent=True)
        await self.set_state(
            "sensor.callbacks_average_executed",
            state=executed_avg,
            _silent=True,
        )

        self.last_stats_time = now
        self.current_callbacks_executed = 0
        self.current_callbacks_fired = 0

    async def init_admin_stats(self):
        await self.add_entity("sensor.callbacks_total_fired", 0)
        await self.add_entity("sensor.callbacks_average_fired", 0)
        await self.add_entity("sensor.callbacks_total_executed", 0)
        await self.add_entity("sensor.callbacks_average_executed", 0)
        await self.add_entity("sensor.threads_current_busy", 0)
        await self.add_entity("sensor.threads_max_busy", 0)
        await self.add_entity("sensor.threads_max_busy_time", "never")
        await self.add_entity("sensor.threads_last_action_time", "never")

    def resolve_thread_counts(self) -> tuple[int, int]:
        """Resolve thread configuration into a concrete count of the total number of threads to create and the number of
        them to reserve for pinning."""
        pin_threads = self.AD.config.pin_threads
        total_threads = self.AD.config.total_threads

        # Handle determining the counts. Each logical path has an associated log message
        match total_threads, pin_threads:
            case 0, _: # Special case of 0 threads
                # Force pin_threads to 0
                pin_threads = 0
                self.logger.info("Starting apps with no worker threads.")
            case int(), int(): # Both are set in the configuration file
                assert total_threads > 0, "specified total_threads has to be above 0"
                assert pin_threads > 0, "specified pin_threads has to be above 0"
                assert pin_threads < total_threads, \
                    "pin_threads has to be less than total_threads if both are specified"
                self.logger.info(
                    "Starting apps with %d worker threads, with threads 0-%d reserved for pinned apps",
                    total_threads,
                    pin_threads - 1,
                )
            case int(), None: # Only total_threads was specified
                assert total_threads > 0, "specified total_threads has to be above 0"
                self.logger.info("Starting %d worker threads for apps", total_threads)
                if self.AD.config.pin_apps:
                    # If the global setting for apps is to pin them, use all the threads for pinning
                    pin_threads = total_threads
                    self.logger.info("All %d threads can be used for pinning.")
            case None, None: # AppDaemon will automatically determine thread counts
                if self.AD.config.pin_apps:
                    # If the global setting is to pin apps, then the thread counts are determined by the number of apps
                    total_threads = self.AD.app_management.dependency_manager.app_deps.app_config.active_app_count()
                    pin_threads = self.AD.app_management.pinned_app_count()
                    if total_threads == pin_threads:
                        self.logger.info("Starting each app with a dedicated thread (%d total)", total_threads)
                    else:
                        assert total_threads >= pin_threads
                        self.logger.info(
                            "Starting %d total threads, %d threads for pinning",
                            total_threads,
                            pin_threads
                        )
                else:
                    # Otherwise the thread counts default to 10
                    total_threads = pin_threads = 10
                    self.logger.info("Startinging with a default of 10 worker threads.")

        # Runtime checks to ensure that nothing weird happened
        match total_threads, pin_threads:
            case int(), int(): # Confirm thread counts at the end
                assert total_threads >= 0
                assert pin_threads <= total_threads, \
                    "pin_threads must be lower than total_threads"
                return total_threads, pin_threads
            case _: # Raise an error with the config if anything is weird
                raise ade.InvalidThreadConfiguration(
                    self.AD.config.total_threads,
                    self.AD.config.pin_apps,
                    self.AD.config.pin_threads,
                )

    async def create_initial_threads(self) -> None:
        """
        Creates the worker threads using self.add_thread().

        By default, the number of threads created is determined by the number of active (not disabled) apps. This can
        be overridden with the `total_threads` config setting.

        Also by default, all of the threads created will be for pinned apps, but this can be overridden to be just a
        subset of the `total_threads` with the `pin_threads` setting.
        """
        total_threads, pin_threads = self.resolve_thread_counts()
        for _ in range(total_threads - self.thread_count):
            await self.add_thread(silent=True)

        free_threads = list(self.threads.keys())[pin_threads:]
        self._roundrobin_cycle = cycle(free_threads)

        # Add thread object to track async
        if not self.AD.state.entity_exists("admin", "thread.async"):
            await self.add_entity(
                "thread.async",
                "idle",
                {
                    "q": 0,
                    "is_alive": True,
                    "time_called": "never",
                    "pinned_apps": [],
                },
            )

    def get_q(self, thread_id: str) -> Queue[dict[str, Any] | None]:
        match self.threads.get(thread_id):
            case {"queue": Queue() as q}:
                return q
        raise KeyError(f"Invalid thread_id: {thread_id}")

    def get_thread(self, thread_id: str) -> Thread:
        match self.threads.get(thread_id):
            case {"thread": Thread() as thread}:
                return thread
        raise KeyError(f"Invalid thread_id: {thread_id}")

    @staticmethod
    def atoi(text):
        return int(text) if text.isdigit() else text

    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split(r"(\d+)", text)]

    # Diagnostics

    def _q_iter(self) -> Generator[tuple[str, Queue]]:
        for thread_name, info in self.threads.items():
                match info:
                    case {"queue": Queue() as q}:
                        yield thread_name, q

    def total_q_size(self) -> int:
        return sum(q.qsize() for _, q in self._q_iter())

    def min_q_id(self) -> str:
        _, min_thread_name = min((q.qsize(), name) for name, q in self._q_iter())
        return min_thread_name

    async def get_thread_info(self):
        info = {
            attr: await self.get_state(f"sensor.threads_{attr}")
            for attr in (
                "max_busy_time",
                "last_action_time",
                "current_busy",
                "max_busy"
            )
        }
        info["threads"] = {}
        for thread in sorted(self.threads, key=self.natural_keys):
            if thread not in info["threads"]:
                info["threads"][thread] = {}
            t = await self.get_state(f"thread.{thread}", attribute="all")
            info["threads"][thread]["time_called"] = t["attributes"]["time_called"]
            info["threads"][thread]["callback"] = t["state"]
            info["threads"][thread]["is_alive"] = t["attributes"]["is_alive"]
        return info

    async def dump_threads(self):
        self.diag.info("--------------------------------------------------")
        self.diag.info("Threads")
        self.diag.info("--------------------------------------------------")
        current_busy = await self.get_state("sensor.threads_current_busy")
        max_busy = await self.get_state("sensor.threads_max_busy")
        max_busy_time = str_to_dt(await self.get_state("sensor.threads_max_busy_time"))
        last_action_time = await self.get_state("sensor.threads_last_action_time")
        self.diag.info("Currently busy threads: %s", current_busy)
        self.diag.info("Most used threads: %s at %s", max_busy, max_busy_time)
        self.diag.info("Last activity: %s", last_action_time)
        self.diag.info("Total Q Entries: %s", self.total_q_size())
        self.diag.info("--------------------------------------------------")
        for thread in sorted(self.threads, key=self.natural_keys):
            t = await self.get_state(f"thread.{thread}", attribute="all")
            # print("thread.{}".format(thread), t)
            self.diag.info(
                "%s - qsize: %s | current callback: %s | since %s, | alive: %s, | pinned apps: %s",
                thread,
                t["attributes"]["q"],
                t["state"],
                t["attributes"]["time_called"],
                t["attributes"]["is_alive"],
                self.get_pinned_apps(thread),
            )
        self.diag.info("--------------------------------------------------")

    #
    # Thread Management
    #

    def select_q(self, args: dict[str, Any]):
        """Selects the queue for the thread and calls put_nowait on it to dispatch the callback to the worker thread."""

        match args:
            case {"pin_app": True, "pin_thread": tid, "name": str(name)}:
                if tid is None:
                    tid = 0
                    self.logger.warning(
                        "Invalid thread ID for pinned thread in app: %s - assigning to thread 0", name
                    )
                thread_name = f'thread-{tid}'
            case {"pin_app": False}:
                # Putting this here to help with "find references"
                pin_threads = self.AD.config.pin_threads
                assert pin_threads is not None, (
                    "pin_threads has to be defined so AppDaemon knows which threads can be used for unpinned callbacks"
                )
                assert pin_threads < self.thread_count, (
                    "AppDaemon needs unreserved threads for unpinned callbacks"
                )

                match self.AD.config.load_distribution:
                    case "load":
                        thread_name = self.min_q_id()
                    case "random":
                        tid = randint(pin_threads, self.thread_count - 1)
                        thread_name = f'thread-{tid}'
                    case "roundrobin", _:
                        thread_name = next(self._roundrobin_cycle)
            case _:
                raise RuntimeError(f'Invalid queue args: {args}')

        match self.threads.get(thread_name):
            case {"queue": Queue() as q}:
                q.put_nowait(args)
            case _:
                raise RuntimeError(f"Invalid thread id {tid} for app '{args['name']}'")

    async def check_overdue_and_dead_threads(self):
        if self.AD.real_time is True and self.AD.thread_duration_warning_threshold != 0:
            for thread_id in self.threads:
                if not self.get_thread(thread_id).is_alive():
                    self.logger.critical("Thread %s has died", thread_id)
                    self.logger.critical("Pinned apps were: %s", self.get_pinned_apps(thread_id))
                    self.logger.critical("Thread will be restarted")
                    id = thread_id.split("-")[1]
                    await self.add_thread(silent=False, id=id)
                if await self.get_state(f"thread.{thread_id}") != "idle":
                    start = datetime.datetime.fromisoformat(
                        await self.get_state(f"thread.{thread_id}", attribute="time_called")
                    )
                    dur = (await self.AD.sched.get_now() - start).total_seconds()
                    if dur >= self.AD.thread_duration_warning_threshold and dur % self.AD.thread_duration_warning_threshold == 0:
                        self.logger.warning(
                            "Excessive time spent in callback: %s - %s",
                            await self.get_state(f"thread.{thread_id}", attribute="callback"),
                            dur,
                        )

    async def check_q_size(self, warning_step, warning_iterations):
        totalqsize = self.total_q_size()
        if totalqsize > self.AD.qsize_warning_threshold:
            if (warning_step == 0 and warning_iterations >= self.AD.qsize_warning_iterations) or warning_iterations == self.AD.qsize_warning_iterations:
                for thread in self.threads:
                    qsize = self.get_q(thread).qsize()
                    if qsize > 0:
                        time_called = await self.get_state(
                            "_threading",
                            "admin",
                            f"thread.{thread}",
                            attribute="time_called",
                        )
                        assert isinstance(time_called, str), "time_called is not a string"

                        self.logger.warning(
                            "Queue size for thread %s is %s, callback is '%s' called at %s - possible thread starvation",
                            thread,
                            qsize,
                            await self.get_state(f"thread.{thread}"),
                            await self.get_state(f"thread.{thread}", attribute="time_called"),
                        )

                await self.dump_threads()
                warning_step = 0
            warning_step += 1
            warning_iterations += 1
            if warning_step >= self.AD.qsize_warning_step:
                warning_step = 0
        else:
            warning_step = 0
            warning_iterations = 0

        return warning_step, warning_iterations

    async def update_thread_info(self, thread_id, callback, app, type, uuid, silent):
        self.logger.debug("Update thread info: %s", thread_id)
        if silent is True:
            return

        if self.AD.log_thread_actions:
            if callback == "idle":
                self.diag.info("%s done", thread_id)
            else:
                self.diag.info("%s calling %s callback %s", thread_id, type, callback)

        appinfo = self.AD.app_management.get_app_info(app)

        if appinfo is None:  # app possibly terminated
            return

        appentity = f"{appinfo.type}.{app}"
        now = await self.AD.sched.get_now()
        now_str = dt_to_str(now, self.AD.tz, round=True)

        if callback == "idle":
            start = str_to_dt(
                await self.get_state(f"thread.{thread_id}", attribute="time_called")
            )
            if start == "never":
                duration = 0.0
            else:
                duration = (now - start).total_seconds()

            if self.AD.real_time and duration >= self.AD.thread_duration_warning_threshold:
                thread_name = f"thread.{thread_id}"
                callback = await self.get_state(thread_name)
                self.logger.warning(
                    f"Excessive time spent in callback {callback}. "
                    f"Thread entity: '{thread_name}' - now complete after {format_timedelta(duration)} "
                    f"(limit={format_timedelta(self.AD.thread_duration_warning_threshold)})"
                )
            await self.add_to_state("sensor.threads_current_busy", -1)

            await self.add_to_attr(appentity, "totalcallbacks", 1)
            await self.add_to_attr(appentity, "instancecallbacks", 1)

            await self.add_to_attr(f"{type}_callback.{uuid}", "executed", 1)
            await self.add_to_state("sensor.callbacks_total_executed", 1)
            self.current_callbacks_executed += 1
        else:
            await self.add_to_state("sensor.threads_current_busy", 1)
            self.current_callbacks_fired += 1

        current_busy: int = await self.get_state("sensor.threads_current_busy")
        max_busy: int = await self.get_state("sensor.threads_max_busy")
        if current_busy > max_busy:
            await self.set_state("sensor.threads_max_busy", state=current_busy)
            await self.set_state("sensor.threads_max_busy_time", state=now_str)
            await self.set_state("sensor.threads_last_action_time", state=now_str)

        # Update thread info

        if thread_id == "async":
            await self.set_state(
                f"thread.{thread_id}",
                q=0,
                state=callback,
                time_called=now_str,
                is_alive=True,
                pinned_apps=[],
            )
        else:
            await self.set_state(
                f"thread.{thread_id}",
                q=self.get_q(thread_id).qsize(),
                state=callback,
                time_called=now_str,
                is_alive=self.get_thread(thread_id).is_alive(),
                pinned_apps=self.get_pinned_apps(thread_id),
            )
        await self.set_state(appentity, state=callback)

    #
    # Pinning
    #

    async def add_thread(self, silent: bool = False, id: int | None = None) -> None:
        """Create a new worker thread.

        This is where the Thread object is actually created and started. The thread will begin running the `worker`
        method as its target, and a new entity will be added to the `thread` domain in the `admin` namespace to track it.
        """
        if id is None:
            thread_id = self.thread_count
        else:
            thread_id = id
        if silent is False:
            self.logger.info("Adding thread %s", thread_id)
        thread = threading.Thread(target=self.worker, name=f"thread-{thread_id}", daemon=True)
        thread_entity = f"thread.{thread.name}"
        if id is None:
            await self.add_entity(
                thread_entity,
                "idle",
                {"q": 0, "is_alive": True, "time_called": "never"},
            )
            self.threads[thread.name] = {"queue": Queue(maxsize=0)}
            thread.start()
        else:
            await self.set_state(
                thread_entity,
                state="idle",
                is_alive=True,
            )

        self.threads[thread.name]["thread"] = thread

    async def assign_app_threads(self):
        """Assigns thread numbers to apps that are supposed to be pinned.

        Apps are assigned to threads based on how many other apps have been assigned to each thread. This depends on the
        `ManagedObject` instances having been already created.

        Updates the state of entities in the `thread` domain in the `admin` namespace. For example `thread.thread-0`.
        """
        _, pin_threads = self.resolve_thread_counts()

        if not pin_threads > 0:
            return

        if not self.AD.app_management.objects:
            self.logger.warning('No managed app objects to assign threads to.')

        # Get the apps that need to have threads assigned
        apps_to_assign = [
            name
            for name, mo in self.AD.app_management.objects.items()
            if mo.pin_app and mo.pin_thread is None
        ]  # fmt: skip

        counts = self.thread_app_counts()

        # Iterate through the names of all the apps that need threads assigned
        for app_name in apps_to_assign:
            # Get the name of the thread that has the fewest apps pinned to it
            _, min_tid = min((v, k) for k, v in counts.items())
            counts[min_tid] += 1
            self.AD.app_management.set_pin_thread(app_name, min_tid)

        for tid, pin_cnt in counts.items():
            await self.AD.state.set_state(
                "_threading",
                "admin",
                f"thread.thread-{tid}",
                pinned_apps=pin_cnt,
            )

    def thread_app_counts(self) -> dict[int, int]:
        """Get a dict that maps thread ID nums to how many apps are pinned to each one."""
        counts = {int(k.split('-')[-1]): 0 for k in self.threads}
        for obj in self.AD.app_management.objects.values():
            match obj:
                case ManagedObject(type="app", pin_thread=int(tid)):
                    try:
                        counts[tid] += 1
                    except KeyError:
                        # raise ade.PinThreadNotFound(pin_thread=tid) from exc
                        continue
        return counts

    def get_pinned_apps(self, thread: str | int) -> list[str]:
        """Gets the names of apps that are pinned to a particular thread"""
        match thread:
            case str():
                thread_id = int(thread.split("-")[1])
            case int(thread_id):
                pass
            case _:
                raise ValueError(f"Invalid thread: {thread}")
        return [app_name for app_name, obj in self.AD.app_management.objects.items() if obj.pin_thread == thread_id]

    def determine_thread(
        self,
        name: str,
        cb_pin: bool | None,
        cb_pin_thread: int | None
    ) -> tuple[bool, int | None]:
        """Determine pin settings for a callback using inputs from the callback registration with settings from the app
        management as defaults.

        If the callback thread is not specified, then which thread it gets called in should be calculated at call time
        to get good results from the different load distribution strategies. The length of the various thread queues can
        be wildly different at call time from when the callback was first registered.

        Dev Note:
            This method is a good place to handle things related to thread/pinning at callback registration.

        Returns:
            tuple[bool, int | None]: Whether to pin the callback and if so, what thread it should be pinned to.
        """
        # Manually specifying a pin_thread implies pin_app=True
        if cb_pin_thread is not None:
            # Validity check for the pin settings specified at the callback registration
            if cb_pin_thread < 0 or cb_pin_thread > self.AD.threading.thread_count:
                raise ade.PinOutofRange(cb_pin_thread, self.AD.threading.thread_count)
            pin_callback = True
        else:
            pin_callback = cb_pin if cb_pin is not None else self.AD.app_management.get_app_pin(name)

        callback_thread = cb_pin_thread if cb_pin_thread is not None else self.AD.app_management.get_pin_thread(name)
        return pin_callback, callback_thread

    #
    # Constraints
    #

    async def check_constraint(self, key, value, app: "ADBase"):
        """Used to check Constraint"""

        unconstrained = True
        if hasattr(app, "constraints") and key in app.constraints:
            method = getattr(app, key)
            unconstrained = await run_async_sync_func(self, method, value)

        return unconstrained

    async def check_time_constraint(self, args, name):
        """Used to check time Constraint"""

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
            in_between_window = await self.AD.sched.now_is_between(start_time=start_time, end_time=end_time)
            if not in_between_window:
                unconstrained = False

        return unconstrained

    async def check_days_constraint(self, args, name):
        """Used to check days Constraint"""

        unconstrained = True
        if "constrain_days" in args:
            days = args["constrain_days"]
            now = (await self.AD.sched.get_now()).astimezone(self.AD.tz)
            daylist = []
            for day in days.split(","):
                daylist.append(await run_in_executor(self, day_of_week, day))

            if now.weekday() not in daylist:
                unconstrained = False

        return unconstrained

    async def check_state_constraint(self, args, new_state, name):
        """Used to check state Constraint"""

        unconstrained = True
        if "constrain_state" in args:
            unconstrained = check_state(self.logger, new_state, args["constrain_state"], name)

        return unconstrained

    #
    # Workers
    #

    async def check_and_dispatch_state(
        self,
        name: str,
        funcref: Callable,
        entity: str,
        attribute: str,
        new_state: dict[str, Any],
        old_state: dict[str, Any],
        cold: Any,
        cnew: Any,
        kwargs: dict[str, Any],
        uuid_: str,
        pin_app: bool,
        pin_thread: int | None,
    ):
        executed = False
        # kwargs["handle"] = uuid_
        #
        #
        #
        if attribute == "all":
            executed = await self.dispatch_worker(
                name,
                {
                    "id": uuid_,
                    "name": name,
                    "objectid": self.AD.app_management.objects[name].id,
                    "type": "state",
                    "function": funcref,
                    "attribute": attribute,
                    "entity": entity,
                    "new_state": new_state,
                    "old_state": old_state,
                    "pin_app": pin_app,
                    "pin_thread": pin_thread,
                    "kwargs": kwargs,
                },
            )
        else:
            #
            # Let's figure out if we need to run a callback
            #
            # Start by figuring out what the incoming old value was
            #
            if old_state is None:
                old = None
            else:
                if attribute in old_state:
                    old = old_state[attribute]
                elif "attributes" in old_state and attribute in old_state["attributes"]:
                    old = old_state["attributes"][attribute]
                else:
                    old = None
            #
            # Now the incoming new value
            #
            if new_state is None:
                new = None
            else:
                if attribute in new_state:
                    new = new_state[attribute]
                elif "attributes" in new_state and attribute in new_state["attributes"]:
                    new = new_state["attributes"][attribute]
                else:
                    new = None

            #
            # Don't do anything unless there has been a change
            #
            if new != old:
                if "__duration" in kwargs:
                    #
                    # We have a pending timer for this, but we are coming around again.
                    # Either we will start a new timer if the conditions are met
                    # Or we won't if they are not.
                    # Either way, we cancel the old timer
                    #
                    if self.AD.sched.timer_running(name, kwargs["__duration"]):
                        await self.AD.sched.cancel_timer(name, kwargs["__duration"], False)

                    del kwargs["__duration"]

                #
                # Check if we care about the change
                #
                if (cold is None or cold == old or (callable(cold) and cold(old) is True)) and (cnew is None or cnew == new or (callable(cnew) and cnew(new) is True)):
                    #
                    # We do!
                    #

                    if "duration" in kwargs:
                        #
                        # Set a timer
                        #
                        exec_time = await self.AD.sched.get_now() + parse.parse_timedelta(kwargs["duration"])

                        #
                        # If it's a oneshot, scheduler will delete the callback once it has executed,
                        # We need to give it the handle so it knows what to delete
                        #
                        if kwargs.get("oneshot", False):
                            kwargs["__handle"] = uuid_

                        #
                        # We're not executing the callback immediately so let's schedule it
                        # Unless we intercede and cancel it, the callback will happen in "duration" seconds
                        #

                        kwargs["__duration"] = await self.AD.sched.insert_schedule(
                            name=name,
                            aware_dt=exec_time,
                            callback=funcref,
                            repeat=False,
                            type_=None,
                            __entity=entity,
                            __attribute=attribute,
                            __old_state=old,
                            __new_state=new,
                            **kwargs,
                        )
                    else:
                        #
                        # Not a delay so make the callback immediately
                        #
                        executed = await self.dispatch_worker(
                            name,
                            {
                                "id": uuid_,
                                "name": name,
                                "objectid": self.AD.app_management.objects[name].id,
                                "type": "state",
                                "function": funcref,
                                "attribute": attribute,
                                "entity": entity,
                                "new_state": new,
                                "old_state": old,
                                "pin_app": pin_app,
                                "pin_thread": pin_thread,
                                "kwargs": kwargs,
                            },
                        )

        return executed

    async def dispatch_worker(self, name: str, args: dict[str, Any]):
        """Apply any constraints and if they pass, dispatch the callback to the worker thread by using the ``select_q``
        method."""

        # Give user the option to discard events during the app initialize methods to prevent race conditions
        state = await self.get_state(f"app.{name}")
        if state == "initializing" and self.AD.config.discard_init_events:
            self.logger.info("Incoming event while initializing - discarding")
            return

        unconstrained = True
        #
        # Argument Constraints
        # (plugins have no args so skip if necessary)
        #
        match self.AD.app_management.app_config.root.get(name):
            case AppConfig(disable=False) as app_cfg:
                for arg, val in app_cfg.args.items():
                    constrained = await self.check_constraint(
                        arg,
                        val,
                        self.AD.app_management.objects[name].object,
                    )
                    if not constrained:
                        unconstrained = False
                if not await self.check_time_constraint(app_cfg.args, name):
                    unconstrained = False
                elif not await self.check_days_constraint(app_cfg.args, name):
                    unconstrained = False

        #
        # Callback level constraints
        #
        myargs = ad_deepcopy(args)
        if "kwargs" in myargs:
            for arg in myargs["kwargs"].keys():
                constrained = await self.check_constraint(
                    arg,
                    myargs["kwargs"][arg],
                    self.AD.app_management.objects[name].object,
                )
                if not constrained:
                    unconstrained = False
            if not await self.check_time_constraint(myargs["kwargs"], name):
                unconstrained = False
            elif not await self.check_days_constraint(myargs["kwargs"], name):
                unconstrained = False

            #
            # Lets determine the state constraint
            #
            if myargs["type"] == "state":
                state_unconstrained = await self.check_state_constraint(myargs["kwargs"], myargs["new_state"], name)
                unconstrained = all((unconstrained, state_unconstrained))

        if unconstrained:
            #
            # It's going to happen
            #
            if "__silent" in args["kwargs"] and args["kwargs"]["__silent"] is True:
                pass
            else:
                await self.add_to_state("sensor.callbacks_total_fired", 1)
                await self.add_to_attr(f"{myargs['type']}_callback.{myargs['id']}", "fired", 1)
            #
            # And Q
            #
            if asyncio.iscoroutinefunction(myargs["function"]):
                future = asyncio.ensure_future(self.async_worker(myargs))
                self.AD.futures.add_future(name, future)
            else:
                self.select_q(myargs)
            return True
        else:
            return False

    # noinspection PyBroadException
    async def async_worker(self, args):  # noqa: C901
        thread_id = threading.current_thread().name
        _type = args["type"]
        funcref = args["function"]
        _id = args["id"]
        objectid = args["objectid"]
        name = args["name"]
        error_logger = logging.getLogger(f"Error.{name}")
        args["kwargs"]["__thread_id"] = thread_id

        silent = False
        if "__silent" in args["kwargs"]:
            silent = args["kwargs"]["__silent"]

        app = self.AD.app_management.get_app_instance(name, objectid)
        if app is not None:
            try:
                pos_args = tuple()
                kwargs = dict()
                match _type:
                    case "scheduler":
                        kwargs = self.AD.sched.sanitize_timer_kwargs(app, args["kwargs"])

                    case "state":
                        pos_args = (
                            args["entity"],
                            args["attribute"],
                            args["old_state"],
                            args["new_state"],
                        )
                        kwargs = self.AD.state.sanitize_state_kwargs(app, args["kwargs"])

                    case "log":
                        data = args["data"]
                        pos_args = (
                            data["app_name"],
                            data["ts"],
                            data["level"],
                            data["log_type"],
                            data["message"],
                        )
                        kwargs = self.AD.logging.sanitize_log_kwargs(app, args["kwargs"])

                    case "event":
                        data = args["data"]
                        pos_args = (args["event"], data)
                        kwargs = self.AD.events.sanitize_event_kwargs(app, args["kwargs"])

                use_dictionary_unpacking = has_expanded_kwargs(funcref)
                if use_dictionary_unpacking:
                    funcref = functools.partial(funcref, *pos_args, **kwargs)
                else:
                    if isinstance(funcref, functools.partial):
                        pos_args += funcref.args
                        kwargs.update(funcref.keywords)
                        funcref = functools.partial(funcref.func, kwargs)
                    else:
                        funcref = functools.partial(funcref, *pos_args, kwargs)

                callback = f"{funcref.func.__name__}() in {name}"
                await self.update_thread_info("async", callback, name, _type, _id, silent)

                @ade.wrap_async(error_logger, self.AD.app_dir, callback)
                async def safe_callback():
                    """Wraps actually calling the function for the callback with logic to transform exceptions based
                    on the callback type"""
                    self.AD.app_management.objects[name].increment_callback_counter()
                    try:
                        await funcref()
                    except Exception as exc:
                        # positional arguments common to all the AppCallbackFail exceptions
                        pos_args = (name, funcref)
                        match args["type"]:
                            case "event":
                                raise ade.EventCallbackFail(*pos_args, args["event"]) from exc
                            case "scheduler":
                                raise ade.SchedulerCallbackFail(*pos_args) from exc
                            case "state":
                                raise ade.StateCallbackFail(*pos_args, args["entity"]) from exc
                            case _:
                                raise ade.AppCallbackFail(*pos_args) from exc

                await safe_callback()

            finally:
                await self.update_thread_info("async", "idle", name, _type, _id, silent)
        else:
            if not self.AD.stopping:
                self.logger.warning("Found stale callback for %s - discarding", name)

    # noinspection PyBroadException
    def worker(self):  # noqa: C901
        thread_id = threading.current_thread().name
        q = self.get_q(thread_id)
        while True:
            match args := q.get():
                case {"type": _type, "function": funcref, "id": _id, "objectid": objectid, "name": name, "kwargs": kwargs}:
                    args["kwargs"]["__thread_id"] = thread_id
                    error_logger = logging.getLogger(f"Error.{name}")
                    silent = kwargs.get("__silent", False)
                case None:
                    self.logger.debug("Stopping worker thread %s", thread_id)
                    break
                case _:
                    self.logger.warning("Unknown callback type for %s - discarding", name)
                    return

            app = self.AD.app_management.get_app_instance(name, objectid)
            if app is not None:
                try:
                    pos_args = tuple()
                    kwargs = dict()
                    match _type:
                        case "scheduler":
                            kwargs = self.AD.sched.sanitize_timer_kwargs(app, args["kwargs"])

                        case "state":
                            pos_args = (
                                args["entity"],
                                args["attribute"],
                                args["old_state"],
                                args["new_state"],
                            )
                            kwargs = self.AD.state.sanitize_state_kwargs(app, args["kwargs"])

                        case "log":
                            data = args["data"]
                            pos_args = (
                                data["app_name"],
                                data["ts"],
                                data["level"],
                                data["log_type"],
                                data["message"],
                            )
                            kwargs = self.AD.logging.sanitize_log_kwargs(app, args["kwargs"])

                        case "event":
                            pos_args = (args["event"], args["data"])
                            kwargs = self.AD.events.sanitize_event_kwargs(app, args["kwargs"])

                    use_dictionary_unpacking = has_expanded_kwargs(funcref)
                    if use_dictionary_unpacking:
                        funcref = functools.partial(funcref, *pos_args, **kwargs)
                    else:
                        if isinstance(funcref, functools.partial):
                            pos_args += funcref.args
                            kwargs.update(funcref.keywords)
                            funcref = functools.partial(funcref.func, kwargs)
                        else:
                            funcref = functools.partial(funcref, *pos_args, kwargs)

                    callback = f"{funcref.func.__qualname__} for {name}"
                    update_coro = self.update_thread_info(thread_id, callback, name, _type, _id, silent)
                    run_coroutine_threadsafe(self, update_coro)

                    @ade.wrap_sync(error_logger, self.AD.app_dir, callback)
                    def safe_callback():
                        """Wraps actually calling the function for the callback with logic to transform exceptions based
                        on the callback type"""
                        self.AD.app_management.objects[name].increment_callback_counter()
                        try:
                            funcref()
                        except Exception as exc:
                            # positional arguments common to all the AppCallbackFail exceptions
                            exc_args = (name, funcref)
                            match args["type"]:
                                case "event":
                                    raise ade.EventCallbackFail(*exc_args, args["event"]) from exc
                                case "scheduler":
                                    raise ade.SchedulerCallbackFail(*exc_args) from exc
                                case "state":
                                    raise ade.StateCallbackFail(*exc_args, args["entity"]) from exc
                                case _:
                                    raise ade.AppCallbackFail(*exc_args) from exc

                    safe_callback()

                finally:
                    update_coro = self.update_thread_info(thread_id, "idle", name, _type, _id, silent)
                    run_coroutine_threadsafe(self, update_coro)
                    q.task_done()  # Have this in multiple places to ensure it gets called even if an exception is raised
            else:
                if not self.AD.stopping:
                    self.logger.warning(f"Found stale callback for {name} - discarding")
                q.task_done()

        self.logger.debug("Shutdown worker thread queue %s", thread_id)

    def report_callback_sig(self, name, type, funcref, args):
        error_logger = logging.getLogger("Error.{}".format(name))

        callback_args = {
            "scheduler": {"count": 1, "signature": {True: "f(self, **kwargs)", False: "f(self, kwargs)"}},
            "state": {
                "count": 5,
                "signature": {
                    True: "f(self, entity, attribute, old, new, **kwargs)",
                    False: "f(self, entity, attribute, old, new, kwargs)",
                },
            },
            "event": {
                "count": 3,
                "signature": {True: "f(self, event, data, **kwargs)", False: "f(self, event, data, kwargs)"},
            },
            "log_event": {
                "count": 6,
                "signature": {
                    True: "f(self, name, ts, level, type, message, kwargs)",
                    False: "f(self, name, ts, level, type, message, kwargs)",
                },
            },
            "initialize": {"count": 0, "signature": {True: "initialize()", False: "initialize()"}},
            "terminate": {"count": 0, "signature": {True: "terminate()", False: "terminate()"}},
        }

        use_dictionary_unpacking = has_expanded_kwargs(funcref)

        try:
            if isinstance(funcref, functools.partial):
                funcref = funcref.func

            sig = inspect.signature(funcref)

            if type in callback_args:
                if len(sig.parameters) != callback_args[type]["count"]:
                    self.logger.warning(
                        "Suspect incorrect signature type for callback %s() in %s, should be %s - discarding",
                        funcref.__name__,
                        name,
                        callback_args[type]["signature"][use_dictionary_unpacking],
                    )
                with self.log_lock:
                    error_logger = logging.getLogger("Error.{}".format(name))
                    error_logger.warning("-" * 60)
                    error_logger.warning("Unexpected error in worker for App %s:", name)
                    error_logger.warning("Worker Args: %s", args)
                    error_logger.warning("-" * 60)
                    error_logger.warning(traceback.format_exc())
                    error_logger.warning("-" * 60)
                if self.AD.logging.separate_error_log() is True:
                    self.logger.warning("Logged an error to %s", self.AD.logging.get_filename("error_log"))

            else:
                self.logger.error("Unknown callback type: %s", type)

        except ValueError:
            self.logger.error("Error in callback signature in %s, for App=%s", funcref, name)
        except BaseException:
            with self.log_lock:
                error_logger.warning("-" * 60)
                error_logger.warning("Unexpected error validating callback format in %s, for App=%s", funcref, name)
                error_logger.warning("-" * 60)
                error_logger.warning(traceback.format_exc())
                error_logger.warning("-" * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning(
                    "Logged an error to %s",
                    self.AD.logging.get_filename("error_log"),
                )
