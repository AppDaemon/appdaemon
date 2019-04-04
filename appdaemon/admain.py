#!/usr/bin/python3
from pkg_resources import parse_version
import sys
import argparse
import logging
import os
import os.path
from logging.handlers import RotatingFileHandler
import time
import signal
import platform
import yaml
import asyncio
import traceback

import appdaemon.utils as utils
import appdaemon.appdaemon as ad
import appdaemon.adapi as api
import appdaemon.rundash as rundash
import appdaemon.runadmin as runadmin

class ADMain():

    def __init__(self):
        self.logger = None
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
            self.AD.dump_schedule()
            self.AD.dump_callbacks()
            self.AD.dump_threads()
            self.AD.dump_objects()
            self.AD.dump_queue()
            self.AD.dump_sun()
        if signum == signal.SIGHUP:
            self.AD.check_app_updates(True)
        if signum == signal.SIGINT:
            self.log(self.logger, "INFO", "Keyboard interrupt")
            self.stop()
        if signum == signal.SIGTERM:
            self.log(self.logger, "INFO", "SIGTERM Recieved")
            self.stop()

    def stop(self):
        self.AD.stop()
        if self.rundash is not None:
            self.rundash.stop()
        if self.runadmin is not None:
            self.runadmin.stop()

    def log(self, logger, level, msg, name=""):
        utils.log(logger, level, msg, name)

    # noinspection PyBroadException,PyBroadException
    def run(self, appdaemon, hadashboard):

        try:
            loop = asyncio.get_event_loop()

            # Initialize AppDaemon

            self.AD = ad.AppDaemon(self.logger, self.error, self.diag, loop, **appdaemon)

            # Initialize Dashboard/API

            if hadashboard["dashboard"] is True:
                self.log(self.logger, "INFO", "Starting Dashboards")
                self.rundash = rundash.RunDash(self.AD, loop, self.logger, self.access, **hadashboard)
                self.AD.register_dashboard(self.rundash)
            else:
                self.log(self.logger, "INFO", "Dashboards are disabled")

            if "api_port" in appdaemon:
                self.log(self.logger, "INFO", "Starting API")
                self.api = api.ADAPI(self.AD, loop, self.logger, self.access, **appdaemon)
            else:
                self.log(self.logger, "INFO", "API is disabled")


            # Lets hide the admin interface for now

            #if "admin_port" in appdaemon:
            #    self.log(self.logger, "INFO", "Starting Admin Interface")
            #    self.runadmin = runadmin.RunAdmin(self.AD, loop, self.logger, self.access, **appdaemon)
            #else:
            #    self.log(self.logger, "INFO", "Admin Interface is disabled")

            self.log(self.logger, "DEBUG", "Start Loop")

            pending = asyncio.Task.all_tasks()
            loop.run_until_complete(asyncio.gather(*pending))
        except:
            self.log(self.logger, "WARNING", '-' * 60)
            self.log(self.logger, "WARNING", "Unexpected error during run()")
            self.log(self.logger, "WARNING", '-' * 60)
            self.log(self.logger, "WARNING", traceback.format_exc())
            self.log(self.logger, "WARNING", '-' * 60)

        self.log(self.logger, "DEBUG", "End Loop")

        self.log(self.logger, "INFO", "AppDeamon Exited")



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
        parser.add_argument("-i", "--interval", help="multiplier for scheduler tick", type=float, default=1)
        parser.add_argument("-D", "--debug", help="debug level", default="INFO", choices=
                            [
                                "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
                            ])
        parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + utils.__version__)
        parser.add_argument('--profiledash', help=argparse.SUPPRESS, action='store_true')

        # Windows does not have Daemonize package so disallow
        if platform.system() != "Windows":
            parser.add_argument("-d", "--daemon", help="run as a background process", action="store_true")

        args = parser.parse_args()

        config_dir = args.config

        if platform.system() != "Windows":
            from daemonize import Daemonize

        if platform.system() != "Windows":
            isdaemon = args.daemon
        else:
            isdaemon = False

        if config_dir is None:
            config_file_yaml = utils.find_path("appdaemon.yaml")
        else:
            config_file_yaml = os.path.join(config_dir, "appdaemon.yaml")

        if config_file_yaml is None:
            print("FATAL: no configuration directory defined and defaults not present\n")
            parser.print_help()
            sys.exit(1)

        config = None

        #
        # First locate secrets file
        #
        try:

            #
            # Initially load file to see if secret directive is present
            #
            yaml.add_constructor('!secret', utils._dummy_secret, Loader=yaml.SafeLoader)
            with open(config_file_yaml, 'r') as yamlfd:
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
                with open(secrets_file, 'r') as yamlfd:
                    secrets_file_contents = yamlfd.read()

                utils.secrets = yaml.load(secrets_file_contents, Loader=yaml.SafeLoader)

            else:
                if "secrets" in config:
                    print("ERROR", "Error loading secrets file: {}".format(config["secrets"]))
                    sys.exit()

            #
            # Read config file again, this time with secrets
            #
            yaml.add_constructor('!secret', utils._secret_yaml, Loader=yaml.SafeLoader)

            with open(config_file_yaml, 'r') as yamlfd:
                config_file_contents = yamlfd.read()

            config = yaml.load(config_file_contents, Loader=yaml.SafeLoader)

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


        if args.starttime is not None:
            appdaemon["starttime"] = args.starttime

        if args.endtime is not None:
            appdaemon["endtime"] = args.endtime

        appdaemon["tick"] = args.tick
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

        if isdaemon and (
                            logfile == "STDOUT" or errorfile == "STDERR"
                            or logfile == "STDERR" or errorfile == "STDOUT"
                        ):
            print("ERROR", "STDOUT and STDERR not allowed with -d")
            sys.exit()

        # Setup Logging

        self.logger = logging.getLogger("log1")
        numeric_level = getattr(logging, args.debug, None)
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
        numeric_level = getattr(logging, args.debug, None)
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

        self.diag = logging.getLogger("log3")
        numeric_level = getattr(logging, args.debug, None)
        self.diag.setLevel(numeric_level)
        self.diag.propagate = False
        # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        if diagfile != "STDOUT":
            dfh = RotatingFileHandler(
                diagfile, maxBytes=log_size, backupCount=log_generations
            )
        else:
            dfh = logging.StreamHandler()

        dfh.setLevel(numeric_level)
        # dfh.setFormatter(formatter)
        self.diag.addHandler(dfh)

        # Setup dash output
        if accessfile is not None:
            self.access = logging.getLogger("log4")
            numeric_level = getattr(logging, args.debug, None)
            self.access.setLevel(numeric_level)
            self.access.propagate = False
            # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
            efh = RotatingFileHandler(
                config['log'].get("accessfile"), maxBytes=log_size, backupCount=log_generations
            )

            efh.setLevel(numeric_level)
            # efh.setFormatter(formatter)
            self.access.addHandler(efh)
        else:
            self.access = self.logger

        # Startup message

        self.log(self.logger, "INFO", "AppDaemon Version {} starting".format(utils.__version__))
        self.log(self.logger, "INFO", "Configuration read from: {}".format(config_file_yaml))
        self.log(self.logger, "DEBUG", "AppDaemon Section: {}".format(config.get("AppDaemon")))
        self.log(self.logger, "DEBUG", "HADashboard Section: {}".format(config.get("HADashboard")))

        utils.check_path("config_file", self.logger, config_file_yaml, pathtype="file")

        if isdaemon:
            keep_fds = [fh.stream.fileno(), efh.stream.fileno()]
            pid = args.pidfile
            daemon = Daemonize(app="appdaemon", pid=pid, action=self.run,
                               keep_fds=keep_fds)
            daemon.start()
            while True:
                time.sleep(1)
        else:
            self.run(appdaemon, hadashboard)

def main():
    admain = ADMain()
    admain.main()

if __name__ == "__main__":
    main()