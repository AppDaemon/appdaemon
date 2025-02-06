#!/usr/bin/python3

"""AppDaemon main() module.

AppDaemon module that contains main() along with argument parsing, instantiation of the AppDaemon and HTTP Objects,
also creates the loop and kicks everything off

"""

import argparse
import asyncio
import itertools
import json
import logging
import os
import platform
import signal
import sys
from pathlib import Path

import pytz
from pydantic import ValidationError

import appdaemon.appdaemon as ad
import appdaemon.utils as utils
from appdaemon.app_management import UpdateMode
from appdaemon.appdaemon import AppDaemon
from appdaemon.exceptions import StartupAbortedException
from appdaemon.http import HTTP
from appdaemon.logging import Logging
from appdaemon.models.config import AppDaemonConfig

try:
    import pid
except ImportError:
    pid = None

try:
    import uvloop
except ImportError:
    uvloop = None


class NoADConfig(Exception):
    pass


class ADMain:
    """
    Class to encapsulate all main() functionality.
    """

    AD: AppDaemon

    logging: Logging

    def __init__(self):
        """Constructor."""

        self.logging = None
        self.error = None
        self.diag = None
        self.AD = None
        self.http_object = None
        self.logger = None

    def init_signals(self):
        """Setup signal handling."""

        # Windows does not support SIGUSR1 or SIGUSR2
        if platform.system() != "Windows":
            signal.signal(signal.SIGUSR1, self.handle_sig)
            signal.signal(signal.SIGINT, self.handle_sig)
            signal.signal(signal.SIGHUP, self.handle_sig)
            signal.signal(signal.SIGTERM, self.handle_sig)

    # noinspection PyUnusedLocal
    def handle_sig(self, signum, frame):
        """Function to handle signals.

        SIGUSR1 will result in internal info being dumped to the DIAG log
        SIGHUP will force a reload of all apps
        SIGINT and SIGTEM both result in AD shutting down

        Args:
            signum: Signal number being processed.
            frame: frame - unused

        Returns:
            None.

        """

        if signum == signal.SIGUSR1:
            self.AD.thread_async.call_async_no_wait(self.AD.sched.dump_schedule)
            self.AD.thread_async.call_async_no_wait(self.AD.callbacks.dump_callbacks)
            self.AD.thread_async.call_async_no_wait(self.AD.threading.dump_threads)
            self.AD.thread_async.call_async_no_wait(self.AD.app_management.dump_objects)
            self.AD.thread_async.call_async_no_wait(self.AD.sched.dump_sun)
        if signum == signal.SIGHUP:
            self.AD.thread_async.call_async_no_wait(self.AD.app_management.check_app_updates, mode=UpdateMode.TERMINATE)
        if signum == signal.SIGINT:
            self.logger.info("Keyboard interrupt")
            self.stop()
        if signum == signal.SIGTERM:
            self.logger.info("SIGTERM Received")
            self.stop()

    def stop(self):
        """Called by the signal handler to shut AD down.

        Returns:
            None.
        """

        self.logger.info("AppDaemon is shutting down")
        self.AD.stop()
        if self.http_object is not None:
            self.http_object.stop()

    # noinspection PyBroadException,PyBroadException
    def run(self, ad_config_model: AppDaemonConfig, hadashboard, admin, aui, api, http):
        """Start AppDaemon up after initial argument parsing.

        Args:
            ad_config_model: Config for AppDaemon Object.
            hadashboard: Config for HADashboard Object.
            admin: Config for admin Object.
            aui: Config for aui Object.
            api: Config for API Object
            http: Config for HTTP Object
        """

        try:
            # if to use uvloop
            if ad_config_model.uvloop and uvloop:
                self.logger.info("Running AD using uvloop")
                uvloop.install()

            loop: asyncio.BaseEventLoop = asyncio.new_event_loop()

            # Initialize AppDaemon

            self.AD = ad.AppDaemon(self.logging, loop, ad_config_model)

            # Initialize Dashboard/API/admin

            if http is not None and (
                hadashboard is not None or 
                admin is not None or 
                aui is not None or 
                api is not False
            ):
                self.logger.info("Initializing HTTP")
                self.http_object = HTTP(
                    self.AD,
                    hadashboard,
                    admin,
                    aui,
                    api,
                    http,
                )
                self.AD.register_http(self.http_object)
            else:
                if http is not None:
                    self.logger.info("HTTP configured but no consumers are configured - disabling")
                else:
                    self.logger.info("HTTP is disabled")

            self.logger.debug("Start Main Loop")

            pending = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*pending))

            #
            # Now we are shutting down - perform any necessary cleanup
            #

            self.AD.terminate()

            self.logger.info("AppDaemon is stopped.")
        except ValidationError as e:
            logging.getLogger().exception(e)
        except StartupAbortedException as e:
            # We got an unrecoverable error during startup so print it out and quit
            self.logger.error(f"AppDaemon terminated with errors: {e}")
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during run()")
            self.logger.warning("-" * 60, exc_info=True)
            self.logger.warning("-" * 60)

            self.logger.debug("End Loop")

            self.logger.info("AppDaemon Exited")

    # noinspection PyBroadException
    def main(self):  # noqa: C901
        """Initial AppDaemon entry point.

        Parse command line arguments, load configuration, set up logging.

        """

        self.init_signals()

        # Get command line args

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
            default="INFO",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        )
        parser.add_argument("-m", "--moduledebug", nargs=2, action="append")
        parser.add_argument("-v", "--version", action="version", version="%(prog)s " + utils.__version__)
        parser.add_argument("--profiledash", help=argparse.SUPPRESS, action="store_true")
        parser.add_argument("--write_toml", help="use TOML for creating new app configuration files", action="store_true")
        # TODO Implement --write_toml
        parser.add_argument("--toml", help="Deprecated", action="store_true")

        args = parser.parse_args()

        pidfile = args.pidfile

        default_config_files = ["appdaemon.yaml", "appdaemon.toml"]
        default_config_paths = [
            Path("~/.homeassistant").expanduser(),
            Path("/etc/appdaemon"),
            Path("/conf")
        ]

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
                    raise NoADConfig
            else:
                all_default_config_paths = itertools.product(default_config_files, default_config_paths)
                for file in all_default_config_paths:
                    if (config_file := file).exists():
                        break
                else:
                    raise NoADConfig

        assert config_file.exists(), f"{config_file} does not exist"
        assert os.access(config_file, os.R_OK), f"{config_file} is not readable"
        try:
            config = utils.read_config_file(config_file)
            ad_kwargs = config["appdaemon"]

            ad_kwargs["config_dir"] = config_dir
            ad_kwargs["config_file"] = config_file
            ad_kwargs["write_toml"] = args.write_toml

            if args.timewarp:
                ad_kwargs["timewarp"] = args.timewarp
            if args.starttime:
                ad_kwargs["starttime"] = args.starttime
            if args.endtime:
                ad_kwargs["endtime"] = args.endtime

            ad_kwargs["stop_function"] = self.stop
            ad_kwargs["loglevel"] = args.debug

            if args.moduledebug is not None:
                module_debug_cli = {arg[0]: arg[1] for arg in args.moduledebug}
            else:
                module_debug_cli = {}

            if isinstance(ad_kwargs.get("module_debug"), dict):
                ad_kwargs["module_debug"] |= module_debug_cli
            else:
                ad_kwargs["module_debug"] = module_debug_cli

            # Validate the AppDaemon configuration
            ad_config_model = AppDaemonConfig.model_validate(ad_kwargs)

            if args.debug.upper() == "DEBUG":
                model_json = ad_config_model.model_dump(by_alias=True, exclude_unset=True)
                print(json.dumps(model_json, indent=4, default=str, sort_keys=True))
        except ValidationError as e:
            print(f"Configuration error in: {config_file}")
            print(e)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error loading config file: {config_file}")
            print(e)
            sys.exit(1)

        hadashboard = None
        if "hadashboard" in config:
            if config["hadashboard"] is None:
                hadashboard = {}
            else:
                hadashboard = config["hadashboard"]

            hadashboard["profile_dashboard"] = args.profiledash
            hadashboard["config_dir"] = config_dir
            hadashboard["config_file"] = config_file
            if args.profiledash:
                hadashboard["profile_dashboard"] = True

            if "dashboard" not in hadashboard:
                hadashboard["dashboard"] = True

        old_admin = None
        if "old_admin" in config:
            if config["old_admin"] is None:
                old_admin = {}
            else:
                old_admin = config["old_admin"]
        admin = None
        if "admin" in config:
            if config["admin"] is None:
                admin = {}
            else:
                admin = config["admin"]
        api = None
        if "api" in config:
            if config["api"] is None:
                api = {}
            else:
                api = config["api"]

        http = None
        if "http" in config:
            http = config["http"]

        # Setup _logging

        if "log" in config:
            print(
                "ERROR",
                "'log' directive deprecated, please convert to new 'logs' syntax",
            )
            sys.exit(1)
        if "logs" in config:
            logs = config["logs"]
        else:
            logs = {}

        self.logging = Logging(logs, args.debug)
        self.logger = self.logging.get_logger()

        if "time_zone" in config["appdaemon"]:
            self.logging.set_tz(pytz.timezone(config["appdaemon"]["time_zone"]))

        # Startup message

        self.logger.info("-" * 60)
        self.logger.info("AppDaemon Version %s starting", utils.__version__)

        if utils.__version_comments__ is not None and utils.__version_comments__ != "":
            self.logger.info("Additional version info: %s", utils.__version_comments__)

        self.logger.info("-" * 60)
        self.logger.info(
            "Python version is %s.%s.%s",
            sys.version_info[0],
            sys.version_info[1],
            sys.version_info[2],
        )
        self.logger.info("Configuration read from: %s", config_file)

        for field in ad_config_model.model_fields_set:
            if field in ad_config_model.__pydantic_extra__:
                self.logger.warning(f"Extra config field '{field}'. This will be ignored")
            elif (info := ad_config_model.model_fields.get(field)) and info.deprecated:
                self.logger.warning(f"Deprecated field '{field}': {info.deprecation_message}")

        self.logging.dump_log_config()
        self.logger.debug("AppDaemon Section: %s", config.get("appdaemon"))
        self.logger.debug("HADashboard Section: %s", config.get("hadashboard"))

        exit = False

        if "time_zone" not in config["appdaemon"]:
            self.logger.error("time_zone not specified in appdaemon.yaml")
            exit = True

        if "latitude" not in config["appdaemon"]:
            self.logger.error("latitude not specified in appdaemon.yaml")
            exit = True

        if "longitude" not in config["appdaemon"]:
            self.logger.error("longitude not specified in appdaemon.yaml")
            exit = True

        if "elevation" not in config["appdaemon"]:
            self.logger.error("elevation not specified in appdaemon.yaml")
            exit = True

        if exit is True:
            sys.exit(1)

        if pidfile is not None:
            self.logger.info("Using pidfile: %s", pidfile)
            dir = os.path.dirname(pidfile)
            name = os.path.basename(pidfile)
            try:
                with pid.PidFile(name, dir):
                    self.run(ad_config_model, hadashboard, old_admin, admin, api, http)
            except pid.PidFileError:
                self.logger.error("Unable to acquire pidfile - terminating")
        else:
            self.run(ad_config_model, hadashboard, old_admin, admin, api, http)


def main():
    """Called when run from the command line."""
    admain = ADMain()
    admain.main()


if __name__ == "__main__":
    main()
