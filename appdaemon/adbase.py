import threading
from functools import wraps
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any

from appdaemon import adapi
from appdaemon import utils
from appdaemon.models.config.app import AppConfig, AllAppConfig


# Check if the module is being imported using the legacy method
if __name__ == Path(__file__).name:
    from appdaemon.logging import Logging

    # It's possible to instantiate the Logging system again here because it's a singleton, and it will already have been
    # created at this point if the legacy import method is being used by an app. Using this accounts for the user maybe
    # having configured the error logger to use a different name than 'Error'
    Logging().get_error().warning(
        "Importing 'adbase' directly is deprecated and will be removed in a future version. "
        "To use the ADBase use 'from appdaemon import adbase' instead.",
    )


if TYPE_CHECKING:
    from .appdaemon import AppDaemon
    from .logging import Logging


class Entities:  # @todo
    def __init__(self):
        pass

    def __get__(self, instance, owner):
        stateattrs = utils.StateAttrs(instance.get_state())
        return stateattrs


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
    config: dict
    """Dictionary of the AppDaemon configuration
    """
    args: dict
    """Dictionary of the app configuration
    """

    _namespace: str

    logger: Logger
    err: Logger

    lock: threading.RLock
    user_logs: dict
    constraints: list

    entities = Entities()

    def __init__(self, ad: "AppDaemon", config_model: "AppConfig"):
        self.AD = ad
        self.config_model = config_model
        self.config = self.AD.config.model_dump(by_alias=True, exclude_unset=True)
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

        # NOTE: This gets called as a side effect of the __init__ method, so the self._plugin attribute should always
        # be available
        self._plugin = self.AD.plugins.get_plugin_object(self.namespace)
        # Sometimes this will be None. Namespaces are not guaranteed to be associated with a plugin

    @property
    def app_config(self) -> AllAppConfig:
        """The full app configuration model for all the apps."""
        return self.AD.app_management.app_config

    @app_config.setter
    def app_config(self, new_config: AppConfig) -> None:
        self.logger.warning("The full app configuration model is read-only")

    @property
    def config_model(self) -> AppConfig:
        """The AppConfig model only for this app."""
        return self._config_model

    @config_model.setter
    def config_model(self, new_config: Any) -> None:
        match new_config:
            case AppConfig():
                self._config_model = new_config
            case _:
                self._config_model = AppConfig.model_validate(new_config)
        self.args = self._config_model.model_dump(by_alias=True, exclude_unset=True)

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

    @utils.sync_decorator
    async def get_plugin_api(self, plugin_name: str):
        """Get the plugin API for a specific plugin."""
        if isinstance(cfg := self.app_config.root.get(self.name), AppConfig):
            return self.AD.plugins.get_plugin_api(plugin_name, cfg)
        self.logger.warning("No plugin API available for app '%s'", self.name)

    #
    # Constraints
    #

    def register_constraint(self, name: str) -> None:
        self.constraints.append(name)

    def deregister_constraint(self, name: str) -> None:
        self.constraints.remove(name)
