import threading
from functools import wraps
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List

from . import adapi, utils

if TYPE_CHECKING:
    from .appdaemon import AppDaemon
    from .logging import Logging
    from .models.config.app import AppConfig


#
# Locking decorator
#
def app_lock(f):
    """Synchronization decorator."""

    @wraps(f)
    def f_app_lock(*args, **kw):
        self = args[0]

        self.lock.acquire()
        try:
            return f(*args, **kw)
        finally:
            self.lock.release()

    return f_app_lock


def global_lock(f):
    """Synchronization decorator."""

    @wraps(f)
    def f_global_lock(*args, **kw):
        self = args[0]

        self.AD.global_lock.acquire()
        try:
            return f(*args, **kw)
        finally:
            self.AD.global_lock.release()

    return f_global_lock


class ADBase:
    AD: "AppDaemon"
    config_model: "AppConfig"

    config: Dict
    """Dictionary of the AppDaemon configuration
    """
    args: Dict
    """Dictionary of the app configuration
    """

    name: str
    namespace: str

    app_dir: Path
    config_dir: Path

    _logging: "Logging"
    logger: Logger
    err: Logger

    lock: threading.RLock
    user_logs: Dict
    constraints: List

    def __init__(self, ad: "AppDaemon", config_model: "AppConfig"):
        self.AD = ad
        self.config_model = config_model

        self.config = self.AD.config.model_dump(by_alias=True, exclude_unset=True)
        self.args = self.config_model.model_dump(by_alias=True, exclude_unset=True)

        self.namespace = "default"
        self.dashboard_dir = None

        if self.AD.http is not None:
            self.dashboard_dir = self.AD.http.dashboard_dir

        self.logger = self._logging.get_child(self.name)
        self.err = self._logging.get_error().getChild(self.name)
        self.user_logs = {}
        if lvl := config_model.log_level:
            self.logger.setLevel(lvl)
            self.err.setLevel(lvl)

        # Some initial Setup

        self.lock = threading.RLock()

        self.constraints = list()

    @property
    def namespace(self) -> str:
        return self._namespace

    @namespace.setter
    def namespace(self, new: str):
        if not self.AD.state.namespace_exists(new):
            self.logger.warning(f"Namespace '{new}' does not exist, setting the namespace for app '{self.name}' anyway")

        self._namespace = new

        # NOTE: This gets called as a side effect of the __init__ method, so the
        # self._plugin attribute should always be available
        self._plugin = self.AD.plugins.get_plugin_object(self.namespace)
        # Sometimes this will be None. Namespaces are not guaranteed to be associated with a plugin

    @property
    def app_config(self):
        return self.AD.app_management.app_config

    @property
    def app_dir(self) -> Path:
        return self.AD.app_dir

    @property
    def config_dir(self) -> Path:
        return self.AD.config_dir

    @property
    def global_vars(self):
        return self.AD.global_vars

    @property
    def _logging(self) -> "Logging":
        return self.AD.logging

    @property
    def name(self) -> str:
        return self.config_model.name

    #
    # API/Plugin
    #

    def get_ad_api(self) -> adapi.ADAPI:
        return adapi.ADAPI(self.AD, self.config_model)

    def get_plugin_api(self, plugin_name: str):
        app_cfg = self.app_config.root[self.name]
        plugin_api = self.AD.plugins.get_plugin_api(plugin_name, app_cfg)
        return plugin_api

    #
    # Constraints
    #

    def register_constraint(self, name: str) -> None:
        self.constraints.append(name)

    def deregister_constraint(self, name: str) -> None:
        self.constraints.remove(name)
