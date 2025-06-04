import asyncio
import datetime
import functools
import inspect
import logging
import re
import sys
import threading
import traceback
from collections.abc import Callable
from logging import Logger
from queue import Queue
from random import randint
from threading import Thread
from typing import TYPE_CHECKING, Any, ClassVar

import iso8601

from . import exceptions as ade
from . import utils
from .models.config.app import AppConfig

if TYPE_CHECKING:
    from .adbase import ADBase
    from .appdaemon import AppDaemon
    from .models.config.app import AllAppConfig


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
    thread_count: int
    threads: dict[str, dict[str, Thread | Queue]]
    """Dictionary with keys of the thread ID (string beginning with `thread-`) and values of
    another dictionary with `thread` and `queue` keys that have values of
    :class:`~threading.Thread` and :class:`~queue.Queue` objects respectively.
    """

    last_stats_time: ClassVar[datetime.datetime] = datetime.datetime.fromtimestamp(0)
    callback_list: list[dict]

    pin_threads: int = 0
    total_threads: int

    next_thread: int = 0
    current_callbacks_executed: int = 0
    current_callbacks_fired: int = 0

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child(self.name)
        self.log_lock = threading.Lock()
        self.diag = ad.logging.get_diag()

        self.thread_count = 0
        self.threads = {}

        # A few shortcuts
        self.add_entity = ad.state.add_entity
        self.get_state = ad.state.get_state
        self.set_state = ad.state.set_state
        self.add_to_state = ad.state.add_to_state
        self.add_to_attr = ad.state.add_to_attr

        self.callback_list = []

    @property
    def pin_apps(self) -> bool:
        "Whether each app should be pinned to a thread"
        return self.AD.config.pin_apps

    @pin_apps.setter
    def pin_apps(self, new: bool) -> None:
        """Set whether each app should be pinned to a thread"""
        self.AD.config.pin_apps = new

    @property
    def total_threads(self) -> int:
        """Number of threads created for apps.

        By default this is automatically calculated, but can also be manually configured by the user in
        ``appdaemon.yaml``.
        """
        return self.AD.config.total_threads

    @total_threads.setter
    def total_threads(self, new: int):
        self.AD.config.total_threads = new

    async def get_q_update(self):
        """Updates queue sizes"""
        for thread in self.threads:
            qsize = self.get_q(thread).qsize()
            await self.set_state("_threading", "admin", "thread.{}".format(thread), q=qsize)

    async def get_callback_update(self):
        """Updates the sensors with information about how many callbacks have been fired. Called by the :class:`~appdaemon.admin_loop.AdminLoop`

        - ``sensor.callbacks_average_fired``
        - ``sensor.callbacks_average_executed``
        """
        now = datetime.datetime.now()
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

        await self.set_state("_threading", "admin", "sensor.callbacks_average_fired", state=fired_avg)
        await self.set_state(
            "_threading",
            "admin",
            "sensor.callbacks_average_executed",
            state=executed_avg,
        )

        self.last_stats_time = now
        self.current_callbacks_executed = 0
        self.current_callbacks_fired = 0

    async def init_admin_stats(self):
        # Initialize admin stats

        await self.add_entity("admin", "sensor.callbacks_total_fired", 0)
        await self.add_entity("admin", "sensor.callbacks_average_fired", 0)
        await self.add_entity("admin", "sensor.callbacks_total_executed", 0)
        await self.add_entity("admin", "sensor.callbacks_average_executed", 0)
        await self.add_entity("admin", "sensor.threads_current_busy", 0)
        await self.add_entity("admin", "sensor.threads_max_busy", 0)
        await self.add_entity(
            "admin",
            "sensor.threads_max_busy_time",
            utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0)),
        )
        await self.add_entity(
            "admin",
            "sensor.threads_last_action_time",
            utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0)),
        )

    async def create_initial_threads(self):
        if self.total_threads:
            self.pin_apps = False
        else:
            # Force a config check here so we have an accurate activate app count
            self.AD.app_management.logger.debug("Reading app config files to determine how many threads to make")
            cfg_paths = await self.AD.app_management.get_app_config_files()
            if not cfg_paths:
                self.logger.warning(f"No apps found in {self.AD.app_dir}. This is probably a mistake")
                self.total_threads = 10
            else:
                full_cfg: "AllAppConfig" = await self.AD.app_management.read_all(cfg_paths)
                self.total_threads = full_cfg.active_app_count

        if self.pin_apps:
            self.pin_threads = self.pin_threads or self.total_threads
        else:
            self.pin_threads = 0
            self.total_threads = self.total_threads or 10

        if self.pin_threads > self.total_threads:
            raise ValueError("pin_threads cannot be > total_threads")

        if self.pin_threads < 0:
            raise ValueError("pin_threads cannot be < 0")

        self.logger.info(
            "Starting Apps with %s workers and %s pins",
            self.total_threads,
            self.pin_threads,
        )

        self.next_thread = self.pin_threads

        self.thread_count = 0
        for _ in range(self.total_threads):
            await self.add_thread(silent=True)

        # Add thread object to track async
        await self.add_entity(
            "admin",
            "thread.async",
            "idle",
            {
                "q": 0,
                "is_alive": True,
                "time_called": utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0)),
                "pinned_apps": [],
            },
        )

    def get_q(self, thread_id: str) -> Queue:
        return self.threads[thread_id]["queue"]

    @staticmethod
    def atoi(text):
        return int(text) if text.isdigit() else text

    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split(r"(\d+)", text)]

    # Diagnostics

    def total_q_size(self):
        qsize = 0
        for thread in self.threads:
            qsize += self.threads[thread]["queue"].qsize()
        return qsize

    def min_q_id(self):
        id = 0
        i = 0
        qsize = sys.maxsize
        for thread in self.threads:
            if self.threads[thread]["queue"].qsize() < qsize:
                qsize = self.threads[thread]["queue"].qsize()
                id = i
            i += 1
        return id

    async def get_thread_info(self):
        info = {}
        info["max_busy_time"] = await self.get_state("_threading", "admin", "sensor.threads_max_busy_time")
        info["last_action_time"] = await self.get_state("_threading", "admin", "sensor.threads_last_action_time")
        info["current_busy"] = await self.get_state("_threading", "admin", "sensor.threads_current_busy")
        info["max_busy"] = await self.get_state("_threading", "admin", "sensor.threads_max_busy")
        info["threads"] = {}
        for thread in sorted(self.threads, key=self.natural_keys):
            if thread not in info["threads"]:
                info["threads"][thread] = {}
            t = await self.get_state("_threading", "admin", "thread.{}".format(thread), attribute="all")
            info["threads"][thread]["time_called"] = t["attributes"]["time_called"]
            info["threads"][thread]["callback"] = t["state"]
            info["threads"][thread]["is_alive"] = t["attributes"]["is_alive"]
        return info

    async def dump_threads(self):
        self.diag.info("--------------------------------------------------")
        self.diag.info("Threads")
        self.diag.info("--------------------------------------------------")
        current_busy = await self.get_state("_threading", "admin", "sensor.threads_current_busy")
        max_busy = await self.get_state("_threading", "admin", "sensor.threads_max_busy")
        max_busy_time = utils.str_to_dt(await self.get_state("_threading", "admin", "sensor.threads_max_busy_time"))
        last_action_time = await self.get_state("_threading", "admin", "sensor.threads_last_action_time")
        self.diag.info("Currently busy threads: %s", current_busy)
        self.diag.info("Most used threads: %s at %s", max_busy, max_busy_time)
        self.diag.info("Last activity: %s", last_action_time)
        self.diag.info("Total Q Entries: %s", self.total_q_size())
        self.diag.info("--------------------------------------------------")
        for thread in sorted(self.threads, key=self.natural_keys):
            t = await self.get_state("_threading", "admin", "thread.{}".format(thread), attribute="all")
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
                self.logger.warning(
                    "Invalid thread ID for pinned thread in app: %s - assigning to thread 0",
                    args["name"],
                )
                thread = 0
        else:
            if self.thread_count == self.pin_threads:
                raise ValueError("pin_threads must be set lower than threads if unpinned_apps are in use")
            if self.AD.load_distribution == "load":
                thread = self.min_q_id()
            elif self.AD.load_distribution == "random":
                thread = randint(self.pin_threads, self.thread_count - 1)
            else:
                # Round Robin is the catch all
                thread = self.next_thread
                self.next_thread += 1
                if self.next_thread == self.thread_count:
                    self.next_thread = self.pin_threads

        if thread < 0 or thread >= self.thread_count:
            raise ValueError(f"invalid thread id: {thread} in app {args['name']}")

        q = self.threads[f"thread-{thread}"]["queue"]
        q.put_nowait(args)

    async def check_overdue_and_dead_threads(self):
        if self.AD.sched.realtime is True and self.AD.thread_duration_warning_threshold != 0:
            for thread_id in self.threads:
                if self.threads[thread_id]["thread"].is_alive() is not True:
                    self.logger.critical("Thread %s has died", thread_id)
                    self.logger.critical("Pinned apps were: %s", self.get_pinned_apps(thread_id))
                    self.logger.critical("Thread will be restarted")
                    id = thread_id.split("-")[1]
                    await self.add_thread(silent=False, pinthread=False, id=id)
                if await self.get_state("_threading", "admin", "thread.{}".format(thread_id)) != "idle":
                    start = utils.str_to_dt(
                        await self.get_state(
                            "_threading",
                            "admin",
                            "thread.{}".format(thread_id),
                            attribute="time_called",
                        )
                    )
                    dur = (await self.AD.sched.get_now() - start).total_seconds()
                    if dur >= self.AD.thread_duration_warning_threshold and dur % self.AD.thread_duration_warning_threshold == 0:
                        self.logger.warning(
                            "Excessive time spent in callback: %s - %s",
                            await self.get_state(
                                "_threading",
                                "admin",
                                "thread.{}".format(thread_id),
                                attribute="callback",
                            ),
                            dur,
                        )

    async def check_q_size(self, warning_step, warning_iterations):
        totalqsize = 0
        for thread in self.threads:
            totalqsize += self.threads[thread]["queue"].qsize()

        if totalqsize > self.AD.qsize_warning_threshold:
            if (warning_step == 0 and warning_iterations >= self.AD.qsize_warning_iterations) or warning_iterations == self.AD.qsize_warning_iterations:
                for thread in self.threads:
                    qsize = self.threads[thread]["queue"].qsize()
                    if qsize > 0:
                        self.logger.warning(
                            "Queue size for thread %s is %s, callback is '%s' called at %s - possible thread starvation",
                            thread,
                            qsize,
                            await self.get_state("_threading", "admin", "thread.{}".format(thread)),
                            iso8601.parse_date(
                                await self.get_state(
                                    "_threading",
                                    "admin",
                                    "thread.{}".format(thread),
                                    attribute="time_called",
                                )
                            ),
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
        if callback == "idle":
            start = utils.str_to_dt(
                await self.get_state(
                    "_threading",
                    "admin",
                    "thread.{}".format(thread_id),
                    attribute="time_called",
                )
            )
            if start == "never":
                duration = 0.0
            else:
                duration = (now - start).total_seconds()

            if self.AD.sched.realtime is True and duration >= self.AD.thread_duration_warning_threshold:
                thread_name = f"thread.{thread_id}"
                callback = await self.get_state("_threading", "admin", thread_name)
                self.logger.warning(
                    f"Excessive time spent in callback {callback}. "
                    f"Thread entity: '{thread_name}' - now complete after {utils.format_timedelta(duration)} "
                    f"(limit={utils.format_timedelta(self.AD.thread_duration_warning_threshold)})"
                )
            await self.add_to_state("_threading", "admin", "sensor.threads_current_busy", -1)

            await self.add_to_attr("_threading", "admin", appentity, "totalcallbacks", 1)
            await self.add_to_attr("_threading", "admin", appentity, "instancecallbacks", 1)

            await self.add_to_attr(
                "_threading",
                "admin",
                "{}_callback.{}".format(type, uuid),
                "executed",
                1,
            )
            await self.add_to_state("_threading", "admin", "sensor.callbacks_total_executed", 1)
            self.current_callbacks_executed += 1
        else:
            await self.add_to_state("_threading", "admin", "sensor.threads_current_busy", 1)
            self.current_callbacks_fired += 1

        current_busy = await self.get_state("_threading", "admin", "sensor.threads_current_busy")
        max_busy = await self.get_state("_threading", "admin", "sensor.threads_max_busy")
        if current_busy > max_busy:
            await self.set_state("_threading", "admin", "sensor.threads_max_busy", state=current_busy)
            await self.set_state(
                "_threading",
                "admin",
                "sensor.threads_max_busy_time",
                state=utils.dt_to_str((await self.AD.sched.get_now()).replace(microsecond=0), self.AD.tz),
            )

            await self.set_state(
                "_threading",
                "admin",
                "sensor.threads_last_action_time",
                state=utils.dt_to_str((await self.AD.sched.get_now()).replace(microsecond=0), self.AD.tz),
            )

        # Update thread info

        if thread_id == "async":
            await self.set_state(
                "_threading",
                "admin",
                "thread.{}".format(thread_id),
                q=0,
                state=callback,
                time_called=utils.dt_to_str(now.replace(microsecond=0), self.AD.tz),
                is_alive=True,
                pinned_apps=[],
            )
        else:
            await self.set_state(
                "_threading",
                "admin",
                "thread.{}".format(thread_id),
                q=self.threads[thread_id]["queue"].qsize(),
                state=callback,
                time_called=utils.dt_to_str(now.replace(microsecond=0), self.AD.tz),
                is_alive=self.threads[thread_id]["thread"].is_alive(),
                pinned_apps=self.get_pinned_apps(thread_id),
            )
        await self.set_state("_threading", "admin", appentity, state=callback)

    #
    # Pinning
    #

    async def add_thread(
        self,
        silent: bool = False,
        pinthread: bool = False,
        id: int | str | None = None,
    ):
        if id is None:
            tid = self.thread_count
        else:
            tid = id
        if silent is False:
            self.logger.info("Adding thread %s", tid)
        t = threading.Thread(target=self.worker)
        t.daemon = True
        t.name = f"thread-{tid}"
        if id is None:
            await self.add_entity(
                "admin",
                "thread.{}".format(t.name),
                "idle",
                {"q": 0, "is_alive": True, "time_called": utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0))},
            )
            self.threads[t.name] = {}
            self.threads[t.name]["queue"] = Queue(maxsize=0)
            t.start()
            self.thread_count += 1
            if pinthread is True:
                self.pin_threads += 1
        else:
            await self.set_state(
                "_threading",
                "admin",
                "thread.{}".format(t.name),
                state="idle",
                is_alive=True,
            )

        self.threads[t.name]["thread"] = t

    async def calculate_pin_threads(self):
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
            pinned_apps = self.get_pinned_apps(thread)
            await self.set_state(
                "_threading",
                "admin",
                "thread.{}".format(thread),
                pinned_apps=pinned_apps,
            )

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

    def get_pinned_apps(self, thread: str):
        """Gets the names of apps that are pinned to a particular thread"""
        id = int(thread.split("-")[1])
        return [app_name for app_name, obj in self.AD.app_management.objects.items() if obj.pin_thread == id]

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
        return pin, pin_thread

    #
    # Constraints
    #

    async def check_constraint(self, key, value, app: "ADBase"):
        """Used to check Constraint"""

        unconstrained = True
        if hasattr(app, "constraints") and key in app.constraints:
            method = getattr(app, key)
            unconstrained = await utils.run_async_sync_func(self, method, value)

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
            if await self.AD.sched.now_is_between(start_time, end_time, name) is False:
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
                daylist.append(await utils.run_in_executor(self, utils.day_of_week, day))

            if now.weekday() not in daylist:
                unconstrained = False

        return unconstrained

    async def check_state_constraint(self, args, new_state, name):
        """Used to check state Constraint"""

        unconstrained = True
        if "constrain_state" in args:
            unconstrained = utils.check_state(self.logger, new_state, args["constrain_state"], name)

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

    async def dispatch_worker(self, name: str, args: dict[str, Any]):
        #
        # If the app isinitializing, it's not ready for this yet so discard
        #
        # not a fully qualified entity name
        entity_id = "app.{}".format(name)

        state = await self.AD.state.get_state("_threading", "admin", entity_id)

        if state in ["initializing"]:
            self.logger.debug("Incoming event while initializing - discarding")
            return

        unconstrained = True
        #
        # Argument Constraints
        # (plugins have no args so skip if necessary)
        #
        if app_cfg := self.AD.app_management.app_config.root.get(name):
            for arg, val in app_cfg.args.items():
                constrained = await self.check_constraint(
                    arg,
                    val,
                    self.AD.app_management.objects[name].object,
                )
                if not constrained:
                    unconstrained = False
            if not await self.check_time_constraint(self.AD.app_management.app_config[name].args, name):
                unconstrained = False
            elif not await self.check_days_constraint(self.AD.app_management.app_config[name].args, name):
                unconstrained = False

        #
        # Callback level constraints
        #
        myargs = utils.deepcopy(args)
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
                await self.add_to_state("_threading", "admin", "sensor.callbacks_total_fired", 1)
                await self.add_to_attr(
                    "_threading",
                    "admin",
                    "{}_callback.{}".format(myargs["type"], myargs["id"]),
                    "fired",
                    1,
                )
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
        else:
            if not self.AD.stopping:
                self.logger.warning("Found stale callback for %s - discarding", name)

    # noinspection PyBroadException
    def worker(self):  # noqa: C901
        thread_id = threading.current_thread().name
        q = self.get_q(thread_id)
        while True:
            args = q.get()
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
                    match args["type"]:
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
                    update_coro = self.update_thread_info(thread_id, callback, name, _type, _id, silent)
                    utils.run_coroutine_threadsafe(self, update_coro)

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
                    utils.run_coroutine_threadsafe(self, update_coro)
                    q.task_done()  # Have this in multiple places to ensure it gets called even if an exception is raised
            else:
                if not self.AD.stopping:
                    self.logger.warning(f"Found stale callback for {name} - discarding")
                q.task_done()

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
