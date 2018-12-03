import datetime
import pytz
import sys

import logging
from logging.handlers import RotatingFileHandler
from logging import StreamHandler
from collections import OrderedDict

from appdaemon.appq import AppDaemon

class AppNameFormatter(logging.Formatter):

    """
    Logger formatter to add 'appname' as an interpolatable field
    """

    def __init__(self, fmt=None, datefmt=None, style=None):
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

    def __init__(self, config, log_level):

        self.AD = None
        self.tz = None

        # Set up defaults

        default_filename = "STDOUT"
        default_logsize = 1000000
        default_log_generations = 3
        default_format = "{asctime} {levelname} {appname}: {message}"
        default_date_format = "%Y-%m-%d %H:%M:%S.%f%z"

        self.config = \
            {
                'main_log':
                    {
                        'name': "AppDaemon",
                        'filename': default_filename,
                        'log_generations': default_log_generations,
                        'log_size': default_logsize,
                        'format': default_format,
                        'date_format': default_date_format
                    },
                'error_log':
                    {
                        'name': "Error",
                        'filename': 'STDERR',
                        'log_generations': default_log_generations,
                        'log_size': default_logsize,
                        'format': default_format,
                        'date_format': default_date_format
                    },
                'access_log':
                    {
                        'name': "Access",
                        'alias': "main_log",
                    },
                'diag_log':
                    {
                        'name': "Diag",
                        'alias': 'main_log',
                    }
            }

        # Merge in any user input

        if config is not None:
            for log in config:
                if log not in self.config:
                    # it's a new log - set it up with some defaults
                    self.config[log] = {}
                    self.config[log]["filename"] = default_filename
                    self.config[log]["log_generations"] = default_log_generations
                    self.config[log]["log_size"] = default_logsize
                    self.config[log]["format"] = "{asctime} {levelname} {appname}: {message}"
                    self.config[log]["date_format"] = default_date_format
                    for arg in config[log]:
                        self.config[log][arg] = config[log][arg]
                elif "alias" in self.config[log] and "alias" not in config[log]:
                # A file aliased by default that the user has supplied one or more config items for
                # We need to remove the alias tag and populate defaults
                    self.config[log]["filename"] = default_filename
                    self.config[log]["log_generations"] = default_log_generations
                    self.config[log]["log_size"] = default_logsize
                    self.config[log]["format"] = "{asctime} {levelname} {appname}: {message}"
                    self.config[log]["date_format"] = default_date_format
                    self.config[log].pop("alias")
                    for arg in config[log]:
                        self.config[log][arg] = config[log][arg]
                else:
                    # A regular file, just fill in the blanks
                    for arg in config[log]:
                        self.config[log][arg] = config[log][arg]

        # Build the logs

        for log in self.config:
            args = self.config[log]
            if 'alias' not in args:
                self.log_level = log_level
                formatter = AppNameFormatter(fmt=args["format"], datefmt=args["date_format"], style='{')
                self.config[log]["formatter"] = formatter
                formatter.formatTime = self.get_time
                logger = logging.getLogger(args["name"])
                self.config[log]["logger"] = logger
                logger.setLevel(log_level)
                logger.propagate = False
                if args["filename"] == "STDOUT":
                    handler = logging.StreamHandler(stream=sys.stdout)
                elif args["filename"] == "STDERR":
                    handler = logging.StreamHandler(stream=sys.stdout)
                else:
                    handler = RotatingFileHandler(args["filename"], maxBytes=args["log_size"], backupCount=args["log_generations"])
                self.config[log]["handler"] = handler
                handler.setFormatter(formatter)
                logger.addHandler(handler)

        # Setup any aliases

        for log in self.config:
            if 'alias' in self.config[log]:
                self.config[log]["logger"] = self.config[self.config[log]["alias"]]["logger"]
                self.config[log]["formatter"] = self.config[self.config[log]["alias"]]["formatter"]
                self.config[log]["filename"] = self.config[self.config[log]["alias"]]["filename"]
                self.config[log]["log_generations"] = self.config[self.config[log]["alias"]]["log_generations"]
                self.config[log]["log_size"] = self.config[self.config[log]["alias"]]["log_size"]
                self.config[log]["format"] = self.config[self.config[log]["alias"]]["format"]

        self.logger = self.get_logger()

    def dump_log_config(self):
        for log in self.config:
            self.logger.info("added log: %s", self.config[log]["name"])
            self.logger.debug("  filename:    %s", self.config[log]["filename"])
            self.logger.debug("  size:        %s", self.config[log]["log_size"])
            self.logger.debug("  generations: %s", self.config[log]["log_generations"])
            self.logger.debug("  format:      %s", self.config[log]["format"])

    def get_time(logger, record, format=None):
        if logger.AD is not None and logger.AD.sched is not None and not logger.AD.sched.is_realtime():
            ts = logger.AD.sched.get_now().astimezone(logger.tz)
        else:
            if logger.tz is not None:
                ts = pytz.utc.localize(datetime.datetime.utcnow()).astimezone(logger.tz)
            else:
                ts = datetime.datetime.now()
        if format is not None:
            return ts.strftime(format)
        else:
            return str(ts)

    def set_tz(self, tz):
        self.tz = tz

    def get_level_from_int(self, level):
        for lvl in self.log_levels:
            if self.log_levels[lvl] == level:
                return lvl
        return "UNKNOWN"

    def separate_error_log(self):
        if self.config["error_log"]["filename"] != "STDERR" and \
                self.config["main_log"]["filename"] != "STDOUT" and \
                not self.is_alias("error_log"):
            return True
        return False

    def register_ad(self, ad):
        self.AD = ad

        # Log Subscriptions

        for log in self.config:
            if not self.is_alias(log):
                lh = LogSubscriptionHandler(self.AD)
                lh.setLevel(logging.INFO)
                self.config[log]["logger"].addHandler(lh)

        # Admin Subscriptions

        for log in self.config:
            if not self.is_alias(log):
                alh = AdminHandler(self.AD, log)
                alh.setFormatter(self.config[log]["formatter"])
                self.config[log]["logger"].addHandler(alh)

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

    def log(self, level, message):
        self._log(self.config["main_log"]["logger"], level, message)

    def err(self, level, message):
        self._log(self.config["error_log"]["logger"], level, message)

    def diag(self, level, message):
        self._log(self.config["diag_log"]["logger"], level, message)

    def access(self, level, message):
        self._log(self.config["access_log"]["logger"], level, message)

    # Log Objects

    def get_error(self):
        return self.config["error_log"]["logger"]

    def get_logger(self):
        return self.config["main_log"]["logger"]

    def get_access(self):
        return self.config["access_log"]["logger"]

    def get_diag(self):
        return self.config["diag_log"]["logger"]

    def get_user_log(self, log):
        return self.config[log]["logger"]

    # Reading Logs

    def get_admin_logs(self):
        # Force main logs to be first in a specific order
        logs = OrderedDict()
        for log in ["main_log", "error_log", "diag_log", "access_log"]:
            logs[log] = {}
            logs[log]["name"] = self.config[log]["name"]
            logs[log]["lines"] = self.read_logfile(log)
        for log in self.config:
            if log not in logs:
                logs[log] = {}
                logs[log]["name"] = self.config[log]["name"]
                logs[log]["lines"] = self.read_logfile(log)
        return logs

    def read_logfile(self, log):
        if self.is_alias(log):
            return None
        if self.config[log]["filename"] == "STDOUT" or self.config[log]["filename"] == "STDERR":
            return []
        else:
            with open(self.config[log]["filename"]) as f:
                lines = f.read().splitlines()
            return lines

    def is_alias(self, log):
        if "alias" in self.config[log]:
            return True
        return False

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


