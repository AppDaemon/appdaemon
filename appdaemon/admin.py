import os
import ast
import re
import yaml
from jinja2 import Environment, BaseLoader, FileSystemLoader, select_autoescape
import traceback
import functools
import time
import cProfile
import io
import pstats
import datetime

import appdaemon.utils as ha


class Admin:

    def __init__(self, config_dir, logger, **kwargs):
        #
        # Set Defaults
        #
        self.config_dir = config_dir
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

    def index(self):

        params = {}

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
