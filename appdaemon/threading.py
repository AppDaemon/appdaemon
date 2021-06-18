import asyncio
import threading
import datetime
from queue import Queue
from random import randint
import re
import sys
import traceback
import inspect
from datetime import timedelta
import logging
import iso8601

from appdaemon import utils as utils
from appdaemon.appdaemon import AppDaemon


class Threading:
    def __init__(self, ad: AppDaemon, kwargs):

        self.AD = ad
        self.kwargs = kwargs

        self.logger = ad.logging.get_child("_threading")
        self.diag = ad.logging.get_diag()
        self.thread_count = 0

        self.threads = {}

        # A few shortcuts

        self.add_entity = ad.state.add_entity
        self.get_state = ad.state.get_state
        self.set_state = ad.state.set_state
        self.add_to_state = ad.state.add_to_state
        self.add_to_attr = ad.state.add_to_attr

        self.auto_pin = True
        self.pin_threads = 0
        self.total_threads = 0
        self.pin_apps = None
        self.next_thread = None
        # Setup stats

        self.current_callbacks_executed = 0
        self.current_callbacks_fired = 0

        self.last_stats_time = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)
        self.callback_list = []

    async def get_q_update(self):
        for thread in self.threads:
            qsize = self.get_q(thread).qsize()
            await self.set_state("_threading", "admin", "thread.{}".format(thread), q=qsize)

    async def get_callback_update(self):
        now = datetime.datetime.now()
        self.callback_list.append(
            {"fired": self.current_callbacks_fired, "executed": self.current_callbacks_executed, "ts": now}
        )

        if len(self.callback_list) > 10:
            self.callback_list.pop(0)

        fired_sum = 0
        executed_sum = 0
        for item in self.callback_list:
            fired_sum += item["fired"]
            executed_sum += item["executed"]

        total_duration = (
            self.callback_list[len(self.callback_list) - 1]["ts"] - self.callback_list[0]["ts"]
        ).total_seconds()

        if total_duration == 0:
            fired_avg = 0
            executed_avg = 0
        else:
            fired_avg = round(fired_sum / total_duration, 1)
            executed_avg = round(executed_sum / total_duration, 1)

        await self.set_state("_threading", "admin", "sensor.callbacks_average_fired", state=fired_avg)
        await self.set_state(
            "_threading", "admin", "sensor.callbacks_average_executed", state=executed_avg,
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
            "admin", "sensor.threads_max_busy_time", utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0)),
        )
        await self.add_entity(
            "admin", "sensor.threads_last_action_time", utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0)),
        )

    async def create_initial_threads(self):
        kwargs = self.kwargs

        if "threads" in kwargs:
            self.logger.warning(
                "Threads directive is deprecated apps - will be pinned. Use total_threads if you want to unpin your apps"
            )

        if "total_threads" in kwargs:
            self.total_threads = kwargs["total_threads"]
            self.auto_pin = False
        else:
            apps = await self.AD.app_management.check_config(True, False)
            self.total_threads = int(apps["active"])

        self.pin_apps = True
        utils.process_arg(self, "pin_apps", kwargs)

        if self.pin_apps is True:
            self.pin_threads = self.total_threads
        else:
            self.auto_pin = False
            self.pin_threads = 0
            if "total_threads" not in kwargs:
                self.total_threads = 10

        utils.process_arg(self, "pin_threads", kwargs, int=True)

        if self.pin_threads > self.total_threads:
            raise ValueError("pin_threads cannot be > total_threads")

        if self.pin_threads < 0:
            raise ValueError("pin_threads cannot be < 0")

        self.logger.info(
            "Starting Apps with %s workers and %s pins", self.total_threads, self.pin_threads,
        )

        self.next_thread = self.pin_threads

        self.thread_count = 0
        for i in range(self.total_threads):
            await self.add_thread(True)

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

    def get_q(self, thread_id):
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
                await self.get_pinned_apps(thread),
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
                    "Invalid thread ID for pinned thread in app: %s - assigning to thread 0", args["name"],
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
            raise ValueError("invalid thread id: {} in app {}".format(thread, args["name"]))

        id = "thread-{}".format(thread)
        q = self.threads[id]["queue"]

        q.put_nowait(args)

    async def check_overdue_and_dead_threads(self):
        if self.AD.sched.realtime is True and self.AD.thread_duration_warning_threshold != 0:
            for thread_id in self.threads:
                if self.threads[thread_id]["thread"].is_alive() is not True:
                    self.logger.critical("Thread %s has died", thread_id)
                    self.logger.critical("Pinned apps were: %s", await self.get_pinned_apps(thread_id))
                    self.logger.critical("Thread will be restarted")
                    id = thread_id.split("-")[1]
                    await self.add_thread(silent=False, pinthread=False, id=id)
                if await self.get_state("_threading", "admin", "thread.{}".format(thread_id)) != "idle":
                    start = utils.str_to_dt(
                        await self.get_state(
                            "_threading", "admin", "thread.{}".format(thread_id), attribute="time_called",
                        )
                    )
                    dur = (await self.AD.sched.get_now() - start).total_seconds()
                    if (
                        dur >= self.AD.thread_duration_warning_threshold
                        and dur % self.AD.thread_duration_warning_threshold == 0
                    ):
                        self.logger.warning(
                            "Excessive time spent in callback: %s - %s",
                            await self.get_state(
                                "_threading", "admin", "thread.{}".format(thread_id), attribute="callback",
                            ),
                            dur,
                        )

    async def check_q_size(self, warning_step, warning_iterations):
        totalqsize = 0
        for thread in self.threads:
            totalqsize += self.threads[thread]["queue"].qsize()

        if totalqsize > self.AD.qsize_warning_threshold:
            if (
                warning_step == 0 and warning_iterations >= self.AD.qsize_warning_iterations
            ) or warning_iterations == self.AD.qsize_warning_iterations:

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
                                    "_threading", "admin", "thread.{}".format(thread), attribute="time_called",
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

        appentity = "{}.{}".format(appinfo["type"], app)

        now = await self.AD.sched.get_now()
        if callback == "idle":
            start = utils.str_to_dt(
                await self.get_state("_threading", "admin", "thread.{}".format(thread_id), attribute="time_called",)
            )
            if (
                self.AD.sched.realtime is True
                and (now - start).total_seconds() >= self.AD.thread_duration_warning_threshold
            ):
                self.logger.warning(
                    "callback %s has now completed",
                    await self.get_state("_threading", "admin", "thread.{}".format(thread_id)),
                )
            await self.add_to_state("_threading", "admin", "sensor.threads_current_busy", -1)

            await self.add_to_attr("_threading", "admin", appentity, "totalcallbacks", 1)
            await self.add_to_attr("_threading", "admin", appentity, "instancecallbacks", 1)

            await self.add_to_attr(
                "_threading", "admin", "{}_callback.{}".format(type, uuid), "executed", 1,
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
                pinned_apps=await self.get_pinned_apps(thread_id),
            )
        await self.set_state("_threading", "admin", appentity, state=callback)

    #
    # Pinning
    #

    async def add_thread(self, silent=False, pinthread=False, id=None):
        if id is None:
            tid = self.thread_count
        else:
            tid = id
        if silent is False:
            self.logger.info("Adding thread %s", tid)
        t = threading.Thread(target=self.worker)
        t.daemon = True
        name = "thread-{}".format(tid)
        t.setName(name)
        if id is None:
            await self.add_entity(
                "admin",
                "thread.{}".format(name),
                "idle",
                {"q": 0, "is_alive": True, "time_called": utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0))},
            )
            self.threads[name] = {}
            self.threads[name]["queue"] = Queue(maxsize=0)
            t.start()
            self.thread_count += 1
            if pinthread is True:
                self.pin_threads += 1
        else:
            await self.set_state(
                "_threading", "admin", "thread.{}".format(name), state="idle", is_alive=True,
            )

        self.threads[name]["thread"] = t

    async def calculate_pin_threads(self):

        if self.pin_threads == 0:
            return

        thread_pins = [0] * self.pin_threads
        for name in self.AD.app_management.objects:
            # Looking for apps that already have a thread pin value
            if await self.get_app_pin(name) and await self.get_pin_thread(name) != -1:
                thread = await self.get_pin_thread(name)
                if thread >= self.thread_count:
                    raise ValueError(
                        "Pinned thread out of range - check apps.yaml for 'pin_thread' or app code for 'set_pin_thread()'"
                    )
                # Ignore anything outside the pin range as it will have been set by the user
                if thread < self.pin_threads:
                    thread_pins[thread] += 1

        # Now we know the numbers, go fill in the gaps

        for name in self.AD.app_management.objects:
            if await self.get_app_pin(name) and await self.get_pin_thread(name) == -1:
                thread = thread_pins.index(min(thread_pins))
                await self.set_pin_thread(name, thread)
                thread_pins[thread] += 1

        for thread in self.threads:
            pinned_apps = await self.get_pinned_apps(thread)
            await self.set_state(
                "_threading", "admin", "thread.{}".format(thread), pinned_apps=pinned_apps,
            )

    def app_should_be_pinned(self, name):
        # Check apps.yaml first - allow override
        app = self.AD.app_management.app_config[name]
        if "pin_app" in app:
            return app["pin_app"]

        # if not, go with the global default
        return self.pin_apps

    async def get_app_pin(self, name):
        return self.AD.app_management.objects[name]["pin_app"]

    async def set_app_pin(self, name, pin):
        self.AD.app_management.objects[name]["pin_app"] = pin
        if pin is True:
            # May need to set this app up with a pinned thread
            await self.calculate_pin_threads()

    async def get_pin_thread(self, name):
        return self.AD.app_management.objects[name]["pin_thread"]

    async def set_pin_thread(self, name, thread):
        self.AD.app_management.objects[name]["pin_thread"] = thread

    def validate_pin(self, name, kwargs):
        valid = True
        if "pin_thread" in kwargs:
            if kwargs["pin_thread"] < 0 or kwargs["pin_thread"] >= self.thread_count:
                self.logger.warning(
                    "Invalid value for pin_thread (%s) in app: %s - discarding callback", kwargs["pin_thread"], name,
                )
                valid = False
        return valid

    async def get_pinned_apps(self, thread):
        id = int(thread.split("-")[1])
        apps = []
        for obj in self.AD.app_management.objects:
            if self.AD.app_management.objects[obj]["pin_thread"] == id:
                apps.append(obj)
        return apps

    #
    # Constraints
    #

    async def check_constraint(self, key, value, app):
        unconstrained = True
        if key in app.list_constraints():
            method = getattr(app, key)
            unconstrained = await utils.run_async_sync_func(self, method, value)

        return unconstrained

    async def check_time_constraint(self, args, name):
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
        unconstrained = True
        if "constrain_days" in args:
            days = args["constrain_days"]
            now = await self.AD.sched.get_now()
            daylist = []
            for day in days.split(","):
                daylist.append(await utils.run_in_executor(self, utils.day_of_week, day))

            if now.weekday() not in daylist:
                unconstrained = False

        return unconstrained

    #
    # Workers
    #

    async def check_and_dispatch_state(
        self, name, funcref, entity, attribute, new_state, old_state, cold, cnew, kwargs, uuid_, pin_app, pin_thread,
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
                    "objectid": self.AD.app_management.objects[name]["id"],
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
                        await self.AD.sched.cancel_timer(name, kwargs["__duration"])

                    del kwargs["__duration"]

                #
                # Check if we care about the change
                #
                if (cold is None or cold == old) and (cnew is None or cnew == new):
                    #
                    # We do!
                    #

                    if "duration" in kwargs:
                        #
                        # Set a timer
                        #
                        exec_time = await self.AD.sched.get_now() + timedelta(seconds=int(kwargs["duration"]))

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
                            name,
                            exec_time,
                            funcref,
                            False,
                            None,
                            __entity=entity,
                            __attribute=attribute,
                            __old_state=old,
                            __new_state=new,
                            **kwargs
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
                                "objectid": self.AD.app_management.objects[name]["id"],
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

    async def dispatch_worker(self, name, args):
        unconstrained = True
        #
        # Argument Constraints
        # (plugins have no args so skip if necessary)
        #
        if name in self.AD.app_management.app_config:
            for arg in self.AD.app_management.app_config[name].keys():
                constrained = await self.check_constraint(
                    arg, self.AD.app_management.app_config[name][arg], self.AD.app_management.objects[name]["object"],
                )
                if not constrained:
                    unconstrained = False
            if not await self.check_time_constraint(self.AD.app_management.app_config[name], name):
                unconstrained = False
            elif not await self.check_days_constraint(self.AD.app_management.app_config[name], name):
                unconstrained = False

        #
        # Callback level constraints
        #
        myargs = utils.deepcopy(args)
        if "kwargs" in myargs:
            for arg in myargs["kwargs"].keys():
                constrained = await self.check_constraint(
                    arg, myargs["kwargs"][arg], self.AD.app_management.objects[name]["object"],
                )
                if not constrained:
                    unconstrained = False
            if not await self.check_time_constraint(myargs["kwargs"], name):
                unconstrained = False
            elif not await self.check_days_constraint(myargs["kwargs"], name):
                unconstrained = False

        if unconstrained:
            #
            # It's going to happen
            #
            if "__silent" in args["kwargs"] and args["kwargs"]["__silent"] is True:
                pass
            else:
                await self.add_to_state("_threading", "admin", "sensor.callbacks_total_fired", 1)
                await self.add_to_attr(
                    "_threading", "admin", "{}_callback.{}".format(myargs["type"], myargs["id"]), "fired", 1,
                )
            #
            # And Q
            #
            if asyncio.iscoroutinefunction(myargs["function"]):
                f = asyncio.ensure_future(self.async_worker(myargs))
                self.AD.futures.add_future(name, f)
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
        error_logger = logging.getLogger("Error.{}".format(name))
        args["kwargs"]["__thread_id"] = thread_id
        callback = "{}() in {}".format(funcref.__name__, name)
        silent = False
        if "__silent" in args["kwargs"]:
            silent = args["kwargs"]["__silent"]

        app = await self.AD.app_management.get_app_instance(name, objectid)
        if app is not None:
            try:
                if _type == "scheduler":
                    try:
                        await self.update_thread_info("async", callback, name, _type, _id, silent)
                        await funcref(self.AD.sched.sanitize_timer_kwargs(app, args["kwargs"]))
                    except TypeError:
                        self.report_callback_sig(name, "scheduler", funcref, args)

                elif _type == "state":
                    try:
                        entity = args["entity"]
                        attr = args["attribute"]
                        old_state = args["old_state"]
                        new_state = args["new_state"]
                        await self.update_thread_info("async", callback, name, _type, _id, silent)
                        await funcref(
                            entity,
                            attr,
                            old_state,
                            new_state,
                            self.AD.state.sanitize_state_kwargs(app, args["kwargs"]),
                        )
                    except TypeError:
                        self.report_callback_sig(name, "state", funcref, args)

                elif _type == "log":
                    data = args["data"]
                    try:
                        await self.update_thread_info("async", callback, name, _type, _id, silent)
                        await funcref(
                            data["app_name"],
                            data["ts"],
                            data["level"],
                            data["log_type"],
                            data["message"],
                            self.AD.events.sanitize_event_kwargs(app, args["kwargs"]),
                        )
                    except TypeError:
                        self.report_callback_sig(name, "log_event", funcref, args)

                elif _type == "event":
                    data = args["data"]
                    try:
                        await self.update_thread_info("async", callback, name, _type, _id, silent)
                        await funcref(args["event"], data, self.AD.events.sanitize_event_kwargs(app, args["kwargs"]))
                    except TypeError:
                        self.report_callback_sig(name, "event", funcref, args)

            except Exception:
                error_logger.warning("-" * 60)
                error_logger.warning("Unexpected error in worker for App %s:", name)
                error_logger.warning("Worker Ags: %s", args)
                error_logger.warning("-" * 60)
                error_logger.warning(traceback.format_exc())
                error_logger.warning("-" * 60)
                if self.AD.logging.separate_error_log() is True:
                    self.logger.warning(
                        "Logged an error to %s", self.AD.logging.get_filename("error_log"),
                    )
            finally:
                pass
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
            error_logger = logging.getLogger("Error.{}".format(name))
            args["kwargs"]["__thread_id"] = thread_id
            callback = "{}() in {}".format(funcref.__name__, name)
            silent = False
            if "__silent" in args["kwargs"]:
                silent = args["kwargs"]["__silent"]

            app = utils.run_coroutine_threadsafe(self, self.AD.app_management.get_app_instance(name, objectid))
            if app is not None:
                try:
                    if _type == "scheduler":
                        try:
                            utils.run_coroutine_threadsafe(
                                self, self.update_thread_info(thread_id, callback, name, _type, _id, silent),
                            )
                            funcref(self.AD.sched.sanitize_timer_kwargs(app, args["kwargs"]))
                        except TypeError:
                            self.report_callback_sig(name, "scheduler", funcref, args)

                    elif _type == "state":
                        try:
                            entity = args["entity"]
                            attr = args["attribute"]
                            old_state = args["old_state"]
                            new_state = args["new_state"]
                            utils.run_coroutine_threadsafe(
                                self, self.update_thread_info(thread_id, callback, name, _type, _id, silent),
                            )
                            funcref(
                                entity,
                                attr,
                                old_state,
                                new_state,
                                self.AD.state.sanitize_state_kwargs(app, args["kwargs"]),
                            )
                        except TypeError:
                            self.report_callback_sig(name, "state", funcref, args)

                    if _type == "log":
                        data = args["data"]
                        try:
                            utils.run_coroutine_threadsafe(
                                self, self.update_thread_info(thread_id, callback, name, _type, _id, silent),
                            )
                            funcref(
                                data["app_name"],
                                data["ts"],
                                data["level"],
                                data["log_type"],
                                data["message"],
                                self.AD.events.sanitize_event_kwargs(app, args["kwargs"]),
                            )
                        except TypeError:
                            self.report_callback_sig(name, "log_event", funcref, args)

                    elif _type == "event":
                        data = args["data"]
                        try:
                            utils.run_coroutine_threadsafe(
                                self, self.update_thread_info(thread_id, callback, name, _type, _id, silent),
                            )
                            funcref(args["event"], data, self.AD.events.sanitize_event_kwargs(app, args["kwargs"]))
                        except TypeError:
                            self.report_callback_sig(name, "event", funcref, args)

                except Exception:
                    error_logger.warning("-" * 60)
                    error_logger.warning("Unexpected error in worker for App %s:", name)
                    error_logger.warning("Worker Ags: %s", args)
                    error_logger.warning("-" * 60)
                    error_logger.warning(traceback.format_exc())
                    error_logger.warning("-" * 60)
                    if self.AD.logging.separate_error_log() is True:
                        self.logger.warning(
                            "Logged an error to %s", self.AD.logging.get_filename("error_log"),
                        )
                finally:
                    utils.run_coroutine_threadsafe(
                        self, self.update_thread_info(thread_id, "idle", name, _type, _id, silent),
                    )

            else:
                if not self.AD.stopping:
                    self.logger.warning("Found stale callback for %s - discarding", name)

            q.task_done()

    def report_callback_sig(self, name, type, funcref, args):

        error_logger = logging.getLogger("Error.{}".format(name))

        callback_args = {
            "scheduler": {"count": 1, "signature": "f(self, kwargs)"},
            "state": {"count": 5, "signature": "f(self, entity, attribute, old, new, kwargs)"},
            "event": {"count": 3, "signature": "f(self, event, data, kwargs)"},
            "log_event": {"count": 6, "signature": "f(self, name, ts, level, type, message, kwargs)"},
            "initialize": {"count": 0, "signature": "initialize()"},
            "terminate": {"count": 0, "signature": "terminate()"},
        }

        try:
            sig = inspect.signature(funcref)

            if type in callback_args:
                if len(sig.parameters) != callback_args[type]["count"]:
                    self.logger.warning(
                        "Suspect incorrect signature type for callback %s() in %s, should be %s - discarding",
                        funcref.__name__,
                        name,
                        callback_args[type]["signature"],
                    )
                error_logger = logging.getLogger("Error.{}".format(name))
                error_logger.warning("-" * 60)
                error_logger.warning("Unexpected error in worker for App %s:", name)
                error_logger.warning("Worker Ags: %s", args)
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
            error_logger.warning("-" * 60)
            error_logger.warning("Unexpected error validating callback format in %s, for App=%s", funcref, name)
            error_logger.warning("-" * 60)
            error_logger.warning(traceback.format_exc())
            error_logger.warning("-" * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning(
                    "Logged an error to %s", self.AD.logging.get_filename("error_log"),
                )
