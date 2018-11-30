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
        self.logger = logger
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

    def appdaemon(self, scheme, url):
        return self.index(scheme, url, "appdaemon")

    def apps(self, scheme, url):
        return self.index(scheme, url, "apps")

    def plugins(self, scheme, url):
        return self.index(scheme, url, "plugins")

    def index(self, scheme, url, tab="appdaemon"):

        try:
            params = {}

            params["tab"] = tab
            params["transport"] = self.transport

            params["appdaemon"] = {}
            params["appdaemon"]["booted"] = self.AD.booted.replace(microsecond=0)
            params["appdaemon"]["version"] = utils.__version__

            params["apps"] = {}
            for obj in self.AD.app_management.objects:
                params["apps"][obj] = {}

            params["plugins"] = {}
            for plug in self.AD.plugins.plugin_objs:
                params["plugins"][plug] = \
                    {
                        "name": self.AD.plugins.plugin_objs[plug]["object"].name,
                        "type": self.AD.plugins.plugin_objs[plug]["object"].__class__.__name__,
                        "namespace": self.AD.plugins.plugin_objs[plug]["object"].namespace,
                    }

            params["threads"] = self.AD.threading.get_thread_info()

            params["callback_updates"] = self.AD.threading.get_callback_update()
            params["state_callbacks"] = self.AD.callbacks.get_callback_entries("state")
            params["event_callbacks"] = self.AD.callbacks.get_callback_entries("event")

            params["sched"] = self.AD.sched.get_scheduler_entries()
            #
            # Render Page
            #

            env = Environment(
                loader=FileSystemLoader(self.template_dir),
                autoescape=select_autoescape(['html', 'xml'])
            )

            template = env.get_template("adminindex.jinja2")
            rendered_template = template.render(params)

            return (rendered_template)

        except:
            self.AD.logging.log("WARNING", '-' * 60)
            self.AD.logging.log("WARNING", "Unexpected err in admin thread")
            self.AD.logging.log("WARNING", '-' * 60)
            self.AD.logging.log("WARNING", traceback.format_exc())
            self.AD.logging.log("WARNING", '-' * 60)

    def logon(self):

        params = {}

        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        template = env.get_template("adminlogon.jinja2")
        rendered_template = template.render(params)

        return (rendered_template)
