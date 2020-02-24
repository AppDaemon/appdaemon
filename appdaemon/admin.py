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
        self.javascript_dir = None
        self.template_dir = None
        self.css_dir = None
        self.fonts_dir = None
        self.images_dir = None
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

    async def admin_page(self, scheme, url):

        try:
            params = {"transport": self.transport, "title": self.title}

            if self.AD.http.dashboard_obj is not None:
                params["dashboard"] = True
            else:
                params["dashboard"] = False

            # Logs

            params["logs"] = await self.AD.logging.get_admin_logs()

            # Entities

            params["namespaces"] = await self.AD.state.list_namespaces()

            env = Environment(
                loader=FileSystemLoader(self.template_dir), autoescape=select_autoescape(["html", "xml"]),
            )

            template = env.get_template("admin.jinja2")
            rendered_template = await utils.run_in_executor(self, template.render, params)

            return rendered_template

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error creating admin page")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
