import datetime

import appdaemon.utils as utils

class Logging:

    def __init__(self, ad):

        self.AD = ad

    def log(self, level, message, name="AppDaemon"):
        if self.AD.sched is not None and not self.AD.sched.is_realtime():
            ts = self.AD.sched.get_now_ts()
        else:
            ts = datetime.datetime.now()
        utils.log(self.AD.logger, level, message, name, ts)

        if level != "DEBUG":
            self.process_log_callback(level, message, name, ts, "log")

    def err(self, level, message, name="AppDaemon"):
        if self.AD.sched is not None and not self.AD.sched.is_realtime():
            ts = self.AD.sched.get_now_ts()
        else:
            ts = datetime.datetime.now()
        utils.log(self.AD.error, level, message, name, ts)

        if level != "DEBUG":
            self.process_log_callback(level, message, name, ts, "error")

    def diag(self, level, message, name="AppDaemon"):
        if self.AD.sched is not None and not self.AD.sched.is_realtime():
            ts = self.AD.sched.get_now_ts()
        else:
            ts = None
        utils.log(self.AD.diagnostic, level, message, name, ts)

        if level != "DEBUG":
            self.process_log_callback(level, message, name, ts, "diag")

    def process_log_callback(self, level, message, name, ts, type):
        # Need to check if this log callback belongs to an app that is accepting log events
        # If so, don't generate the event to avoid loops
        has_log_callback = False
        with self.AD.callbacks.callbacks_lock:
            for callback in self.AD.callbacks.callbacks:
                for uuid in self.AD.callbacks.callbacks[callback]:
                    cb = self.AD.callbacks.callbacks[callback][uuid]
                    if cb["name"] == name and cb["type"] == "event" and cb["event"] == "__AD_LOG_EVENT":
                        has_log_callback = True

        if has_log_callback is False:
            self.AD.events.process_event("global", {"event_type": "__AD_LOG_EVENT",
                                          "data": {
                                              "level": level,
                                              "app_name": name,
                                              "message": message,
                                              "ts": ts,
                                              "type": type
                                          }})

    def add_log_callback(self, namespace, name, cb, level, **kwargs):
        # Add a separate callback for each log level
        handle = []
        for thislevel in utils.log_levels:
            if utils.log_levels[thislevel] >= utils.log_levels[level] :
                handle.append(self.AD.events.add_event_callback(name, namespace, cb, "__AD_LOG_EVENT", level=thislevel, **kwargs))

        return handle

    def cancel_log_callback(self, name, handle):
        for h in handle:
            self.AD.events.cancel_event_callback(name, h)


