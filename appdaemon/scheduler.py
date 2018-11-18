import threading
import traceback
import datetime
import pytz
import astral
import random
import uuid
import time
import re
import asyncio

import appdaemon.utils as utils


class Scheduler:

    def __init__(self, ad):
        self.AD = ad

        self.time_zone = self.AD.time_zone

        self.schedule = {}
        self.schedule_lock = threading.RLock()

        self.sun = {}
        self.sun_lock = threading.RLock()

        self.tz = None
        self.now = datetime.datetime.now().timestamp()

        if self.AD.tick != self.AD.interval or self.AD.starttime is not None:
            self.realtime = False

        self.stopping = False
        self.realtime = True

        # Take a note of DST

        self.was_dst = self.is_dst()

        # Setup sun

        self.init_sun()

        self.update_sun()

        tt = None
        if self.AD.starttime:
            tt = datetime.datetime.strptime(self.AD.starttime, "%Y-%m-%d %H:%M:%S")
            self.now = tt.timestamp()
        else:
            new_now = datetime.datetime.now()
            self.now = new_now.timestamp()
            if self.AD.tick != self.AD.interval:
                tt = new_now

        if tt is not None:
            self.AD.logging.log("INFO", "Starting time travel ...")
            self.AD.logging.log("INFO", "Setting clocks to {}".format(tt))
            if self.AD.tick == 0:
                self.AD.logging.log("INFO", "Time displacement factor infinite")
            else:
                self.AD.logging.log("INFO", "Time displacement factor {}".format(self.AD.interval / self.AD.tick))
        else:
            self.AD.logging.log("INFO", "Scheduler tick set to {}s".format(self.AD.tick))

    def stop(self):
        self.stopping = True

    def cancel_timer(self, name, handle):
        self.AD.logging.log("DEBUG", "Canceling timer for {}".format(name))
        with self.schedule_lock:
            if name in self.schedule and handle in self.schedule[name]:
                del self.schedule[name][handle]
            if name in self.schedule and self.schedule[name] == {}:
                del self.schedule[name]

    # noinspection PyBroadException
    def exec_schedule(self, name, entry, args):
        try:
            # Locking performed in calling function
            if "inactive" in args:
                return
            # Call function
            with self.AD.app_management.objects_lock:
                if "__entity" in args["kwargs"]:
                    self.AD.threading.dispatch_worker(name, {
                        "name": name,
                        "id": self.AD.app_management.objects[name]["id"],
                        "type": "attr",
                        "function": args["callback"],
                        "attribute": args["kwargs"]["__attribute"],
                        "entity": args["kwargs"]["__entity"],
                        "new_state": args["kwargs"]["__new_state"],
                        "old_state": args["kwargs"]["__old_state"],
                        "pin_app": args["pin_app"],
                        "pin_thread": args["pin_thread"],
                        "kwargs": args["kwargs"],
                    })
                else:
                    self.AD.threading.dispatch_worker(name, {
                        "name": name,
                        "id": self.AD.app_management.objects[name]["id"],
                        "type": "timer",
                        "function": args["callback"],
                        "pin_app": args["pin_app"],
                        "pin_thread": args["pin_thread"],
                        "kwargs": args["kwargs"],
                    })
            # If it is a repeating entry, rewrite with new timestamp
            if args["repeat"]:
                if args["type"] == "next_rising" or args["type"] == "next_setting":
                    # It's sunrise or sunset - if the offset is negative we
                    # won't know the next rise or set time yet so mark as inactive
                    # So we can adjust with a scan at sun rise/set
                    if args["offset"] < 0:
                        args["inactive"] = 1
                    else:
                        # We have a valid time for the next sunrise/set so use it
                        c_offset = self.get_offset(args)
                        args["timestamp"] = self.calc_sun(args["type"]) + c_offset
                        args["offset"] = c_offset
                else:
                    # Not sunrise or sunset so just increment
                    # the timestamp with the repeat interval
                    args["basetime"] += args["interval"]
                    args["timestamp"] = args["basetime"] + self.get_offset(args)
            else:  # Otherwise just delete
                del self.schedule[name][entry]

        except:
            self.AD.logging.err("WARNING", '-' * 60)
            self.AD.logging.err(
                "WARNING",
                "Unexpected error during exec_schedule() for App: {}".format(name)
            )
            self.AD.logging.err("WARNING", "Args: {}".format(args))
            self.AD.logging.err("WARNING", '-' * 60)
            self.AD.logging.err("WARNING", traceback.format_exc())
            self.AD.logging.err("WARNING", '-' * 60)
            if self.AD.errfile != "STDERR" and self.AD.logfile != "STDOUT":
                # When explicitly logging to stdout and stderr, suppress
                # verbose_log messages about writing an error (since they show up anyway)
                self.AD.logging.log("WARNING", "Logged an error to {}".format(self.AD.errfile))
            self.AD.logging.err("WARNING", "Scheduler entry has been deleted")
            self.AD.logging.err("WARNING", '-' * 60)

            del self.schedule[name][entry]

    def process_sun(self, action):
        self.AD.logging.log(
            "DEBUG",
            "Process sun: {}, next sunrise: {}, next sunset: {}".format(
                action, self.sun["next_rising"], self.sun["next_setting"]
            )
        )
        with self.schedule_lock:
            for name in self.schedule.keys():
                for entry in sorted(
                        self.schedule[name].keys(),
                        key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
                ):
                    schedule = self.schedule[name][entry]
                    if schedule["type"] == action and "inactive" in schedule:
                        del schedule["inactive"]
                        c_offset = self.get_offset(schedule)
                        schedule["timestamp"] = self.calc_sun(action) + c_offset
                        schedule["offset"] = c_offset

    def sun_up(self):
        with self.sun_lock:
            return self.sun["next_rising"] > self.sun["next_setting"]

    def sun_down(self):
        with self.sun_lock:
            return self.sun["next_rising"] < self.sun["next_setting"]

    def calc_sun(self, type_):
        # convert to a localized timestamp
        with self.sun_lock:
            return self.sun[type_].timestamp()

    def info_timer(self, handle, name):
        with self.schedule_lock:
            if name in self.schedule and handle in self.schedule[name]:
                callback = self.schedule[name][handle]
                return (
                    datetime.datetime.fromtimestamp(callback["timestamp"]),
                    callback["interval"],
                    self.sanitize_timer_kwargs(self.AD.app_management.objects[name]["object"], callback["kwargs"])
                )
            else:
                raise ValueError("Invalid handle: {}".format(handle))

    def init_sun(self):
        latitude = self.AD.latitude
        longitude = self.AD.longitude

        if -90 > latitude < 90:
            raise ValueError("Latitude needs to be -90 .. 90")

        if -180 > longitude < 180:
            raise ValueError("Longitude needs to be -180 .. 180")

        elevation = self.AD.elevation

        self.tz = pytz.timezone(self.AD.time_zone)

        self.location = astral.Location((
            '', '', latitude, longitude, self.tz.zone, elevation
        ))

    def update_sun(self):

        #now = datetime.datetime.now(self.tz)
        #now = pytz.utc.localize(self.get_now())

        now = self.tz.localize(self.get_now())

        mod = -1
        while True:
            try:
                next_rising_dt = self.location.sunrise(
                    (now + datetime.timedelta(days=mod)).date(), local=False
                )
                if next_rising_dt > now:
                    break
            except astral.AstralError:
                pass
            mod += 1

        mod = -1
        while True:
            try:
                next_setting_dt = self.location.sunset(
                    (now + datetime.timedelta(days=mod)).date(), local=False
                )
                if next_setting_dt > now:
                    break
            except astral.AstralError:
                pass
            mod += 1

        with self.sun_lock:
            old_next_rising_dt = self.sun.get("next_rising")
            old_next_setting_dt = self.sun.get("next_setting")
            self.sun["next_rising"] = next_rising_dt
            self.sun["next_setting"] = next_setting_dt

            if old_next_rising_dt is not None and old_next_rising_dt != self.sun["next_rising"]:
                # dump_schedule()
                self.process_sun("next_rising")
                # dump_schedule()
            if old_next_setting_dt is not None and old_next_setting_dt != self.sun["next_setting"]:
                # dump_schedule()
                self.process_sun("next_setting")
                # dump_schedule()

        self.AD.logging.log(
            "DEBUG",
            "Update sun: next sunrise: {}, next sunset: {}".format(
                self.sun["next_rising"], self.sun["next_setting"]
            )
        )

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
        # verbose_log(conf.logger, "INFO", "sun: offset = {}".format(offset))
        return offset

    def insert_schedule(self, name, utc, callback, repeat, type_, **kwargs):
        with self.AD.app_management.objects_lock:
            if "pin" in kwargs:
                pin_app = kwargs["pin"]
            else:
                pin_app = self.AD.app_management.objects[name]["pin_app"]

            if "pin_thread" in kwargs:
                pin_thread = kwargs["pin_thread"]
                pin_app = True
            else:
                pin_thread = self.AD.app_management.objects[name]["pin_thread"]

        with self.schedule_lock:
            if name not in self.schedule:
                self.schedule[name] = {}
            handle = uuid.uuid4()
            utc = int(utc)
            c_offset = self.get_offset({"kwargs": kwargs})
            ts = utc + c_offset
            interval = kwargs.get("interval", 0)

            with self.AD.app_management.objects_lock:
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
                # verbose_log(conf.logger, "INFO", conf.schedule[name][handle])
        return handle

    def term_object(self, name):
        with self.schedule_lock:
            if name in self.schedule:
                del self.schedule[name]

    def is_realtime(self):
        return self.realtime

    def get_scheduler_entries(self):
        schedule = {}
        for name in self.schedule.keys():
            schedule[name] = {}
            for entry in sorted(
                    self.schedule[name].keys(),
                    key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
            ):
                schedule[name][entry] = {}
                schedule[name][entry]["timestamp"] = self.schedule[name][entry]["timestamp"]
                schedule[name][entry]["type"] = self.schedule[name][entry]["type"]
                schedule[name][entry]["name"] = self.schedule[name][entry]["name"]
                schedule[name][entry]["basetime"] = self.schedule[name][entry]["basetime"]
                schedule[name][entry]["repeat"] = self.schedule[name][entry]["repeat"]
                schedule[name][entry]["offset"] = self.schedule[name][entry]["offset"]
                schedule[name][entry]["interval"] = self.schedule[name][entry]["interval"]
                schedule[name][entry]["kwargs"] = self.schedule[name][entry]["kwargs"]
                schedule[name][entry]["callback"] = self.schedule[name][entry]["callback"]
        return schedule

    def is_dst(self):
        return bool(time.localtime(self.get_now_ts()).tm_isdst)

    def get_now(self):
        return datetime.datetime.fromtimestamp(self.now)

    def get_now_ts(self):
        return self.now

    def now_is_between(self, start_time_str, end_time_str, name=None):
        start_time = self.parse_time(start_time_str, name)
        end_time = self.parse_time(end_time_str, name)
        now = self.get_now()
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

    def sunset(self):
        return datetime.datetime.fromtimestamp(self.calc_sun("next_setting"))

    def sunrise(self):
        return datetime.datetime.fromtimestamp(self.calc_sun("next_rising"))


    def parse_time(self, time_str, name=None):
        return self._parse_time(time_str, name)["datetime"].time()

    def parse_datetime(self, time_str, name=None):
        return self._parse_time(time_str, name)["datetime"]

    def _parse_time(self, time_str, name=None):
        parsed_time = None
        sun = None
        offset = 0
        parts = re.search('^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+):(\d+)', time_str)
        if parts:
            parsed_time = datetime.datetime(int(parts.group(1)), int(parts.group(2)), int(parts.group(3)), int(parts.group(4)), int(parts.group(5)), int(parts.group(6)), 0)
        else:
            parts = re.search('^(\d+):(\d+):(\d+)', time_str)
            if parts:
                today = datetime.datetime.fromtimestamp(self.get_now_ts())
                time = datetime.time(
                    int(parts.group(1)), int(parts.group(2)), int(parts.group(3)), 0
                )
                parsed_time = today.replace(hour=time.hour, minute=time.minute, second=time.second, microsecond=0)

            else:
                if time_str == "sunrise":
                    parsed_time = self.sunrise()
                    sun = "sunrise"
                    offset = 0
                elif time_str == "sunset":
                    parsed_time = self.sunset()
                    sun = "sunset"
                    offset = 0
                else:
                    parts = re.search(
                        '^sunrise\s*([+-])\s*(\d+):(\d+):(\d+)', time_str
                    )
                    if parts:
                        sun = "sunrise"
                        if parts.group(1) == "+":
                            td = datetime.timedelta(
                                hours=int(parts.group(2)), minutes=int(parts.group(3)),
                                seconds=int(parts.group(4))
                            )
                            offset = td.total_seconds()
                            parsed_time = (self.sunrise() + td)
                        else:
                            td = datetime.timedelta(
                                hours=int(parts.group(2)), minutes=int(parts.group(3)),
                                seconds=int(parts.group(4))
                            )
                            offset = td.total_seconds() * -1
                            parsed_time = (self.sunrise() - td)
                    else:
                        parts = re.search(
                            '^sunset\s*([+-])\s*(\d+):(\d+):(\d+)', time_str
                        )
                        if parts:
                            sun = "sunset"
                            if parts.group(1) == "+":
                                td = datetime.timedelta(
                                    hours=int(parts.group(2)), minutes=int(parts.group(3)),
                                    seconds=int(parts.group(4))
                                )
                                offset = td.total_seconds()
                                parsed_time = (self.sunset() + td)
                            else:
                                td = datetime.timedelta(
                                    hours=int(parts.group(2)), minutes=int(parts.group(3)),
                                    seconds=int(parts.group(4))
                                )
                                offset = td.total_seconds() * -1
                                parsed_time = (self.sunset() - td)
        if parsed_time is None:
            if name is not None:
                raise ValueError(
                    "{}: invalid time string: {}".format(name, time_str))
            else:
                raise ValueError("invalid time string: {}".format(time_str))
        return {"datetime": parsed_time, "sun": sun, "offset": offset}

    def sanitize_timer_kwargs(self, app, kwargs):
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(kwargs_copy, [
            "interval", "constrain_days", "constrain_input_boolean", "_pin_app", "_pin_thread"
        ] + app.list_constraints())

    def dump_sun(self):
        self.AD.logging.diag("INFO", "--------------------------------------------------")
        self.AD.logging.diag("INFO", "Sun")
        self.AD.logging.diag("INFO", "--------------------------------------------------")
        self.AD.logging.diag("INFO", self.sun)
        self.AD.logging.diag("INFO", "--------------------------------------------------")

    def dump_schedule(self):
        if self.schedule == {}:
            self.AD.logging.diag("INFO", "Schedule is empty")
        else:
            self.AD.logging.diag("INFO", "--------------------------------------------------")
            self.AD.logging.diag("INFO", "Scheduler Table")
            self.AD.logging.diag("INFO", "--------------------------------------------------")
            for name in self.schedule.keys():
                self.AD.logging.diag( "INFO", "{}:".format(name))
                for entry in sorted(
                        self.schedule[name].keys(),
                        key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
                ):
                    self.AD.logging.diag(
                        "INFO",
                        "  Timestamp: {} - data: {}".format(
                            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(
                                self.schedule[name][entry]["timestamp"]
                            )),
                            self.schedule[name][entry]
                        )
                    )
            self.AD.logging.diag("INFO", "--------------------------------------------------")

    def myround(self, x, base=1, prec=10):
        if base == 0:
            return x
        else:
            return round(base * round(float(x) / base), prec)

    async def do_every(self):
        #
        # We already set self.now for DST calculation and initial sunset,
        # but lets reset it at the start of the timer loop to avoid an initial clock skew
        #
        if self.AD.starttime:
            self.now = datetime.datetime.strptime(self.AD.starttime, "%Y-%m-%d %H:%M:%S").timestamp()
        else:
            self.now = datetime.datetime.now().timestamp()

        t = self.myround(self.now, base=self.AD.tick)
        count = 0
        t_ = self.myround(time.time(), base=self.AD.tick)
        #print(t, t_, period)
        while not self.stopping:
            count += 1
            delay = max(t_ + count * self.AD.tick - time.time(), 0)
            await asyncio.sleep(delay)
            t = self.myround(t + self.AD.interval, base=self.AD.tick)
            r = await self.do_every_tick(t)
            if r is not None and r != t:
                #print("r: {}, t: {}".format(r,t))
                t = r
                t_ = r
                count = 0

    #
    # Scheduler Loop
    #

    # noinspection PyBroadException,PyBroadException

    async def do_every_tick(self, utc):
        try:
            start_time = datetime.datetime.now().timestamp()
            self.now = utc

            #print("tick - {}".format(utc))

            # If we have reached endtime bail out

            if self.AD.endtime is not None and self.get_now() >= self.AD.endtime:
                self.AD.logging.log("INFO", "End time reached, exiting")
                if self.AD.stop_function is not None:
                    self.AD.stop_function()
                else:
                    #
                    # We aren't in a standalone environment so the best we can do is terminate the AppDaemon parts
                    #
                    self.stop()

            if self.realtime:
                real_now = datetime.datetime.now().timestamp()
                delta = abs(utc - real_now)
                if delta > self.AD.max_clock_skew:
                    self.AD.logging.log("WARNING",
                              "Scheduler clock skew detected - delta = {} - resetting".format(delta))
                    return real_now

            # Update sunrise/sunset etc.

            self.update_sun()

            # Check if we have entered or exited DST - if so, reload apps
            # to ensure all time callbacks are recalculated

            now_dst = self.is_dst()
            if now_dst != self.was_dst:
                self.AD.logging.log(
                    "INFO",
                    "Detected change in DST from {} to {} -"
                    " reloading all modules".format(self.was_dst, now_dst)
                )
                # dump_schedule()
                self.AD.logging.log("INFO", "-" * 40)
                await utils.run_in_executor(self.AD.loop, self.AD.executor, self.AD.check_app_updates, "__ALL__")
                # dump_schedule()
            self.was_dst = now_dst

            # dump_schedule()

            # test code for clock skew
            # if random.randint(1, 10) == 5:
            #    time.sleep(random.randint(1,20))


            # Process callbacks

            # self.log("DEBUG", "Scheduler invoked at {}".format(now))
            with self.schedule_lock:
                for name in self.schedule.keys():
                    for entry in sorted(
                            self.schedule[name].keys(),
                            key=lambda uuid_: self.schedule[name][uuid_]["timestamp"]
                    ):

                        if self.schedule[name][entry]["timestamp"] <= utc:
                            self.exec_schedule(name, entry, self.schedule[name][entry])
                        else:
                            break
                for k, v in list(self.schedule.items()):
                    if v == {}:
                        del self.schedule[k]

            end_time = datetime.datetime.now().timestamp()

            loop_duration = end_time - start_time
            self.AD.logging.log("DEBUG", "Scheduler loop compute time: {}s".format(loop_duration))

            #if loop_duration > 900:
            if loop_duration > self.AD.tick * 0.9:
                self.AD.logging.log("WARNING", "Excessive time spent in scheduler loop: {}s".format(loop_duration))

            return utc

        except:
            self.AD.logging.err("WARNING", '-' * 60)
            self.AD.logging.err("WARNING", "Unexpected error during do_every_tick()")
            self.AD.logging.err("WARNING", '-' * 60)
            self.AD.logging.err( "WARNING", traceback.format_exc())
            self.AD.logging.err("WARNING", '-' * 60)
            if self.AD.errfile != "STDERR" and self.AD.logfile != "STDOUT":
                # When explicitly logging to stdout and stderr, suppress
                # verbose_log messages about writing an error (since they show up anyway)
                self.AD.logging.log(
                    "WARNING",
                    "Logged an error to {}".format(self.AD.errfile)
                )

