#!/usr/bin/python3

"""AppDaemon main() module.

AppDaemon module that contains main() along with argument parsing, instantiation of the AppDaemon and HTTP Objects,
also creates the loop and kicks everything off

"""

import argparse
import asyncio
import functools
import itertools
import json
import logging
import logging.config
import os
import signal
import sys
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from logging import Logger
from pathlib import Path
from time import perf_counter

import appdaemon.appdaemon as ad
import appdaemon.utils as utils
from appdaemon import exceptions as ade
from appdaemon.app_management import UpdateMode
from appdaemon.appdaemon import AppDaemon
from appdaemon.exceptions import NoADConfig
from appdaemon.http import HTTP
from appdaemon.logging import Logging

from .dependency_manager import DependencyManager
from .models.config.yaml import MainConfig

logger = logging.getLogger(__name__)
err_logger = logging.getLogger("bare")

try:
    import pid
except ImportError:
    pid = None

try:
    import uvloop
except ImportError:
    uvloop = None


# This dict sets up the default logging before the config has even been read.
PRE_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "bare": {
            "format": "{levelname}: {message}",
            "style": "{",
        },
        "full": {
            "format": "{asctime}.{msecs:03.0f} {levelname} AppDaemon: {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "full",
            "stream": "ext://sys.stdout",
        },
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "bare",
            "stream": "ext://sys.stderr",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["stdout"],
    },
    "loggers": {"bare": {"handlers": ["stderr"], "propagate": False}},
}


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed command line arguments.
    """
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-c",
        "--config",
        help="full path to config directory",
        type=str,
    )
    parser.add_argument("-p", "--pidfile", help="full path to PID File", default=None)
    parser.add_argument(
        "-t",
        "--timewarp",
        help="speed that the scheduler will work at for time travel",
        type=float,
    )
    parser.add_argument(
        "-s",
        "--starttime",
        help="start time for scheduler <YYYY-MM-DD HH:MM:SS|YYYY-MM-DD#HH:MM:SS>",
        type=str,
    )
    parser.add_argument(
        "-e",
        "--endtime",
        help="end time for scheduler <YYYY-MM-DD HH:MM:SS|YYYY-MM-DD#HH:MM:SS>",
        type=str,
    )
    parser.add_argument(
        "-C",
        "--configfile",
        help="name for config file",
        type=str,
    )
    parser.add_argument(
        "-D",
        "--debug",
        help="global debug level",
        # default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    parser.add_argument("-m", "--moduledebug", nargs=2, action="append")
    parser.add_argument("-v", "--version", action="version", version="%(prog)s " + utils.__version__)
    parser.add_argument("--profiledash", help=argparse.SUPPRESS, action="store_true")
    parser.add_argument("--write_toml", help="use TOML for creating new app configuration files", action="store_true")
    # TODO Implement --write_toml
    parser.add_argument("--toml", help="Deprecated", action="store_true")

    return parser.parse_args()


def resolve_config_file(args: argparse.Namespace) -> tuple[Path, Path]:
    """Resolve configuration file and directory paths.

    Args:
        args: Parsed command line arguments

    Returns:
        Tuple of (config_file, config_dir) paths

    Raises:
        NoADConfig: If no valid configuration file is found
    """
    default_config_files = [
        "appdaemon.toml",
        "appdaemon.yaml",
    ]
    default_config_paths = [Path("~/.homeassistant").expanduser(), Path("/etc/appdaemon"), Path("/conf")]

    if args.configfile is not None:
        config_file = Path(args.configfile).resolve()
        if args.config is not None:
            config_dir = Path(args.config).resolve()
        else:
            config_dir = config_file.parent
    else:
        if args.config is not None:
            config_dir = Path(args.config).resolve()
            for file in default_config_files:
                if (config_file := (config_dir / file)).exists():
                    break
            else:
                raise NoADConfig(f"{config_file} not found")
        else:
            all_default_config_paths = itertools.product(default_config_files, default_config_paths)
            for file in all_default_config_paths:
                dir = file[1]
                final_path = dir / file[0]
                if (config_file := final_path).exists():
                    break
            else:
                raise NoADConfig(f"No valid configuration file found in default locations: {[str(d) for d in default_config_paths]}")

    if not config_file.exists():
        raise NoADConfig(f"{config_file} does not exist")
    if not os.access(config_file, os.R_OK):
        raise NoADConfig(f"{config_file} is not readable")

    return config_file, config_dir


def parse_config(args: argparse.Namespace) -> MainConfig:
    """Parse configuration file and return MainConfig model.

    Args:
        args: Parsed command line arguments
        stop_function: Function to call for stopping the application

    Returns:
        Tuple of MainConfig model instance and parsed arguments

    Raises:
        SystemExit: If configuration cannot be loaded or parsed
    """

    try:
        config_file, config_dir = resolve_config_file(args)
    except NoADConfig as e:
        err_logger.error(f"Error accessing configuration: {e}")
        sys.exit(1)

    config = utils.read_config_file(config_file)
    assert isinstance(config, dict), "Configuration file must be a dictionary"

    # Only process sections that actually have None values
    for key, value in config.items():
        if value is None:
            config[key] = {}

    ad_kwargs = config["appdaemon"]
    assert isinstance(ad_kwargs, dict), "AppDaemon configuration must be a dictionary"

    # Batch assign required parameters
    ad_kwargs.update(
        {
            "config_dir": config_dir,
            "config_file": config_file,
            "write_toml": args.write_toml,
        }
    )

    # Conditionally assign time-related parameters
    for attr in ("timewarp", "starttime", "endtime"):
        if value := getattr(args, attr):
            ad_kwargs[attr] = value

    # Set log level with fallback
    ad_kwargs["loglevel"] = args.debug or ad_kwargs.get("loglevel", "INFO")

    # Handle module debug efficiently
    module_debug_cli = {arg[0]: arg[1] for arg in args.moduledebug} if args.moduledebug else {}

    if isinstance(ad_kwargs.get("module_debug"), dict):
        ad_kwargs["module_debug"] |= module_debug_cli
    else:
        ad_kwargs["module_debug"] = module_debug_cli

    if isinstance((hadashboard := config.get("hadashboard")), dict):
        hadashboard["config_dir"] = config_dir
        hadashboard["config_file"] = config_file
        hadashboard["dashboard"] = True
        hadashboard["profile_dashboard"] = args.profiledash

    model = MainConfig.model_validate(config)

    if ad_kwargs["loglevel"] == "DEBUG":
        # need to dump as python types or serializing the timezone object will fail
        model_json = model.model_dump(mode="python", by_alias=True)
        logger.debug(json.dumps(model_json, indent=4, default=str, sort_keys=True))

    return model


class ADMain:
    """Main application class for AppDaemon, which contains the parsed CLI arguments, top-level config model, and the async event loop.

    When this class is instantiated, it creates a :py:class:`~appdaemon.dependency_manager.DependencyManager` from the app directory. This causes
    """

    AD: AppDaemon
    loop: asyncio.AbstractEventLoop

    logging: Logging
    logger: Logger
    error: Logger
    diag: Logger
    AD: AppDaemon
    _cleanup_stack: ExitStack

    model: MainConfig
    """Pydantic model of the top-level object for the appdaemon.yaml file."""
    args: argparse.Namespace

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.http_object = None
        self._cleanup_stack = ExitStack()

        try:
            self.model = parse_config(self.args)
            self.setup_logging()
            utils.deprecation_warnings(self.model.appdaemon, self.logger)

            # Create the dependency manager here so that all the initial file reading happens in here
            self.dep_manager = DependencyManager.from_app_directory(
                self.model.appdaemon.app_dir,
                exclude=self.model.appdaemon.exclude_dirs,
            )

        except Exception as e:
            # err_logger.exception(e)
            ade.user_exception_block(logger, e, None, header="Failed to configure AppDaemon")
            sys.exit(1)
            # raise ade.StartupAbortedException() from e

    def __enter__(self):
        try:
            self._cleanup_stack.enter_context(
                ade.exception_context(
                    self.logger,
                    self.model.appdaemon.app_dir,
                    header="ADMain",
                )
            )

            if self.args.pidfile is not None and pid is not None:
                pidfile_path = Path(self.args.pidfile).resolve()
                self.logger.info("Using pidfile: %s", pidfile_path)
                pid_file = pid.PidFile(pidfile_path.name, pidfile_path.parent)
                self._cleanup_stack.enter_context(pid_file)

            self._cleanup_stack.enter_context(self.loop_context())
            self._cleanup_stack.enter_context(self.signal_handlers(self.loop))
            return self
        except Exception as e:
            ade.user_exception_block(self.logger, e, self.model.appdaemon.app_dir, header="ADMain __enter__")
            sys.exit(1)
            # raise ade.StartupAbortedException() from e

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._cleanup_stack.close()

    def add_cleanup(self, cleanup_func, *args, **kwargs):
        """Add a cleanup function to be called on exit."""
        self._cleanup_stack.callback(cleanup_func, *args, **kwargs)

    def handle_sig(self, signum: int):
        """Function to handle signals.

        Signals:
            SIGUSR1 will result in internal info being dumped to the DIAG log
            SIGUSR2 will reload apps with modified code/config (useful in production_mode)
            SIGHUP will force a reload of all apps
            SIGINT and SIGTEM both result in AD shutting down
        """
        match signum:
            case signal.SIGUSR1:
                self.AD.thread_async.call_async_no_wait(self.AD.sched.dump_schedule)
                self.AD.thread_async.call_async_no_wait(self.AD.callbacks.dump_callbacks)
                self.AD.thread_async.call_async_no_wait(self.AD.threading.dump_threads)
                self.AD.thread_async.call_async_no_wait(self.AD.app_management.dump_objects)
                self.AD.thread_async.call_async_no_wait(self.AD.sched.dump_sun)
            case signal.SIGUSR2:
                self.AD.thread_async.call_async_no_wait(self.AD.app_management.check_app_updates, mode=UpdateMode.NORMAL)
            case signal.SIGHUP:
                self.AD.thread_async.call_async_no_wait(self.AD.app_management.check_app_updates, mode=UpdateMode.TERMINATE)
            case (signal.SIGINT | signal.SIGTERM) as sig:
                self.logger.info(f"Received signal: {signal.Signals(sig).name}")
                self.stop()

    @contextmanager
    def loop_context(self) -> Generator[asyncio.AbstractEventLoop]:
        """Context manager that creates a new async event loop and cleans it up afterwards.

        Includes the logic to install uvloop if it's enabled.
        """
        # uvloop needs to be installed outside of self.run_context
        if self.model.appdaemon.uvloop and uvloop is not None:
            uvloop.install()
            self.logger.info("Enabled uvloop")

        try:
            self.loop = asyncio.new_event_loop()
            self.logger.debug("Created new async event loop")
            yield self.loop
        finally:
            self.loop.close()
            del self.loop
            self.logger.debug("Closed async event loop")

    @contextmanager
    def signal_handlers(self, loop: asyncio.AbstractEventLoop):
        """Context manager for signal handler registration and cleanup."""
        registered_signals = []
        try:
            for sig in signal.Signals:
                callback = functools.partial(self.handle_sig, sig)
                try:
                    loop.add_signal_handler(sig.value, callback)
                    registered_signals.append(sig.value)
                except RuntimeError:
                    # This happens for some signals on some operating systems, no problem
                    continue
            yield
        finally:
            for sig_value in registered_signals:
                try:
                    loop.remove_signal_handler(sig_value)
                except (ValueError, RuntimeError):
                    # Signal handler might not be registered or already removed
                    pass

    def stop(self):
        """Stop AppDaemon and stop the event loop afterwards."""
        self.AD.stop_time = perf_counter()
        task = self.loop.create_task(self.AD.stop())
        task.add_done_callback(lambda _: self.loop.stop())

    def run(self) -> None:
        """Start AppDaemon up after initial argument parsing.

        This uses :py:meth:`~asyncio.loop.run_forever` on the event loop to run it indefinitely.
        """
        self._cleanup_stack.enter_context(self.startup_text())
        self._cleanup_stack.enter_context(self.run_context(self.loop))
        self.AD.start()
        self.logger.debug("Running async event loop forever")
        self.loop.run_forever()
        self.logger.debug("Stopped running async event loop forever")

    @contextmanager
    def run_context(self, loop: asyncio.AbstractEventLoop):
        """Context manager for the main run logic with exception handling."""
        try:
            # Initialize AppDaemon
            self.AD = ad.AppDaemon(self.logging, loop, self.model.appdaemon, self._cleanup_stack)
            self.AD.app_management.dependency_manager = self.dep_manager
            exception_handler = functools.partial(ade.exception_handler, self.AD)
            self.loop.set_exception_handler(exception_handler)

            # Initialize Dashboard/API/admin
            http_components = (
                self.model.hadashboard,
                self.model.old_admin,
                self.model.admin,
                self.model.api,
            )
            http_auto_enable = any(arg is not None for arg in http_components)

            if self.model.http is not None and http_auto_enable:
                self.logger.info("Initializing HTTP")
                self.http_object = HTTP(self.AD, self.model)
                self.AD.register_http(self.http_object)
            else:
                if self.model.http is not None:
                    self.logger.warning("HTTP component is enabled but no consumers are configured - disabling")
                else:
                    self.logger.info("HTTP is disabled")

            yield
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during run()")
            self.logger.warning("-" * 60, exc_info=True)
            self.logger.warning("-" * 60)
        finally:
            self.logger.debug("Exiting self.run_context")
            self.loop.set_exception_handler(None)
            self.logger.info("AppDaemon is stopped.")

    def setup_logging(self) -> None:
        """Set up logging configuration and timezone."""
        log_cfg = self.model.logs.model_dump(mode="python", by_alias=True, exclude_unset=True)
        self.logging = Logging(log_cfg, self.args.debug)
        self.logger = self.logging.get_logger().getChild("_startup")

        if self.model.appdaemon.time_zone is not None:
            self.logging.set_tz(self.model.appdaemon.time_zone)

    @contextmanager
    def startup_text(self):
        try:
            # Startup message
            self.logger.info("-" * 60)
            self.logger.info("AppDaemon Version %s starting", utils.__version__)

            if utils.__version_comments__ is not None and utils.__version_comments__ != "":
                self.logger.info("Additional version info: %s", utils.__version_comments__)

            self.logger.info("-" * 60)
            self.logger.info("Python version is %s.%s.%s", *sys.version_info[:3])
            self.logger.info("Configuration read from: %s", self.model.appdaemon.config_file)

            # self.logging.dump_log_config()
            yield
        finally:
            stop_duration = perf_counter() - self.AD.stop_time
            self.logger.info("AppDaemon main() stopped gracefully in %s", utils.format_timedelta(stop_duration))


def main() -> None:
    """Top-level entrypoint for AppDaemon

    Parses the CLI arguments, configures logging, and runs the AppDaemon.
    """
    args = parse_arguments()

    CLI_LOG_CFG = PRE_LOGGING.copy()

    if args.debug is not None:
        CLI_LOG_CFG["root"]["level"] = args.debug
        logger.debug("Configured logging level from command line argument")

    logging.config.dictConfig(CLI_LOG_CFG)

    with ADMain(args) as admain:
        admain.run()


if __name__ == "__main__":
    """Called when run from the command line."""
    main()
