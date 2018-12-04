#!/usr/bin/python3
import sys
import argparse
import os
import os.path
import signal
import platform
import yaml
import asyncio
import pytz

import appdaemon.utils as utils
import appdaemon.appdaemon as ad
import appdaemon.run_restapi as api
import appdaemon.run_dash as rundash
import appdaemon.logging as logging
import appdaemon.run_admin as run_admin

class ADMain():

    def __init__(self):
        self.logging = None
        self.error = None
        self.diag = None
        self.AD = None
        self.rundash = None
        self.runadmin = None

    def init_signals(self):
        # Windows does not support SIGUSR1 or SIGUSR2
        if platform.system() != "Windows":
            signal.signal(signal.SIGUSR1, self.handle_sig)
            signal.signal(signal.SIGINT, self.handle_sig)
            signal.signal(signal.SIGHUP, self.handle_sig)
            signal.signal(signal.SIGTERM, self.handle_sig)

    # noinspection PyUnusedLocal
    def handle_sig(self, signum, frame):
        if signum == signal.SIGUSR1:
            self.AD.sched.dump_schedule()
            self.AD.callbacks.dump_callbacks()
            qinfo = self.AD.threading.q_info()
            self.AD.threading.dump_threads(qinfo)
            self.AD.app_management.dump_objects()
            self.AD.sched.dump_sun()
        if signum == signal.SIGHUP:
            self.AD.app_management.check_app_updates(True)
        if signum == signal.SIGINT:
            self.logger.info("Keyboard interrupt")
            self.stop()
        if signum == signal.SIGTERM:
            self.logger.info("SIGTERM Recieved")
            self.stop()

    def stop(self):
        self.logger.info("AppDaemon is shutting down")
        self.AD.stop()
        if self.rundash is not None:
            self.rundash.stop()
        if self.runadmin is not None:
            self.runadmin.stop()

    # noinspection PyBroadException,PyBroadException
    def run(self, appdaemon, hadashboard):

        try:
            loop = asyncio.get_event_loop()

            # Initialize AppDaemon

            self.AD = ad.AppDaemon(self.logging, loop, **appdaemon)

            # Initialize Dashboard/API

            if hadashboard["dashboard"] is True:
                self.logger.info("Starting Dashboards")
                self.rundash = rundash.RunDash(self.AD, loop, self.logging, **hadashboard)
                self.AD.register_dashboard(self.rundash)
            else:
                self.logger.info("Dashboards are disabled")

            if "api_port" in appdaemon:
                self.logger.info("Starting API on port %s", appdaemon["api_port"])
                self.api = api.ADAPI(self.AD, loop, self.logging, **appdaemon)
                self.AD.register_api(self.api)
            else:
                self.logger.info("API is disabled")

            if "admin" in appdaemon and "port" in appdaemon["admin"]:
                self.logger.info("Starting Admin Interface on port %s", appdaemon["admin"]["port"])
                admin = appdaemon["admin"]
                self.runadmin = run_admin.RunAdmin(self.AD, loop, self.logging, **admin)
                self.AD.register_admin(self.runadmin)
            else:
                self.logger.info("Admin Interface is disabled")

            self.logger.debug("Start Loop")

            pending = asyncio.Task.all_tasks()
            loop.run_until_complete(asyncio.gather(*pending))

            #
            # Now we are sutting down - perform and necessary cleanup
            #

            self.AD.terminate()

            self.logger.info("AppDaemon is stopped.")

        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error during run()")
            self.logger.warning('-' * 60, exc_info=True)
            self.logger.warning('-' * 60)

            self.logger.debug("End Loop")

            self.logger.info("AppDeamon Exited")



    # noinspection PyBroadException
    def main(self):

        # import appdaemon.stacktracer
        # appdaemon.stacktracer.trace_start("/tmp/trace.html")

        self.init_signals()

        # Get command line args

        parser = argparse.ArgumentParser()

        parser.add_argument("-c", "--config", help="full path to config directory", type=str, default=None)
        parser.add_argument("-p", "--pidfile", help="full path to PID File", default="/tmp/hapush.pid")
        parser.add_argument("-t", "--tick", help="time that a tick in the schedular lasts (seconds)", default=1, type=float)
        parser.add_argument("-s", "--starttime", help="start time for scheduler <YYYY-MM-DD HH:MM:SS>", type=str)
        parser.add_argument("-e", "--endtime", help="end time for scheduler <YYYY-MM-DD HH:MM:SS>", type=str, default=None)
        parser.add_argument("-i", "--interval", help="multiplier for scheduler tick", type=float, default=None)
        parser.add_argument("-D", "--debug", help="global debug level", default="INFO", choices=
                            [
                                "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
                            ])
        parser.add_argument('-m', '--moduledebug', nargs=2, action='append', help=argparse.SUPPRESS)
        parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + utils.__version__)
        parser.add_argument('--profiledash', help=argparse.SUPPRESS, action='store_true')

        args = parser.parse_args()

        config_dir = args.config

        if config_dir is None:
            config_file_yaml = utils.find_path("appdaemon.yaml")
        else:
            config_file_yaml = os.path.join(config_dir, "appdaemon.yaml")

        if config_file_yaml is None:
            print("FATAL: no configuration directory defined and defaults not present\n")
            parser.print_help()
            sys.exit(1)

        config = None

        module_debug = {}
        if args.moduledebug is not None:
            for arg in args.moduledebug:
                module_debug[arg[0]] = arg[1]

        #
        # First locate secrets file
        #
        try:

            #
            # Initially load file to see if secret directive is present
            #
            yaml.add_constructor('!secret', utils._dummy_secret)
            with open(config_file_yaml, 'r') as yamlfd:
                config_file_contents = yamlfd.read()

            config = yaml.load(config_file_contents)

            if "secrets" in config:
                secrets_file = config["secrets"]
            else:
                secrets_file = os.path.join(os.path.dirname(config_file_yaml), "secrets.yaml")

            #
            # Read Secrets
            #
            if os.path.isfile(secrets_file):
                with open(secrets_file, 'r') as yamlfd:
                    secrets_file_contents = yamlfd.read()

                utils.secrets = yaml.load(secrets_file_contents)

            else:
                if "secrets" in config:
                    print("ERROR", "Error loading secrets file: {}".format(config["secrets"]))
                    sys.exit()

            #
            # Read config file again, this time with secrets
            #
            yaml.add_constructor('!secret', utils._secret_yaml)

            with open(config_file_yaml, 'r') as yamlfd:
                config_file_contents = yamlfd.read()

            config = yaml.load(config_file_contents)

        except yaml.YAMLError as exc:
            print("ERROR", "Error loading configuration")
            if hasattr(exc, 'problem_mark'):
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

        if "tick" not in appdaemon:
            appdaemon["tick"] = args.tick

        if "interval" not in appdaemon:
            appdaemon["interval"] = args.interval

        appdaemon["loglevel"] = args.debug

        appdaemon["config_dir"] = os.path.dirname(config_file_yaml)

        appdaemon["stop_function"] = self.stop

        if "hadashboard" in config:
            hadashboard = config["hadashboard"]
            hadashboard["profile_dashboard"] = args.profiledash
            hadashboard["config_dir"] = config_dir
            hadashboard["config_file"] = config_file_yaml
            hadashboard["config_dir"] = os.path.dirname(config_file_yaml)
            if args.profiledash:
                hadashboard["profile_dashboard"] = True

            if "dashboard" not in hadashboard:
                hadashboard["dashboard"] = True

        else:
            hadashboard = {"dashboard": False}

        # Setup logging

        if "log" in config:
            print("ERROR", "'log' directive deprecated, please convert to new 'logs' syntax")
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
        self.logger.info("Configuration read from: %s", config_file_yaml)
        self.logging.dump_log_config()
        self.logger.debug("AppDaemon Section: %s", config.get("appdaemon"))
        self.logger.debug("HADashboard Section: %s", config.get("hadashboard"))

        utils.check_path("config_file", self.logging, config_file_yaml, pathtype="file")

        self.run(appdaemon, hadashboard)

def main():
    admain = ADMain()
    admain.main()

if __name__ == "__main__":
    main()