import datetime
import pytz
import sys
import uuid
import copy

import logging
from logging.handlers import RotatingFileHandler
from logging import StreamHandler
from collections import OrderedDict
import traceback

from appdaemon.thread_async import AppDaemon
import appdaemon.utils as utils


class DuplicateFilter(logging.Filter):
    def __init__(self, logger, threshold, delay, timeout):
        self.logger = logger
        self.last_log = None
        self.current_count = 0
        self.threshold = threshold
        self.delay = delay
        self.filtering = False
        self.start_time = None
        self.first_time = True
        self.timeout = timeout
        self.last_log_time = None

    def filter(self, record):
        if record.msg == "Previous message repeated %s times":
            return True
        if self.threshold == 0:
            return True
        current_log = (record.module, record.levelno, record.msg, record.args)
        if current_log != self.last_log:
            self.last_log = current_log
            if self.filtering is True:
                self.logger.info(
                    "Previous message repeated %s times", self.current_count - self.threshold + 1,
                )
            self.current_count = 0
            self.filtering = False
            self.start_time = None
            result = True
            self.first_time = True
            self.last_log_time = datetime.datetime.now()
        else:
            now = datetime.datetime.now()
            # Reset if we haven't exceeded the initial grace period
            if self.filtering is False and now - self.last_log_time >= datetime.timedelta(seconds=self.timeout):
                return True

            if self.start_time is not None and now - self.start_time >= datetime.timedelta(seconds=self.delay):
                self.start_time = now
                if self.first_time is True:
                    count = self.current_count - self.threshold + 1
                    self.first_time = False
                else:
                    count = self.current_count + 1

                self.logger.info("Previous message repeated %s times", count)
                self.current_count = 0
                result = True
            else:
                if self.filtering is False and self.current_count >= self.threshold - 1:
                    self.filtering = True
                    self.start_time = datetime.datetime.now()
                if self.filtering is True:
                    result = False
                else:
                    result = True
                    self.last_log_time = datetime.datetime.now()
                self.current_count += 1
        return result


class AppNameFormatter(logging.Formatter):

    """Logger formatter to add 'appname' as an interpolatable field."""

    def __init__(self, fmt=None, datefmt=None, style=None):
        super().__init__(fmt, datefmt, style)

    def format(self, record):
        #
        # Figure out the name of the app and add it to the LogRecord
        # Each logger is named after the app so split it out form the logger name
        #
        try:
            appname = record.name
            modulename = record.name
            if "." in record.name:
                loggers = record.name.split(".")
                name = loggers[len(loggers) - 1]
                if name[0] == "_":
                    # It's a module
                    appname = "AppDaemon"
                    modulename = "AD:" + name[1:]
                else:
                    # It's an app
                    appname = name
                    modulename = "App:" + appname

            record.modulename = modulename
            record.appname = appname
            result = super().format(record)
        except Exception:
            raise

        return result


class LogSubscriptionHandler(StreamHandler):

    """Handle apps that subscribe to logs.

    This Handler requires that it's formatter is an instance of AppNameFormatter.

    """

    def __init__(self, ad: AppDaemon, type):
        StreamHandler.__init__(self)
        self.AD = ad
        self.type = type

    def emit(self, record):
        logger = self.AD.logging.get_logger()
        try:
            if (
                self.AD is not None
                and self.AD.callbacks is not None
                and self.AD.events is not None
                and self.AD.thread_async is not None
            ):
                try:
                    msg = self.format(record)
                except TypeError as e:
                    logger.warning("Log formatting error - '%s'", e)
                    logger.warning("message: %s, args: %s", record.msg, record.args)
                    return
                record.ts = datetime.datetime.fromtimestamp(record.created)
                self.AD.thread_async.call_async_no_wait(
                    self.AD.events.process_event,
                    "admin",
                    {
                        "event_type": "__AD_LOG_EVENT",
                        "data": {
                            "level": record.levelname,
                            "app_name": record.appname,
                            "message": record.message,
                            "type": "log",
                            "log_type": self.type,
                            "asctime": record.asctime,
                            "ts": record.ts,
                            "formatted_message": msg,
                        },
                    },
                )
        except Exception:
            logger.warning("-" * 60)
            logger.warning("Unexpected error occured in LogSubscriptionHandler.emit()")
            logger.warning("-" * 60)
            logger.warning(traceback.format_exc())
            logger.warning("-" * 60)


