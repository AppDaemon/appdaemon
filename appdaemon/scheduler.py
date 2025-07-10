import asyncio
import functools
import logging
import re
import traceback
import uuid
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from logging import Logger
from typing import TYPE_CHECKING, Any, Callable

import pytz
from astral import LocationInfo
from astral.location import Location

from . import utils

if TYPE_CHECKING:
    from .adbase import ADBase
    from .appdaemon import AppDaemon


time_regex_str = r"(?P<hour>\d+):(?P<minute>\d+):(?P<second>\d+)(?:\.(?P<microsecond>\d+))?"
date_regex_str = r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})" + r"(?:\s+" + f"{time_regex_str})?"
DATE_REGEX = re.compile(date_regex_str)
TIME_REGEX = re.compile(f"^{time_regex_str}")
SUN_REGEX = re.compile(
    r"^(?P<dir>sunrise|sunset)(?:\s+[+-]\s+(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+)(?:\.(?P<microseconds>\d+))?)?",
    re.IGNORECASE,
)
ELEVATION_REGEX = re.compile(r"^(?P<N>\d+(?:\.\d+)?)\s+deg\s+(?P<dir>rising|setting)$", re.IGNORECASE)


class Scheduler:
    AD: "AppDaemon"
    logger: Logger
    error: Logger
    diag: Logger

    schedule: dict[str, dict[str, Any]]

    name: str = "_scheduler"
    active: bool = False
    stopping: bool = False
    loop_task: asyncio.Task[None]

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child("_scheduler")
        self.error = ad.logging.get_error()
        self.diag = ad.logging.get_diag()
        self.last_fired = None
        self.sleep_task = None
        self.timer_resetted = False
        self.location = None
        self.schedule = {}

        self.now = datetime.now(timezone.utc)

        #
        # If we were waiting for a timezone from metadata, we have it now.
        #
        self.AD.logging.set_tz(self.AD.tz)

        # Setup sun
        self.init_sun()

    def start(self):
        def _set_inactive(task: asyncio.Task[None]) -> None:
            """
            Callback to set the scheduler as inactive when the loop task is done.
            """
            self.active = False
            self.logger.debug("Scheduler loop task completed, setting active to False")

        self.loop_task = self.AD.loop.create_task(self.loop(), name="scheduler loop")
        self.loop_task.add_done_callback(_set_inactive)

    @property
    def realtime(self) -> bool:
        """Return whether the scheduler is running in real time."""
        return self.AD.real_time

    def stop(self):
        self.logger.debug("stop() called for scheduler")
        self.stopping = True

    async def set_start_time(self, starttime: datetime | None = None):
        self.last_fired = datetime.now(timezone.utc).astimezone(self.AD.tz)
        if not self.AD.real_time:
            self.logger.info("Starting time travel ...")
            self.logger.info("Setting clocks to %s", await self.get_now())
            if self.AD.timewarp == 0:
                self.logger.info("Time displacement factor infinite")
            else:
                self.logger.info("Time displacement factor %d", self.AD.timewarp)
        else:
            self.logger.info("Scheduler running in realtime")

    async def insert_schedule(
        self,
        name: str,
        aware_dt: datetime,
        callback: Callable | None,
        repeat: bool = False,
        type_: str | None = None,
        interval: str | int | float | timedelta = 0,
        offset: str | int | float | timedelta | None = None,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        assert isinstance(aware_dt, datetime), "aware_dt must be a datetime object"
        assert aware_dt.tzinfo is not None, "aware_dt must be timezone aware"
        # aware_dt will include a timezone of some sort - convert to utc timezone
        basetime = aware_dt.astimezone(pytz.utc)

        if pin_thread is not None:
            # If the pin_thread is specified, force pin_app to True
            pin_app = True
        else:
            # Otherwise, use the current pin_app setting in app management
            if pin is None:
                pin_app = self.AD.app_management.objects[name].pin_app

            if pin_thread is None:
                pin_thread = self.AD.app_management.objects[name].pin_thread

        # Ensure that there's a dict available for this app name
        if name not in self.schedule:
            self.schedule[name] = {}

        # Generate the handle
        handle = uuid.uuid4().hex

        # Resolve the first run
        offset = utils.parse_timedelta(offset)
        c_offset = utils.resolve_offset(offset=offset, random_start=random_start, random_end=random_end)
        timestamp = basetime + c_offset

        # Preserve randomization kwargs because this is where they're looked for later
        if random_start is not None:
            kwargs["random_start"] = random_start
        if random_end is not None:
            kwargs["random_end"] = random_end

        self.schedule[name][handle] = {
            "name": name,
            "id": self.AD.app_management.objects[name].id,
            "callback": callback,
            "timestamp": timestamp,
            "interval": utils.parse_timedelta(interval).total_seconds(),  # guarantees that interval is a float
            "basetime": basetime,
            "repeat": repeat,
            "offset": offset.total_seconds(),
            "type": type_,
            "pin_app": pin_app,
            "pin_thread": pin_thread,
            "kwargs": kwargs,
        }

        if callback is None:
            function_name = "cancel_callback"
        else:
            if isinstance(callback, functools.partial):
                function_name = callback.func.__name__
            else:
                function_name = callback.__name__

        await self.AD.state.add_entity(
            namespace="admin",
            entity=f"scheduler_callback.{handle}",
            state="active",
            attributes={
                "app": name,
                "execution_time": utils.dt_to_str(timestamp, self.AD.tz, round=True),
                "repeat": str(utils.parse_timedelta(interval)),
                "function": function_name,
                "pinned": pin_app,
                "pinned_thread": pin_thread,
                "fired": 0,
                "executed": 0,
                "kwargs": kwargs,
            },
        )
        # verbose_log(conf.logger, "INFO", conf.schedule[name][handle])

        if self.active is True:
            await self.kick()

        return handle

    async def cancel_timer(self, name: str, handle: str, silent: bool) -> bool:
        executed = False
        self.logger.debug("Canceling timer for %s", name)
        if self.timer_running(name, handle):
            del self.schedule[name][handle]
            await self.AD.state.remove_entity("admin", f"scheduler_callback.{handle}")
            executed = True

        if name in self.schedule and self.schedule[name] == {}:
            del self.schedule[name]

        if not executed and not silent:
            self.logger.warning(f"Invalid callback handle '{handle}' in " f"cancel_timer() from app {name}")

        return executed

    async def restart_timer(self, uuid_: str, args: dict[str, Any]) -> dict:
        """Used to restart a timer. This directly modifies the internal schedule dict."""
        match args:
            case {"type": "next_rising" | "next_setting", "offset": offset}:
                # If the offset is negative, the next sunrise/sunset will still be today, so get tomorrow's by setting
                # the days_offset to 1.
                days_offset = 1 if offset < 0 else 0
                match args:
                    case {"type": "next_rising"}:
                        args["basetime"] = await self.next_sunrise(days_offset)
                    case {"type": "next_setting"}:
                        args["basetime"] = await self.next_sunset(days_offset)
            case {"interval": interval}:
                # Just increment the basetime with the repeat interval
                args["basetime"] += utils.parse_timedelta(interval)
            case _:
                raise ValueError("Malformed scheduler args, expected 'type' or 'interval' key")

        c_offset = utils.resolve_offset(
            offset=args.get("offset"),
            random_start=args.get("random_start"),
            random_end=args.get("random_end"),
        )  # fmt: skip
        args["timestamp"] = args["basetime"] + c_offset

        # Update entity
        execution_time = utils.dt_to_str(args["timestamp"].replace(microsecond=0), self.AD.tz)
        await self.AD.state.set_state(
            "_scheduler",
            "admin",
            f"scheduler_callback.{uuid_}",
            execution_time=execution_time,
        )

        return args

    async def reset_timer(self, name: str, handle: str) -> bool:
        """Only used by the ADAPI to reset an internal timer."""
        if not self.timer_running(name, handle):
            self.logger.warning(
                f"The given handle '{handle}' in reset_timer() from app "
                f"{name}, doesn't have a running timer"
            )  # fmt: skip
            return False

        args = await utils.run_in_executor(self, deepcopy, self.schedule[name][handle])
        match args:
            case {"type": "next_rising" | "next_setting"}:
                self.logger.warning(
                    f"The given handle '{handle}' in reset_timer() from "
                    f"app {name} is a Sun timer, cannot" " reset that"
                )  # fmt: skip
                return False

        self.logger.debug("Resetting timer %s for %s", handle, name)
        args["basetime"] = await self.get_now()
        args = await self.restart_timer(handle, args)
        self.schedule[name][handle] = args

        if self.active is True:
            await self.kick()

        # we need to indicate a reset took place
        self.timer_resetted = True

        return True

    def timer_running(self, name: str, handle: str) -> bool:
        """Check if the handler is still running by checking for the existence of the handle in the schedule."""
        return handle in self.schedule.get(name, {})

    def _log_exec_start(self, args: dict[str, Any]) -> None:
        logger = self.logger.getChild("_reset")
        if logger.getEffectiveLevel() > logging.DEBUG:
            return  # The logging below is relatively expensive, so skip it if not needed

        match args:
            case {
                "repeat": True,
                # "name": name_,
                "callback": callback,
                "timestamp": datetime() as timestamp,
                "basetime": datetime() as basetime,
                "interval": (int() | float()) as interval,
            }:
                callback_name = utils.unwrapped(callback).__name__
                logger.debug(f"callback name={callback_name}")
                logger.debug(f"     basetime={basetime.astimezone(self.AD.tz).isoformat()}")
                logger.debug(f"    timestamp={timestamp.astimezone(self.AD.tz).isoformat()}")
                logger.debug(f"     interval={utils.parse_timedelta(interval)}")
                pass
            case _:
                logger.debug("  Executing: %s", args)

    # noinspection PyBroadException
    async def exec_schedule(self, name: str, args: dict[str, Any], uuid_: str) -> None:
        self._log_exec_start(args)
        try:
            # Call function
            if "__entity" in args["kwargs"]:
                #
                # it's a "duration" entry
                #

                # first remove the duration parameter
                if args["kwargs"].get("__duration"):
                    del args["kwargs"]["__duration"]

                executed = await self.AD.threading.dispatch_worker(
                    name,
                    {
                        "id": uuid_,
                        "name": name,
                        "objectid": self.AD.app_management.objects[name].id,
                        "type": "state",
                        "function": args["callback"],
                        "attribute": args["kwargs"]["__attribute"],
                        "entity": args["kwargs"]["__entity"],
                        "new_state": args["kwargs"]["__new_state"],
                        "old_state": args["kwargs"]["__old_state"],
                        "pin_app": args["pin_app"],
                        "pin_thread": args["pin_thread"],
                        "kwargs": args["kwargs"],
                    },
                )

                if executed is True:
                    remove = args["kwargs"].get("oneshot", False)
                    if remove is True:
                        await self.AD.state.cancel_state_callback(args["kwargs"]["__handle"], name)

                        if "__timeout" in args["kwargs"] and self.timer_running(name, args["kwargs"]["__timeout"]):  # meaning there is a timeout for this callback
                            await self.cancel_timer(name, args["kwargs"]["__timeout"], False)  # cancel it as no more needed

            elif "__state_handle" in args["kwargs"]:
                #
                # It's a state timeout entry - just delete the callback
                #
                await self.AD.state.cancel_state_callback(args["kwargs"]["__state_handle"], name)
            elif "__event_handle" in args["kwargs"]:
                #
                # It's an event timeout entry - just delete the callback
                #
                await self.AD.events.cancel_event_callback(name, args["kwargs"]["__event_handle"])
            elif "__log_handle" in args["kwargs"]:
                #
                # It's a log timeout entry - just delete the callback
                #
                await self.AD.logging.cancel_log_callback(name, args["kwargs"]["__log_handle"])
            else:
                #
                # A regular callback
                #
                await self.AD.threading.dispatch_worker(
                    name,
                    {
                        "id": uuid_,
                        "name": name,
                        "objectid": self.AD.app_management.objects[name].id,
                        "type": "scheduler",
                        "function": args["callback"],
                        "pin_app": args["pin_app"],
                        "pin_thread": args["pin_thread"],
                        "kwargs": args["kwargs"],
                    },
                )
            # If it is a repeating entry, rewrite with new timestamp
            if args["repeat"]:
                # restart the timer
                args = await self.restart_timer(uuid_, args)

            else:
                # Otherwise just delete
                await self.AD.state.remove_entity("admin", "scheduler_callback.{}".format(uuid_))

                del self.schedule[name][uuid_]

        except Exception:
            error_logger = logging.getLogger("Error.{}".format(name))
            error_logger.warning("-" * 60)
            error_logger.warning("Unexpected error during exec_schedule() for App: %s", name)
            error_logger.warning("Args: %s", args)
            error_logger.warning("-" * 60)
            error_logger.warning(traceback.format_exc())
            error_logger.warning("-" * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning("Logged an error to %s", self.AD.logging.get_filename("error_log"))
            error_logger.warning("Scheduler entry has been deleted")
            error_logger.warning("-" * 60)
            await self.AD.state.remove_entity("admin", "scheduler_callback.{}".format(uuid_))
            del self.schedule[name][uuid_]

    def init_sun(self):
        latitude = self.AD.latitude
        longitude = self.AD.longitude

        if latitude < -90 or latitude > 90:
            raise ValueError("Latitude needs to be -90 .. 90")

        if longitude < -180 or longitude > 180:
            raise ValueError("Longitude needs to be -180 .. 180")

        assert self.AD.tz.zone is not None
        self.location = Location(LocationInfo("", "", self.AD.tz.zone, latitude, longitude))

    async def get_next_period(
        self,
        interval: int | float | timedelta,
        start: time | datetime | str | None = None,
    ) -> datetime:
        start = "now" if start is None else start
        aware_start = await self.parse_datetime(start, aware=True)
        interval = utils.parse_timedelta(interval)
        assert isinstance(aware_start, datetime) and aware_start.tzinfo is not None
        while True:
            if aware_start >= await self.get_now():
                return aware_start
            else:
                aware_start += interval

    async def terminate_app(self, name):
        if name in self.schedule:
            for id in self.schedule[name]:
                await self.AD.state.remove_entity("admin", "scheduler_callback.{}".format(id))
            del self.schedule[name]

    def is_realtime(self) -> bool:
        return self.AD.real_time

    #
    # Timer
    #

    def next_exec_time(self) -> datetime | None:
        timestamps = {
            handle: entry["timestamp"]
            for entries in self.schedule.values()
            for handle, entry in entries.items()
        }  # fmt: skip
        if len(timestamps) > 0:
            next_exec = min(timestamps.values())
            assert isinstance(next_exec, datetime), "next_exec must be a datetime object"
            assert next_exec.tzinfo is not None, "next_exec must be timezone aware"
            next_exec = next_exec.astimezone(pytz.utc)
            return next_exec

    def get_next_entries(self) -> list[dict[str, str | datetime]]:
        if (next_exec := self.next_exec_time()) is not None:
            next_entries = [
                {
                    "name": name,
                    "uuid": handle,
                    "timestamp": entry["timestamp"],
                }
                for name, entries in self.schedule.items()
                for handle, entry in entries.items()
                if entry["timestamp"] == next_exec
            ]  # fmt: skip
            return next_entries
        else:
            return []

    def get_next_dst_offset(self, base, limit):
        #
        # I can't believe there isn't a better way to find the next DST transition but ...
        # We know the lower and upper bounds of DST so do a search to find the actual transition time
        # I don't want to rely on heuristics such as "it occurs at 2am" because I don't know if that holds
        # true for every timezone. With this method, as long as pytz's dst() function is correct, this should work
        #

        # TODO : Convert this to some sort of binary search for efficiency
        # TODO : This really should support sub 1 second periods better
        self.logger.debug("get_next_dst_offset() base=%s limit=%s", base, limit)
        current = base.astimezone(self.AD.tz).dst()
        self.logger.debug("current=%s", current)
        for offset in range(1, int(limit) + 1):
            candidate = (base + timedelta(seconds=offset)).astimezone(self.AD.tz)
            # print(candidate)
            if candidate.dst() != current:
                return offset
        return limit

    async def loop(self):  # noqa: C901
        self.logger.debug("Starting scheduler loop()")
        self.active = True
        if self.AD.starttime is not None:
            self.now = utils.ensure_timezone(self.AD.starttime, self.AD.tz)
        else:
            self.now = datetime.now(self.AD.tz)

        if self.AD.endtime is not None:
            self.endtime = utils.ensure_timezone(self.AD.endtime, self.AD.tz)
        else:
            self.endtime = None

        self.AD.booted = await self.get_now_naive()

        await self.set_start_time()

        next_entries = []
        result = False
        idle_time = 1
        delay = 0
        old_dst_offset = (await self.get_now()).astimezone(self.AD.tz).dst()
        while not self.stopping:
            try:
                if self.endtime is not None and self.now >= self.endtime:
                    self.logger.info("End time reached, exiting")
                    if self.AD.stop_function is not None:
                        self.AD.stop_function()
                    else:
                        self.stop()

                now = datetime.now(pytz.utc)
                if self.realtime:
                    self.now = now

                else:
                    if result is True:
                        # We got kicked so lets figure out the elapsed pseudo time
                        delta = (now - self.last_fired).total_seconds() * self.AD.timewarp

                    else:
                        if len(next_entries) > 0:
                            # Time is progressing infinitely fast and it's already time for our next callback
                            delta = delay
                        else:
                            # No kick, no scheduler expiry ...
                            delta = idle_time

                    self.now += utils.parse_timedelta(delta)

                self.last_fired = datetime.now(pytz.utc)
                internal_now = await self.get_now()
                now_local = internal_now.astimezone(self.AD.tz)
                self.logger.debug("self.now   utc=%s", internal_now.isoformat())
                # self.logger.debug("-" * 51)
                # self.logger.debug("Wakeup time   utc=%s", internal_now.isoformat())
                # self.logger.debug("Wakeup time local=%s", now_local.isoformat())

                #
                # Now we're awake and know what time it is
                #
                dst_offset = now_local.dst()
                self.logger.debug(
                    "local now=%s old_dst_offset=%s new_dst_offset=%s",
                    now_local.isoformat(),
                    old_dst_offset,
                    dst_offset,
                )
                if old_dst_offset != dst_offset:
                    #
                    # DST began or ended, lets prove we noticed
                    self.logger.info("Daylight Savings Time transition detected")
                    #
                    # Re calculate next entries
                    #
                    next_entries = self.get_next_entries()

                elif self.timer_resetted is True:
                    # a timer was reset, so need to recalculate next entries
                    next_entries = self.get_next_entries()
                    self.timer_resetted = False

                old_dst_offset = dst_offset
                #
                # OK, lets fire the entries
                #
                for entry in next_entries:
                    # Check timestamps as we might have been interrupted to add a callback
                    if entry["timestamp"] <= internal_now:
                        name = entry["name"]
                        uuid_ = entry["uuid"]
                        # Things may have changed since we last woke up
                        # so check our callbacks are still valid before we execute them
                        if name in self.schedule and uuid_ in self.schedule[name]:
                            args = self.schedule[name][uuid_]
                            await self.exec_schedule(name, args, uuid_)
                    else:
                        break
                for k, v in list(self.schedule.items()):
                    if v == {}:
                        del self.schedule[k]

                next_entries = self.get_next_entries()
                self.logger.debug("Next entries: %s", next_entries)
                if len(next_entries) > 0:
                    delay = (next_entries[0]["timestamp"] - self.now).total_seconds()
                else:
                    # Nothing to do, lets wait for a while, we will get woken up if anything new comes along
                    delay = idle_time

                # Initially we don't want to skip over any events that haven't had a chance to be registered yet, but now
                # we can loosen up a little
                idle_time = 60

                #
                # We are about to go to sleep, but we need to ensure we don't miss a DST transition or we will
                # sleep in and potentially miss an event that should happen earlier than expected due to the time change
                #

                next = internal_now + utils.parse_timedelta(delay)

                self.logger.debug("next event=%s", next.astimezone(self.AD.tz).isoformat())

                if await self.is_dst() != await self.is_dst(next):
                    #
                    # Reset delay to wake up at the DST change so we can re-jig everything
                    #

                    delay = self.get_next_dst_offset(internal_now, delay)
                    self.logger.debug(
                        "DST transition before next event: %s %s",
                        await self.is_dst(),
                        await self.is_dst(next),
                    )

                self.logger.debug("Delay = %s seconds", delay)

                if delay > 0 and self.AD.timewarp > 0:
                    #
                    # Sleep until the next event
                    #
                    result = await self.sleep(delay / self.AD.timewarp)
                    sleep_msg = "Sleep done, not cancelled" if result is False else "Sleep cancelled"
                    self.logger.debug(sleep_msg)
                else:
                    # Not sleeping but lets be fair to the rest of AD
                    await asyncio.sleep(0)

            except Exception:
                self.logger.warning("-" * 60)
                self.logger.warning("Unexpected error in scheduler loop")
                self.logger.warning("-" * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning("-" * 60)
                # Prevent spamming of the logs
                await self.sleep(1)

    async def sleep(self, delay: float) -> bool:
        try:
            self.sleep_task = asyncio.create_task(asyncio.sleep(delay))
            await self.sleep_task
            return False
        except asyncio.CancelledError:
            return True
        finally:
            self.sleep_task = None

    async def kick(self):
        while self.sleep_task is None:
            await asyncio.sleep(1)
        self.sleep_task.cancel()

    #
    # App API Calls
    #

    async def sun_up(self) -> bool:
        return await self.now_is_between(start_time="sunrise", end_time="sunset")

    async def sun_down(self) -> bool:
        return await self.now_is_between(start_time="sunset", end_time="sunrise")

    async def info_timer(self, handle, name) -> tuple[datetime, float, dict] | None:
        if self.timer_running(name, handle):
            callback = self.schedule[name][handle]
            return (
                self.make_naive(callback["timestamp"]),
                callback["interval"],
                self.sanitize_timer_kwargs(self.AD.app_management.objects[name].object, callback["kwargs"]),
            )

    async def get_scheduler_entries(self):
        schedule = {}
        for name in self.schedule.keys():
            schedule[name] = {}
            for entry in sorted(
                self.schedule[name].keys(),
                key=lambda uuid_: self.schedule[name][uuid_]["timestamp"],
            ):
                schedule[name][str(entry)] = {}
                schedule[name][str(entry)]["timestamp"] = str(self.AD.sched.make_naive(self.schedule[name][entry]["timestamp"]))
                schedule[name][str(entry)]["type"] = self.schedule[name][entry]["type"]
                schedule[name][str(entry)]["name"] = self.schedule[name][entry]["name"]
                schedule[name][str(entry)]["basetime"] = str(self.AD.sched.make_naive(self.schedule[name][entry]["basetime"]))
                schedule[name][str(entry)]["repeat"] = self.schedule[name][entry]["repeat"]
                if self.schedule[name][entry]["type"] == "next_rising":
                    schedule[name][str(entry)]["interval"] = "sunrise:{}".format(utils.format_seconds(self.schedule[name][entry]["offset"]))
                elif self.schedule[name][entry]["type"] == "next_setting":
                    schedule[name][str(entry)]["interval"] = "sunset:{}".format(utils.format_seconds(self.schedule[name][entry]["offset"]))
                elif self.schedule[name][entry]["repeat"] is True:
                    schedule[name][str(entry)]["interval"] = utils.format_seconds(self.schedule[name][entry]["interval"])
                else:
                    schedule[name][str(entry)]["interval"] = "None"

                schedule[name][str(entry)]["offset"] = self.schedule[name][entry]["offset"]
                schedule[name][str(entry)]["kwargs"] = ""
                for kwarg in self.schedule[name][entry]["kwargs"]:
                    schedule[name][str(entry)]["kwargs"] = utils.get_kwargs(self.schedule[name][entry]["kwargs"])
                if isinstance(self.schedule[name][entry]["callback"], functools.partial):
                    schedule[name][str(entry)]["callback"] = self.schedule[name][entry]["callback"].func.__name__
                else:
                    schedule[name][str(entry)]["callback"] = self.schedule[name][entry]["callback"].__name__
                schedule[name][str(entry)]["pin_thread"] = self.schedule[name][entry]["pin_thread"] if self.schedule[name][entry]["pin_thread"] != -1 else "None"
                schedule[name][str(entry)]["pin_app"] = "True" if self.schedule[name][entry]["pin_app"] is True else "False"

        # Order it

        ordered_schedule = OrderedDict(sorted(schedule.items(), key=lambda x: x[0]))

        return ordered_schedule

    async def is_dst(self, dt=None):
        if dt is None:
            return (await self.get_now()).astimezone(self.AD.tz).dst() != timedelta(0)
        else:
            return dt.astimezone(self.AD.tz).dst() != timedelta(0)

    async def get_now(self) -> datetime:
        if self.realtime:
            return datetime.now(self.AD.time_zone)
        else:
            return self.now

    # Non async version of get_now(), required for logging time formatter - no locking but only used during time travel
    # so should be OK ...
    def get_now_sync(self):
        if self.realtime:
            return pytz.utc.localize(datetime.utcnow())
        else:
            return self.now

    async def get_now_ts(self) -> float:
        return (await self.get_now()).timestamp()

    async def get_now_naive(self):
        return self.make_naive(await self.get_now())

    async def now_is_between(
        self,
        start_time: str | time | datetime,
        end_time: str | time | datetime,
        now: datetime | None = None,
    ) -> bool:
        now = now if now is not None else await self.get_now()
        # Need to force timezone during time-travel mode
        now = now.astimezone(self.AD.tz)
        return utils.now_is_between(
            now=now,
            start_time=start_time,
            end_time=end_time,
            tz=self.AD.tz,
            location=self.location,
        )

    async def sunrise(self, aware: bool = True, today: bool | None = None, days_offset: int = 0) -> datetime:
        return await self.parse_datetime("sunrise", aware=aware, today=today, days_offset=days_offset)

    async def todays_sunrise(self, days_offset: int = 0) -> datetime:
        return await self.sunrise(days_offset=days_offset, today=True)

    async def next_sunrise(self, days_offset: int = 0) -> datetime:
        return await self.sunrise(days_offset=days_offset, today=False)

    async def sunset(self, aware: bool = True, today: bool | None = None, days_offset: int = 0) -> datetime:
        return await self.parse_datetime("sunset", aware=aware, today=today, days_offset=days_offset)

    async def todays_sunset(self, days_offset: int = 0) -> datetime:
        return await self.sunset(days_offset=days_offset, today=True)

    async def next_sunset(self, days_offset: int = 0) -> datetime:
        return await self.sunset(days_offset=days_offset, today=False)

    async def parse_time(
        self,
        time_str: str,
        name: str | None = None,
        aware: bool = False,
        today: bool | None = None,
        days_offset: int = 0
    ) -> time:  # fmt: skip
        dt = await self.parse_datetime(
            time_str,
            aware=aware,
            today=today,
            days_offset=days_offset,
        )
        return dt.time()

    async def parse_datetime(
        self,
        input_: str | time | datetime,
        name: str | None = None,
        aware: bool = False,
        today: bool | None = None,
        days_offset: int = 0
    ) -> datetime:  # fmt: skip
        now = await self.get_now()
        # Need to force timezone during time-travel mode
        now = now.astimezone(self.AD.tz)
        return utils.parse_datetime(
            input_=input_,
            now=now,
            location=self.location,
            timezone=self.AD.tz,
            today=today,
            days_offset=days_offset,
            aware=aware,
        )

    #
    # Diagnostics
    #

    async def dump_sun(self):
        self.diag.info("-------------------------------------------------")
        self.diag.info("Sun")
        self.diag.info("-------------------------------------------------")
        self.diag.info("Next Sunrise:    %s", await self.next_sunrise())
        self.diag.info("Today's Sunrise: %s", await self.todays_sunrise())
        self.diag.info("Next Sunset:     %s", await self.next_sunset())
        self.diag.info("Today's Sunset:  %s", await self.todays_sunset())
        self.diag.info("-------------------------------------------------")
        self.diag.info("Sun Up:   %s", await self.sun_up())
        self.diag.info("Sun Down: %s", await self.sun_down())
        self.diag.info("-------------------------------------------------")

    async def dump_schedule(self):
        if self.schedule == {}:
            self.diag.info("Scheduler Table is empty")
        else:
            self.diag.info("--------------------------------------------------")
            self.diag.info("Scheduler Table")
            self.diag.info("--------------------------------------------------")
            for name in self.schedule.keys():
                self.diag.info("%s:", name)
                for entry in sorted(
                    self.schedule[name].keys(),
                    key=lambda uuid_: self.schedule[name][uuid_]["timestamp"],
                ):
                    self.diag.info(
                        " Next Event Time: %s - data: %s",
                        self.make_naive(self.schedule[name][entry]["timestamp"]),
                        self.schedule[name][entry],
                    )
            self.diag.info("--------------------------------------------------")

    #
    # Utilities
    #

    @staticmethod
    def sanitize_timer_kwargs(app: "ADBase", kwargs: dict) -> dict:
        """Removes keywords from the keywords"""
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(
            kwargs_copy,
            ["interval", "constrain_days", "constrain_input_boolean", "_pin_app", "_pin_thread", "__silent"] + app.constraints,
        )

    @staticmethod
    def myround(x, base=1, prec=10):
        if base == 0:
            return x
        else:
            return round(base * round(float(x) / base), prec)

    @staticmethod
    def my_dt_round(dt, base=1, prec=10):
        if base == 0:
            return dt
        else:
            ts = dt.timestamp()
            rounded = round(base * round(float(ts) / base), prec)
            result = datetime.utcfromtimestamp(rounded)
            aware_result = pytz.utc.localize(result)
            return aware_result

    def convert_naive(self, dt):
        # Is it naive?
        result = None
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            # Localize with the configured timezone
            result = self.AD.tz.localize(dt)
        else:
            result = dt

        return result

    def make_naive(self, dt: datetime) -> datetime:
        return dt.replace(tzinfo=None)
