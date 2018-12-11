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
        self.title = "AppDaemon Administrative Interface"
        #
        # Process any overrides
        #
        self._process_arg("javascript_dir", kwargs)
        self._process_arg("template_dir", kwargs)
        self._process_arg("css_dir", kwargs)
        self._process_arg("fonts_dir", kwargs)
        self._process_arg("images_dir", kwargs)
        self._process_arg("title", kwargs)

        self.transport = "ws"
        self._process_arg("transport", kwargs)

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    #
    # Methods
    #

    async def admin(self, scheme, url):

        try:
            params = {}

            params["transport"] = self.transport
            params["title"] = self.title

            # AppDaemon

            params["appdaemon"] = {}
            params["appdaemon"]["booted"] = self.AD.booted.replace(microsecond=0)
            params["appdaemon"]["version"] = utils.__version__

            # Logs

            params["logs"] = self.AD.logging.get_admin_logs()

            # Entities

            params["namespaces"] = self.AD.state.list_namespaces()

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

