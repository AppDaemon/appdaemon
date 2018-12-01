import datetime
import pytz
import sys

import logging
from logging.handlers import RotatingFileHandler
from logging import StreamHandler

from appdaemon.appq import AppDaemon

class AppNameFormatter(logging.Formatter):

    """
    Logger formatter to add 'appname' as an interpolatable field
    """

    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)

    def format(self, record):
        #
        # Figure out the name of the app and add it to the LogRecord
        # Each logger is named after the app so split it out form the logger name
        #
        name = record.name
        if "." in record.name:
            loggers = record.name.split(".")
            name = loggers[len(loggers) - 1]
        record.appname = name
        return super().format(record)


class AdminHandler(StreamHandler):

    """
    Handle sending of logs to the admin interface
    """

    def __init__(self, ad: AppDaemon, type):
        StreamHandler.__init__(self)
        self.AD = ad
        self.type = type

    def emit(self, record):
        msg = self.format(record)
        if self.AD is not None and self.AD.appq is not None:
            self.AD.appq.admin_update({"log_entry": {"type": self.type, "msg": msg}})

class LogSubscriptionHandler(StreamHandler):

    """
    Handle apps that subscribe to logs
    This Handler requires that it's formatter is an instance of AppNameFormatter
    """

    def __init__(self, ad: AppDaemon):
        StreamHandler.__init__(self)
        self.AD = ad
        self.type = type

    def emit(self, record):
        if self.AD is not None and self.AD.callbacks is not None and self.AD.events is not None:
            # Need to check if this log callback belongs to an app that is accepting log events
            # If so, don't generate the event to avoid loops
            has_log_callback = False
            msg = self.format(record)
            with self.AD.callbacks.callbacks_lock:
                for callback in self.AD.callbacks.callbacks:
                    for uuid in self.AD.callbacks.callbacks[callback]:
                        cb = self.AD.callbacks.callbacks[callback][uuid]
                        if cb["name"] == record.appname and cb["type"] == "event" and cb["event"] == "__AD_LOG_EVENT":
                            has_log_callback = True

            if has_log_callback is False:
                self.AD.events.process_event("global", {"event_type": "__AD_LOG_EVENT",
                                              "data": {
                                                  "level": record.levelname,
                                                  "app_name": record.appname,
                                                  "message": msg,
                                                  "type": "log"
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

        log_format_default = '%(asctime)s %(levelname)s %(appname)s: %(message)s'
        error_format_default = '%(asctime)s %(levelname)s %(appname)s: %(message)s'
        access_format_default = '%(asctime)s %(levelname)s %(message)s'
        diag_format_default = '%(asctime)s %(levelname)s %(message)s'

        if "log" not in config:
            self.logfile = "STDOUT"
            self.errorfile = "STDERR"
            self.diagfile = "STDOUT"
            self.accessfile = None

            log_size = 1000000
            log_generations = 3
            log_format = log_format_default
            error_format = error_format_default
            access_format = access_format_default
            diag_format = diag_format_default
        else:
            self.logfile = config['log'].get("logfile", "STDOUT")
            self.errorfile = config['log'].get("errorfile", "STDERR")
            self.diagfile = config['log'].get("diagfile", "NONE")
            if self.diagfile == "NONE":
                self.diagfile = self.logfile
            log_size = config['log'].get("log_size", 1000000)
            log_generations = config['log'].get("log_generations", 3)
            self.accessfile = config['log'].get("accessfile")
            log_format = config['log'].get("log_format", log_format_default)
            error_format = config['log'].get("error_format", error_format_default)
            access_format = config['log'].get("access_format", access_format_default)
            diag_format = config['log'].get("diag_format", diag_format_default)

        self.log_level = debug
        numeric_level = getattr(logging, debug, None)
        self.log_formatter = AppNameFormatter(log_format)
        #
        # Add a time formatter that understands time travel and formats the log correctly
        #
        self.log_formatter.formatTime = self.get_time

        self.error_formatter = AppNameFormatter(error_format)
        self.error_formatter.formatTime = self.get_time

        self.access_formatter = AppNameFormatter(access_format)
        self.access_formatter.formatTime = self.get_time

        self.diag_formatter = AppNameFormatter(diag_format)
        self.diag_formatter.formatTime = self.get_time

        self.logger = logging.getLogger("AppDaemon")
        self.logger.setLevel(numeric_level)
        self.logger.propagate = False
        if self.logfile != "STDOUT":
            fh = RotatingFileHandler(self.logfile, maxBytes=log_size, backupCount=log_generations)
        else:
            fh = logging.StreamHandler(stream=sys.stdout)

        fh.setFormatter(self.log_formatter)
        self.logger.addHandler(fh)
        self.log_filehandler = fh

        # Setup compile output

        self.error = logging.getLogger("Error")
        self.error.setLevel(numeric_level)
        self.error.propagate = False
        if self.errorfile != "STDERR":
            efh = RotatingFileHandler(
                self.errorfile, maxBytes=log_size, backupCount=log_generations)
        else:
            efh = logging.StreamHandler()

        efh.setFormatter(self.error_formatter)
        self.error.addHandler(efh)
        self.error_filehandler = efh

        # setup diag output

        self.diagnostic = logging.getLogger("Diag")
        self.diagnostic.setLevel(numeric_level)
        self.diagnostic.propagate = False
        if self.diagfile != "STDOUT":
            dfh = RotatingFileHandler(
                self.diagfile, maxBytes=log_size, backupCount=log_generations
            )
        else:
            dfh = logging.StreamHandler()

        dfh.setFormatter(self.diag_formatter)
        self.diagnostic.addHandler(dfh)
        self.diag_filehandler = dfh

        # Setup dash output
        if self.accessfile is not None:
            self.acc = logging.getLogger("Access")
            self.acc.setLevel(numeric_level)
            self.acc.propagate = False
            afh = RotatingFileHandler(
                config['log'].get("accessfile"), maxBytes=log_size, backupCount=log_generations
            )

            afh.setFormatter(self.access_formatter)
            self.acc.addHandler(afh)
            self.access_filehandler = fh
        else:
            self.acc = self.logger
            self.access_filehandler = None

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

    def get_level_from_int(self, level):
        for lvl in self.log_levels:
            if self.log_levels[lvl] == level:
                return lvl
        return "UNKNOWN"

    def register_ad(self, ad):
        self.AD = ad

        # Log Subscriptions

        lh = LogSubscriptionHandler(self.AD)
        #lh.setFormatter(AppNameFormatter())
        lh.setLevel(logging.INFO)
        self.logger.addHandler(lh)

        eh = LogSubscriptionHandler(self.AD)
        #eh.setFormatter(AppNameFormatter())
        eh.setLevel(logging.INFO)
        self.error.addHandler(eh)

        dh = LogSubscriptionHandler(self.AD)
        #dh.setFormatter(AppNameFormatter())
        dh.setLevel(logging.INFO)
        self.acc.addHandler(dh)

        ah = LogSubscriptionHandler(self.AD)
        #ah.setFormatter(AppNameFormatter())
        ah.setLevel(logging.INFO)
        self.diagnostic.addHandler(ah)

        # Admin Subscriptions

        alh = AdminHandler(self.AD, "main_log")
        alh.setFormatter(self.log_formatter)
        self.logger.addHandler(alh)

        elh = AdminHandler(self.AD, "error_log")
        elh.setFormatter(self.error_formatter)
        self.error.addHandler(elh)

        dlh = AdminHandler(self.AD, "diag_log")
        dlh.setFormatter(self.diag_formatter)
        self.diagnostic.addHandler(dlh)

        if self.accessfile is not None:
            clh = AdminHandler(self.AD, "access_log")
            clh.setFormatter(self.access_formatter)
            self.acc.addHandler(clh)


    def _log(self, logger, level, message):
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        elif level == "DEBUG":
            logger.debug(message)
        else:
            logger.log(self.log_levels[level], message)

    def log(self, level, message, name="AppDaemon", ascii_encode=True):
        self._log(self.logger, level, message)

    def err(self, level, message, name="AppDaemon", ascii_encode=True):
        self._log(self.error, level, message)

    def diag(self, level, message, name="AppDaemon", ascii_encode=True):
        self._log(self.diagnostic, level, message)

    def access(self, level, message, name="AppDaemon", ascii_encode=True):
        self._log(self.acc, level, message)

    def get_error(self):
        return self.error

    def get_logger(self):
        return self.logger

    def get_access(self):
        return self.acc

    def get_diag(self):
        return self.diagnostic

    def read_logfile(self):
        return self._read_logfile(self.logfile)

    def read_errorfile(self):
        return self._read_logfile(self.errorfile)

    def read_diagfile(self):
        return self._read_logfile(self.diagfile)

    def read_accessfile(self):
        if self.accessfile is None:
            return None
        return self._read_logfile(self.accessfile)

    def _read_logfile(self, file):
        if file == "STDOUT" or file == "STDERR" or file is None:
            return []
        else:
            with open(file) as f:
                lines = f.read().splitlines()
            return lines

    def add_log_callback(self, namespace, name, cb, level, **kwargs):
        if self.AD.threading.validate_pin(name, kwargs) is True:
            if self.AD.events is not None:
                # Add a separate callback for each log level
                handle = []
                for thislevel in self.log_levels:
                    if self.log_levels[thislevel] >= self.log_levels[level] :
                        handle.append(self.AD.events.add_event_callback(name, namespace, cb, "__AD_LOG_EVENT", level=thislevel, **kwargs))

                return handle
        else:
            return None

    def cancel_log_callback(self, name, handle):
        if self.AD.events is not None:
            for h in handle:
                self.AD.events.cancel_event_callback(name, h)


