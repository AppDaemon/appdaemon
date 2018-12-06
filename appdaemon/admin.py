import os
import traceback

from jinja2 import Environment, FileSystemLoader, select_autoescape

import appdaemon.utils as utils

from appdaemon.appdaemon import AppDaemon


class Admin:

    def __init__(self, config_dir, logger, ad: AppDaemon, **kwargs):
        #
        # Set Defaults
        #
        self.config_dir = config_dir
        self.AD = ad
        self.logger = self.logger = ad.logging.get_child("_admin")
        self.dash_install_dir = os.path.dirname(__file__)
        self.javascript_dir = os.path.join(self.dash_install_dir, "assets", "javascript")
        self.template_dir = os.path.join(self.dash_install_dir, "assets", "templates")
        self.css_dir = os.path.join(self.dash_install_dir, "assets", "css")
        self.fonts_dir = os.path.join(self.dash_install_dir, "assets", "fonts")
        self.images_dir = os.path.join(self.dash_install_dir, "assets", "images")
        self.base_url = ""
        #
        # Process any overrides
        #
        self._process_arg("javascript_dir", kwargs)
        self._process_arg("template_dir", kwargs)
        self._process_arg("css_dir", kwargs)
        self._process_arg("fonts_dir", kwargs)
        self._process_arg("images_dir", kwargs)

        self.transport = "ws"
        self._process_arg("transport", kwargs)

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    #
    # Methods
    #

    def admin(self, scheme, url):

        try:
            params = {}

            params["transport"] = self.transport

            # AppDaemon

            params["appdaemon"] = {}
            params["appdaemon"]["booted"] = self.AD.booted.replace(microsecond=0)
            params["appdaemon"]["version"] = utils.__version__

            # Apps

            params["apps"] = {}
            app_config = self.AD.app_management.app_config
            for app in app_config:
                params["apps"][app] = {}

                if "disabled" in app_config[app] and app_config[app][app]["disabled"] is True:
                    params["apps"][app]["disabled"] = True
                else:
                    params["apps"][app]["disabled"] = False

                params["apps"][app]["debug"] = self.AD.app_management.get_app_debug_level(app)

            # Plugins

            params["plugins"] = {}
            for plug in self.AD.plugins.plugin_objs:
                params["plugins"][plug] = \
                    {
                        "name": self.AD.plugins.plugin_objs[plug]["object"].name,
                        "type": self.AD.plugins.plugin_objs[plug]["object"].__class__.__name__,
                        "namespace": self.AD.plugins.plugin_objs[plug]["object"].namespace,
                    }

            # Threads

            params["threads"] = self.AD.threading.get_thread_info()

            # Callbacks

            params["callback_updates"] = self.AD.threading.get_callback_update()
            params["state_callbacks"] = self.AD.callbacks.get_callback_entries("state")
            params["event_callbacks"] = self.AD.callbacks.get_callback_entries("event")
            params["sched"] = self.AD.sched.get_scheduler_entries()

            # Logs

            params["logs"] = self.AD.logging.get_admin_logs()

            # Entities

            params["entities"] = {}

            for ns in sorted(self.AD.state.get_namespaces()):
                params["entities"][ns] = self.AD.state.get_state(ns, None, None, None)
                print(params["entities"][ns])
            #
            # Render Page
            #

            env = Environment(
                loader=FileSystemLoader(self.template_dir),
                autoescape=select_autoescape(['html', 'xml'])
            )

            template = env.get_template("admin.jinja2")
            rendered_template = template.render(params)

            return (rendered_template)

        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error in admin thread")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)

