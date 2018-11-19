import datetime
import pytz
import sys

import logging
from logging.handlers import RotatingFileHandler


class Logging:

    log_levels = {
        "CRITICAL": 50,
        "ERROR": 40,
        "WARNING": 30,
        "INFO": 20,
        "DEBUG": 10,
        "NOTSET": 0
    }

    def __init__(self, config, debug):

        self.AD = None
        self.tz = None

        if "log" not in config:
            logfile = "STDOUT"
            errorfile = "STDERR"
            diagfile = "STDOUT"
            log_size = 1000000
            log_generations = 3
            accessfile = None
            self.log_level = debug
        else:
            logfile = config['log'].get("logfile", "STDOUT")
            errorfile = config['log'].get("errorfile", "STDERR")
            diagfile = config['log'].get("diagfile", "NONE")
            if diagfile == "NONE":
                diagfile = logfile
            log_size = config['log'].get("log_size", 1000000)
            log_generations = config['log'].get("log_generations", 3)
            accessfile = config['log'].get("accessfile")

        self.logger = logging.getLogger("log1")
        numeric_level = getattr(logging, debug, None)
        self.logger.setLevel(numeric_level)
        self.logger.propagate = False
        # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        # Send to file if we are daemonizing, else send to console

        fh = None
        if logfile != "STDOUT":
            fh = RotatingFileHandler(logfile, maxBytes=log_size, backupCount=log_generations)
            fh.setLevel(numeric_level)
            # fh.setFormatter(formatter)
            self.logger.addHandler(fh)
        else:
            # Default for StreamHandler() is sys.stderr
            ch = logging.StreamHandler(stream=sys.stdout)
            ch.setLevel(numeric_level)
            # ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        # Setup compile output

        self.error = logging.getLogger("log2")
        numeric_level = getattr(logging, debug, None)
        self.error.setLevel(numeric_level)
        self.error.propagate = False
        # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        if errorfile != "STDERR":
            efh = RotatingFileHandler(
                errorfile, maxBytes=log_size, backupCount=log_generations
            )
        else:
            efh = logging.StreamHandler()

        efh.setLevel(numeric_level)
        # efh.setFormatter(formatter)
        self.error.addHandler(efh)

        # setup diag output

        self.diagnostic = logging.getLogger("log3")
        numeric_level = getattr(logging, debug, None)
        self.diagnostic.setLevel(numeric_level)
        self.diagnostic.propagate = False
        # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        if diagfile != "STDOUT":
            dfh = RotatingFileHandler(
                diagfile, maxBytes=log_size, backupCount=log_generations
            )
        else:
            dfh = logging.StreamHandler()

        dfh.setLevel(numeric_level)
        # dfh.setFormatter(formatter)
        self.diagnostic.addHandler(dfh)

        # Setup dash output
        if accessfile is not None:
            self.acc = logging.getLogger("log4")
            numeric_level = getattr(logging, debug, None)
            self.acc.setLevel(numeric_level)
            self.acc.propagate = False
            # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
            efh = RotatingFileHandler(
                config['log'].get("accessfile"), maxBytes=log_size, backupCount=log_generations
            )

            efh.setLevel(numeric_level)
            # efh.setFormatter(formatter)
            self.acc.addHandler(efh)
        else:
            self.access = self.logger

    def set_tz(self, tz):
        self.tz = tz

    def register_ad(self, ad):
        self.AD = ad

    def _log(self, logger, level, message, name, ascii_encode):
        if self.AD is not None and self.AD.sched is not None and not self.AD.sched.is_realtime():
            ts = self.AD.sched.get_now()
        elif self.tz is not None:
            ts = pytz.utc.localize(datetime.datetime.utcnow()).astimezone(self.tz)
        else:
            ts = datetime.datetime.now()

        name = " {}:".format(name)

        if ascii_encode is True:
            safe_enc = lambda s: str(s).encode("utf-8", "replace").decode("ascii", "replace")
            name = safe_enc(name)
            message = safe_enc(message)

        logger.log(self.log_levels[level], "{} {}{} {}".format(ts, level, name, message))

        if level != "DEBUG":
            self.process_log_callback(level, message, name, ts, "log")

    def log(self, level, message, name="AppDaemon", ascii_encode=True):
        self._log(self.logger, level, message, name, ascii_encode)

    def err(self, level, message, name="AppDaemon", ascii_encode=True):
        self._log(self.error, level, message, name, ascii_encode)

    def diag(self, level, message, name="AppDaemon", ascii_encode=True):
        self._log(self.diagnostic, level, message, name, ascii_encode)

    def access(self, level, message, name="AppDaemon", ascii_encode=True):
        self._log(self.acc, level, message, name, ascii_encode)

    def get_error(self):
        return self.error

    def get_logger(self):
        return self.logger

    def get_access(self):
        return self.acc

    def get_diag(self):
        return self.error

    def process_log_callback(self, level, message, name, ts, type):
        if self.AD is not None and self.AD.callbacks is not None and self.AD.events is not None:
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
        if self.AD.events is not None:
            # Add a separate callback for each log level
            handle = []
            for thislevel in self.log_levels:
                if self.log_levels[thislevel] >= self.log_levels[level] :
                    handle.append(self.AD.events.add_event_callback(name, namespace, cb, "__AD_LOG_EVENT", level=thislevel, **kwargs))

            return handle

    def cancel_log_callback(self, name, handle):
        if self.AD.events is not None:
            for h in handle:
                self.AD.events.cancel_event_callback(name, h)


