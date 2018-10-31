import os

from jinja2 import Environment, BaseLoader, FileSystemLoader, select_autoescape

import datetime

import appdaemon.utils as ha


class Admin:

    def __init__(self, config_dir, logger, AD, **kwargs):
        #
        # Set Defaults
        #
        self.config_dir = config_dir
        self.AD = AD
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
        self._process_arg("dashboard_dir", kwargs)
        self._process_arg("javascript_dir", kwargs)
        self._process_arg("template_dir", kwargs)
        self._process_arg("css_dir", kwargs)
        self._process_arg("fonts_dir", kwargs)
        self._process_arg("images_dir", kwargs)
        #
        # Create some dirs
        #

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    #
    # Methods
    #

    def appdaemon(self, scheme, url):
        print("appdaemon")
        return self.index(scheme, url, "appdaemon")

    def apps(self, scheme, url):
        return self.index(scheme, url, "apps")

    def plugins(self, scheme, url):
        return self.index(scheme, url, "plugins")

    def index(self, scheme, url, tab="appdaemon"):

        params = {}

        params["tab"] = tab

        params["appdaemon"] = {}
        params["appdaemon"]["booted"] = self.AD.booted

        params["apps"] = {}
        for obj in self.AD.objects:
            params["apps"][obj] = {}

        params["plugins"] = {}
        for plug in self.AD.plugin_objs:
            params["plugins"][plug] = \
                {
                    "name": self.AD.plugin_objs[plug].name,
                    "type": self.AD.plugin_objs[plug].__class__.__name__,
                    "namespace": self.AD.plugin_objs[plug].namespace,
                }

        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        template = env.get_template("adminindex.jinja2")
        rendered_template = template.render(params)

        return (rendered_template)

    def logon(self):

        params = {}

        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        template = env.get_template("adminlogon.jinja2")
        rendered_template = template.render(params)

        return (rendered_template)
