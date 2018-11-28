import datetime
import pytz
import sys

import logging
from logging.handlers import RotatingFileHandler
from logging import StreamHandler

class LogSubscriptionHandler(StreamHandler):
    def __init__(self, ad, type):
        StreamHandler.__init__(self)
        self.AD = ad
        self.type = type

    def emit(self, record):
        msg = self.format(record)
        if self.AD is not None and self.AD.callbacks is not None and self.AD.events is not None:
            # Need to check if this log callback belongs to an app that is accepting log events
            # If so, don't generate the event to avoid loops
            has_log_callback = False
            with self.AD.callbacks.callbacks_lock:
                for callback in self.AD.callbacks.callbacks:
                    for uuid in self.AD.callbacks.callbacks[callback]:
                        cb = self.AD.callbacks.callbacks[callback][uuid]
                        if cb["name"] == self.name and cb["type"] == "event" and cb["event"] == "__AD_LOG_EVENT":
                            has_log_callback = True

            if has_log_callback is False:
                self.AD.events.process_event("global", {"event_type": "__AD_LOG_EVENT",
                                              "data": {
                                                  "level": self.level,
                                                  "app_name": record.name,
                                                  "message": msg,
                                                  "type": self.type
                                              }})


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
        else:
            logfile = config['log'].get("logfile", "STDOUT")
            errorfile = config['log'].get("errorfile", "STDERR")
            diagfile = config['log'].get("diagfile", "NONE")
            if diagfile == "NONE":
                diagfile = logfile
            log_size = config['log'].get("log_size", 1000000)
            log_generations = config['log'].get("log_generations", 3)
            accessfile = config['log'].get("accessfile")

        self.log_level = debug
        self.logger = logging.getLogger("AppDaemon")
        numeric_level = getattr(logging, debug, None)
        self.logger.setLevel(numeric_level)
        self.logger.propagate = False

        log_fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
        log_fmt.formatTime = self.get_time
        diag_format = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        fh = None
        if logfile != "STDOUT":
            fh = RotatingFileHandler(logfile, maxBytes=log_size, backupCount=log_generations)
            fh.setFormatter(log_fmt)
            self.logger.addHandler(fh)
        else:
            # Default for StreamHandler() is sys.stderr
            ch = logging.StreamHandler(stream=sys.stdout)
            ch.setFormatter(log_fmt)
            self.logger.addHandler(ch)

        # Setup compile output

        self.error = logging.getLogger("Error")
        numeric_level = getattr(logging, debug, None)
        self.error.setLevel(numeric_level)
        self.error.propagate = False

        if errorfile != "STDERR":
            efh = RotatingFileHandler(
                errorfile, maxBytes=log_size, backupCount=log_generations
            )
        else:
            efh = logging.StreamHandler()

        efh.setFormatter(log_fmt)
        self.error.addHandler(efh)

        # setup diag output

        self.diagnostic = logging.getLogger("Diag")
        numeric_level = getattr(logging, debug, None)
        self.diagnostic.setLevel(numeric_level)
        self.diagnostic.propagate = False

        if diagfile != "STDOUT":
            dfh = RotatingFileHandler(
                diagfile, maxBytes=log_size, backupCount=log_generations
            )
        else:
            dfh = logging.StreamHandler()

        dfh.setFormatter(diag_format)
        self.diagnostic.addHandler(dfh)

        # Setup dash output
        if accessfile is not None:
            self.acc = logging.getLogger("Access")
            numeric_level = getattr(logging, debug, None)
            self.acc.setLevel(numeric_level)
            self.acc.propagate = False
            efh = RotatingFileHandler(
                config['log'].get("accessfile"), maxBytes=log_size, backupCount=log_generations
            )

            efh.setFormatter(diag_format)
            self.acc.addHandler(efh)
        else:
            self.acc = self.logger

        # Log Subscriptions

        self.logger.addHandler(LogSubscriptionHandler(self.AD, ""))


    def get_time(logger, record, format=None):
        if logger.AD is not None and logger.AD.sched is not None and not logger.AD.sched.is_realtime():
            ts = logger.AD.sched.get_now().astimezone(logger.tz)
        else:
            if logger.tz is not None:
                ts = pytz.utc.localize(datetime.datetime.utcnow()).astimezone(logger.tz)
            else:
                ts = datetime.datetime.now()

        return str(ts)

    def set_tz(self, tz):
        self.tz = tz

    def register_ad(self, ad):
        self.AD = ad
        self.logger.AD = ad
        self.error.AD = ad
        self.diagnostic.AD = ad
        self.acc.AD = ad

    def _log(self, logger, level, message, name, ascii_encode):
        if level == "INFO":
            self.logger.info(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)
        elif level == "DEBUG":
            self.logger.debug(message)
        else:
            self.logger.log(self.log_levels[level], message)

        #if level != "DEBUG":
        #    self.process_log_callback(level, message, name, ts, "log")

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


