#!/usr/bin/python3

"""AppDaemon main() module.

AppDaemon module that contains main() along with argument parsing, instantiation of the AppDaemon and HTTP Objects,
also creates the loop and kicks everything off

"""

import argparse
import asyncio
import os
import os.path
import platform
import signal
import sys

import appdaemon.appdaemon as ad
import appdaemon.http as adhttp
import appdaemon.logging as logging
import appdaemon.utils as utils
import pytz
import yaml

try:
    import pid
except ImportError:
    pid = None

try:
    import uvloop
except ImportError:
    uvloop = None


class ADMain:
    """
    Class to encapsulate all main() functionality.
    """

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
            self.AD.thread_async.call_async_no_wait(self.AD.app_management.check_app_updates, mode="term")
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
    def run(self, appdaemon, hadashboard, admin, aui, api, http):
        """ Start AppDaemon up after initial argument parsing.

        Args:
            appdaemon: Config for AppDaemon Object.
            hadashboard: Config for HADashboard Object.
            admin: Config for admin Object.
            aui: Config for aui Object.
            api: Config for API Object
            http: Config for HTTP Object

        Returns:
            None.

        """

        try:

            # if to use uvloop
            if appdaemon.get("uvloop") is True and uvloop:
                self.logger.info("Running AD using uvloop")
                uvloop.install()

            loop = asyncio.get_event_loop()

            # Initialize AppDaemon

            self.AD = ad.AppDaemon(self.logging, loop, **appdaemon)

            # Initialize Dashboard/API/admin

            if http is not None and (
                hadashboard is not None or admin is not None or aui is not None or api is not False
            ):
                self.logger.info("Initializing HTTP")
                self.http_object = adhttp.HTTP(
                    self.AD, loop, self.logging, appdaemon, hadashboard, admin, aui, api, http,
                )
                self.AD.register_http(self.http_object)
            else:
                if http is not None:
                    self.logger.info("HTTP configured but no consumers are configured - disabling")
                else:
                    self.logger.info("HTTP is disabled")

            self.logger.debug("Start Main Loop")

            pending = asyncio.Task.all_tasks()
            loop.run_until_complete(asyncio.gather(*pending))

            #
            # Now we are shutting down - perform any necessary cleanup
            #

            self.AD.terminate()

            self.logger.info("AppDaemon is stopped.")

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
            "-c", "--config", help="full path to config directory", type=str, default=None,
        )
        parser.add_argument("-p", "--pidfile", help="full path to PID File", default=None)
        parser.add_argument(
            "-t", "--timewarp", help="speed that the scheduler will work at for time travel", default=1, type=float,
        )
        parser.add_argument(
            "-s", "--starttime", help="start time for scheduler <YYYY-MM-DD HH:MM:SS|YYYY-MM-DD#HH:MM:SS>", type=str,
        )
        parser.add_argument(
            "-e",
            "--endtime",
            help="end time for scheduler <YYYY-MM-DD HH:MM:SS|YYYY-MM-DD#HH:MM:SS>",
            type=str,
            default=None,
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

        args = parser.parse_args()

        config_dir = args.config
        pidfile = args.pidfile

        if config_dir is None:
            config_file_yaml = utils.find_path("appdaemon.yaml")
        else:
            config_file_yaml = os.path.join(config_dir, "appdaemon.yaml")

        if config_file_yaml is None:
            print("FATAL: no configuration directory defined and defaults not present\n")
            parser.print_help()
            sys.exit(1)

        module_debug = {}
        if args.moduledebug is not None:
            for arg in args.moduledebug:
                module_debug[arg[0]] = arg[1]

        #
        # First locate secrets file
        #
        try:

            #
            # Read config file using include directory
            #

            yaml.add_constructor("!include", utils._include_yaml, Loader=yaml.SafeLoader)

            #
            # Read config file using environment variables
            #

            yaml.add_constructor("!env_var", utils._env_var_yaml, Loader=yaml.SafeLoader)

            #
            # Initially load file to see if secret directive is present
            #
            yaml.add_constructor("!secret", utils._dummy_secret, Loader=yaml.SafeLoader)
            with open(config_file_yaml, "r") as yamlfd:
                config_file_contents = yamlfd.read()

            config = yaml.load(config_file_contents, Loader=yaml.SafeLoader)

            if "secrets" in config:
                secrets_file = config["secrets"]
            else:
                secrets_file = os.path.join(os.path.dirname(config_file_yaml), "secrets.yaml")

            #
            # Read Secrets
            #
            if os.path.isfile(secrets_file):
                with open(secrets_file, "r") as yamlfd:
                    secrets_file_contents = yamlfd.read()

                utils.secrets = yaml.load(secrets_file_contents, Loader=yaml.SafeLoader)

            else:
                if "secrets" in config:
                    print(
                        "ERROR", "Error loading secrets file: {}".format(config["secrets"]),
                    )
                    sys.exit()

            #
            # Read config file again, this time with secrets
            #

            yaml.add_constructor("!secret", utils._secret_yaml, Loader=yaml.SafeLoader)

            with open(config_file_yaml, "r") as yamlfd:
                config_file_contents = yamlfd.read()

            config = yaml.load(config_file_contents, Loader=yaml.SafeLoader)

        except yaml.YAMLError as exc:
            print("ERROR", "Error loading configuration")
            if hasattr(exc, "problem_mark"):
                if exc.context is not None:
                    print("ERROR", "parser says")
                    print("ERROR", str(exc.problem_mark))
                    print("ERROR", str(exc.problem) + " " + str(exc.context))
                else:
                    print("ERROR", "parser says")
                    print("ERROR", str(exc.problem_mark))
                    print("ERROR", str(exc.problem))
            sys.exit()

        if "appdaemon" not in config:
            print("ERROR", "no 'appdaemon' section in {}".format(config_file_yaml))
            sys.exit()

        appdaemon = config["appdaemon"]
        if "disable_apps" not in appdaemon:
            appdaemon["disable_apps"] = False

        appdaemon["config_dir"] = config_dir
        appdaemon["config_file"] = config_file_yaml
        appdaemon["app_config_file"] = os.path.join(os.path.dirname(config_file_yaml), "apps.yaml")
        appdaemon["module_debug"] = module_debug

        if args.starttime is not None:
            appdaemon["starttime"] = args.starttime

        if args.endtime is not None:
            appdaemon["endtime"] = args.endtime

        if "timewarp" not in appdaemon:
            appdaemon["timewarp"] = args.timewarp

        appdaemon["loglevel"] = args.debug

        appdaemon["config_dir"] = os.path.dirname(config_file_yaml)

        appdaemon["stop_function"] = self.stop

        hadashboard = None
        if "hadashboard" in config:
            if config["hadashboard"] is None:
                hadashboard = {}
            else:
                hadashboard = config["hadashboard"]

            hadashboard["profile_dashboard"] = args.profiledash
            hadashboard["config_dir"] = config_dir
            hadashboard["config_file"] = config_file_yaml
            hadashboard["config_dir"] = os.path.dirname(config_file_yaml)
            if args.profiledash:
                hadashboard["profile_dashboard"] = True

            if "dashboard" not in hadashboard:
                hadashboard["dashboard"] = True

        admin = None
        if "admin" in config:
            if config["admin"] is None:
                admin = {}
            else:
                admin = config["admin"]
        aui = None
        if "aui" in config:
            if config["aui"] is None:
                aui = {}
            else:
                aui = config["aui"]
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
                "ERROR", "'log' directive deprecated, please convert to new 'logs' syntax",
            )
            sys.exit(1)
        if "logs" in config:
            logs = config["logs"]
        else:
            logs = {}

        self.logging = logging.Logging(logs, args.debug)
        self.logger = self.logging.get_logger()

        if "time_zone" in config["appdaemon"]:
            self.logging.set_tz(pytz.timezone(config["appdaemon"]["time_zone"]))

        # Startup message

        self.logger.info("AppDaemon Version %s starting", utils.__version__)
        self.logger.info(
            "Python version is %s.%s.%s", sys.version_info[0], sys.version_info[1], sys.version_info[2],
        )
        self.logger.info("Configuration read from: %s", config_file_yaml)
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

        utils.check_path("config_file", self.logger, config_file_yaml, pathtype="file")

        if pidfile is not None:
            self.logger.info("Using pidfile: %s", pidfile)
            dir = os.path.dirname(pidfile)
            name = os.path.basename(pidfile)
            try:
                with pid.PidFile(name, dir):
                    self.run(appdaemon, hadashboard, admin, aui, api, http)
            except pid.PidFileError:
                self.logger.error("Unable to acquire pidfile - terminating")
        else:
            self.run(appdaemon, hadashboard, admin, aui, api, http)


def main():
    """Called when run from the command line."""
    admain = ADMain()
    admain.main()


if __name__ == "__main__":
    main()
