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
import os
import signal
import sys
from pathlib import Path

import pytz
from pydantic import ValidationError

import appdaemon.appdaemon as ad
import appdaemon.utils as utils
from appdaemon import exceptions as ade
from appdaemon.app_management import UpdateMode
from appdaemon.appdaemon import AppDaemon
from appdaemon.exceptions import StartupAbortedException
from appdaemon.http import HTTP
from appdaemon.logging import Logging
from appdaemon.models.config import AppDaemonConfig

from .models.config.yaml import MainConfig

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

    # noinspection PyUnusedLocal
    def handle_sig(self, signum: int):
        """Function to handle signals.

        Signals:
            SIGUSR1 will result in internal info being dumped to the DIAG log
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
            case signal.SIGHUP:
                self.AD.thread_async.call_async_no_wait(self.AD.app_management.check_app_updates, mode=UpdateMode.TERMINATE)
            case signal.SIGINT:
                self.logger.info("Keyboard interrupt")
                self.stop()
            case signal.SIGTERM:
                self.logger.info("SIGTERM Received")
                self.stop()
            # case signal.SIGWINCH:
            #     ... # disregard window changes
            # case _:
            #     self.logger.error(f'Unhandled signal: {signal.Signals(signum).name}')

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
    def run(self, ad_config_model: AppDaemonConfig, *args, http):
        """Start AppDaemon up after initial argument parsing.

        Args:
            ad_config_model: Config for AppDaemon Object.
            *args: Gets used to create the HTTP object.
            http: Main HTTP config
        """

        try:
            # if to use uvloop
            if ad_config_model.uvloop and uvloop:
                self.logger.info("Running AD using uvloop")
                uvloop.install()

            loop: asyncio.BaseEventLoop = asyncio.new_event_loop()

            # Initialize AppDaemon

            self.AD = ad.AppDaemon(self.logging, loop, ad_config_model)
            loop.set_exception_handler(functools.partial(ade.exception_handler, self.AD))

            for sig in signal.Signals:
                callback = functools.partial(self.handle_sig, sig)
                try:
                    loop.add_signal_handler(sig.value, callback)
                except RuntimeError:
                    # This happens for some signals on some operating systems, no problem
                    continue

            # Initialize Dashboard/API/admin

            if http is not None and any(arg is not None for arg in args):
                self.logger.info("Initializing HTTP")
                self.http_object = HTTP(self.AD, *args, http)
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
        except ade.AppDaemonException as e:
            ade.user_exception_block(self.logger, e, self.AD.app_dir)
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

        default_config_files = [
            "appdaemon.toml",
            "appdaemon.yaml",
        ]
        default_config_paths = [Path("~/.homeassistant").expanduser(), Path("/etc/appdaemon"), Path("/conf")]

        try:
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

            assert config_file.exists(), f"{config_file} does not exist"
            assert os.access(config_file, os.R_OK), f"{config_file} is not readable"
        except (AssertionError, NoADConfig) as e:
            print(f"FATAL: Error accessing configuration: {e}")
            sys.exit(1)

        try:
            config = utils.read_config_file(config_file)
            config = {
                k: v if v is not None else {}
                for k, v in config.items()
            } # fmt: skip

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

            if isinstance((hadashboard := config.get("hadashboard")), dict):
                hadashboard["config_dir"] = config_dir
                hadashboard["config_file"] = config_file
                hadashboard["dashboard"] = True
                hadashboard["profile_dashboard"] = args.profiledash

            model = MainConfig.model_validate(config)

            if args.debug.upper() == "DEBUG":
                # need to dump as python types or serializing the timezone object will fail
                model_json = model.model_dump(mode='python', by_alias=True)
                print(json.dumps(model_json, indent=4, default=str, sort_keys=True))
        except ValidationError as e:
            print(f"Configuration error in: {config_file}")
            print(e)
            sys.exit(1)
        except ade.ConfigReadFailure as e:
            ade.user_exception_block(logging.getLogger(), e, config_dir, "Reading AppDaemon configuration")
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error loading config file: {config_file}")
            print(e)
            sys.exit(1)

        log_cfg = model.model_dump(mode='python', by_alias=True)['logs']
        self.logging = Logging(log_cfg, args.debug)
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

        utils.deprecation_warnings(model.appdaemon, self.logger)

        self.logging.dump_log_config()
        self.logger.debug("AppDaemon Section: %s", config.get("appdaemon"))
        self.logger.debug("HADashboard Section: %s", config.get("hadashboard"))

        dump_kwargs = dict(mode='json', by_alias=True, exclude_unset=True)

        if (hadashboard := model.hadashboard) is not None:
            hadashboard = hadashboard.model_dump(**dump_kwargs)

        if (http := model.http) is not None:
            http = http.model_dump(**dump_kwargs)

        run = functools.partial(
            self.run,
            model.appdaemon,
            hadashboard,
            model.old_admin,
            model.admin,
            model.api,
            http=http,
        )

        if pidfile is not None:
            self.logger.info("Using pidfile: %s", pidfile)
            dir = os.path.dirname(pidfile)
            name = os.path.basename(pidfile)
            try:
                with pid.PidFile(name, dir):
                    run()
            except pid.PidFileError:
                self.logger.error("Unable to acquire pidfile - terminating")
        else:
            run()


def main():
    """Called when run from the command line."""
    admain = ADMain()
    admain.main()


if __name__ == "__main__":
    main()
