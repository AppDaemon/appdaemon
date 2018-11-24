import threading
import datetime
from copy import copy
from queue import Queue
from random import randint
import re
import sys
import traceback
import inspect

from appdaemon import utils as utils
from appdaemon.appdaemon import AppDaemon

class Threading:

    def __init__(self, ad: AppDaemon, kwargs):

        self.AD = ad

        self.thread_info = {}
        self.thread_info_lock = threading.RLock()

        self.thread_info["max_used"] = 0
        self.thread_info["max_used_time"] = 0
        self.thread_info["threads"] = {}
        self.thread_info["current_busy"] = 0
        self.thread_info["max_busy"] = 0
        self.thread_info["max_busy_time"] = 0
        # Scheduler isn;t setup so we can't get an accurate localized time
        self.thread_info["last_action_time"] = datetime.datetime.now()

        self.auto_pin = True

        self.total_callbacks_fired = 0
        self.total_callbacks_executed = 0
        self.current_callbacks_fired = 0
        self.current_callbacks_executed = 0
        self.last_stats_time = datetime.datetime.now()
        self.callback_list = []

        if "threads" in kwargs:
            self.AD.logging.log("WARNING",
                     "Threads directive is deprecated apps - will be pinned. Use total_threads if you want to unpin your apps")

        if "total_threads" in kwargs:
            self.total_threads = kwargs["total_threads"]
            self.auto_pin = False
        else:
            self.total_threads = int(self.AD.app_management.check_config(True, False)["total"])

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
            raise ValueError("pin_threads cannot be > threads")

        if self.pin_threads < 0:
            raise ValueError("pin_threads cannot be < 0")

        self.AD.logging.log("INFO", "Starting Apps with {} workers and {} pins".format(self.total_threads, self.pin_threads))

        self.next_thread = self.pin_threads

    def get_callback_info(self):
        now = datetime.datetime.now()
        self.callback_list.append(
            {
                "fired": self.current_callbacks_fired,
                "executed": self.current_callbacks_executed,
                "ts": now
            })

        if len(self.callback_list) > 10:
            self.callback_list.pop(0)

        fired_sum = 0
        executed_sum = 0
        for item in self.callback_list:
            fired_sum += item["fired"]
            executed_sum += item["executed"]

        total_duration = (self.callback_list[len(self.callback_list) -1]["ts"] - self.callback_list[0]["ts"]).total_seconds()

        if total_duration == 0:
            fired_avg = 0
            executed_avg = 0
        else:
            fired_avg = round(fired_sum / total_duration, 1)
            executed_avg = round(executed_sum / total_duration, 1)

        stats = \
        {
            "total_callbacks_executed": self.total_callbacks_executed,
            "total_callbacks_fired": self.total_callbacks_fired,
            "avg_callbacks_executed_per_sec": fired_avg,
            "avg_callbacks_fired_per_sec": executed_avg,
        }

        self.last_stats_time = now
        self.current_callbacks_executed = 0
        self.current_callbacks_fired = 0

        return stats

    def create_initial_threads(self):
        self.threads = 0
        for i in range(self.total_threads):
            self.add_thread(True)

    def get_q(self, thread_id):
        return self.thread_info["threads"][thread_id]["q"]

    def add_thread(self, silent=False):
        id = self.threads
        if silent is False:
            self.AD.logging.log("INFO", "Adding thread {}".format(id))
        t = threading.Thread(target=self.worker)
        t.daemon = True
        t.setName("thread-{}".format(id))
        with self.thread_info_lock:
            self.thread_info["threads"][t.getName()] = \
                {"callback": "idle",
                 "time_called": datetime.datetime.now(),
                 "q": Queue(maxsize=0),
                 "id": id,
                 "thread": t}
        t.start()
        self.threads += 1

    @staticmethod
    def atoi(text):
        return int(text) if text.isdigit() else text

    def natural_keys(self, text):
        return [self.atoi(c) for c in re.split('(\d+)', text)]

    # Diagnostics

    def q_info(self):
        qsize = 0
        with self.thread_info_lock:
            thread_info = self.get_thread_info()

        for thread in thread_info["threads"]:
            qsize += self.thread_info["threads"][thread]["q"].qsize()
        return {"qsize": qsize, "thread_info": thread_info}

    def min_q_id(self):
        id = 0
        i = 0
        qsize = sys.maxsize
        with self.thread_info_lock:
            for thread in self.thread_info["threads"]:
                if self.thread_info["threads"][thread]["q"].qsize() < qsize:
                    qsize = self.thread_info["threads"][thread]["q"].qsize()
                    id = i
                i += 1
        return id

    def get_thread_info(self):
        info = {}
        # Make a copy without the thread objects
        with self.thread_info_lock:
            info["max_busy_time"] = copy(self.thread_info["max_busy_time"])
            info["last_action_time"] = copy(self.thread_info["last_action_time"])
            info["current_busy"] = copy(self.thread_info["current_busy"])
            info["max_busy"] = copy(self.thread_info["max_busy"])
            info["threads"] = {}
            for thread in self.thread_info["threads"]:
                if thread not in info["threads"]:
                    info["threads"][thread] = {}
                info["threads"][thread]["time_called"] = copy(self.thread_info["threads"][thread]["time_called"])
                info["threads"][thread]["callback"] = copy(self.thread_info["threads"][thread]["callback"])
                info["threads"][thread]["is_alive"] = copy(self.thread_info["threads"][thread]["thread"].is_alive())
                info["threads"][thread]["pinned_apps"] = copy(self.get_pinned_apps(thread))
                info["threads"][thread]["qsize"] = copy(self.thread_info["threads"][thread]["q"].qsize())
        return info

    def dump_threads(self, qinfo):
        thread_info = qinfo["thread_info"]
        self.AD.logging.diag("INFO", "--------------------------------------------------")
        self.AD.logging.diag("INFO", "Threads")
        self.AD.logging.diag("INFO", "--------------------------------------------------")
        max_ts = thread_info["max_busy_time"]
        last_ts = thread_info["last_action_time"]
        self.AD.logging.diag("INFO", "Currently busy threads: {}".format(thread_info["current_busy"]))
        self.AD.logging.diag("INFO", "Most used threads: {} at {}".format(thread_info["max_busy"], max_ts))
        self.AD.logging.diag("INFO", "Last activity: {}".format(last_ts))
        self.AD.logging.diag("INFO", "Total Q Entries: {}".format(qinfo["qsize"]))
        self.AD.logging.diag("INFO", "--------------------------------------------------")
        for thread in sorted(thread_info["threads"], key=self.natural_keys):
            self.AD.logging.diag("INFO",
                     "{} - qsize: {} | current callback: {} | since {}, | alive: {}, | pinned apps: {}".format(
                         thread,
                         thread_info["threads"][thread]["qsize"],
                         thread_info["threads"][thread]["callback"],
                         thread_info["threads"][thread]["time_called"],
                         thread_info["threads"][thread]["is_alive"],
                         self.AD.threading.get_pinned_apps(thread)
                     ))
        self.AD.logging.diag("INFO", "--------------------------------------------------")

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
                self.AD.logging.log("WARNING", "Invalid thread ID for pinned thread in app: {} - assigning to thread 0".format(args["name"]))
                thread = 0
        else:
            if self.threads == self.pin_threads:
                raise ValueError("pin_threads must be set lower than threads if unpinned_apps are in use")
            if self.AD.load_distribution == "load":
                thread = self.min_q_id()
            elif self.AD.load_distribution == "random":
                thread = randint(self.pin_threads, self.threads - 1)
            else:
                # Round Robin is the catch all
                thread = self.next_thread
                self.next_thread += 1
                if self.next_thread == self.threads:
                    self.next_thread = self.pin_threads

        if thread < 0 or thread >= self.threads:
            raise ValueError("invalid thread id: {} in app {}".format(thread, args["name"]))

        with self.thread_info_lock:
            id = "thread-{}".format(thread)
            q = self.thread_info["threads"][id]["q"]
            q.put_nowait(args)

    def check_overdue_threads(self):
        if self.AD.sched.realtime is True and self.AD.thread_duration_warning_threshold != 0:
            for thread_id in self.thread_info["threads"]:
                if self.thread_info["threads"][thread_id]["callback"] != "idle":
                    start = self.thread_info["threads"][thread_id]["time_called"]
                    dur = (self.AD.sched.get_now() - start).total_seconds()
                    if dur >= self.AD.thread_duration_warning_threshold and dur % self.AD.thread_duration_warning_threshold == 0:
                        self.AD.logging.log("WARNING", "Excessive time spent in callback: {} - {}s".format
                        (self.thread_info["threads"][thread_id]["callback"], dur))

    def check_q_size(self, warning_step):
        qinfo = self.q_info()
        if qinfo["qsize"] > self.AD.qsize_warning_threshold:
            if warning_step == 0:
                self.AD.logging.log("WARNING", "Queue size is {}, suspect thread starvation".format(qinfo["qsize"]))
                self.dump_threads(qinfo)
            warning_step += 1
            if warning_step >= self.AD.qsize_warning_step:
                warning_step = 0
        else:
            warning_step = 0

        return warning_step

    def update_thread_info(self, thread_id, callback, type = None):

        if self.AD.log_thread_actions:
            if callback == "idle":
                self.AD.logging.diag("INFO",
                         "{} done".format(thread_id, type, callback))
            else:
                self.AD.logging.diag("INFO",
                         "{} calling {} callback {}".format(thread_id, type, callback))

        with self.thread_info_lock:
            now = self.AD.sched.get_now()
            if callback == "idle":
                start = self.thread_info["threads"][thread_id]["time_called"]
                if self.AD.sched.realtime is True and (now - start).total_seconds() >= self.AD.thread_duration_warning_threshold:
                    self.AD.logging.log("WARNING", "callback {} has now completed".format(self.thread_info["threads"][thread_id]["callback"]))
            self.thread_info["threads"][thread_id]["callback"] = callback
            self.thread_info["threads"][thread_id]["time_called"] = now
            if callback == "idle":
                self.thread_info["current_busy"] -= 1
            else:
                self.thread_info["current_busy"] += 1

            if self.thread_info["current_busy"] > self.thread_info["max_busy"]:
                self.thread_info["max_busy"] = self.thread_info["current_busy"]
                self.thread_info["max_busy_time"] = self.AD.sched.get_now()

            self.thread_info["last_action_time"] = self.AD.sched.get_now()

    #
    # Pinning
    #

    def calculate_pin_threads(self):

        if self.pin_threads == 0:
            return

        thread_pins = [0] * self.pin_threads
        with self.AD.app_management.objects_lock:
            for name in self.AD.app_management.objects:
                # Looking for apps that already have a thread pin value
                if self.get_app_pin(name) and self.get_pin_thread(name) != -1:
                    thread = self.get_pin_thread(name)
                    if thread >= self.threads:
                        raise ValueError("Pinned thread out of range - check apps.yaml for 'pin_thread' or app code for 'set_pin_thread()'")
                    # Ignore anything outside the pin range as it will have been set by the user
                    if thread < self.pin_threads:
                        thread_pins[thread] += 1

            # Now we know the numbers, go fill in the gaps

            for name in self.AD.app_management.objects:
                if self.get_app_pin(name) and self.get_pin_thread(name) == -1:
                    thread = thread_pins.index(min(thread_pins))
                    self.set_pin_thread(name, thread)
                    thread_pins[thread] += 1

    def app_should_be_pinned(self, name):
        # Check apps.yaml first - allow override
        app = self.AD.app_management.app_config[name]
        if "pin_app" in app:
            return app["pin_app"]

        # if not, go with the global default
        return self.pin_apps

    def get_app_pin(self, name):
        with self.AD.app_management.objects_lock:
            return self.AD.app_management.objects[name]["pin_app"]

    def set_app_pin(self, name, pin):
        with self.AD.app_management.objects_lock:
            self.AD.app_management.objects[name]["pin_app"] = pin
        if pin is True:
            # May need to set this app up with a pinned thread
            self.calculate_pin_threads()

    def get_pin_thread(self, name):
        with self.AD.app_management.objects_lock:
            return self.AD.app_management.objects[name]["pin_thread"]

    def set_pin_thread(self, name, thread):
        with self.AD.app_management.objects_lock:
            self.AD.app_management.objects[name]["pin_thread"] = thread

    def validate_pin(self, name, kwargs):
        if "pin_thread" in kwargs:
            if kwargs["pin_thread"] < 0 or kwargs["pin_thread"] >= self.threads:
                self.AD.logging.log("WARNING", "Invalid value for pin_thread ({}) in app: {} - discarding callback".format(kwargs["pin_thread"], name))
                return False
        else:
            return True


    def get_pinned_apps(self, thread):
        id = int(thread.split("-")[1])
        apps = []
        with self.AD.app_management.objects_lock:
            for obj in self.AD.app_management.objects:
                if self.AD.app_management.objects[obj]["pin_thread"] == id:
                    apps.append(obj)
        return apps

    #
    # Constraints
    #

    def check_constraint(self, key, value, app):
        unconstrained = True
        if key in app.list_constraints():
            method = getattr(app, key)
            unconstrained = method(value)

        return unconstrained

    def check_time_constraint(self, args, name):
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
            if self.AD.sched.now_is_between(start_time, end_time, name) is False:
                unconstrained = False

        return unconstrained

    #
    # Workers
    #

    def check_and_dispatch_state(self, name, funcref, entity, attribute, new_state,
                                 old_state, cold, cnew, kwargs, uuid_, pin_app, pin_thread):
        executed = False
        kwargs["handle"] = uuid_
        if attribute == "all":
            with self.AD.app_management.objects_lock:
                executed = self.dispatch_worker(name, {
                    "name": name,
                    "id": self.AD.app_management.objects[name]["id"],
                    "type": "attr",
                    "function": funcref,
                    "attribute": attribute,
                    "entity": entity,
                    "new_state": new_state,
                    "old_state": old_state,
                    "pin_app": pin_app,
                    "pin_thread": pin_thread,
                    "kwargs": kwargs,
                })
        else:
            if old_state is None:
                old = None
            else:
                if attribute in old_state:
                    old = old_state[attribute]
                elif 'attributes' in old_state and attribute in old_state['attributes']:
                    old = old_state['attributes'][attribute]
                else:
                    old = None
            if new_state is None:
                new = None
            else:
                if attribute in new_state:
                    new = new_state[attribute]
                elif 'attributes' in new_state and attribute in new_state['attributes']:
                    new = new_state['attributes'][attribute]
                else:
                    new = None

            if (cold is None or cold == old) and (cnew is None or cnew == new):
                if "duration" in kwargs:
                    # Set a timer
                    exec_time = self.AD.sched.get_now_ts() + int(kwargs["duration"])
                    kwargs["__duration"] = self.AD.sched.insert_schedule(
                        name, exec_time, funcref, False, None,
                        __entity=entity,
                        __attribute=attribute,
                        __old_state=old,
                        __new_state=new, **kwargs
                    )
                else:
                    # Do it now
                    with self.AD.app_management.objects_lock:
                        executed = self.dispatch_worker(name, {
                            "name": name,
                            "id": self.AD.app_management.objects[name]["id"],
                            "type": "attr",
                            "function": funcref,
                            "attribute": attribute,
                            "entity": entity,
                            "new_state": new,
                            "old_state": old,
                            "pin_app": pin_app,
                            "pin_thread": pin_thread,
                            "kwargs": kwargs
                        })
            else:
                if "__duration" in kwargs:
                    # cancel timer
                    self.AD.sched.cancel_timer(name, kwargs["__duration"])

        return executed

    def dispatch_worker(self, name, args):
        with self.AD.app_management.objects_lock:
            unconstrained = True
            #
            # Argument Constraints
            #
            for arg in self.AD.app_management.app_config[name].keys():
                constrained = self.check_constraint(arg, self.AD.app_management.app_config[name][arg], self.AD.app_management.objects[name]["object"])
                if not constrained:
                    unconstrained = False
            if not self.check_time_constraint(self.AD.app_management.app_config[name], name):
                unconstrained = False
            #
            # Callback level constraints
            #
            if "kwargs" in args:
                for arg in args["kwargs"].keys():
                    constrained = self.check_constraint(arg, args["kwargs"][arg], self.AD.app_management.objects[name]["object"])
                    if not constrained:
                        unconstrained = False
                if not self.check_time_constraint(args["kwargs"], name):
                    unconstrained = False

        if unconstrained:
            #
            # It's gonna happen - so lets update stats
            #
            self.total_callbacks_fired += 1
            self.current_callbacks_fired += 1
            #
            # And Q
            #
            self.select_q(args)
            return True
        else:
            return False

    # noinspection PyBroadException
    def worker(self):
        thread_id = threading.current_thread().name
        q = self.get_q(thread_id)
        while True:
            args = q.get()
            _type = args["type"]
            funcref = args["function"]
            _id = args["id"]
            name = args["name"]
            args["kwargs"]["__thread_id"] = thread_id
            callback = "{}() in {}".format(funcref.__name__, name)
            app = None
            with self.AD.app_management.objects_lock:
                if name in self.AD.app_management.objects and self.AD.app_management.objects[name]["id"] == _id:
                    app = self.AD.app_management.objects[name]["object"]
            if app is not None:
                try:
                    if _type == "timer":
                        if self.validate_callback_sig(name, "timer", funcref):
                            self.update_thread_info(thread_id, callback, _type)
                            funcref(self.AD.sched.sanitize_timer_kwargs(app, args["kwargs"]))
                    elif _type == "attr":
                        if self.validate_callback_sig(name, "attr", funcref):
                            entity = args["entity"]
                            attr = args["attribute"]
                            old_state = args["old_state"]
                            new_state = args["new_state"]
                            self.update_thread_info(thread_id, callback, _type)
                            funcref(entity, attr, old_state, new_state,
                                    self.AD.state.sanitize_state_kwargs(app, args["kwargs"]))
                    elif _type == "event":
                        data = args["data"]
                        if args["event"] == "__AD_LOG_EVENT":
                            if self.validate_callback_sig(name, "log_event", funcref):
                                self.update_thread_info(thread_id, callback, _type)
                                funcref(data["app_name"], data["ts"], data["level"], data["type"], data["message"], args["kwargs"])
                        else:
                            if self.validate_callback_sig(name, "event", funcref):
                                self.update_thread_info(thread_id, callback, _type)
                                funcref(args["event"], data, args["kwargs"])
                except:
                    self.AD.logging.err("WARNING", '-' * 60, name=name)
                    self.AD.logging.err("WARNING", "Unexpected error in worker for App {}:".format(name), name=name)
                    self.AD.logging.err("WARNING", "Worker Ags: {}".format(args), name=name)
                    self.AD.logging.err("WARNING", '-' * 60, name=name)
                    self.AD.logging.err("WARNING", traceback.format_exc(), name=name)
                    self.AD.logging.err("WARNING", '-' * 60, name=name)
                    if self.AD.errfile != "STDERR" and self.AD.logfile != "STDOUT":
                        self.AD.logging.log("WARNING", "Logged an error to {}".format(self.AD.errfile), name=name)
                finally:
                    self.update_thread_info(thread_id, "idle")
                    self.total_callbacks_executed += 1
                    self.current_callbacks_executed += 1

            else:
                self.AD.logging.log("WARNING", "Found stale callback for {} - discarding".format(name), name=name)

            q.task_done()

    def validate_callback_sig(self, name, type, funcref):

        callback_args = {
            "timer": {"count": 1, "signature": "f(self, kwargs)"},
            "attr": {"count": 5, "signature": "f(self, entity, attribute, old, new, kwargs)"},
            "event": {"count": 3, "signature": "f(self, event, data, kwargs)"},
            "log_event": {"count": 6, "signature": "f(self, name, ts, level, type, message, kwargs)"},
            "initialize": {"count": 0, "signature": "initialize()"}
        }

        sig = inspect.signature(funcref)

        if type in callback_args:
            if len(sig.parameters) != callback_args[type]["count"]:
                self.AD.logging.log("WARNING", "Incorrect signature type for callback {}(), should be {} - discarding".format(funcref.__name__, callback_args[type]["signature"]), name=name)
                return False
            else:
                return True
        else:
            self.AD.logging.log("ERROR", "Unknown callback type: {}".format(type), name=name)

        return False

