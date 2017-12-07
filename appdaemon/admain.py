#!/usr/bin/python3
from pkg_resources import parse_version
import sys
import traceback
import configparser
import argparse
import logging
import os
import os.path
from logging.handlers import RotatingFileHandler
import time
import datetime
import signal
import platform
from urllib.parse import urlparse
import yaml
import asyncio

import appdaemon.conf as confmodule
import appdaemon.utils as utils
import appdaemon.appdaemon as ad
import appdaemon.adapi as api
import appdaemon.rundash as rundash

# Windows does not have Daemonize package so disallow

#
# Empty class to store attributes
#
class Config():
    pass

class ADMain():

    def __init__(self):
        self.logger = None
        self.error = None

    # noinspection PyUnusedLocal
    def handle_sig(self, signum, frame):
        if signum == signal.SIGUSR1:
            self.AD.dump_schedule()
            self.AD.dump_callbacks()
            self.AD.dump_objects()
            self.AD.dump_queue()
            self.AD.dump_sun()
        if signum == signal.SIGHUP:
            self.AD.read_apps(True)
        if signum == signal.SIGINT:
            utils.log(self.logger, "INFO", "Keyboard interrupt")
            self.AD.stop()

    def find_path(self, name):
        for path in [os.path.join(os.path.expanduser("~"), ".homeassistant"),
                     os.path.join(os.path.sep, "etc", "appdaemon")]:
            _file = os.path.join(path, name)
            if os.path.isfile(_file) or os.path.isdir(_file):
                return _file
        return None

    # noinspection PyBroadException,PyBroadException
    def run(self):

        conf = self.conf
        tasks = []

        loop = asyncio.get_event_loop()

        # Initialize AppDaemon

        if conf.apps is True:
            utils.log(self.logger, "INFO", "Starting Apps")
            kwargs = conf.__dict__
            self.AD = ad.AppDaemon(self.logger, self.error, **kwargs)
            self.AD.run_ad(loop, tasks)
        else:
            utils.log(self.logger, "INFO", "Apps are disabled")

        # Initialize Dashboard/API

        if conf.dashboard is True:
            utils.log(self.logger, "INFO", "Starting dashboard")
            self.rundash = rundash.RunDash()
            self.rundash.run_dash(loop, tasks, conf)
        else:
            utils.log(self.logger, "INFO", "Dashboards are disabled")

        if conf.api_port is not None:
            utils.log(self.logger, "INFO", "Starting API")
            api.run_api(loop, tasks, conf)
        else:
            utils.log(self.logger, "INFO", "API is disabled")

        utils.log(self.logger, "DEBUG", "Start Loop")
        loop.run_until_complete(asyncio.wait(tasks))
        loop.close()
        utils.log(self.logger, "DEBUG", "End Loop")

        utils.log(self.logger, "INFO", "AppDeamon Exited")



    # noinspection PyBroadException
    def main(self):

        # import appdaemon.stacktracer
        # appdaemon.stacktracer.trace_start("/tmp/trace.html")

        # Windows does not support SIGUSR1 or SIGUSR2
        if platform.system() != "Windows":
            signal.signal(signal.SIGUSR1, self.handle_sig)
            signal.signal(signal.SIGINT, self.handle_sig)
            signal.signal(signal.SIGHUP, self.handle_sig)

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
        parser.add_argument('--commtype', help="Communication Library to use", default="WEBSOCKETS", choices=
                            [
                                "SSE",
                                "WEBSOCKETS"
                            ])
        parser.add_argument('--profiledash', help=argparse.SUPPRESS, action='store_true')
        parser.add_argument('--convertcfg', help="Convert existing .cfg file to yaml", action='store_true')

        # Windows does not have Daemonize package so disallow
        if platform.system() != "Windows":
            parser.add_argument("-d", "--daemon", help="run as a background process", action="store_true")

        args = parser.parse_args()

        conf = Config()

        conf.tick = args.tick
        conf.interval = args.interval
        conf.loglevel = args.debug
        conf.profile_dashboard = args.profiledash

        if args.starttime is not None:
            conf.now = datetime.datetime.strptime(args.starttime, "%Y-%m-%d %H:%M:%S").timestamp()
        else:
            conf.now = datetime.datetime.now().timestamp()

        if args.endtime is not None:
            conf.endtime = datetime.datetime.strptime(args.endtime, "%Y-%m-%d %H:%M:%S")

        if conf.tick != 1 or conf.interval != 1 or args.starttime is not None:
            conf.realtime = False

        config_dir = args.config

        conf.commtype = args.commtype

        if platform.system() != "Windows":
            from daemonize import Daemonize

        if platform.system() != "Windows":
            isdaemon = args.daemon
        else:
            isdaemon = False

        if config_dir is None:
            config_file_yaml = self.find_path("appdaemon.yaml")
        else:
            config_file_yaml = os.path.join(config_dir, "appdaemon.yaml")

        config = None

        #
        # First locate secrets file
        #
        try:

            secrets_file = os.path.join(os.path.dirname(config_file_yaml), "secrets.yaml")
            if os.path.isfile(secrets_file):
                with open(secrets_file, 'r') as yamlfd:
                    secrets_file_contents = yamlfd.read()

                confmodule.secrets = yaml.load(secrets_file_contents)

            yaml.add_constructor('!secret', utils._secret_yaml)

            conf.config_file = config_file_yaml
            conf.app_config_file = os.path.join(os.path.dirname(config_file_yaml), "apps.yaml")
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

        conf.config_dir = os.path.dirname(conf.config_file)
        conf.config = config
        conf.logfile = config['AppDaemon'].get("logfile")
        conf.errorfile = config['AppDaemon'].get("errorfile")
        conf.threads = int(config['AppDaemon'].get('threads'))
        conf.certpath = config['AppDaemon'].get("cert_path")
        conf.app_dir = config['AppDaemon'].get("app_dir")
        conf.latitude = config['AppDaemon'].get("latitude")
        conf.longitude = config['AppDaemon'].get("longitude")
        conf.elevation = config['AppDaemon'].get("elevation")
        conf.time_zone = config['AppDaemon'].get("time_zone")
        conf.rss_feeds = config['AppDaemon'].get("rss_feeds")
        conf.rss_update = config['AppDaemon'].get("rss_update")
        conf.utility_delay = config['AppDaemon'].get("utility_delay", 1)
        conf.api_key = config['AppDaemon'].get("api_key")
        conf.api_port = config['AppDaemon'].get("api_port")
        conf.api_ssl_certificate = config['AppDaemon'].get("api_ssl_certificate")
        conf.api_ssl_key = config['AppDaemon'].get("api_ssl_key")

        if 'HADashboard' in config:
            conf.dash_url = config['HADashboard'].get("dash_url")
            conf.dashboard_dir = config['HADashboard'].get("dash_dir")
            conf.dash_ssl_certificate = config['HADashboard'].get("dash_ssl_certificate")
            conf.dash_ssl_key = config['HADashboard'].get("dash_ssl_key")
            conf.dash_password = config['HADashboard'].get("dash_password")

            if config['HADashboard'].get("dash_force_compile") == "1":
                conf.dash_force_compile = True
            else:
                conf.dash_force_compile = False

            if config['HADashboard'].get("dash_compile_on_start") == "1":
                conf.dash_compile_on_start = True
            else:
                conf.dash_compile_on_start = False

            if "disable_dash" in config['HADashboard'] and config['HADashboard']["disable_dash"] == 1:
                conf.dashboard = False
            else:
                conf.dashboard = True

        if config['AppDaemon'].get("disable_apps") == "1":
            conf.apps = False
        else:
            conf.apps = True
            conf.plugins = {}
            for section in config:
                if section == "AppDaemon" or section == "HADashboard":
                    pass
                else:
                    conf.plugins[section] = config[section]


        if config['AppDaemon'].get("cert_verify", True) == False:
            conf.certpath = False

        if conf.dash_url is not None:
            url = urlparse(conf.dash_url)

            dash_net = url.netloc.split(":")
            conf.dash_host = dash_net[0]
            try:
                conf.dash_port = dash_net[1]
            except IndexError:
                conf.dash_port = 80

            if conf.dash_host == "":
                raise ValueError("Invalid host for 'dash_url'")

        if conf.threads is None:
            conf.threads = 10

        if conf.logfile is None:
            conf.logfile = "STDOUT"

        if conf.errorfile is None:
            conf.errorfile = "STDERR"

        log_size = config['AppDaemon'].get("log_size", 1000000)
        log_generations = config['AppDaemon'].get("log_generations", 3)

        if isdaemon and (
                            conf.logfile == "STDOUT" or conf.errorfile == "STDERR"
                            or conf.logfile == "STDERR" or conf.errorfile == "STDOUT"
                        ):
            raise ValueError("STDOUT and STDERR not allowed with -d")


        self.conf = conf

        # Setup Logging

        self.logger = logging.getLogger("log1")
        numeric_level = getattr(logging, args.debug, None)
        self.logger.setLevel(numeric_level)
        self.logger.propagate = False
        # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        # Send to file if we are daemonizing, else send to console

        fh = None
        if conf.logfile != "STDOUT":
            fh = RotatingFileHandler(conf.logfile, maxBytes=log_size, backupCount=log_generations)
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

        if conf.errorfile != "STDERR":
            efh = RotatingFileHandler(
                conf.errorfile, maxBytes=log_size, backupCount=log_generations
            )
        else:
            efh = logging.StreamHandler()

        efh.setLevel(numeric_level)
        # efh.setFormatter(formatter)
        self.error.addHandler(efh)

        # Setup dash output

        if config['AppDaemon'].get("accessfile") is not None:
            conf.dash = logging.getLogger("log3")
            numeric_level = getattr(logging, args.debug, None)
            conf.dash.setLevel(numeric_level)
            conf.dash.propagate = False
            # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
            efh = RotatingFileHandler(
                config['AppDaemon'].get("accessfile"), maxBytes=log_size, backupCount=log_generations
            )

            efh.setLevel(numeric_level)
            # efh.setFormatter(formatter)
            conf.dash.addHandler(efh)
        else:
            conf.dash = self.logger

        # Startup message

        utils.log(self.logger, "INFO", "AppDaemon Version {} starting".format(utils.__version__))
        utils.log(self.logger, "INFO", "Configuration read from: {}".format(conf.config_file))
        utils.log(self.logger, "DEBUG", "AppDaemon Section: {}".format(config.get("AppDaemon")))
        utils.log(self.logger, "DEBUG", "Hass Section: {}".format(config.get("HASS")))
        utils.log(self.logger, "DEBUG", "HADashboard Section: {}".format(config.get("HADashboard")))


        #TODO: Figure out how to get this from HASS if available

        # Now we have logging, warn about deprecated directives
        #if "latitude" in config['AppDaemon']:
        #    utils.verbose_log(self.logger, "WARNING", "'latitude' directive is deprecated, please remove")

        #if "longitude" in config['AppDaemon']:
        #    utils.verbose_log(self.logger, "WARNING", "'longitude' directive is deprecated, please remove")

        #if "timezone" in config['AppDaemon']:
        #    utils.verbose_log(self.logger, "WARNING", "'timezone' directive is deprecated, please remove")

        #if "time_zone" in config['AppDaemon']:
        #    utils.verbose_log(self.logger, "WARNING", "'time_zone' directive is deprecated, please remove")

        #ad.init_sun()

        # Add appdir  and subdirs to path
        if conf.apps is True:
            conf.app_config_file_modified = os.path.getmtime(conf.app_config_file)
            if conf.app_dir is None:
                if config_dir is None:
                    conf.app_dir = self.find_path("apps")
                else:
                    conf.app_dir = os.path.join(config_dir, "apps")
            for root, subdirs, files in os.walk(conf.app_dir):
                if root[-11:] != "__pycache__":
                    sys.path.insert(0, root)
        else:
            conf.app_config_file_modified = 0

        # find dashboard dir

        if conf.dashboard:
            if conf.dashboard_dir is None:
                if config_dir is None:
                    conf.dashboard_dir = self.find_path("dashboards")
                else:
                    conf.dashboard_dir = os.path.join(config_dir, "dashboards")


            #
            # Setup compile directories
            #
            if config_dir is None:
                conf.compile_dir = self.find_path("compiled")
            else:
                conf.compile_dir = os.path.join(config_dir, "compiled")

        # Start main loop

        if isdaemon:
            keep_fds = [fh.stream.fileno(), efh.stream.fileno()]
            pid = args.pidfile
            daemon = Daemonize(app="appdaemon", pid=pid, action=self.run,
                               keep_fds=keep_fds)
            daemon.start()
            while True:
                time.sleep(1)
        else:
            self.run()


if __name__ == "__main__":
    admain = ADMain()
    admain.main()