class Logging:

    log_levels = {
        "CRITICAL": 50,
        "ERROR": 40,
        "WARNING": 30,
        "INFO": 20,
        "DEBUG": 10,
        "NOTSET": 0,
    }

    def __init__(self, config, log_level):

        self.AD = None
        self.tz = None

        logging.raiseExceptions = False

        # Set up defaults

        default_filename = "STDOUT"
        default_logsize = 1000000
        default_log_generations = 3
        default_format = "{asctime} {levelname} {appname}: {message}"
        default_date_format = "%Y-%m-%d %H:%M:%S.%f"
        default_filter_threshold = 1
        default_filter_timeout = 0.1
        default_filter_repeat_delay = 5
        self.log_level = log_level

        self.config = {
            "main_log": {
                "name": "AppDaemon",
                "filename": default_filename,
                "log_generations": default_log_generations,
                "log_size": default_logsize,
                "format": default_format,
                "date_format": default_date_format,
                "logger": None,
                "formatter": None,
                "filter_threshold": default_filter_threshold,
                "filter_timeout": default_filter_timeout,
                "filter_repeat_delay": default_filter_repeat_delay,
            },
            "error_log": {
                "name": "Error",
                "filename": "STDERR",
                "log_generations": default_log_generations,
                "log_size": default_logsize,
                "format": default_format,
                "date_format": default_date_format,
                "logger": None,
                "formatter": None,
                "filter_threshold": default_filter_threshold,
                "filter_timeout": default_filter_timeout,
                "filter_repeat_delay": default_filter_repeat_delay,
            },
            "access_log": {"name": "Access", "alias": "main_log"},
            "diag_log": {"name": "Diag", "alias": "main_log"},
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
                    self.config[log]["filter_threshold"] = default_filter_threshold
                    self.config[log]["filter_timeout"] = default_filter_timeout
                    self.config[log]["filter_repeat_delay"] = default_filter_repeat_delay
                    # Copy over any user defined fields
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
                    self.config[log]["filter_threshold"] = default_filter_threshold
                    self.config[log]["filter_timeout"] = default_filter_timeout
                    self.config[log]["filter_repeat_delay"] = default_filter_repeat_delay
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
            if "alias" not in args:
                formatter = AppNameFormatter(fmt=args["format"], datefmt=args["date_format"], style="{")
                args["formatter"] = formatter
                formatter.formatTime = self.get_time
                logger = logging.getLogger(args["name"])
                logger.addFilter(
                    DuplicateFilter(
                        logger, args["filter_threshold"], args["filter_repeat_delay"], args["filter_timeout"],
                    )
                )
                args["logger"] = logger
                logger.setLevel(log_level)
                logger.propagate = False
                if args["filename"] == "STDOUT":
                    handler = logging.StreamHandler(stream=sys.stdout)
                elif args["filename"] == "STDERR":
                    handler = logging.StreamHandler(stream=sys.stdout)
                else:
                    handler = RotatingFileHandler(
                        args["filename"], maxBytes=args["log_size"], backupCount=args["log_generations"],
                    )
                self.config[log]["handler"] = handler
                handler.setFormatter(formatter)
                logger.addFilter(
                    DuplicateFilter(
                        logger, args["filter_threshold"], args["filter_repeat_delay"], args["filter_timeout"],
                    )
                )
                logger.addHandler(handler)

        # Setup any aliases

        for log in self.config:
            if "alias" in self.config[log]:
                self.config[log]["logger"] = self.config[self.config[log]["alias"]]["logger"]
                self.config[log]["formatter"] = self.config[self.config[log]["alias"]]["formatter"]
                self.config[log]["filename"] = self.config[self.config[log]["alias"]]["filename"]
                self.config[log]["log_generations"] = self.config[self.config[log]["alias"]]["log_generations"]
                self.config[log]["log_size"] = self.config[self.config[log]["alias"]]["log_size"]
                self.config[log]["format"] = self.config[self.config[log]["alias"]]["format"]
                self.config[log]["date_format"] = self.config[self.config[log]["alias"]]["date_format"]
                self.config[log]["filter_threshold"] = self.config[self.config[log]["alias"]]["filter_threshold"]
                self.config[log]["filter_timeout"] = self.config[self.config[log]["alias"]]["filter_timeout"]
                self.config[log]["filter_repeat_delay"] = self.config[self.config[log]["alias"]]["filter_repeat_delay"]

        self.logger = self.get_logger()
        self.error = self.get_error()

    async def manage_services(self, namespace, domain, service, kwargs):
        if domain == "logs" and service == "get_admin":
            ml = 50
            if "maxlines" in kwargs:
                ml = kwargs["maxlines"]

            return await self.get_admin_logs(ml)

    def dump_log_config(self):
        for log in self.config:
            self.logger.info("Added log: %s", self.config[log]["name"])
            self.logger.debug("  filename:    %s", self.config[log]["filename"])
            self.logger.debug("  size:        %s", self.config[log]["log_size"])
            self.logger.debug("  generations: %s", self.config[log]["log_generations"])
            self.logger.debug("  format:      %s", self.config[log]["format"])

    def get_time(logger, record, format=None):
        if logger.AD is not None and logger.AD.sched is not None and not logger.AD.sched.is_realtime():
            ts = logger.AD.sched.get_now_sync().astimezone(logger.tz)
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
        if (
            self.config["error_log"]["filename"] != "STDERR"
            and self.config["main_log"]["filename"] != "STDOUT"
            and not self.is_alias("error_log")
        ):
            return True
        return False

    def register_ad(self, ad):
        self.AD = ad

        # Log Subscriptions

        for log in self.config:
            if not self.is_alias(log):
                lh = LogSubscriptionHandler(self.AD, log)
                lh.setFormatter(self.config[log]["formatter"])
                lh.setLevel(logging.INFO)
                self.config[log]["logger"].addHandler(lh)

    # Log Objects

    def get_error(self):
        return self.config["error_log"]["logger"]

    def get_logger(self):
        return self.config["main_log"]["logger"]

    def get_access(self):
        return self.config["access_log"]["logger"]

    def get_diag(self):
        return self.config["diag_log"]["logger"]

    def get_filename(self, log):
        return self.config[log]["filename"]

    def get_user_log(self, app, log):
        if log not in self.config:
            app.err.error("User defined log %s not found", log)
            return None
        return self.config[log]["logger"]

    def get_child(self, name):
        logger = self.get_logger().getChild(name)
        logger.addFilter(
            DuplicateFilter(
                logger,
                self.config["main_log"]["filter_threshold"],
                self.config["main_log"]["filter_repeat_delay"],
                self.config["main_log"]["filter_timeout"],
            )
        )

        if name in self.AD.module_debug:
            logger.setLevel(self.AD.module_debug[name])
        else:
            logger.setLevel(self.AD.loglevel)

        return logger

    async def get_admin_logs(self, maxlines=50):
        return await utils.run_in_executor(self, self._get_admin_logs, maxlines)

    def _get_admin_logs(self, maxlines):
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

    async def add_log_callback(self, namespace, name, cb, level, **kwargs):
        """Adds a callback for log which is called internally by apps.

        Args:
            name (str): Name of the app.
            namespace  (str): Namespace of the log event.
            cb: Callback function.
            event (str): Name of the event.
            **kwargs: List of values to filter on, and additional arguments to pass to the callback.

        Returns:
            ``None`` or the reference to the callback handle.

        """
        if self.AD.threading.validate_pin(name, kwargs) is True:
            if "pin" in kwargs:
                pin_app = kwargs["pin"]
            else:
                pin_app = self.AD.app_management.objects[name]["pin_app"]

            if "pin_thread" in kwargs:
                pin_thread = kwargs["pin_thread"]
                pin_app = True
            else:
                pin_thread = self.AD.app_management.objects[name]["pin_thread"]

            #
            # Add the callback
            #

            if name not in self.AD.callbacks.callbacks:
                self.AD.callbacks.callbacks[name] = {}

            # Add a separate callback for each log level
            handles = []
            for thislevel in self.log_levels:
                if self.log_levels[thislevel] >= self.log_levels[level]:
                    handle = uuid.uuid4().hex
                    cb_kwargs = copy.deepcopy(kwargs)
                    cb_kwargs["level"] = thislevel
                    self.AD.callbacks.callbacks[name][handle] = {
                        "name": name,
                        "id": self.AD.app_management.objects[name]["id"],
                        "type": "log",
                        "function": cb,
                        "namespace": namespace,
                        "pin_app": pin_app,
                        "pin_thread": pin_thread,
                        "kwargs": cb_kwargs,
                    }

                    handles.append(handle)

                    #
                    # If we have a timeout parameter, add a scheduler entry to delete the callback later
                    #
                    if "timeout" in cb_kwargs:
                        exec_time = await self.AD.sched.get_now() + datetime.timedelta(seconds=int(kwargs["timeout"]))

                        cb_kwargs["__timeout"] = await self.AD.sched.insert_schedule(
                            name, exec_time, None, False, None, __log_handle=handle,
                        )

                    await self.AD.state.add_entity(
                        "admin",
                        "log_callback.{}".format(handle),
                        "active",
                        {
                            "app": name,
                            "function": cb.__name__,
                            "pinned": pin_app,
                            "pinned_thread": pin_thread,
                            "fired": 0,
                            "executed": 0,
                            "kwargs": cb_kwargs,
                        },
                    )

            return handles

        else:
            return None

    async def process_log_callbacks(self, namespace, log_data):
        """Process Log callbacks"""

        data = log_data["data"]

        # Process log callbacks

        removes = []
        for name in self.AD.callbacks.callbacks.keys():
            for uuid_ in self.AD.callbacks.callbacks[name]:
                callback = self.AD.callbacks.callbacks[name][uuid_]
                if callback["type"] == "log" and (
                    callback["namespace"] == namespace or callback["namespace"] == "global" or namespace == "global"
                ):

                    # Check any filters
                    _run = True
                    if "log" in callback["kwargs"] and callback["kwargs"]["log"] != data["log_type"]:
                        _run = False

                    if "level" in callback["kwargs"] and callback["kwargs"]["level"] != data["level"]:
                        _run = False

                    if _run:
                        if name in self.AD.app_management.objects:
                            executed = await self.AD.threading.dispatch_worker(
                                name,
                                {
                                    "id": uuid_,
                                    "name": name,
                                    "objectid": self.AD.app_management.objects[name]["id"],
                                    "type": "log",
                                    "function": callback["function"],
                                    "data": data,
                                    "pin_app": callback["pin_app"],
                                    "pin_thread": callback["pin_thread"],
                                    "kwargs": callback["kwargs"],
                                },
                            )

                        # Remove the callback if appropriate
                        if executed is True:
                            remove = callback["kwargs"].get("oneshot", False)
                            if remove is True:
                                removes.append({"name": callback["name"], "uuid": uuid_})

        for remove in removes:
            await self.cancel_log_callback(remove["name"], remove["uuid"])

    async def cancel_log_callback(self, name, handles):
        """Cancels an log callback.

        Args:
            name (str): Name of the app or module.
            handle: Previously supplied callback handle for the callback.

        Returns:
            None.

        """

        if not isinstance(handles, list):
            handles = [handles]

        for handle in handles:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                del self.AD.callbacks.callbacks[name][handle]
                await self.AD.state.remove_entity("admin", "log_callback.{}".format(handle))
            if name in self.AD.callbacks.callbacks and self.AD.callbacks.callbacks[name] == {}:
                del self.AD.callbacks.callbacks[name]
