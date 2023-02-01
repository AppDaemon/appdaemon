import traceback
import datetime
from datetime import timedelta
import pytz
import random
import uuid
import re
import asyncio
import logging
from collections import OrderedDict

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from astral.location import Location, LocationInfo


class Scheduler:
    def __init__(self, ad: AppDaemon):
        self.AD = ad

        self.logger = ad.logging.get_child("_scheduler")
        self.error = ad.logging.get_error()
        self.diag = ad.logging.get_diag()
        self.last_fired = None
        self.sleep_task = None
        self.active = False
        self.timer_resetted = False
        self.location = None
        self.schedule = {}

        self.now = pytz.utc.localize(datetime.datetime.utcnow())

        #
        # If we were waiting for a timezone from metadata, we have it now.
        #
        tz = pytz.timezone(self.AD.time_zone)
        self.AD.tz = tz
        self.AD.logging.set_tz(tz)

        self.stopping = False
        self.realtime = True

        self.set_start_time()

        if self.AD.endtime is not None:
            unaware_end = None
            try:
                unaware_end = datetime.datetime.strptime(self.AD.endtime, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    unaware_end = datetime.datetime.strptime(self.AD.endtime, "%Y-%m-%d#%H:%M:%S")
                except ValueError:
                    pass
            if unaware_end is None:
                raise ValueError("Invalid end time for time travel")
            aware_end = self.AD.tz.localize(unaware_end)
            self.endtime = aware_end.astimezone(pytz.utc)
        else:
            self.endtime = None

        # Setup sun

        self.init_sun()

    def set_start_time(self):
        tt = False
        unaware_now = None
        if self.AD.starttime is not None:
            tt = True
            try:
                unaware_now = datetime.datetime.strptime(self.AD.starttime, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Support "#" as date and time separator as well
                try:
                    unaware_now = datetime.datetime.strptime(self.AD.starttime, "%Y-%m-%d#%H:%M:%S")
                except ValueError:
                    # Catching this allows us to raise a single exception and avoid a nested exception
                    pass
            if unaware_now is None:
                raise ValueError("Invalid start time for time travel")
            aware_now = self.AD.tz.localize(unaware_now)
            self.now = aware_now.astimezone(pytz.utc)
        else:
            self.now = pytz.utc.localize(datetime.datetime.utcnow())

        if self.AD.timewarp != 1:
            tt = True

        return tt

    def stop(self):
        self.logger.debug("stop() called for scheduler")
        self.stopping = True

    async def insert_schedule(self, name, aware_dt, callback, repeat, type_, **kwargs):

        # aware_dt will include a timezone of some sort - convert to utc timezone
        utc = aware_dt.astimezone(pytz.utc)

        # we get the time now
        now = await self.get_now()

        # Round to nearest second
        #
        # Take this out to allow fractional run_in() times
        #
        # utc = self.my_dt_round(utc, base=1)

        if "pin" in kwargs:
            pin_app = kwargs["pin"]
        else:
            pin_app = self.AD.app_management.objects[name]["pin_app"]

        if "pin_thread" in kwargs:
            pin_thread = kwargs["pin_thread"]
            pin_app = True
        else:
            pin_thread = self.AD.app_management.objects[name]["pin_thread"]

        if name not in self.schedule:
            self.schedule[name] = {}

        handle = uuid.uuid4().hex
        c_offset = self.get_offset({"kwargs": kwargs})
        ts = utc + timedelta(seconds=c_offset)
        interval = kwargs.get("interval", 0)
        basetime_interval = (ts - now).seconds

        self.schedule[name][handle] = {
            "name": name,
            "id": self.AD.app_management.objects[name]["id"],
            "callback": callback,
            "timestamp": ts,
            "interval": interval,
            "basetime": utc,
            "basetime_interval": basetime_interval,
            "repeat": repeat,
            "offset": c_offset,
            "type": type_,
            "pin_app": pin_app,
            "pin_thread": pin_thread,
            "kwargs": kwargs,
        }

        if callback is None:
            function_name = "cancel_callback"
        else:
            function_name = callback.__name__

        await self.AD.state.add_entity(
            "admin",
            "scheduler_callback.{}".format(handle),
            "active",
            {
                "app": name,
                "execution_time": utils.dt_to_str(ts.replace(microsecond=0), self.AD.tz),
                "repeat": str(datetime.timedelta(seconds=interval)),
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

    async def cancel_timer(self, name, handle):
        executed = False
        self.logger.debug("Canceling timer for %s", name)
        if self.timer_running(name, handle):
            del self.schedule[name][handle]
            await self.AD.state.remove_entity("admin", f"scheduler_callback.{handle}")
            executed = True

        if name in self.schedule and self.schedule[name] == {}:
            del self.schedule[name]

        if not executed:
            self.logger.warning(f"Invalid callback handle '{handle}' in cancel_timer() from app {name}")

        return executed

    async def restart_timer(self, uuid_: str, args: dict, restart_offset: int = 0) -> dict:
        """Used to restart a timer"""

        if args["type"] == "next_rising" or args["type"] == "next_setting":
            c_offset = self.get_offset(args)
            args["timestamp"] = self.sun(args["type"], c_offset)
            args["offset"] = c_offset

        else:
            # Not sunrise or sunset so just increment
            # the timestamp with the repeat interval
            if restart_offset > 0:
                # we to restart with an offset
                new_timestamp = args["timestamp"] + timedelta(seconds=restart_offset)
                args["timestamp"] = new_timestamp

            else:
                args["basetime"] += timedelta(seconds=args["interval"])
                args["timestamp"] = args["basetime"] + timedelta(seconds=self.get_offset(args))

        # Update entity

        await self.AD.state.set_state(
            "_scheduler",
            "admin",
            f"scheduler_callback.{uuid_}",
            execution_time=utils.dt_to_str(args["timestamp"].replace(microsecond=0), self.AD.tz),
        )

        return args

    async def reset_timer(self, name: str, handle: str) -> bool:
        """Used to reset a timer"""

        executed = False

        if self.timer_running(name, handle):
            self.logger.debug("Resetting timer %s for %s", handle, name)

            args = await utils.run_in_executor(self, utils.deepcopy, self.schedule[name][handle])

            if args["type"] == "next_rising" or args["type"] == "next_setting":
                self.logger.warning(
                    f"The given handle '{handle}' in reset_timer() from app {name} is a Sun timer, cannot reset that"
                )
                return executed

            # we get the time now
            now = await self.get_now()

            # we get the time from now to be added
            basetime_interval = args["basetime_interval"]
            restart_offset = basetime_interval - (args["timestamp"] - now).seconds

            args = await self.restart_timer(handle, args, restart_offset)
            self.schedule[name][handle] = args

            if self.active is True:
                await self.kick()

            executed = True

            # we need to indicate a reset took place
            self.timer_resetted = True

        if not executed:
            self.logger.warning(
                f"The given handle '{handle}' in reset_timer() from app {name}, doesn't have a running timer"
            )

        return executed

    def timer_running(self, name, handle):
        """Check if the handler is valid
        by ensuring the timer is still running"""

        if name in self.schedule and handle in self.schedule[name]:
            return True

        return False

    # noinspection PyBroadException
    async def exec_schedule(self, name, args, uuid_):
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
                        "objectid": self.AD.app_management.objects[name]["id"],
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

                        if "__timeout" in args["kwargs"] and self.timer_running(
                            name, args["kwargs"]["__timeout"]
                        ):  # meaning there is a timeout for this callback
                            await self.cancel_timer(name, args["kwargs"]["__timeout"])  # cancel it as no more needed

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
                        "objectid": self.AD.app_management.objects[name]["id"],
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

        self.location = Location(LocationInfo("", "", self.AD.tz.zone, latitude, longitude))

    def sun(self, type: str, secs_offset: int):
        return self.get_next_sun_event(type, secs_offset) + datetime.timedelta(seconds=secs_offset)

    def get_next_sun_event(self, type: str, day_offset: int):
        if type == "next_rising":
            return self.next_sunrise(day_offset)
        else:
            return self.next_sunset(day_offset)

    def todays_sunrise(self, days_offset):
        candidate_date = (self.now + datetime.timedelta(days=days_offset)).astimezone(self.AD.tz).date()
        next_rising_dt = self.location.sunrise(date=candidate_date, local=False, observer_elevation=self.AD.elevation)

        return next_rising_dt

    def next_sunrise(self, offset: int = 0):
        day_offset = 0
        while True:
            try:
                candidate_date = (self.now + datetime.timedelta(days=day_offset)).astimezone(self.AD.tz).date()
                next_rising_dt = self.location.sunrise(
                    date=candidate_date, local=False, observer_elevation=self.AD.elevation
                )
                if next_rising_dt + datetime.timedelta(seconds=offset) > (self.now + datetime.timedelta(seconds=1)):
                    break
            except ValueError:
                pass
            day_offset += 1

        return next_rising_dt

    def next_sunset(self, offset: int = 0):
        day_offset = 0
        while True:
            try:
                candidate_date = (self.now + datetime.timedelta(days=day_offset)).astimezone(self.AD.tz).date()
                next_setting_dt = self.location.sunset(
                    date=candidate_date, local=False, observer_elevation=self.AD.elevation
                )
                if next_setting_dt + datetime.timedelta(seconds=offset) > (self.now + datetime.timedelta(seconds=1)):
                    break
            except ValueError:
                pass
            day_offset += 1

        return next_setting_dt

    def todays_sunset(self, days_offset):
        candidate_date = (self.now + datetime.timedelta(days=days_offset)).astimezone(self.AD.tz).date()
        next_setting_dt = self.location.sunset(date=candidate_date, local=False, observer_elevation=self.AD.elevation)

        return next_setting_dt

    @staticmethod
    def get_offset(kwargs: dict):
        if "offset" in kwargs["kwargs"]:
            if "random_start" in kwargs["kwargs"] or "random_end" in kwargs["kwargs"]:
                raise ValueError(
                    "Can't specify offset as well as 'random_start' or "
                    "'random_end' in 'run_at_sunrise()' or 'run_at_sunset()'"
                )
            else:
                offset = kwargs["kwargs"]["offset"]
        else:
            rbefore = kwargs["kwargs"].get("random_start", 0)
            rafter = kwargs["kwargs"].get("random_end", 0)
            offset = random.randint(rbefore, rafter)
            # self.logger.debug("get_offset(): offset = %s", offset)
        return offset

    async def terminate_app(self, name):
        if name in self.schedule:
            for id in self.schedule[name]:
                await self.AD.state.remove_entity("admin", "scheduler_callback.{}".format(id))
            del self.schedule[name]

    def is_realtime(self):
        return self.realtime

    #
    # Timer
    #

    def get_next_entries(self):

        next_exec = datetime.datetime.now(pytz.utc).replace(year=datetime.MAXYEAR, month=12, day=31)
        for name in self.schedule.keys():
            for entry in self.schedule[name].keys():
                if self.schedule[name][entry]["timestamp"] < next_exec:
                    next_exec = self.schedule[name][entry]["timestamp"]

        next_entries = []

        for name in self.schedule.keys():
            for entry in self.schedule[name].keys():
                if self.schedule[name][entry]["timestamp"] == next_exec:
                    next_entries.append(
                        {"name": name, "uuid": entry, "timestamp": self.schedule[name][entry]["timestamp"]}
                    )

        return next_entries

    async def process_dst(self, old, new):
        #
        # Rewrite timestamps to new local time
        #
        offset = old - new
        self.logger.debug("Process_dst()")
        self.logger.debug("offset  %s", offset)
        for app in self.schedule:
            for entry in self.schedule[app]:
                args = self.schedule[app][entry]
                # Sunrise and sunset will already be correct. Anything else needs to be reset to a new local time
                self.logger.debug("Before rewrite: %s", args)
                if args["type"] != "next_rising" and args["type"] != "next_setting":
                    # If our interval is less than the jump don't rewrite the timestamp
                    if float(args["interval"]) > abs(offset.total_seconds()):
                        args["timestamp"] += offset
                        args["basetime"] += offset
                self.logger.debug("After rewrite: %s", args)

    def get_next_dst_offset(self, base, limit):
        #
        # I can't believe there isn't a better way to find the next DST transition but ...
        # We know the lower and upper bounds of DST so do a search to find the actual transition time
        # I don't want to rely on heuristics such as "it occurs at 2am" because I don't know if that holds
        # true for every timezone. With this method, as long as pytz's dst() function is correct, this should work
        #

        # TODO: Convert this to some sort of binary search for efficiency
        # TODO: This really should support sub 1 second periods better
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
        self.active = True
        self.logger.debug("Starting scheduler loop()")
        self.AD.booted = await self.get_now_naive()

        tt = self.set_start_time()
        self.last_fired = pytz.utc.localize(datetime.datetime.utcnow())
        if tt is True:
            self.realtime = False
            self.logger.info("Starting time travel ...")
            self.logger.info("Setting clocks to %s", await self.get_now_naive())
            if self.AD.timewarp == 0:
                self.logger.info("Time displacement factor infinite")
            else:
                self.logger.info("Time displacement factor %s", self.AD.timewarp)
        else:
            self.logger.info("Scheduler running in realtime")

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
                now = pytz.utc.localize(datetime.datetime.utcnow())
                if self.realtime is True:
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

                    self.now = self.now + timedelta(seconds=delta)

                self.last_fired = pytz.utc.localize(datetime.datetime.utcnow())
                self.logger.debug("self.now = %s", self.now)
                #
                # Now we're awake and know what time it is
                #
                dst_offset = (await self.get_now()).astimezone(self.AD.tz).dst()
                self.logger.debug(
                    "local now=%s old_dst_offset=%s new_dst_offset=%s",
                    self.now.astimezone(self.AD.tz),
                    old_dst_offset,
                    dst_offset,
                )
                if old_dst_offset != dst_offset:
                    #
                    # DST began or ended, we need to go fix any existing scheduler entries to match the new local time
                    #
                    self.logger.info("Daylight Savings Time transition detected - rewriting events to new local time")
                    await self.process_dst(old_dst_offset, dst_offset)
                    #
                    # Re calculate next entries
                    #
                    next_entries = self.get_next_entries()

                elif self.timer_resetted is True:
                    # a timer was resetted, so need to recalculate next entries
                    next_entries = self.get_next_entries()
                    self.timer_resetted = False

                old_dst_offset = dst_offset
                #
                # OK, lets fire the entries
                #
                for entry in next_entries:
                    # Check timestamps as we might have been interrupted to add a callback
                    if entry["timestamp"] <= self.now:
                        name = entry["name"]
                        uuid_ = entry["uuid"]
                        # Things may have changed since we last woke up
                        # so check our callbacks are still valid before we execute them
                        if name in self.schedule and uuid_ in self.schedule[name]:
                            args = self.schedule[name][uuid_]
                            self.logger.debug("Executing: %s", args)
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

                next = self.now + timedelta(seconds=delay)

                self.logger.debug("next event=%s", next)

                if await self.is_dst() != await self.is_dst(next):
                    #
                    # Reset delay to wake up at the DST change so we can re-jig everything
                    #

                    delay = self.get_next_dst_offset(self.now, delay)
                    self.logger.debug(
                        "DST transition before next event: %s %s", await self.is_dst(), await self.is_dst(next)
                    )

                self.logger.debug("Delay = %s seconds", delay)

                if delay > 0 and self.AD.timewarp > 0:
                    #
                    # Sleep until the next event
                    #
                    result = await self.sleep(delay / self.AD.timewarp)
                    self.logger.debug("result = %s", result)
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

    async def sleep(self, delay):
        coro = asyncio.sleep(delay)
        self.sleep_task = asyncio.create_task(coro)
        try:
            await self.sleep_task
            self.sleep_task = None
            return False
        except asyncio.CancelledError:
            return True

    async def kick(self):
        while self.sleep_task is None:
            await asyncio.sleep(1)
        self.sleep_task.cancel()

    #
    # App API Calls
    #

    async def sun_up(self):
        return self.next_sunrise() > self.next_sunset()

    async def sun_down(self):
        return self.next_sunrise() < self.next_sunset()

    async def info_timer(self, handle, name):
        if self.timer_running(name, handle):
            callback = self.schedule[name][handle]
            return (
                self.make_naive(callback["timestamp"]),
                callback["interval"],
                self.sanitize_timer_kwargs(self.AD.app_management.objects[name]["object"], callback["kwargs"]),
            )
        else:
            # self.logger.warning("Invalid timer handle given as: %s", handle)
            return None

    async def get_scheduler_entries(self):
        schedule = {}
        for name in self.schedule.keys():
            schedule[name] = {}
            for entry in sorted(
                self.schedule[name].keys(),
                key=lambda uuid_: self.schedule[name][uuid_]["timestamp"],
            ):
                schedule[name][str(entry)] = {}
                schedule[name][str(entry)]["timestamp"] = str(
                    self.AD.sched.make_naive(self.schedule[name][entry]["timestamp"])
                )
                schedule[name][str(entry)]["type"] = self.schedule[name][entry]["type"]
                schedule[name][str(entry)]["name"] = self.schedule[name][entry]["name"]
                schedule[name][str(entry)]["basetime"] = str(
                    self.AD.sched.make_naive(self.schedule[name][entry]["basetime"])
                )
                schedule[name][str(entry)]["repeat"] = self.schedule[name][entry]["repeat"]
                if self.schedule[name][entry]["type"] == "next_rising":
                    schedule[name][str(entry)]["interval"] = "sunrise:{}".format(
                        utils.format_seconds(self.schedule[name][entry]["offset"])
                    )
                elif self.schedule[name][entry]["type"] == "next_setting":
                    schedule[name][str(entry)]["interval"] = "sunset:{}".format(
                        utils.format_seconds(self.schedule[name][entry]["offset"])
                    )
                elif self.schedule[name][entry]["repeat"] is True:
                    schedule[name][str(entry)]["interval"] = utils.format_seconds(
                        self.schedule[name][entry]["interval"]
                    )
                else:
                    schedule[name][str(entry)]["interval"] = "None"

                schedule[name][str(entry)]["offset"] = self.schedule[name][entry]["offset"]
                schedule[name][str(entry)]["kwargs"] = ""
                for kwarg in self.schedule[name][entry]["kwargs"]:
                    schedule[name][str(entry)]["kwargs"] = utils.get_kwargs(self.schedule[name][entry]["kwargs"])
                schedule[name][str(entry)]["callback"] = self.schedule[name][entry]["callback"].__name__
                schedule[name][str(entry)]["pin_thread"] = (
                    self.schedule[name][entry]["pin_thread"]
                    if self.schedule[name][entry]["pin_thread"] != -1
                    else "None"
                )
                schedule[name][str(entry)]["pin_app"] = (
                    "True" if self.schedule[name][entry]["pin_app"] is True else "False"
                )

        # Order it

        ordered_schedule = OrderedDict(sorted(schedule.items(), key=lambda x: x[0]))

        return ordered_schedule

    async def is_dst(self, dt=None):
        if dt is None:
            return (await self.get_now()).astimezone(self.AD.tz).dst() != datetime.timedelta(0)
        else:
            return dt.astimezone(self.AD.tz).dst() != datetime.timedelta(0)

    async def get_now(self):
        if self.realtime is True:
            return pytz.utc.localize(datetime.datetime.utcnow())
        else:
            return self.now

    # Non async version of get_now(), required for logging time formatter - no locking but only used during time travel so should be OK ...
    def get_now_sync(self):
        if self.realtime is True:
            return pytz.utc.localize(datetime.datetime.utcnow())
        else:
            return self.now

    async def get_now_ts(self):
        return (await self.get_now()).timestamp()

    async def get_now_naive(self):
        return self.make_naive(await self.get_now())

    async def now_is_between(self, start_time_str, end_time_str, name=None, now=None):
        start_time = (await self._parse_time(start_time_str, name, today=True, days_offset=0))["datetime"]
        end_time = (await self._parse_time(end_time_str, name, today=True, days_offset=0))["datetime"]
        if now is not None:
            now = (await self._parse_time(now, name))["datetime"]
        else:
            now = (await self.get_now()).astimezone(self.AD.tz)

        # Comparisons
        if end_time < start_time:
            # self.logger.info("Midnight transition")
            # Start and end time backwards.
            # Spans midnight
            # Lets start by assuming end_time is wrong and should be tomorrow
            # This will be true if we are currently after start_time
            end_time = (await self._parse_time(end_time_str, name, today=True, days_offset=1))["datetime"]
            if now < start_time and now < end_time:
                # self.logger.info("Reverse")
                # Well, it's complicated -
                # We crossed into a new day and things changed.
                # Now all times have shifted relative to the new day, so we need to look at it differently
                # If both times are now in the future, we now actually want to set start time back a day and keep end_time as today
                start_time = (await self._parse_time(start_time_str, name, today=True, days_offset=-1))["datetime"]
                end_time = (await self._parse_time(end_time_str, name, today=True, days_offset=0))["datetime"]

        # self.logger.info(f"\nstart = {start_time}\nnow   = {now}\nend   = {end_time}")
        return start_time <= now <= end_time

    async def sunset(self, aware, today=False, days_offset=0):
        if aware is True:
            if today is True:
                return self.todays_sunset(days_offset).astimezone(self.AD.tz)
            else:
                return self.next_sunset().astimezone(self.AD.tz)
        else:
            if today is True:
                return self.make_naive(self.todays_sunset(days_offset).astimezone(self.AD.tz))
            else:
                return self.make_naive(self.next_sunset().astimezone(self.AD.tz))

    async def sunrise(self, aware, today=False, days_offset=0):
        if aware is True:
            if today is True:
                return self.todays_sunrise(days_offset).astimezone(self.AD.tz)
            else:
                return self.next_sunrise().astimezone(self.AD.tz)
        else:
            if today is True:
                return self.make_naive(self.todays_sunrise(days_offset).astimezone(self.AD.tz))
            else:
                return self.make_naive(self.next_sunrise().astimezone(self.AD.tz))

    async def parse_time(self, time_str, name=False, aware=False, today=False, days_offset=0):
        if aware is True:
            return (
                (await self._parse_time(time_str, name, today=today, days_offset=days_offset))["datetime"]
                .astimezone(self.AD.tz)
                .time()
            )
        else:
            return self.make_naive(
                (await self._parse_time(time_str, name, today=today, days_offset=days_offset))["datetime"]
            ).time()

    async def parse_datetime(self, time_str, name=None, aware=False, today=False, days_offset=0):
        if aware is True:
            return (await self._parse_time(time_str, name, today=today, days_offset=days_offset))[
                "datetime"
            ].astimezone(self.AD.tz)
        else:
            return self.make_naive(
                (await self._parse_time(time_str, name, today=today, days_offset=days_offset))["datetime"]
            )

    async def _parse_time(self, time_str, name=None, today=False, days_offset=0):
        parsed_time = None
        sun = None
        offset = 0
        parts = re.search(r"^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+):(\d+)(?:\.(\d+))?$", time_str)
        if parts:
            if parts.group(7) is None:
                us = 0
            else:
                us = int(float("0." + parts.group(7)) * 1000000)

            this_time = datetime.datetime(
                int(parts.group(1)),
                int(parts.group(2)),
                int(parts.group(3)),
                int(parts.group(4)),
                int(parts.group(5)),
                int(parts.group(6)),
                us,
            )
            parsed_time = self.AD.tz.localize(this_time + datetime.timedelta(days=days_offset))
        else:
            parts = re.search(r"^(\d+):(\d+):(\d+)(?:\.(\d+))?$", time_str)
            if parts:
                if parts.group(4) is None:
                    us = 0
                else:
                    us = int(float("0." + parts.group(4)) * 1000000)

                today = (await self.get_now()).astimezone(self.AD.tz)
                time = datetime.time(int(parts.group(1)), int(parts.group(2)), int(parts.group(3)), us)
                parsed_time = today.replace(
                    hour=time.hour,
                    minute=time.minute,
                    second=time.second,
                    microsecond=us,
                ) + datetime.timedelta(days=days_offset)
            else:
                if time_str == "sunrise":
                    parsed_time = await self.sunrise(True, today, days_offset)
                    sun = "sunrise"
                    offset = 0
                elif time_str == "sunset":
                    parsed_time = await self.sunset(True, today, days_offset)
                    sun = "sunset"
                    offset = 0
                else:
                    parts = re.search(r"^sunrise\s*([+-])\s*(\d+):(\d+):(\d+)(?:\.(\d+))?$", time_str)
                    if parts:
                        if parts.group(5) is None:
                            us = 0
                        else:
                            us = int(float("0." + parts.group(5)) * 1000000)

                        sun = "sunrise"
                        td = datetime.timedelta(
                            hours=int(parts.group(2)),
                            minutes=int(parts.group(3)),
                            seconds=int(parts.group(4)),
                            microseconds=us,
                        )

                        if parts.group(1) == "+":
                            offset = td.total_seconds()
                            parsed_time = await self.sunrise(True, today, days_offset) + td
                        else:
                            offset = td.total_seconds() * -1
                            parsed_time = await self.sunrise(True, today, days_offset) - td
                    else:
                        parts = re.search(r"^sunset\s*([+-])\s*(\d+):(\d+):(\d+)(?:\.(\d+))?$", time_str)
                        if parts:
                            if parts.group(5) is None:
                                us = 0
                            else:
                                us = int(float("0." + parts.group(5)) * 1000000)

                            sun = "sunset"
                            td = datetime.timedelta(
                                hours=int(parts.group(2)),
                                minutes=int(parts.group(3)),
                                seconds=int(parts.group(4)),
                                microseconds=us,
                            )
                            if parts.group(1) == "+":
                                offset = td.total_seconds()
                                parsed_time = await self.sunset(True, today, days_offset) + td
                            else:
                                offset = td.total_seconds() * -1
                                parsed_time = await self.sunset(True, today, days_offset) - td

        if parsed_time is None:
            if name is not None:
                raise ValueError("%s: invalid time string: %s", name, time_str)
            else:
                raise ValueError("invalid time string: %s", time_str)
        return {"datetime": parsed_time, "sun": sun, "offset": offset}

    #
    # Diagnostics
    #

    async def dump_sun(self):
        self.diag.info("--------------------------------------------------")
        self.diag.info("Sun")
        self.diag.info("--------------------------------------------------")
        self.diag.info("Next Sunrise: %s", self.next_sunrise())
        self.diag.info("Today's Sunrise: %s", self.todays_sunrise(days_offset=0))
        self.diag.info("Next Sunset: %s", self.next_sunset())
        self.diag.info("Today's Sunset: %s", self.todays_sunset(days_offset=0))
        self.diag.info("--------------------------------------------------")

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
    def sanitize_timer_kwargs(app, kwargs):
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(
            kwargs_copy,
            ["interval", "constrain_days", "constrain_input_boolean", "_pin_app", "_pin_thread", "__silent"]
            + app.list_constraints(),
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
            result = datetime.datetime.utcfromtimestamp(rounded)
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

    def make_naive(self, dt):
        local = dt.astimezone(self.AD.tz)
        return datetime.datetime(
            local.year,
            local.month,
            local.day,
            local.hour,
            local.minute,
            local.second,
            local.microsecond,
        )
