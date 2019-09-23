import traceback
import datetime
from datetime import timedelta
import pytz
import astral
import random
import uuid
import re
import asyncio
import logging
from collections import OrderedDict
from copy import deepcopy

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon


class Scheduler:

    def __init__(self, ad: AppDaemon):
        self.AD = ad

        self.logger = ad.logging.get_child("_scheduler")
        self.error = ad.logging.get_error()
        self.diag = ad.logging.get_diag()
        self.last_fired = None
        self.sleep_task = None
        self.active = False

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
            unaware_end = datetime.datetime.strptime(self.AD.endtime, "%Y-%m-%d %H:%M:%S")
            aware_end = self.AD.tz.localize(unaware_end)
            self.endtime = aware_end.astimezone(pytz.utc)
        else:
            self.endtime = None

        # Setup sun

        self.init_sun()

    def set_start_time(self):
        tt = False
        if self.AD.starttime is not None:
            tt = True
            unaware_now = datetime.datetime.strptime(self.AD.starttime, "%Y-%m-%d %H:%M:%S")
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

    async def cancel_timer(self, name, handle):
        self.logger.debug("Canceling timer for %s", name)
        if name in self.schedule and handle in self.schedule[name]:
            del self.schedule[name][handle]
            await self.AD.state.remove_entity("admin", "scheduler_callback.{}".format(handle))
        if name in self.schedule and self.schedule[name] == {}:
            del self.schedule[name]

    # noinspection PyBroadException
    async def exec_schedule(self, name, args, uuid_):
        try:
            if "inactive" in args:
                return
            # Call function
            if "__entity" in args["kwargs"]:
                #
                # it's a "duration" entry
                #
                executed = await self.AD.threading.dispatch_worker(name, {
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
                })

                if executed is True:
                    remove = args["kwargs"].get("oneshot", False)
                    if remove is True:
                        await self.AD.state.cancel_state_callback(args["kwargs"]["__handle"], name)
                        
                        if "__timeout" in args["kwargs"]: #meaning there is a timeout for this callback
                            await self.cancel_timer(name, args["kwargs"]["__timeout"]) #cancel it as no more needed
                            
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
            else:
                #
                # A regular callback
                #
                await self.AD.threading.dispatch_worker(name, {
                    "id": uuid_,
                    "name": name,
                    "objectid": self.AD.app_management.objects[name]["id"],
                    "type": "scheduler",
                    "function": args["callback"],
                    "pin_app": args["pin_app"],
                    "pin_thread": args["pin_thread"],
                    "kwargs": deepcopy(args["kwargs"]),
                })
            # If it is a repeating entry, rewrite with new timestamp
            if args["repeat"]:
                if args["type"] == "next_rising" or args["type"] == "next_setting":
                    c_offset = self.get_offset(args)
                    args["timestamp"] = self.sun(args["type"], c_offset)
                    args["offset"] = c_offset
                else:
                    # Not sunrise or sunset so just increment
                    # the timestamp with the repeat interval
                    args["basetime"] += timedelta(seconds=args["interval"])
                    args["timestamp"] = args["basetime"] + timedelta(seconds=self.get_offset(args))
                # Update entity

                await self.AD.state.set_state("_scheduler", "admin", "scheduler_callback.{}".format(uuid_), execution_time=utils.dt_to_str(args["timestamp"].replace(microsecond=0), self.AD.tz))
            else:
                # Otherwise just delete
                await self.AD.state.remove_entity("admin", "scheduler_callback.{}".format(uuid_))

                del self.schedule[name][uuid_]

        except:
            error_logger = logging.getLogger("Error.{}".format(name))
            error_logger.warning('-' * 60)
            error_logger.warning("Unexpected error during exec_schedule() for App: %s", name)
            error_logger.warning("Args: %s", args)
            error_logger.warning('-' * 60)
            error_logger.warning(traceback.format_exc())
            error_logger.warning('-' * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning("Logged an error to %s", self.AD.logging.get_filename("error_log"))
            error_logger.warning("Scheduler entry has been deleted")
            error_logger.warning('-' * 60)
            await self.AD.state.remove_entity("admin", "scheduler_callback.{}".format(uuid_))
            del self.schedule[name][uuid_]

    def init_sun(self):
        latitude = self.AD.latitude
        longitude = self.AD.longitude

        if latitude < -90 or latitude > 90:
            raise ValueError("Latitude needs to be -90 .. 90")

        if longitude < -180 or longitude > 180:
            raise ValueError("Longitude needs to be -180 .. 180")

        elevation = self.AD.elevation

        self.location = astral.Location((
            '', '', latitude, longitude, self.AD.tz.zone, elevation
        ))

    def sun(self, type, offset):
        if offset < 0:
            # For negative offset we need to look forward to the next event after the current one
            return self.get_next_sun_event(type, 1) + datetime.timedelta(seconds=offset)
        else:
            # Positive or zero offset so no need to specify anything special
            return self.get_next_sun_event(type, 0) + datetime.timedelta(seconds=offset)

    def get_next_sun_event(self, type, offset):
        if type == "next_rising":
            return self.next_sunrise(offset)
        else:
            return self.next_sunset(offset)

    def next_sunrise(self, offset=0):
        mod = offset
        while True:
            try:
                next_rising_dt = self.location.sunrise(
                    (self.now + datetime.timedelta(seconds=offset) + datetime.timedelta(days=mod)).date(), local=False
                )
                if next_rising_dt > self.now:
                    break
            except astral.AstralError:
                pass
            mod += 1

        return next_rising_dt

    def next_sunset(self, offset = 0):
        mod = offset
        while True:
            try:
                next_setting_dt = self.location.sunset(
                    (self.now + datetime.timedelta(seconds=offset) + datetime.timedelta(days=mod)).date(), local=False
                )
                if next_setting_dt > self.now:
                    break
            except astral.AstralError:
                pass
            mod += 1

        return next_setting_dt

    @staticmethod
    def get_offset(kwargs):
        if "offset" in kwargs["kwargs"]:
            if "random_start" in kwargs["kwargs"] \
                    or "random_end" in kwargs["kwargs"]:
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
            #self.logger.debug("get_offset(): offset = %s", offset)
        return offset

    async def insert_schedule(self, name, aware_dt, callback, repeat, type_, **kwargs):

        #aware_dt will include a timezone of some sort - convert to utc timezone
        utc = aware_dt.astimezone(pytz.utc)

        # Round to nearest second

        utc = self.my_dt_round(utc, base=1)

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

        self.schedule[name][handle] = {
            "name": name,
            "id": self.AD.app_management.objects[name]["id"],
            "callback": callback,
            "timestamp": ts,
            "interval": interval,
            "basetime": utc,
            "repeat": repeat,
            "offset": c_offset,
            "type": type_,
            "pin_app": pin_app,
            "pin_thread": pin_thread,
            "kwargs": kwargs
        }

        if callback is None:
            function_name = "cancel_callback"
        else:
            function_name = callback.__name__

        await self.AD.state.add_entity("admin",
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
                                           "kwargs": kwargs
                                       })
                # verbose_log(conf.logger, "INFO", conf.schedule[name][handle])

        if self.active is True:
            await self.kick()
        return handle

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

        next_exec = datetime.datetime.now(pytz.utc).replace(year=3000)
        for name in self.schedule.keys():
            for entry in self.schedule[name].keys():
                if self.schedule[name][entry]["timestamp"] < next_exec:
                    next_exec = self.schedule[name][entry]["timestamp"]

        next_entries =[]

        for name in self.schedule.keys():
            for entry in self.schedule[name].keys():
                if self.schedule[name][entry]["timestamp"] == next_exec:
                    next_entries.append({"name": name, "uuid": entry, "timestamp": self.schedule[name][entry]["timestamp"]})

        return next_entries

    async def loop(self):
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
        idle_time = 60
        while not self.stopping:
            try:
                if self.endtime is not None and self.now >= self.endtime:
                    self.logger.info("End time reached, exiting")
                    if self.AD.stop_function is not None:
                        self.AD.stop_function()
                    else:
                        #
                        # We aren't in a standalone environment so the best we can do is terminate the AppDaemon parts
                        #
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
                            delta = (next_entries[0]["timestamp"] - self.now).total_seconds()
                        else:
                            # No kick, no scheduler expiry ...
                            delta = idle_time

                    self.now = self.now + timedelta(seconds=delta)

                self.last_fired = pytz.utc.localize(datetime.datetime.utcnow())
                self.logger.debug("self.now = %s", self.now)
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

                self.logger.debug("Delay = %s seconds", delay)
                if delay > 0 and self.AD.timewarp > 0:
                    result = await self.sleep(delay / self.AD.timewarp)
                    self.logger.debug("result = %s", result)
                else:
                    # Not sleeping but lets be fair to the rest of AD
                    await asyncio.sleep(0)

            except:
                self.logger.warning('-' * 60)
                self.logger.warning("Unexpected error in scheduler loop")
                self.logger.warning('-' * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning('-' * 60)
                # Prevent spamming of the logs
                await self.sleep(1)

    async def sleep(self, delay):
        coro = asyncio.sleep(delay, loop=self.AD.loop)
        self.sleep_task = asyncio.ensure_future(coro)
        try:
            await self.sleep_task
            self.sleep_task = None
            return False
        except asyncio.CancelledError:
            return True

    async def kick(self):
        while self.sleep_task is None:
            await asyncio.sleep(0)
        self.sleep_task.cancel()

    #
    # App API Calls
    #

    async def sun_up(self):
        return self.next_sunrise() > self.next_sunset()

    async def sun_down(self):
        return self.next_sunrise() < self.next_sunset()

    async def info_timer(self, handle, name):
        if name in self.schedule and handle in self.schedule[name]:
            callback = self.schedule[name][handle]
            return (
                self.make_naive(callback["timestamp"]),
                callback["interval"],
                self.sanitize_timer_kwargs(self.AD.app_management.objects[name]["object"], callback["kwargs"])
            )
        else:
            self.logger.warning("Invalid timer handle given as: %s", handle)
            return None

    async def get_scheduler_entries(self):
        schedule = {}
        for name in self.schedule.keys():
            schedule[name] = {}
            for entry in sorted(
                    self.schedule[name].keys(),
                    key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
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
                schedule[name][str(entry)]["callback"] = self.schedule[name][entry]["callback"].__name__
                schedule[name][str(entry)]["pin_thread"] = self.schedule[name][entry]["pin_thread"] if self.schedule[name][entry]["pin_thread"] != -1 else "None"
                schedule[name][str(entry)]["pin_app"] = "True" if self.schedule[name][entry]["pin_app"] is True else "False"

        # Order it

        ordered_schedule = OrderedDict(sorted(schedule.items(), key=lambda x: x[0]))

        return ordered_schedule

    async def is_dst(self):
        return (await self.get_now()).astimezone(self.AD.tz).dst() != datetime.timedelta(0)

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

    async def now_is_between(self, start_time_str, end_time_str, name=None):
        start_time = (await self._parse_time(start_time_str, name))["datetime"]
        end_time = (await self._parse_time(end_time_str, name))["datetime"]
        now = (await self.get_now()).astimezone(self.AD.tz)
        start_date = now.replace(
            hour=start_time.hour, minute=start_time.minute,
            second=start_time.second
        )
        end_date = now.replace(
            hour=end_time.hour, minute=end_time.minute, second=end_time.second
        )
        if end_date < start_date:
            # Spans midnight
            if now < start_date and now < end_date:
                now = now + datetime.timedelta(days=1)
            end_date = end_date + datetime.timedelta(days=1)
        return start_date <= now <= end_date

    async def sunset(self, aware):
        if aware is True:
            return self.next_sunset().astimezone(self.AD.tz)
        else:
            return self.make_naive(self.next_sunset().astimezone(self.AD.tz))

    async def sunrise(self, aware):
        if aware is True:
            return self.next_sunrise().astimezone(self.AD.tz)
        else:
            return self.make_naive(self.next_sunrise().astimezone(self.AD.tz))

    async def parse_time(self, time_str, name=None, aware=False):
        if aware is True:
            return (await self._parse_time(time_str, name))["datetime"].astimezone(self.AD.tz).time()
        else:
            return self.make_naive((await self._parse_time(time_str, name))["datetime"]).time()

    async def parse_datetime(self, time_str, name=None, aware=False):
        if aware is True:
            return (await self._parse_time(time_str, name))["datetime"].astimezone(self.AD.tz)
        else:
            return self.make_naive((await self._parse_time(time_str, name))["datetime"])


    async def _parse_time(self, time_str, name=None):
        parsed_time = None
        sun = None
        offset = 0
        parts = re.search('^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+):(\d+)$', time_str)
        if parts:
            this_time = datetime.datetime(int(parts.group(1)), int(parts.group(2)), int(parts.group(3)), int(parts.group(4)), int(parts.group(5)), int(parts.group(6)), 0)
            parsed_time = self.AD.tz.localize(this_time)
        else:
            parts = re.search('^(\d+):(\d+):(\d+)$', time_str)
            if parts:
                today = (await self.get_now()).astimezone(self.AD.tz)
                time = datetime.time(
                    int(parts.group(1)), int(parts.group(2)), int(parts.group(3)), 0
                )
                parsed_time = today.replace(hour=time.hour, minute=time.minute, second=time.second, microsecond=0)

            else:
                if time_str == "sunrise":
                    parsed_time = await self.sunrise(True)
                    sun = "sunrise"
                    offset = 0
                elif time_str == "sunset":
                    parsed_time = await self.sunset(True)
                    sun = "sunset"
                    offset = 0
                else:
                    parts = re.search(
                        '^sunrise\s*([+-])\s*(\d+):(\d+):(\d+)$', time_str
                    )
                    if parts:
                        sun = "sunrise"
                        if parts.group(1) == "+":
                            td = datetime.timedelta(
                                hours=int(parts.group(2)), minutes=int(parts.group(3)),
                                seconds=int(parts.group(4))
                            )
                            offset = td.total_seconds()
                            parsed_time = (await self.sunrise(True) + td)
                        else:
                            td = datetime.timedelta(
                                hours=int(parts.group(2)), minutes=int(parts.group(3)),
                                seconds=int(parts.group(4))
                            )
                            offset = td.total_seconds() * -1
                            parsed_time = (await self.sunrise(True) - td)
                    else:
                        parts = re.search(
                            '^sunset\s*([+-])\s*(\d+):(\d+):(\d+)$', time_str
                        )
                        if parts:
                            sun = "sunset"
                            if parts.group(1) == "+":
                                td = datetime.timedelta(
                                    hours=int(parts.group(2)), minutes=int(parts.group(3)),
                                    seconds=int(parts.group(4))
                                )
                                offset = td.total_seconds()
                                parsed_time = (await self.sunset(True) + td)
                            else:
                                td = datetime.timedelta(
                                    hours=int(parts.group(2)), minutes=int(parts.group(3)),
                                    seconds=int(parts.group(4))
                                )
                                offset = td.total_seconds() * -1
                                parsed_time = (await self.sunset(True) - td)
        if parsed_time is None:
            if name is not None:
                raise ValueError(
                    "%s: invalid time string: %s", name, time_str)
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
        self.diag.info("Next Sunset: %s", self.next_sunset())
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
                        key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
                ):
                    self.diag.info(" Next Event Time: %s - data: %s", self.make_naive(self.schedule[name][entry]["timestamp"]), self.schedule[name][entry])
            self.diag.info("--------------------------------------------------")

    #
    # Utilities
    #
    @staticmethod
    def sanitize_timer_kwargs(app, kwargs):
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(kwargs_copy, [
            "interval", "constrain_days", "constrain_input_boolean", "_pin_app", "_pin_thread"
        ] + app.list_constraints())

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
            #Localize with the configured timezone
            result = self.AD.tz.localize(dt)
        else:
            result = dt

        return result

    def make_naive(self, dt):
        local = dt.astimezone(self.AD.tz)
        return datetime.datetime(local.year, local.month, local.day,local.hour, local.minute, local.second, local.microsecond)
