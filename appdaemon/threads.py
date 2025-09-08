import asyncio
import functools
import inspect
import logging
import queue
import threading
import traceback
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from itertools import count
from logging import Logger
from queue import Queue
from random import randint
from threading import Thread
from typing import TYPE_CHECKING, Any, Literal, overload

from appdaemon.app_management import ManagedObject

from . import exceptions as ade
from . import utils
from .models.config.app import AppConfig

if TYPE_CHECKING:
    from .adbase import ADBase
    from .appdaemon import AppDaemon


@dataclass
class ManagedThread:
    thread: Thread
    queue: Queue[dict[str, Any] | None]
    id: int = field(init=False)

    def __post_init__(self) -> None:
        self.id = int(self.thread.name.split("-", 1)[1])


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
    threads: dict[str, ManagedThread]
    """Dictionary with keys of the thread ID (string beginning with `thread-`) and values of
    :py:class:`ManagedThread` objects.
    """

    last_stats_time: datetime
    callback_list: list[dict]

    next_thread: int = 0
    current_callbacks_executed: int = 0
    current_callbacks_fired: int = 0

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child(self.name)
        self.log_lock = threading.Lock()
        self.diag = ad.logging.get_diag()
        self.threads = {}
        self.last_stats_time = utils.MIN_DATETIME
        self.callback_list = []
        self.add_entity = functools.partial(ad.state.add_entity, "admin")

    @property
    def auto_pin(self) -> bool:
        """This is derived from pin_apps and total_threads, and is True by default."""
        return self.pin_apps and self.total_threads is None

    @property
    def pin_apps(self) -> bool:
        "Config flag for whether each app should be pinned to a thread"
        return self.AD.config.pin_apps

    @pin_apps.setter
    def pin_apps(self, new: bool) -> None:
        """Set the config flag for whether each app should be pinned to a thread"""
        self.AD.config.pin_apps = bool(new)

    @property
    def pin_threads(self) -> int | None:
        """Config value for the number of threads that are dedicated to pinned apps."""
        return self.AD.config.pin_threads

    @pin_threads.setter
    def pin_threads(self, new: int | None) -> None:
        """Set the number of threads that are dedicated to pinned apps."""
        assert isinstance(new, int) or new is None, "pin_threads must be an integer or None"
        self.AD.config.pin_threads = new

    @property
    def thread_count(self) -> int:
        """The number of threads that have actually been created. This is calculated from the length of the internal
        `threads` dictionary, so it can't be set directly."""
        return len(self.threads)

    @property
    def total_threads(self) -> int | None:
        """Number of threads to create for apps.

        By default this is automatically calculated, but can also be manually configured by the user in
        ``appdaemon.yaml``.
        """
        return self.AD.config.total_threads

    @total_threads.setter
    def total_threads(self, new: int):
        self.AD.config.total_threads = new

    def stop(self):
        """Stop all threads."""
        for thread in self.threads.values():
            match thread:
                case {"queue": Queue() as q, "thread": Thread() as t}:
                    q.put(None)
                    t.join(timeout=1)

    async def _add_to_attr(self, entity: str, attribute: str, i: int = 1) -> None:
        return await self.AD.state.add_to_attr(self.name, "admin", entity, attribute, i)

    async def _add_to_state(self, entity: str, i: int = 1) -> None:
        return await self.AD.state.add_to_state(self.name, "admin", entity, i)

    def _format_thread_name(self, input_: int | str) -> str:
        """Ensures a formatted thread ID string of the format ``thread-<ID>`` is returned."""
        match input_:
            case int(thread_num):
                return f"thread-{thread_num}"
            case "async" | "thread.async":
                return "async"
            case str(thread_str):
                if thread_str.startswith("thread-"):
                    return thread_str
                elif thread_str.startswith("thread.thread-"):
                    return thread_str.split(".", 1)[1]
                else:
                    raise ValueError(f'Invalid thread ID: {input_}')

    def _format_thread_entity(self, input_: int | str) -> str:
        """Ensures a formatted thread entity string of the format ``thread.thread-<ID>`` is returned."""
        return f"thread.{self._format_thread_name(input_)}"

    def _get_state(self, entity: str, attribute: str = "state") -> str | int | dict[str, Any] | None:
        match val := self.AD.state.get_state(self.name, "admin", entity, attribute=attribute):
            case datetime() as dt:
                return utils.dt_to_str(dt)
            case _:
                return val

    @overload
    def _get_thread_state(self, thread_id: int | str, attribute: Literal["all"]) -> dict[str, Any] | None: ...

    @overload
    def _get_thread_state(self, thread_id: int | str, attribute: str) -> str | int | None: ...

    def _get_thread_state(self, thread_id: int | str, attribute: str) -> str | int | dict[str, Any] | None:
        return self._get_state(self._format_thread_entity(thread_id), attribute=attribute)

    async def _set_state(self, entity: str, state: str | int | float | None = None, **kwargs: Any) -> dict[str, Any]:
        return await self.AD.state.set_state(self.name, "admin", entity, state=state, **kwargs)

    def _sorted_threads(self) -> OrderedDict[str, ManagedThread]:
        return OrderedDict(sorted(self.threads.items(), key=lambda item: item[1].id))

    async def update_queue_sizes(self) -> None:
        """Update the admin entities for the threads with the current queue sizes."""
        for thread, thread_info in self.threads.items():
            match thread_info:
                case ManagedThread(queue=Queue() as q):
                    await self._set_state(self._format_thread_entity(thread), q=q.qsize())

    async def get_callback_update(self) -> None:
        """Updates the sensors with information about how many callbacks have been fired. Called by the
        :py:class:`~appdaemon.admin_loop.AdminLoop`

        - ``sensor.callbacks_average_fired``
        - ``sensor.callbacks_average_executed``
        """
        now = self.AD.sched.get_now_sync().replace(tzinfo=None)
        self.callback_list.append({"fired": self.current_callbacks_fired, "executed": self.current_callbacks_executed, "ts": now})

        if len(self.callback_list) > 10:
            self.callback_list.pop(0)

        fired_sum = 0
        executed_sum = 0
        for item in self.callback_list:
            fired_sum += item["fired"]
            executed_sum += item["executed"]

        total_duration = (self.callback_list[len(self.callback_list) - 1]["ts"] - self.callback_list[0]["ts"]).total_seconds()

        if total_duration == 0:
            fired_avg = 0
            executed_avg = 0
        else:
            fired_avg = round(fired_sum / total_duration, 1)
            executed_avg = round(executed_sum / total_duration, 1)

        await self._set_state("sensor.callbacks_average_fired", state=fired_avg, _silent=True)
        await self._set_state("sensor.callbacks_average_executed", state=executed_avg, _silent=True)

        self.last_stats_time = now
        self.current_callbacks_executed = 0
        self.current_callbacks_fired = 0

    def _init_admin_stats(self) -> None:
        """Create all the admin sensor entities used to track callback and thread stats."""
        self.add_entity("sensor.callbacks_total_fired", 0)
        self.add_entity("sensor.callbacks_average_fired", 0)
        self.add_entity("sensor.callbacks_total_executed", 0)
        self.add_entity("sensor.callbacks_average_executed", 0)
        self.add_entity("sensor.threads_current_busy", 0)
        self.add_entity("sensor.threads_max_busy", 0)

        min_string = utils.dt_to_str(utils.MIN_DATETIME)
        self.add_entity("sensor.threads_max_busy_time", min_string)
        self.add_entity("sensor.threads_last_action_time", min_string)

    async def create_initial_threads(self) -> None:
        """
        Creates the worker threads using self.add_thread().

        By default, the number of threads created is determined by the number of active (not disabled) apps. This can
        be overridden with the `total_threads` config setting.

        Also by default, all of the threads created will be for pinned apps, but this can be overridden to be just a
        subset of the `total_threads` with the `pin_threads` setting.
        """
        match self.total_threads, self.pin_apps:
            case None, True:
                self.total_threads = self.pin_threads = self.AD.app_management.dependency_manager.app_deps.app_config.active_app_count or 1
                self.logger.info(
                    "Starting apps with %s worker threads. Apps will all be assigned threads and pinned to them.",
                    self.total_threads,
                )
            case int(), False:
                self.logger.info(
                    "Starting apps with %s worker threads, with %s reserved for pinned apps",
                    self.total_threads,
                    self.pin_threads,
                )
                self.pin_threads = 0
            case _:
                self.logger.error("Invalid thread configuration.")
                raise ade.InvalidThreadConfiguration(
                    self.total_threads,
                    self.pin_apps,
                    self.pin_threads,
                )

        assert self.pin_threads is not None
        assert self.total_threads is not None and self.total_threads > 0
        for _ in range(self.total_threads):
            await self.add_thread(silent=True)

        # Add thread object to track async
        self.add_entity(
            "thread.async",
            "idle",
            {
                "q": 0,
                "is_alive": True,
                "time_called": utils.dt_to_str(utils.MIN_DATETIME),
                "pinned_apps": [],
            },
        )

    def get_q(self, thread_id: int | str) -> Queue[dict[str, Any] | None]:
        """Get a queue associated with a thread.

        Args:
            thread_id (int | str): Thread ID, either as an integer or a string beginning with ``thread-``
        """
        match self.threads[self._format_thread_name(thread_id)]:
            case ManagedThread(queue=Queue() as q):
                return q
            case _:
                raise TypeError(f"Invalid queue for thread {thread_id}")

    # Diagnostics

    def total_q_size(self) -> int:
        return sum(mt.queue.qsize() for mt in self.threads.values())

    def min_q_id(self) -> int:
        min_thread = min(self.threads.keys(), key=lambda k: self.threads[k].queue.qsize())
        return int(min_thread.split("-", 1)[1])

    async def get_thread_info(self) -> dict[str, Any]:
        info = {
            "max_busy_time": self._get_state("sensor.threads_max_busy_time"),
            "last_action_time": self._get_state("sensor.threads_last_action_time"),
            "current_busy": self._get_state("sensor.threads_current_busy"),
            "max_busy": self._get_state("sensor.threads_max_busy"),
            "threads": {},
        }
        for thread in self._sorted_threads():
            if thread not in info["threads"]:
                info["threads"][thread] = {}

            match self._get_thread_state(thread, attribute="all"):
                case {"state": state, "attributes": {"time_called": time_called, "is_alive": alive}}:
                    info["threads"][thread].update(
                        {
                            "time_called": time_called,
                            "callback": state,
                            "is_alive": alive,
                        }
                    )
        return info

    def dump_threads(self):
        self.diag.info("--------------------------------------------------")
        self.diag.info("Threads")
        self.diag.info("--------------------------------------------------")
        current_busy = self._get_state("sensor.threads_current_busy")
        max_busy = self._get_state("sensor.threads_max_busy")
        max_busy_time = self._get_state("sensor.threads_max_busy_time")
        last_action_time = self._get_state("sensor.threads_last_action_time")
        self.diag.info("Currently busy threads: %s", current_busy)
        self.diag.info("Most used threads: %s at %s", max_busy, max_busy_time)
        self.diag.info("Last activity: %s", last_action_time)
        self.diag.info("Total queue size: %s", self.total_q_size())
        self.diag.info("--------------------------------------------------")
        for thread in self._sorted_threads():
            match self._get_thread_state(thread, attribute="all"):
                case {"attributes": {"q": q, "time_called": time_called, "is_alive": is_alive}, "state": state}:
                    self.diag.info(
                        "%s - qsize: %s | current callback: %s | since %s, | alive: %s, | pinned apps: %s",
                        thread,
                        q,
                        state,
                        time_called,
                        is_alive,
                        self.get_pinned_apps(thread),
                    )
        self.diag.info("--------------------------------------------------")

    #
    # Thread Management
    #

    def select_q(self, pin_app: bool = True, pin_thread: int | None = None, **kwargs: Any) -> None:
        #
        # Select Q based on distribution method:
        #   Round Robin
        #   Random
        #   Load distribution
        #

        # Check for pinned app and if so figure correct thread for app
        if pin_app:
            thread = pin_thread
            # Handle the case where an App is unpinned but selects a pinned callback without specifying a thread
            # If this happens a lot, thread 0 might get congested but the alternatives are worse!
            if thread is None or thread < 0:
                self.logger.warning(
                    "Invalid thread ID for pinned thread in app: %s - assigning to thread 0",
                    kwargs["name"],
                )
                thread = 0
        else:
            if self.thread_count == self.pin_threads:
                raise ValueError("pin_threads must be set lower than threads if unpinned_apps are in use")

            match self.AD.load_distribution:
                case "load":
                    thread = self.min_q_id()
                case "random":
                    assert self.pin_threads is not None
                    thread = randint(self.pin_threads, self.thread_count - 1)
                case _:
                    # Round Robin is the catch all
                    thread = self.next_thread
                    self.next_thread += 1
                    if self.next_thread == self.thread_count:
                        assert self.pin_threads is not None
                        self.next_thread = self.pin_threads

        if thread < 0 or thread >= self.thread_count:
            raise ValueError(f"invalid thread id: {thread} in app {kwargs['name']}")

        self.threads[self._format_thread_name(thread)].queue.put_nowait(kwargs)

    async def check_overdue_and_dead_threads(self) -> None:
        if self.AD.real_time is True and self.AD.thread_duration_warning_threshold != 0:
            for thread_name, thread_info in self.threads.items():
                thread_entity = self._format_thread_entity(thread_name)

                match thread_info:
                    case ManagedThread(thread=Thread() as t) if not t.is_alive():
                        self.logger.critical("Thread %s has died", thread_name)
                        self.logger.critical("Pinned apps were: %s", self.get_pinned_apps(thread_name))
                        self.logger.critical("Thread will be restarted")
                        thread_id = int(thread_name.split("-")[1])
                        await self.restart_thread(thread_id)

                match self._get_state(thread_entity, "all"):
                    case {"state": "idle"}:
                        continue
                    case {"attributes": {"time_called": str(time_str)}, "callback": str(callback)}:
                        now = await self.AD.sched.get_now()
                        start = utils.str_to_dt(time_str)
                        dur = (now - start).total_seconds()
                        if (
                            dur >= self.AD.thread_duration_warning_threshold and
                            dur % self.AD.thread_duration_warning_threshold == 0
                        ):
                            self.logger.warning("Excessive time spent in callback: %s - %s", callback, dur)

    def check_q_size(self, warning_step: int, warning_iterations: int) -> tuple[int, int]:
        totalqsize = self.total_q_size()
        if totalqsize > self.AD.qsize_warning_threshold:
            if (
                (
                    warning_step == 0 and
                    warning_iterations >= self.AD.qsize_warning_iterations
                ) or
                warning_iterations == self.AD.qsize_warning_iterations
            ):  # fmt: skip
                for thread, thread_info in self.threads.items():
                    thread_state = self._get_thread_state(thread, "all")
                    if thread_state is None:
                        self.logger.warning("No state found for thread %s", thread)
                        continue
                    match thread_info:
                        case ManagedThread(queue=Queue() as q) if (size := q.qsize()) > 0:
                            self.logger.warning(
                                "Queue size for thread %s is %s, callback is '%s' called at %s - possible thread starvation",
                                thread,
                                size,
                                thread_state.get("state", "unknown"),
                                thread_state.get("time_called", "never"),
                            )

                self.dump_threads()
                warning_step = 0
            warning_step += 1
            warning_iterations += 1
            if warning_step >= self.AD.qsize_warning_step:
                warning_step = 0
        else:
            warning_step = 0
            warning_iterations = 0

        return warning_step, warning_iterations

    async def update_thread_info(self, thread_id: str | int, callback: str, app: str, type: str, uuid: str, silent: bool) -> None:
        self.logger.debug("Update thread info: %s", thread_id)
        if silent is True:
            return

        now = await self.AD.sched.get_now()
        now_str = utils.dt_to_str(now, include_us=True)
        thread_entity = self._format_thread_entity(thread_id)

        match self.AD.app_management.get_managed_object(app):
            case ManagedObject(type=typ):
                appentity = f"{typ}.{app}"
            case None:
                return # app possibly terminated

        if self.AD.log_thread_actions:
            if callback == "idle":
                self.diag.info("%s done", thread_id)
            else:
                self.diag.info("%s calling %s callback %s", thread_id, type, callback)

        if callback == "idle":
            match self._get_thread_state(thread_entity, attribute="time_called"):
                case "never":
                    duration = 0.0
                case str(time_str):
                    start = utils.str_to_dt(time_str)
                    duration = (now - start).total_seconds()
                case _:
                    self.logger.warning("Invalid time_called for thread %s", thread_id)
                    return

            if self.AD.real_time and duration >= self.AD.thread_duration_warning_threshold:
                callback = self._get_state(thread_entity)
                self.logger.warning(
                    "Excessive time spent in callback %s. Thread entity: '%s' - now complete after %s (limit=%s)",
                    callback,
                    thread_entity,
                    utils.format_timedelta(duration),
                    utils.format_timedelta(self.AD.thread_duration_warning_threshold)
                )
            await self._add_to_state("sensor.threads_current_busy", -1)
            await self._add_to_state("sensor.callbacks_total_executed")
            await self._add_to_attr(appentity, "totalcallbacks")
            await self._add_to_attr(appentity, "instancecallbacks")
            await self._add_to_attr(f"{type}_callback.{uuid}", "executed")
            self.current_callbacks_executed += 1
        else:
            await self._add_to_state("sensor.threads_current_busy")
            self.current_callbacks_fired += 1

        current_busy = self._get_state("sensor.threads_current_busy")
        max_busy = self._get_state("sensor.threads_max_busy")
        match current_busy, max_busy:
            case (int() | float(), int() | float()) if current_busy > max_busy:
                await self._set_state("sensor.threads_max_busy", current_busy)
                await self._set_state("sensor.threads_max_busy_time", now_str)
                await self._set_state("sensor.threads_last_action_time", now_str)

        thread_state = {"state": callback, "time_called": now_str, "q": 0, "is_alive": True, "pinned_apps": []}
        match self.threads.get(self._format_thread_name(thread_id)):
            case ManagedThread(queue=Queue() as q, thread=Thread() as t):
                thread_state.update(
                    {
                        "q": q.qsize(),
                        "is_alive": t.is_alive(),
                        "pinned_apps": self.get_pinned_apps(thread_id),
                    }
                )

        await self._set_state(thread_entity, **thread_state)
        await self._set_state(appentity, state=callback)

    #
    # Pinning
    #

    async def restart_thread(self, thread_id: int | str) -> None:
        thread_id = self._format_thread_name(thread_id)
        match self.threads.pop(thread_id):
            case ManagedThread(thread=Thread() as old_thread):
                assert not old_thread.is_alive()
                old_thread.join(timeout=1)
        await self.add_thread(id=thread_id, silent=False)

    def _new_thread_num(self) -> int:
        for i in count():
            if self._format_thread_name(i) not in self.threads:
                return i
        raise RuntimeError("Unable to determine new thread number")

    async def add_thread(self, *, silent: bool = False, id: int | str | None = None) -> None:
        thread_id = self._new_thread_num() if id is None else id

        if not silent:
            self.logger.info("Adding thread %s", thread_id)

        thread_name = self._format_thread_name(thread_id)
        match self.threads.get(thread_name):
            case ManagedThread(queue=Queue() as q):
                queue = q
            case _:
                queue = Queue(maxsize=0)

        thread = threading.Thread(target=self.worker, name=thread_name, args=(queue,), daemon=True)
        self.threads[thread.name] = ManagedThread(thread=thread, queue=queue)

        update_kwargs = {"state": "idle", "is_alive": True}
        if not self.AD.state.entity_exists("admin", self._format_thread_entity(thread_id)):
            update_kwargs["q"] = 0
            update_kwargs["time_called"] = utils.dt_to_str(utils.MIN_DATETIME)

        await self._set_state(self._format_thread_entity(thread_id), _silent=silent, **update_kwargs)
        thread.start()

    async def calculate_pin_threads(self) -> None:
        """Assigns thread numbers to apps that are supposed to be pinned"""
        if self.pin_threads == 0:
            return

        thread_pins = [0] * self.pin_threads
        for name, obj in self.AD.app_management.objects.items():
            # Looking for apps that already have a thread pin value
            if obj.pin_app and (thread := obj.pin_thread) != -1:
                if thread >= self.thread_count:
                    raise ValueError("Pinned thread out of range - check apps.yaml for 'pin_thread' or app code for 'set_pin_thread()'")
                # Ignore anything outside the pin range as it will have been set by the user
                if thread < self.pin_threads:
                    thread_pins[thread] += 1

        # Now we know the numbers, go fill in the gaps
        for name, obj in self.AD.app_management.objects.items():
            if obj.pin_app and obj.pin_thread == -1:
                thread = thread_pins.index(min(thread_pins))
                self.AD.app_management.set_pin_thread(name, thread)
                thread_pins[thread] += 1

        for thread in self.threads:
            await self._set_state(self._format_thread_entity(thread), pinned_apps=self.get_pinned_apps(thread))

    def app_should_be_pinned(self, app_name: str) -> bool:
        # Check apps.yaml first - allow override
        cfg = self.AD.app_management.app_config.root[app_name]
        assert isinstance(cfg, AppConfig)
        return cfg.pin_app or self.pin_apps

    def validate_pin(self, name: str, pin_thread: int | None) -> None:
        """Check to see if the ID for the pin thread is valid.

        Raises:
            PinOutofRange: if the pin_thread is not valid.

        Returns:
            None
        """
        if pin_thread is not None and (pin_thread < 0 or pin_thread >= self.thread_count):
            self.logger.warning(
                "Invalid value for pin_thread (%s) in app: %s - discarding callback",
                pin_thread,
                name,
            )
            raise ade.PinOutofRange(pin_thread, self.thread_count)

    def get_pinned_apps(self, thread: str | int) -> list[str]:
        """Gets the names of apps that are pinned to a particular thread"""
        match self.threads.get(self._format_thread_name(thread)):
            case ManagedThread(id=int(id_)):
                return [app_name for app_name, obj in self.AD.app_management.objects.items() if obj.pin_thread == id_]
            case _:
                return []

    def determine_thread(self, name: str, pin: bool | None, pin_thread: int | None) -> tuple[bool, int | None]:
        """Determine whether the app should be pinned to a thread and which one.

        Applies defaults from app management

        Returns:
            A tuple of (pin, pin_thread) where pin is ``True`` if the app should be pinned and pin_thread is the
            thread ID number
        """

        if pin_thread is None:
            pin = self.AD.app_management.objects[name].pin_app if pin is None else pin
            pin_thread = self.AD.app_management.objects[name].pin_thread
        else:
            assert isinstance(pin_thread, int)
            pin = True

        self.validate_pin(name, pin_thread)
        return bool(pin), pin_thread

    #
    # Constraints
    #

    async def check_constraint(self, key, value, app: "ADBase") -> bool:
        """Used to check constraints"""
        unconstrained = True
        if hasattr(app, "constraints") and key in app.constraints:
            method = getattr(app, key)
            unconstrained = await utils.run_async_sync_func(self, method, value)
        return unconstrained

    async def check_time_constraint(self, args: dict[str, Any]) -> bool:
        """Check the time constraint. Returns ``True`` if the constraint it met and the callback should proceed."""
        if "constrain_start_time" in args or "constrain_end_time" in args:
            in_between_window = self.AD.sched.now_is_between(
                start_time=args.get("constrain_start_time", "00:00:00"),
                end_time=args.get("constrain_end_time", "23:59:59"),
            )
            if not in_between_window:
                return False
        return True

    async def check_days_constraint(self, args: dict[str, Any]) -> bool:
        """Check the day of the week constraint. Returns ``True`` if the constraint it met and the callback should
        proceed."""
        match args:
            case {"constrain_days": str(days_str)}:
                daylist = set(map(utils.day_of_week, days_str.split(",")))
                current_weekday = (await self.AD.sched.get_now()).weekday()
                if current_weekday not in daylist:
                    return False
        return True

    async def check_state_constraint(self, args: dict[str, Any], new_state: str | int | float) -> bool:
        """Check the state constraint. Returns ``True`` if the constraint it met and the callback should proceed."""
        match args:
            case {"constrain_state": (str()| int() | float()) as constraint}:
                return new_state == constraint
            case {"constrain_state": Callable() as check}:
                return check(new_state)
            case {"constrain_state": constraints}:
                return new_state in constraints
        return True

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
                        exec_time = await self.AD.sched.get_now() + utils.parse_timedelta(kwargs["duration"])

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

    async def dispatch_worker(self, name: str, args: dict[str, Any]) -> bool:
        # Give user the option to discard events during the app initialize methods to prevent race conditions
        match self._get_state(f"app.{name}"):
            case "initializing" if self.AD.config.discard_init_events:
                self.logger.info("Incoming event while initializing - discarding")
                return False

        unconstrained = True
        #
        # Argument Constraints
        # (plugins have no args so skip if necessary)
        #
        match self.AD.app_management.app_config.root.get(name):
            case AppConfig() as app_cfg:
                for arg, val in app_cfg.args.items():
                    constrained = await self.check_constraint(
                        arg,
                        val,
                        self.AD.app_management.objects[name].object,
                    )
                    if not constrained:
                        unconstrained = False
                if not await self.check_time_constraint(app_cfg.args):
                    unconstrained = False
                elif not await self.check_days_constraint(app_cfg.args):
                    unconstrained = False
            case _:
                self.logger.warning("No app configuration found for %s - discarding callback", name)
                return False

        #
        # Callback level constraints
        #
        match args:
            case {"kwargs": dict(kwargs)}:
                for arg, val in kwargs.items():
                    constrained = await self.check_constraint(
                        arg,
                        val,
                        self.AD.app_management.objects[name].object,
                    )
                    if not constrained:
                        unconstrained = False
                if not await self.check_time_constraint(kwargs):
                    unconstrained = False
                elif not await self.check_days_constraint(kwargs):
                    unconstrained = False

        match args:
            # Determine the state constraint
            case {"type": "state", "kwargs": dict(kwargs), "new_state": new}:
                state_unconstrained = await self.check_state_constraint(kwargs, new)
                unconstrained = all((unconstrained, state_unconstrained))

        if unconstrained:
            #
            # It's going to happen
            #
            if not args["kwargs"].get("__silent"):
                await self._add_to_state("sensor.callbacks_total_fired")
                await self._add_to_attr("{type}_callback.{id}".format(**args), "fired")
            #
            # And Q
            #
            if asyncio.iscoroutinefunction(utils.unwrapped(args["function"])):
                future = asyncio.ensure_future(self.async_worker(args))
                self.AD.futures.add_future(name, future)
            else:
                self.select_q(**args)
            return True
        else:
            return False

    # noinspection PyBroadException
    async def async_worker(self, args: dict[str, Any]) -> None:  # noqa: C901
        match args:
            case {
                "type": _type,
                "function": funcref,
                "id": _id,
                "objectid": objectid,
                "name": name,
                "kwargs": raw_kwargs
            }:
                silent = raw_kwargs.get("__silent", False)
                thread_id = threading.current_thread().name
                raw_kwargs["__thread_id"] = thread_id
                error_logger = logging.getLogger(f"Error.{name}")
            case _:
                self.logger.warning("Invalid submission for async worker: %s", args)
                return

        app = self.AD.app_management.get_app_instance(name, objectid)
        if app is None and not self.AD.stopping:
            self.logger.warning("Found stale callback for %s - discarding", name)
            return

        try:
            pos_args = tuple()
            kwargs = dict()
            match args:
                case {"type": "Scheduler"}:
                    kwargs = self.AD.sched.sanitize_timer_kwargs(app, raw_kwargs)
                case {"type": "state", "entity": entity, "attribute": attr, "old_state": old, "new_state": new}:
                    pos_args = (entity, attr, old, new)
                    kwargs = self.AD.state.sanitize_state_kwargs(app, raw_kwargs)
                case {
                    "type": "log",
                    "data": {
                        "app_name": app_name,
                        "ts": ts,
                        "level": level,
                        "log_type": log_type,
                        "message": msg
                    }
                }:
                    pos_args = (app_name, ts, level, log_type, msg)
                    kwargs = self.AD.logging.sanitize_log_kwargs(app, raw_kwargs)
                case {"type": "event", "event": event, "data": data}:
                    pos_args = (event, data)
                    kwargs = self.AD.events.sanitize_event_kwargs(app, raw_kwargs)

            use_dictionary_unpacking = utils.has_expanded_kwargs(funcref)
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

    # noinspection PyBroadException
    def worker(self, q: queue.Queue) -> None:  # noqa: C901
        thread_name = threading.current_thread().name
        while (args := q.get()) is not None:
            try:
                match args:
                    case {"type": _type, "function": funcref, "id": _id, "objectid": objectid, "name": name, "kwargs": kwargs}:
                        args["kwargs"]["__thread_id"] = thread_name
                        error_logger = logging.getLogger(f"Error.{name}")
                        silent = kwargs.get("__silent", False)
                    case _:
                        self.logger.warning("Unknown callback type for %s - discarding", name)
                        continue

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

                        use_dictionary_unpacking = utils.has_expanded_kwargs(funcref)
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
                        update_coro = self.update_thread_info(thread_name, callback, name, _type, _id, silent)
                        utils.run_coroutine_threadsafe(self, update_coro)

                        @ade.wrap_sync(error_logger, self.AD.app_dir, callback)
                        def safe_callback() -> None:
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
                        update_coro = self.update_thread_info(thread_name, "idle", name, _type, _id, silent)
                        utils.run_coroutine_threadsafe(self, update_coro)
            finally:
                q.task_done()

        self.logger.debug("Shutdown worker thread queue %s", thread_name)

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

        use_dictionary_unpacking = utils.has_expanded_kwargs(funcref)

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
