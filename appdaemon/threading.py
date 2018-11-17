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

class Threading:

    def __init__(self, ad, kwargs):

        self.AD = ad

        self.thread_info = {}
        self.thread_info_lock = threading.RLock()

        self.thread_info["max_used"] = 0
        self.thread_info["max_used_time"] = 0
        self.thread_info["threads"] = {}
        self.thread_info["current_busy"] = 0
        self.thread_info["max_busy"] = 0
        self.thread_info["max_busy_time"] = 0
        self.thread_info["last_action_time"] = 0

        self.auto_pin = True

        if "threads" in kwargs:
            self.AD.log("WARNING",
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

        self.AD.log("INFO", "Starting Apps with {} workers and {} pins".format(self.total_threads, self.pin_threads))

        self.next_thread = self.pin_threads

    def create_initial_threads(self):
        self.threads = 0
        for i in range(self.total_threads):
            self.add_thread(True)

    def get_q(self, thread_id):
        return self.thread_info["threads"][thread_id]["q"]

    def add_thread(self, silent=False):
        id = self.threads
        if silent is False:
            self.AD.log("INFO", "Adding thread {}".format(id))
        t = threading.Thread(target=self.worker)
        t.daemon = True
        t.setName("thread-{}".format(id))
        with self.thread_info_lock:
            self.thread_info["threads"][t.getName()] = \
                {"callback": "idle",
                 "time_called": 0,
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
        self.AD.diag("INFO", "--------------------------------------------------")
        self.AD.diag("INFO", "Threads")
        self.AD.diag("INFO", "--------------------------------------------------")
        max_ts = datetime.datetime.fromtimestamp(thread_info["max_busy_time"])
        last_ts = datetime.datetime.fromtimestamp(thread_info["last_action_time"])
        self.AD.diag("INFO", "Currently busy threads: {}".format(thread_info["current_busy"]))
        self.AD.diag("INFO", "Most used threads: {} at {}".format(thread_info["max_busy"], max_ts))
        self.AD.diag("INFO", "Last activity: {}".format(last_ts))
        self.AD.diag("INFO", "Total Q Entries: {}".format(qinfo["qsize"]))
        self.AD.diag("INFO", "--------------------------------------------------")
        for thread in sorted(thread_info["threads"], key=self.natural_keys):
            ts = datetime.datetime.fromtimestamp(thread_info["threads"][thread]["time_called"])
            self.AD.diag("INFO",
                     "{} - qsize: {} | current callback: {} | since {}, | alive: {}, | pinned apps: {}".format(
                         thread,
                         thread_info["threads"][thread]["qsize"],
                         thread_info["threads"][thread]["callback"],
                         ts,
                         thread_info["threads"][thread]["is_alive"],
                         self.AD.get_pinned_apps(thread)
                     ))
        self.AD.diag("INFO", "--------------------------------------------------")

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
                self.AD.log("WARNING", "Invalid thread ID for pinned thread in app: {} - assigning to thread 0".format(args["name"]))
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
        if self.AD.thread_duration_warning_threshold != 0:
            for thread_id in self.thread_info["threads"]:
                if self.thread_info["threads"][thread_id]["callback"] != "idle":
                    start = self.thread_info["threads"][thread_id]["time_called"]
                    dur = self.AD.sched.get_now_ts() - start
                    if dur >= self.AD.thread_duration_warning_threshold and dur % self.AD.thread_duration_warning_threshold == 0:
                        self.AD.log("WARNING", "Excessive time spent in callback: {} - {}s".format
                        (self.thread_info["threads"][thread_id]["callback"], dur))

    def check_q_size(self, warning_step):
        qinfo = self.q_info()
        if qinfo["qsize"] > self.AD.qsize_warning_threshold:
            if warning_step == 0:
                self.AD.log("WARNING", "Queue size is {}, suspect thread starvation".format(qinfo["qsize"]))
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
                self.AD.diag("INFO",
                         "{} done".format(thread_id, type, callback))
            else:
                self.AD.diag("INFO",
                         "{} calling {} callback {}".format(thread_id, type, callback))

        with self.thread_info_lock:
            ts = self.AD.sched.get_now_ts()
            if callback == "idle":
                start = self.thread_info["threads"][thread_id]["time_called"]
                if ts - start >= self.AD.thread_duration_warning_threshold:
                    self.AD.log("WARNING", "callback {} has now completed".format(self.thread_info["threads"][thread_id]["callback"]))
            self.thread_info["threads"][thread_id]["callback"] = callback
            self.thread_info["threads"][thread_id]["time_called"] = ts
            if callback == "idle":
                self.thread_info["current_busy"] -= 1
            else:
                self.thread_info["current_busy"] += 1

            if self.thread_info["current_busy"] > self.thread_info["max_busy"]:
                self.thread_info["max_busy"] = self.thread_info["current_busy"]
                self.thread_info["max_busy_time"] = ts

            self.thread_info["last_action_time"] = ts

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
                self.log("WARNING", "Invalid value for pin_thread ({}) in app: {} - discarding callback".format(kwargs["pin_thread"], name))
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
            if not self.AD.sched.now_is_between(start_time, end_time, name):
                unconstrained = False

        return unconstrained


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
                                    self.AD.sanitize_state_kwargs(app, args["kwargs"]))
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
                    self.AD.err("WARNING", '-' * 60, name=name)
                    self.AD.err("WARNING", "Unexpected error in worker for App {}:".format(name), name=name)
                    self.AD.err("WARNING", "Worker Ags: {}".format(args), name=name)
                    self.AD.err("WARNING", '-' * 60, name=name)
                    self.AD.err("WARNING", traceback.format_exc(), name=name)
                    self.AD.err("WARNING", '-' * 60, name=name)
                    if self.AD.errfile != "STDERR" and self.AD.logfile != "STDOUT":
                        self.AD.log("WARNING", "Logged an error to {}".format(self.AD.errfile), name=name)
                finally:
                    self.update_thread_info(thread_id, "idle")
            else:
                self.AD.log("WARNING", "Found stale callback for {} - discarding".format(name), name=name)

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
                self.AD.log("WARNING", "Incorrect signature type for callback {}(), should be {} - discarding".format(funcref.__name__, callback_args[type]["signature"]), name=name)
                return False
            else:
                return True
        else:
            self.AD.log("ERROR", "Unknown callback type: {}".format(type), name=name)

        return False
