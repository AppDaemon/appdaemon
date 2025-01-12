import threading
from functools import wraps
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List

import appdaemon.adapi as adapi
import appdaemon.utils as utils
from appdaemon.logging import Logging
from appdaemon.models.app_config import AppConfig

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon

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
    config_model: AppConfig

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

    _logging: Logging
    logger: Logger
    err: Logger

    lock: threading.RLock
    user_logs: Dict
    constraints: List

    def __init__(self, ad: "AppDaemon", config_model: AppConfig):
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
        self._namespace = new

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
    def _logging(self) -> Logging:
        return self.AD.logging

    @property
    def name(self) -> str:
        return self.config_model.name

    #
    # API/Plugin
    #

    def get_ad_api(self) -> adapi.ADAPI:
        return adapi.ADAPI(self.AD, self.config_model)

    @utils.sync_decorator
    async def get_plugin_api(self, plugin_name: str) -> Callable:
        return await self.AD.plugins.get_plugin_api(
            plugin_name,
            self.name,
            self._logging,
            self.args,
            self.config_model,
            self.app_config,
            self.global_vars,
        )

    #
    # Constraints
    #

    def register_constraint(self, name: str) -> None:
        self.constraints.append(name)

    def deregister_constraint(self, name: str) -> None:
        self.constraints.remove(name)
