import asyncio
import datetime as dt
import functools
import inspect
import logging
import re
import sys
import uuid
from collections.abc import Callable, Coroutine, Iterable, Mapping
from concurrent.futures import Future
from copy import deepcopy
from datetime import timedelta
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

from appdaemon import dependency, utils
from appdaemon import exceptions as ade
from appdaemon.appdaemon import AppDaemon
from appdaemon.models.config.app import AppConfig
from appdaemon.entity import Entity
from appdaemon.events import EventCallback
from appdaemon.logging import Logging
from appdaemon.state import StateCallback

T = TypeVar("T")


# Check if the module is being imported using the legacy method
if __name__ == Path(__file__).name:
    from appdaemon.logging import Logging

    # It's possible to instantiate the Logging system again here because it's a singleton, and it will already have been
    # created at this point if the legacy import method is being used by an app. Using this accounts for the user maybe
    # having configured the error logger to use a different name than 'Error'
    Logging().get_error().warning(
        "Importing 'adapi' directly is deprecated and will be removed in a future version. To use the ADAPI use 'from appdaemon import adapi' instead.",
    )


if TYPE_CHECKING:
    from .models.config.app import AppConfig
    from .plugin_management import PluginBase


class ADAPI:
    """AppDaemon API class.

    This class includes all native API calls to AppDaemon

    """

    AD: AppDaemon
    """Reference to the top-level AppDaemon container object
    """
    config_model: "AppConfig"
    """Pydantic model of the app configuration
    """
    config: dict[str, Any]
    """Dict of the AppDaemon configuration. This meant to be read-only, and modifying it won't affect any behavior.
    """
    app_config: dict[str, dict[str, Any]]
    """Dict of the full config for all apps. This meant to be read-only, and modifying it won't affect any behavior.
    """
    args: dict[str, Any]
    """Dict of this app's configuration. This meant to be read-only, and modifying it won't affect any behavior.
    """
    logger: Logger
    err: Logger
    user_logs: dict[str, Logger]

    constraints: list[dict]

    namespace: str
    _plugin: "PluginBase"

    def __init__(self, ad: AppDaemon, config_model: "AppConfig"):
        self.AD = ad
        self.config_model = config_model
        self.dashboard_dir = None

        if self.AD.http is not None:
            self.dashboard_dir = self.AD.http.dashboard_dir

        self.namespace = "default"
        self.logger = self._logging.get_child(self.name)
        self.err = self._logging.get_error().getChild(self.name)

        if lvl := config_model.log_level:
            self.logger.setLevel(lvl)
            self.err.setLevel(lvl)

        self.user_logs = {}
        if log_name := config_model.log:
            if user_log := self.get_user_log(log_name):
                self.logger = user_log

        self.constraints = []
        self.dialogflow_v = 2

    @staticmethod
    def _sub_stack(msg):
        # If msg is a data structure of some type, don't sub
        if isinstance(msg, str):
            stack = inspect.stack()
            if msg.find("__module__") != -1:
                msg = msg.replace("__module__", stack[2][1])
            if msg.find("__line__") != -1:
                msg = msg.replace("__line__", str(stack[2][2]))
            if msg.find("__function__") != -1:
                msg = msg.replace("__function__", stack[2][3])
        return msg

    def _get_namespace(self, **kwargs):
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]
            del kwargs["namespace"]
        else:
            namespace = self._namespace

        return namespace

    #
    # Properties
    #

    @property
    def app_dir(self) -> Path:
        """Top-level path to where AppDaemon looks for user's apps. Defaults to ``./apps`` relative to the config
        directory, but can be overridden in ``appdaemon.app_dir`` in the ``appdaemon.yaml`` file."""
        return self.AD.app_dir

    @app_dir.setter
    def app_dir(self, value: Path) -> None:
        self.logger.warning('app_dir is read-only and needs to be set before AppDaemon starts')

    @property
    def callback_counter(self) -> int:
        return self.AD.app_management.objects[self.name].callback_counter

    @callback_counter.setter
    def callback_counter(self, value: Path) -> None:
        self.logger.warning('callback_counter is read-only and is set internally by AppDaemon')

    @property
    def config_dir(self) -> Path:
        """Directory that contains the ``appdaemon.yaml`` file."""
        return self.AD.config_dir

    @config_dir.setter
    def config_dir(self, value: Path) -> None:
        self.logger.warning('config_dir is read-only and needs to be set before AppDaemon starts')

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
    def global_vars(self) -> Any:
        """Globally locked attribute that can be used to share data between apps."""
        with self.AD.global_lock:
            return self.AD.global_vars

    @global_vars.setter
    def global_vars(self, value: Any) -> None:
        with self.AD.global_lock:
            self.AD.global_vars = Any

    @property
    def _logging(self) -> Logging:
        """Reference to the AppDaemon Logging subsystem object."""
        return self.AD.logging

    @_logging.setter
    def _logging(self, value: Logging) -> None:
        self.logger.warning('The _logging property is read-only')

    @property
    def name(self) -> str:
        """The name for the app, as defined by it's key in the corresponding YAML file."""
        return self.config_model.name

    @name.setter
    def name(self, value: str) -> None:
        self.logger.warning("The name property is read-only and is defined by the app's key in the YAML file")

    @property
    def plugin_config(self) -> dict:
        self.get_plugin_config()
        return self.AD.plugins.config

    @plugin_config.setter
    def plugin_config(self, value: dict) -> None:
        self.logger.warning("The plugin_config property is read-only and is set by the plugin itself")

    #
    # Logging
    #

    def _log(
        self, logger: Logger, msg: str, level: str | int = "INFO", *args, ascii_encode: bool = True, stack_info: bool = False, stacklevel: int = 1, extra: Mapping[str, object] | None = None, **kwargs
    ) -> None:
        if ascii_encode:
            msg = str(msg).encode("utf-8", "replace").decode("ascii", "replace")

        match level:
            case str():
                level = logging._nameToLevel[level]
            case int():
                assert level in logging._levelToName

        extra = extra or {}
        extra = dict(extra) if not isinstance(extra, dict) else extra
        extra.update(kwargs)
        logger.log(level, msg, *args, stack_info=stack_info, stacklevel=stacklevel, extra=extra)

    def log(
        self,
        msg: str,
        *args,
        level: str | int = "INFO",
        log: str | None = None,
        ascii_encode: bool | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None,
        **kwargs,
    ) -> None:
        """Logs a message to AppDaemon's main logfile.

        Args:
            msg (str): The message to log.
            level (str, optional): String representing the standard logger levels. Defaults to ``INFO``.
            log (str, optional): Send the message to a specific log, either system or user_defined. System logs are
                ``main_log``, ``error_log``, ``diag_log`` or ``access_log``. Any other value in use here must have a
                corresponding user-defined entity in the ``logs`` section of appdaemon.yaml.
            ascii_encode (bool, optional): Switch to disable the encoding of all log messages to ascii. Set this to
                false if you want to log UTF-8 characters (Default is controlled by ``appdaemon.ascii_encode``, and is
                True unless modified).
            stack_info (bool, optional): If ``True`` the stack info will included.
            stacklevel (int, optional): Defaults to 1.
            extra (dict, optional): Extra values to add to the log record

        Returns:
            None.

        Examples:
            Log a message to the main logfile of the system.

            >>> self.log("Log Test: Parameter is %s", some_variable)

            Log a message to the specified logfile.

            >>> self.log("Log Test: Parameter is %s", some_variable, log="test_log")

            Log a message with error-level to the main logfile of the system.

            >>> self.log("Log Test: Parameter is %s", some_variable, level = "ERROR")

            Log a message using `placeholders` to the main logfile of the system.

            >>> self.log("Line: __line__, module: __module__, function: __function__, Msg: Something bad happened")

            Log a WARNING message (including the stack info) to the main logfile of the system.

            >>> self.log("Stack is", some_value, level="WARNING", stack_info=True)

        """
        # Its a user defined log
        logger = self.logger if log is None else self.get_user_log(log)

        if ascii_encode is None:
            ascii_encode = self.AD.config.ascii_encode

        kwargs = dict(ascii_encode=ascii_encode, stack_info=stack_info, stacklevel=stacklevel, extra=extra, **kwargs)

        try:
            msg = self._sub_stack(msg)
        except IndexError as i:
            self._log(self.err, str(i), "ERROR", *args, **kwargs)

        self._log(logger, msg, level, *args, **kwargs)

    def error(self, msg: str, *args, level: str | int = "INFO", ascii_encode: bool = True, stack_info: bool = False, stacklevel: int = 1, extra: Mapping[str, object] | None = None, **kwargs) -> None:
        """Logs a message to AppDaemon's error logfile.

        Args:
            msg (str): The message to log.
            *args: Positional arguments for populating the msg fields
            level (str, optional): String representing the standard logger levels. Defaults to ``INFO``.
            ascii_encode (bool, optional): Switch to disable the encoding of all log messages to ascii. Set this to
                false if you want to log UTF-8 characters (Default: ``True``).
            stack_info (bool, optional): If ``True`` the stack info will included.
            **kwargs: Keyword arguments

        Returns:
            None.

        Examples:
            Log an error message to the error logfile of the system.

            >>> self.error("Some Warning string")

            Log an error message with critical-level to the error logfile of the system.

            >>> self.error("Some Critical string", level = "CRITICAL")

        """
        self._log(self.err, msg, level, *args, ascii_encode=ascii_encode or self.AD.config.ascii_encode, stack_info=stack_info, stacklevel=stacklevel, extra=extra, **kwargs)

    @utils.sync_decorator
    async def listen_log(
        self, callback: Callable, level: str | int = "INFO", namespace: str = "admin", log: str | None = None, pin: bool | None = None, pin_thread: int | None = None, **kwargs
    ) -> list[str] | None:
        """Register a callback for whenever an app logs a message.

        Args:
            callback: Function that will be called when a message is logged. It must conform to the standard event
                callback format documented `here <APPGUIDE.html#event-callbacks>`__
            level (str, optional): Minimum level for logs to trigger the callback. Lower levels will be ignored. Default
                is ``INFO``.
            namespace (str, optional): Namespace to use for the call. Defaults to ``admin`` for log callbacks. See the
                `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.
            log (str, optional): Name of the log to listen to, default is all logs. The name should be one of the 4
                built in types ``main_log``, ``error_log``, ``diag_log`` or ``access_log`` or a user defined log entry.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number. The ID numbers start at 0 and go through (number of threads - 1).
            **kwargs (optional): One or more keyword arguments to supply to the callback.

        Returns:
            A handle that can be used to cancel the callback.

        Examples:
            Listen to all ``WARNING`` log messages of the system.

            >>> self.handle = self.listen_log(self.cb, "WARNING")

            Sample callback:

            >>> def log_message(self, name, ts, level, type, message, kwargs):

            Listen to all ``WARNING`` log messages of the `main_log`.

            >>> self.handle = self.listen_log(self.cb, "WARNING", log="main_log")

            Listen to all ``WARNING`` log messages of a user-defined logfile.

            >>> self.handle = self.listen_log(self.cb, "WARNING", log="my_custom_log")

        """
        return await self.AD.logging.add_log_callback(namespace=namespace, name=self.name, callback=callback, level=level, log=log, pin=pin, pin_thread=pin_thread, **kwargs)

    @utils.sync_decorator
    async def cancel_listen_log(self, handle: str) -> None:
        """Cancels the log callback for the App.

        Args:
            handle: The handle returned when the `listen_log` call was made.

        Returns:
            Boolean.

        Examples:
              >>> self.cancel_listen_log(handle)

        """
        self.logger.debug("Canceling listen_log for %s", self.name)
        await self.AD.logging.cancel_log_callback(self.name, handle)

    def get_main_log(self) -> Logger:
        """Returns the underlying logger object used for the main log.

        Examples:
            Log a critical message to the `main` logfile of the system.

            >>> log = self.get_main_log()
            >>> log.critical("Log a critical error")

        """
        return self.logger

    def get_error_log(self) -> Logger:
        """Returns the underlying logger object used for the error log.

        Examples:
            Log an error message to the `error` logfile of the system.

            >>> error_log = self.get_error_log()
            >>> error_log.error("Log an error", stack_info=True, exc_info=True)

        """
        return self.err

    def get_user_log(self, log: str) -> Logger:
        """Gets the specified-user logger of the App.

        Args:
            log (str): The name of the log you want to get the underlying logger object from, as described in the
                ``logs`` section of ``appdaemon.yaml``.

        Returns:
            The underlying logger object used for the error log.

        Examples:
            Log an error message to a user-defined logfile.

            >>> log = self.get_user_log("test_log")
            >>> log.error("Log an error", stack_info=True, exc_info=True)

        """

        if (logger := self.user_logs.get(log)) is None:
            # Build it on the fly
            if (parent := self.AD.logging.get_user_log(self, log)) is not None:
                logger = parent.getChild(self.name)
                self.user_logs[log] = logger
                if "log_level" in self.args:
                    logger.setLevel(self.args["log_level"])

        assert isinstance(logger, Logger)
        return logger

    def set_log_level(self, level: str | int) -> None:
        """Sets the log level for this App, which applies to the main log, error log, and all user logs.

        Args:
            level (str): Log level.

        Returns:
            None.

        Note:
            Supported log levels: ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``,
            ``DEBUG``, ``NOTSET``.

        Examples:
              >>> self.set_log_level("DEBUG")

        """
        self.logger.setLevel(level)
        self.err.setLevel(level)
        for log in self.user_logs:
            self.user_logs[log].setLevel(level)

    def set_error_level(self, level: str | int) -> None:
        """Sets the log level to send to the `error` logfile of the system.

        Args:
            level (str): Error level.

        Returns:
            None.

        Note:
            Supported log levels: ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``,
            ``DEBUG``, ``NOTSET``.

        """
        self.err.setLevel(level)

    #
    # Threading
    #

    @utils.sync_decorator
    async def set_app_pin(self, pin: bool) -> None:
        """Sets an App to be pinned or unpinned.

        Args:
            pin (bool): Sets whether the App becomes pinned or not.

        Returns:
            None.

        Examples:
            The following line should be put inside the `initialize()` function.

            >>> self.set_app_pin(True)

        """
        self.AD.app_management.set_app_pin(self.name, pin)

    @utils.sync_decorator
    async def get_app_pin(self) -> bool:
        """Finds out if the current App is currently pinned or not.

        Returns:
            bool: ``True`` if the App is pinned, ``False`` otherwise.

        Examples:
            >>> if self.get_app_pin(True):
            >>>     self.log("App pinned!")

        """
        return self.AD.app_management.get_app_pin(self.name)

    @utils.sync_decorator
    async def set_pin_thread(self, thread: int) -> None:
        """Sets the thread that the App will be pinned to.

        Args:
            thread (int): Number of the thread to pin to. Threads start at 0 and go up to the number
                of threads specified in ``appdaemon.yaml`` -1.

        Returns:
            None.

        Examples:
            The following line should be put inside the `initialize()` function.

            >>> self.set_pin_thread(5)

        """
        self.AD.app_management.set_pin_thread(self.name, thread)

    @utils.sync_decorator
    async def get_pin_thread(self) -> int:
        """Finds out which thread the App is pinned to.

        Returns:
            int: The thread number or -1 if the App is not pinned.

        Examples:
            >>> thread = self.get_pin_thread():
            >>> self.log(f"I'm pinned to thread: {thread}")

        """
        return self.AD.app_management.get_pin_thread(self.name)

    #
    # Namespace
    #

    def set_namespace(self, namespace: str, writeback: str = "safe", persist: bool = True) -> None:
        """Set the current namespace of the app

        See the `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.

        Args:
            namespace (str): Name of the new namespace
            writeback (str, optional): The writeback to be used if a new namespace gets created. Will be ``safe`` by
                default.
            persist (bool, optional): Whether to make the namespace persistent if a new one is created. Defaults to
                ``True``.

        Returns:
            None.

        Examples:
            >>> self.set_namespace("hass1")

        """
        # Keeping namespace get/set functions for legacy compatibility
        if not self.namespace_exists(namespace):
            self.add_namespace(namespace=namespace, writeback=writeback, persist=persist)
        self.namespace = namespace

    def get_namespace(self) -> str:
        """Get the app's current namespace.

        See the `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.
        """
        # Keeping namespace get/set functions for legacy compatibility
        return self.namespace

    @utils.sync_decorator
    async def namespace_exists(self, namespace: str) -> bool:
        """Check the existence of a namespace in AppDaemon.

        See the `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.

        Args:
            namespace (str): The namespace to be checked.

        Returns:
            bool: ``True`` if the namespace exists, otherwise ``False``.

        Examples:
            Check if the namespace ``storage`` exists within AD

            >>> if self.namespace_exists("storage"):
            >>>     #do something like create it

        """
        return self.AD.state.namespace_exists(namespace)

    @utils.sync_decorator
    async def add_namespace(self, namespace: str, writeback: str = "safe", persist: bool = True) -> str | None:
        """Add a user-defined namespace, which has a database file associated with it.

        When AppDaemon restarts these entities will be loaded into the namespace with all their previous states. This
        can be used as a basic form of non-volatile storage of entity data. Depending on the configuration of the
        namespace, this function can be setup to constantly be running automatically
        or only when AD shutdown.

        See the `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.

        Args:
            namespace (str): The name of the new namespace to create
            writeback (optional): The writeback to be used. Will be ``safe`` by default
            persist (bool, optional): Whether to make the namespace persistent. Persistent namespaces are stored in a
                database file and are reloaded when AppDaemon restarts. Defaults to ``True``

        Returns:
            The file path to the newly created namespace. Will be ``None`` if not persistent

        Examples:
            Add a new namespace called `storage`.

            >>> self.add_namespace("storage")

        """
        new_namespace = await self.AD.state.add_namespace(namespace, writeback, persist, self.name)
        self.AD.state.app_added_namespaces.add(new_namespace)
        return new_namespace

    @utils.sync_decorator
    async def remove_namespace(self, namespace: str) -> dict[str, Any] | None:
        """Remove a user-defined namespace, which has a database file associated with it.

        See the `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.

        Args:
            namespace (str): The namespace to be removed, which must not be the current namespace.

        Returns:
            The data within that namespace

        Examples:
            Removes the namespace called `storage`.

            >>> self.remove_namespace("storage")

        """
        if namespace == self.namespace:  # if it belongs to this app's namespace
            raise ValueError("Cannot remove the current namespace")

        return await self.AD.state.remove_namespace(namespace)

    @utils.sync_decorator
    async def list_namespaces(self) -> list[str]:
        """Get a list of all the namespaces in AppDaemon.

        Examples:
            >>> self.list_namespaces()

        """
        return self.AD.state.list_namespaces()

    @utils.sync_decorator
    async def save_namespace(self, namespace: str | None = None) -> None:
        """Saves entities created in user-defined namespaces into a file.

        This way, when AD restarts these entities will be reloaded into AD with its
        previous states within the namespace. This can be used as a basic form of
        non-volatile storage of entity data. Depending on the configuration of the
        namespace, this function can be setup to constantly be running automatically
        or only when AD shutdown. This function also allows for users to manually
        execute the command as when needed.

        Args:
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            None.

        Examples:
            Save all entities of the default namespace.

            >>> self.save_namespace()

        """
        namespace = namespace or self.namespace
        await self.AD.state.save_namespace(namespace)

    #
    # Utility
    #

    @utils.sync_decorator
    async def get_app(self, name: str) -> "ADAPI":
        """Gets the instantiated object of another app running within the system.

        This is useful for calling functions or accessing variables that reside
        in different apps without requiring duplication of code.

        Args:
            name (str): Name of the app required. This is the name specified in
                header section of the config file, not the module or class.

        Returns:
            An object reference to the class.

        Examples:
            >>> MyApp = self.get_app("MotionLights")
            >>> MyApp.turn_light_on()

        """
        return self.AD.app_management.get_app(name)

    def _check_entity(self, namespace: str, entity_id: str | None) -> None:
        """Ensures that the entity exists in the given namespace"""
        if entity_id is not None and "." in entity_id and not self.AD.state.entity_exists(namespace, entity_id):
            if namespace == "default":
                self.logger.warning(f"Entity {entity_id} not found in the default namespace")
            else:
                self.logger.warning(f"Entity {entity_id} not found in namespace {namespace}")

    @staticmethod
    def get_ad_version() -> str:
        """Returns a string with the current version of AppDaemon.

        Examples:
            >>> version = self.get_ad_version()

        """
        return utils.__version__

    #
    # Entity
    #

    @utils.sync_decorator
    async def add_entity(self, entity_id: str, state: Any | None = None, attributes: dict | None = None, namespace: str | None = None) -> None:
        """Adds a non-existent entity, by creating it within a namespaces.

         If an entity doesn't exists and needs to be created, this function can be used to create it locally.
         Please note this only creates the entity locally.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            state (str, optional): The state the entity is to have
            attributes (dict, optional): The attributes the entity is to have
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            None.

        Examples:
            Add the entity in the present namespace.

            >>> self.add_entity('sensor.living_room')

            adds the entity in the `mqtt` namespace.

            >>> self.add_entity('mqtt.living_room_temperature', namespace='mqtt')

        """

        if self.entity_exists(entity_id, namespace):
            self.logger.warning("%s already exists, will not be adding it", entity_id)
            return None

        return await self.AD.state.add_entity(namespace, entity_id, state, attributes)

    @utils.sync_decorator
    async def entity_exists(self, entity_id: str, namespace: str | None = None) -> bool:
        """Checks the existence of an entity in AD.

        When working with multiple AD namespaces, it is possible to specify the
        namespace, so that it checks within the right namespace in in the event the app is
        working in a different namespace. Also when using this function, it is also possible
        to check if an AppDaemon entity exists.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            bool: ``True`` if the entity id exists, ``False`` otherwise.

        Examples:
            Check if the entity light.living_room exist within the app's namespace

            >>> if self.entity_exists("light.living_room"):
            >>>     #do something

            Check if the entity mqtt.security_settings exist within the `mqtt` namespace
            if the app is operating in a different namespace like default

            >>> if self.entity_exists("mqtt.security_settings", namespace = "mqtt"):
            >>>    #do something
        """
        namespace = namespace or self.namespace
        return self.AD.state.entity_exists(namespace, entity_id)

    @utils.sync_decorator
    async def split_entity(self, entity_id: str, namespace: str | None = None) -> list:
        """Splits an entity into parts.

        This utility function will take a fully qualified entity id of the form ``light.hall_light``
        and split it into 2 values, the device and the entity, e.g. light and hall_light.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            A list with 2 entries, the device and entity respectively.

        Examples:
            Do some action if the device of the entity is `scene`.

            >>> device, entity = self.split_entity(entity_id)
            >>> if device == "scene":
            >>>     #do something specific to scenes

        """
        namespace = namespace or self.namespace
        self._check_entity(namespace, entity_id)
        return entity_id.split(".")

    @utils.sync_decorator
    async def remove_entity(self, entity_id: str, namespace: str | None = None) -> None:
        """Deletes an entity created within a namespaces.

         If an entity was created, and its deemed no longer needed, by using this function,
         the entity can be removed from AppDaemon permanently.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            None.

        Examples:
            Delete the entity in the present namespace.

            >>> self.remove_entity('sensor.living_room')

            Delete the entity in the `mqtt` namespace.

            >>> self.remove_entity('mqtt.living_room_temperature', namespace = 'mqtt')

        """
        namespace = namespace or self.namespace
        await self.AD.state.remove_entity(namespace, entity_id)

    @staticmethod
    def split_device_list(devices: str) -> list[str]:
        """Converts a comma-separated list of device types to an iterable list.

        This is intended to assist in use cases where the App takes a list of
        entities from an argument, e.g., a list of sensors to monitor. If only
        one entry is provided, an iterable list will still be returned to avoid
        the need for special processing.

        Args:
            devices (str): A comma-separated list of devices to be split (without spaces).

        Returns:
            A list of split devices with 1 or more entries.

        Examples:
            >>> for sensor in self.split_device_list(self.args["sensors"]):
            >>>    #do something for each sensor, e.g., make a state subscription

        """
        return devices.split(",")

    @utils.sync_decorator
    async def get_plugin_config(self, namespace: str | None = None) -> Any:
        """Gets any useful metadata that the plugin may have available.

        For instance, for the HASS plugin, this will return Home Assistant configuration
        data such as latitude and longitude.

        Args:
            namespace (str): Select the namespace of the plugin for which data is desired.

        Returns:
            A dictionary containing all the configuration information available
            from the Home Assistant ``/api/config`` endpoint.

        Examples:
            >>> config = self.get_plugin_config()
            >>> self.log(f'My current position is {config["latitude"]}(Lat), {config["longitude"]}(Long)')
            My current position is 50.8333(Lat), 4.3333(Long)

        """
        namespace = namespace or self.namespace
        return self.AD.plugins.get_plugin_meta(namespace)

    @utils.sync_decorator
    async def friendly_name(self, entity_id: str, namespace: str | None = None) -> str:
        """Gets the Friendly Name of an entity.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            str: The friendly name of the entity if it exists or the entity id if not.

        Examples:
            >>> tracker = "device_tracker.andrew"
            >>> friendly_name = self.friendly_name(tracker)
            >>> tracker_state = self.get_tracker_state(tracker)
            >>> self.log(f"{tracker}  ({friendly_name}) is {tracker_state}.")
            device_tracker.andrew (Andrew Tracker) is on.

        """
        namespace = namespace or self.namespace
        self._check_entity(namespace, entity_id)

        return await self.get_state(entity_id=entity_id, attribute="friendly_name", default=entity_id, namespace=namespace, copy=False)
        # if entity_id in state:
        #     if "friendly_name" in state[entity_id]["attributes"]:
        #         return state[entity_id]["attributes"]["friendly_name"]
        #     else:
        #         return entity_id
        # return None

    @utils.sync_decorator
    async def set_production_mode(self, mode: bool = True) -> bool | None:
        """Deactivates or activates the production mode in AppDaemon.

        When called without declaring passing any arguments, mode defaults to ``True``.

        Args:
            mode (bool): If it is ``True`` the production mode is activated, or deactivated
                otherwise.

        Returns:
            The specified mode or ``None`` if a wrong parameter is passed.

        """
        if isinstance(mode, bool):
            self.AD.production_mode = mode
            return mode
        else:
            self.logger.warning("%s not a valid parameter for Production Mode", mode)

    #
    # Internal Helper functions
    #

    def start_app(self, app: str) -> None:
        """Starts an App which can either be running or not.

        This API call cannot start an app which has already been disabled in the App Config.
        It essentially only runs the initialize() function in the app, and changes to attributes
        like class name or app config are not taken into account.

        Args:
            app (str): Name of the app.

        Returns:
            None.

        Examples:
            >>> self.start_app("lights_app")

        """
        self.call_service("app/start", namespace="admin", app=app, __name=self.name)

    def stop_app(self, app: str) -> None:
        """Stops an App which is running.

        Args:
            app (str): Name of the app.

        Returns:
            None.

        Examples:
            >>> self.stop_app("lights_app")

        """
        self.call_service("app/stop", namespace="admin", app=app, __name=self.name)

    def restart_app(self, app: str) -> None:
        """Restarts an App which can either be running or not.

        Args:
            app (str): Name of the app.

        Returns:
            None.

        Examples:
            >>> self.restart_app("lights_app")

        """
        self.call_service("app/restart", namespace="admin", app=app, __name=self.name)

    def reload_apps(self) -> None:
        """Reloads the apps, and loads up those that have changes made to their .yaml or .py files.

        This utility function can be used if AppDaemon is running in production mode, and it is
        needed to reload apps that changes have been made to.

        Returns:
            None.

        Examples:
            >>> self.reload_apps()

        """
        self.call_service("app/reload", namespace="admin", __name=self.name)

    #
    # Dialogflow
    #

    def get_dialogflow_intent(self, data: dict) -> Any | None:
        """Gets the intent's action from the Google Home response.

        Args:
            data: Response received from Google Home.

        Returns:
            A string representing the Intent from the interaction model that was requested,
            or ``None``, if no action was received.

        Examples:
            >>> intent = ADAPI.get_dialogflow_intent(data)

        """
        if "result" in data and "action" in data["result"]:
            self.dialogflow_v = 1
            return data["result"]["action"]
        elif "queryResult" in data and "action" in data["queryResult"]:
            self.dialogflow_v = 2
            return data["queryResult"]["action"]
        return None

    @staticmethod
    def get_dialogflow_slot_value(data, slot=None) -> Any | None:
        """Gets slots' values from the interaction model.

        Args:
            data: Response received from Google Home.
            slot (str): Name of the slot. If a name is not specified, all slots will be returned
                as a dictionary. If a name is specified but is not found, ``None`` will be returned.

        Returns:
            A string representing the value of the slot from the interaction model, or a hash of slots.

        Examples:
            >>> beer_type = ADAPI.get_dialogflow_intent(data, "beer_type")
            >>> all_slots = ADAPI.get_dialogflow_intent(data)

        """
        if "result" in data:
            # using V1 API
            contexts = data["result"]["contexts"][0]
            if contexts:
                parameters = contexts.get("parameters")
            else:
                parameters = data["result"]["parameters"]
            if slot is None:
                return parameters
            elif slot in parameters:
                return parameters[slot]
            else:
                return None
        elif "queryResult" in data:
            # using V2 API
            contexts = data["queryResult"]["outputContexts"][0]
            if contexts:
                parameters = contexts.get("parameters")
            else:
                parameters = data["queryResult"]["parameters"]
            if slot is None:
                return parameters
            elif slot in parameters:
                return parameters[slot]
            else:
                return None
        else:
            return None

    def format_dialogflow_response(self, speech=None) -> Any | None:
        """Formats a response to be returned to Google Home, including speech.

        Args:
            speech (str): The text for Google Home to say.

        Returns:
            None.

        Examples:
            >>> ADAPI.format_dialogflow_response(speech = "Hello World")

        """
        if self.dialogflow_v == 1:
            speech = {"speech": speech, "source": "Appdaemon", "displayText": speech}
        elif self.dialogflow_v == 2:
            speech = {"fulfillmentText": speech, "source": "Appdaemon"}
        else:
            speech = None
        return speech

    #
    # Alexa
    #

    @staticmethod
    def format_alexa_response(speech: str | None = None, card: str | None = None, title: str | None = None) -> dict:
        """Formats a response to be returned to Alexa including speech and a card.

        Args:
            speech (str): The text for Alexa to say.
            card (str): Text for the card.
            title (str): Title for the card.

        Returns:
            None.

        Examples:
            >>> ADAPI.format_alexa_response(speech = "Hello World", card = "Greetings to the world", title = "Hello")

        """
        response: dict[str, Any] = {"shouldEndSession": True}

        if speech is not None:
            response["outputSpeech"] = {"type": "PlainText", "text": speech}

        if card is not None:
            response["card"] = {"type": "Simple", "title": title, "content": card}

        return {"version": "1.0", "response": response, "sessionAttributes": {}}

    @staticmethod
    def get_alexa_error(data: dict) -> str | None:
        """Gets the error message from the Alexa API response.

        Args:
            data: Response received from the Alexa API.

        Returns:
            A string representing the value of message, or ``None`` if no error message was received.

        """
        if "request" in data and "err" in data["request"] and "message" in data["request"]["err"]:
            return data["request"]["err"]["message"]
        else:
            return None

    @staticmethod
    def get_alexa_intent(data: dict) -> str | None:
        """Gets the Intent's name from the Alexa response.

        Args:
            data: Response received from Alexa.

        Returns:
            A string representing the Intent's name from the interaction model that was requested,
            or ``None``, if no Intent was received.

        Examples:
            >>> intent = ADAPI.get_alexa_intent(data)

        """
        if "request" in data and "intent" in data["request"] and "name" in data["request"]["intent"]:
            return data["request"]["intent"]["name"]
        else:
            return None

    @staticmethod
    def get_alexa_slot_value(data, slot=None) -> str | None:
        """Gets values for slots from the interaction model.

        Args:
            data: The request data received from Alexa.
            slot: Name of the slot. If a name is not specified, all slots will be returned as
                a dictionary. If a name is specified but is not found, None will be returned.

        Returns:
            A ``string`` representing the value of the slot from the interaction model, or a ``hash`` of slots.

        Examples:
            >>> beer_type = ADAPI.get_alexa_intent(data, "beer_type")
            >>> all_slots = ADAPI.get_alexa_intent(data)

        """
        if "request" in data and "intent" in data["request"] and "slots" in data["request"]["intent"]:
            if slot is None:
                return data["request"]["intent"]["slots"]
            else:
                if slot in data["request"]["intent"]["slots"] and "value" in data["request"]["intent"]["slots"][slot]:
                    return data["request"]["intent"]["slots"][slot]["value"]
                else:
                    return None
        else:
            return None

    #
    # API
    #

    @utils.sync_decorator
    async def register_endpoint(self, callback: Callable[[Any, dict], Any], endpoint: str | None = None, **kwargs) -> str | None:
        """Registers an endpoint for API calls into the current App.

        Args:
            callback: The function to be called when a request is made to the named endpoint.
            endpoint (str, optional): The name of the endpoint to be used for the call  (Default: ``None``).
            This must be unique across all endpoints, and when not given, the name of the app is used as the endpoint.
            It is possible to register multiple endpoints to a single app instance.
        Keyword Args:
            **kwargs (optional): Zero or more keyword arguments.

        Returns:
            A handle that can be used to remove the registration.

        Examples:
            It should be noted that the register function, should return a string (can be empty),
            and an HTTP OK status response (e.g., `200`. If this is not added as a returned response,
            the function will generate an error each time it is processed. If the POST request
            contains JSON data, the decoded data will be passed as the argument to the callback.
            Otherwise the callback argument will contain the query string. A `request` kwarg contains
            the http request object.

            >>> self.register_endpoint(self.my_callback)
            >>> self.register_endpoint(self.alexa_cb, "alexa")

            >>> async def alexa_cb(self, json_obj, kwargs):
            >>>     self.log(json_obj)
            >>>     response = {"message": "Hello World"}
            >>>     return response, 200

        """
        endpoint = endpoint or self.name

        if self.AD.http is not None:
            return await self.AD.http.register_endpoint(callback, endpoint, self.name, **kwargs)
        else:
            self.logger.warning(
                "register_endpoint for %s failed - HTTP component is not configured",
                endpoint,
            )
            return None

    @utils.sync_decorator
    async def deregister_endpoint(self, handle: str) -> None:
        """Removes a previously registered endpoint.

        Args:
            handle: A handle returned by a previous call to ``register_endpoint``

        Returns:
            None.

        Examples:
            >>> self.deregister_endpoint(handle)

        """
        await self.AD.http.deregister_endpoint(handle, self.name)

    #
    # Web Route
    #

    @utils.sync_decorator
    async def register_route(self, callback: Callable[[Any, dict], Any], route: str | None = None, **kwargs: dict[str, Any]) -> str | None:
        """Registers a route for Web requests into the current App.
           By registering an app web route, this allows to make use of AD's internal web server to serve
           web clients. All routes registered using this api call, can be accessed using
           ``http://AD_IP:Port/app/route``.

        Args:
            callback: The function to be called when a request is made to the named route. This must be an async function
            route (str, optional): The name of the route to be used for the request (Default: the app's name).

        Keyword Args:
            **kwargs (optional): Zero or more keyword arguments.

        Returns:
            A handle that can be used to remove the registration.

        Examples:
            It should be noted that the register function, should return a aiohttp Response.

            >>> from aiohttp import web

            >>> def initialize(self):
            >>>   self.register_route(my_callback)
            >>>   self.register_route(stream_cb, "camera")
            >>>
            >>> async def camera(self, request, kwargs):
            >>>   return web.Response(text="test", content_type="text/html")


        """
        if route is None:
            route = self.name

        if self.AD.http is not None:
            return await self.AD.http.register_route(callback, route, self.name, **kwargs)
        else:
            self.logger.warning("register_route for %s filed - HTTP component is not configured", route)
            return None

    @utils.sync_decorator
    async def deregister_route(self, handle: str) -> None:
        """Removes a previously registered app route.

        Args:
            handle: A handle returned by a previous call to ``register_app_route``

        Returns:
            None.

        Examples:
            >>> self.deregister_route(handle)

        """
        await self.AD.http.deregister_route(handle, self.name)

    #
    # State
    #

    @overload  # single entity
    @utils.sync_decorator
    async def listen_state(
        self,
        callback: StateCallback,
        entity_id: str | None,
        namespace: str | None = None,
        new: str | Callable[[Any], bool] | None = None,
        old: str | Callable[[Any], bool] | None = None,
        duration: str | int | float | timedelta | None = None,
        attribute: str | None = None,
        timeout: str | int | float | timedelta | None = None,
        immediate: bool = False,
        oneshot: bool = False,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs: Any,
    ) -> str: ...

    @overload  # multiple entities
    @utils.sync_decorator
    async def listen_state(
        self,
        callback: StateCallback,
        entity_id: Iterable[str],
        namespace: str | None = None,
        new: str | Callable[[Any], bool] | None = None,
        old: str | Callable[[Any], bool] | None = None,
        duration: str | int | float | timedelta | None = None,
        attribute: str | None = None,
        timeout: str | int | float | timedelta | None = None,
        immediate: bool = False,
        oneshot: bool = False,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs: Any,
    ) -> list[str]: ...

    @utils.sync_decorator
    async def listen_state(
        self,
        callback: StateCallback,
        entity_id: str | Iterable[str] | None = None,
        namespace: str | None = None,
        new: str | Callable[[Any], bool] | None = None,
        old: str | Callable[[Any], bool] | None = None,
        duration: str | int | float | timedelta | None = None,
        attribute: str | None = None,
        timeout: str | int | float | timedelta | None = None,
        immediate: bool = False,
        oneshot: bool = False,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs: Any,
    ) -> str | list[str]:
        """Registers a callback to react to state changes.

        The callback needs to have the following form:

        >>> def my_callback(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> None: ...

        Args:
            callback: Function that will be called when the callback gets triggered. It must conform to the standard
                state callback format documented `here <APPGUIDE.html#state-callbacks>`__
            entity_id (str | Iterable[str], optional): Entity ID or a domain. If a domain is provided, e.g., ``light``,
                or ``binary_sensor`` the callback will be triggered for state changes of any entities in that domain.
                If a list of entities is provided, the callback will be registered for each of those entities.
            namespace (str, optional): Optional namespace to use. Defaults to using the app's current namespace. See
                the `namespace documentation <APPGUIDE.html#namespaces>`__ for more information. Using the value
                ``global`` will register the callback for all namespaces.
            new (str | Callable[[Any], bool], optional): If given, the callback will only be invoked if the state of
                the selected attribute (usually state) matches this value in the new data. The data type is dependent on
                the specific entity and attribute. Values that look like ints or floats are often actually strings, so
                be careful when comparing them. The ``self.get_state()`` method is useful for checking the data type of
                the desired attribute. If ``new`` is a callable (lambda, function, etc), then it will be called with
                the new state, and the callback will only be invoked if the callable returns ``True``.
            old (str | Callable[[Any], bool], optional): If given, the callback will only be invoked if the selected
                attribute (usually state) changed from this value in the new data. The data type is dependent on the
                specific entity and attribute. Values that look like ints or floats are often actually strings, so be
                careful when comparing them. The ``self.get_state()`` method is useful for checking the data type of
                the desired attribute. If ``old`` is a callable (lambda, function, etc), then it will be called with
                the old state, and the callback will only be invoked if the callable returns ``True``.
            duration (str | int | float | timedelta, optional): If supplied, the callback will not be invoked unless the
                desired state is maintained for that amount of time. This requires that a specific attribute is
                specified (or the default of ``state`` is used), and should be used in conjunction with either or both
                of the ``new`` and ``old`` parameters. When the callback is called, it is supplied with the values of
                ``entity``, ``attr``, ``old``, and ``new`` that were current at the time the actual event occurred,
                since the assumption is that none of them have changed in the intervening period.

                If you use ``duration`` when listening for an entire device type rather than a specific entity, or for
                all state changes, you may get unpredictable results, so it is recommended that this parameter is only
                used in conjunction with the state of specific entities.
            attribute (str, optional): Optional name of an attribute to use for the new/old checks. If not specified,
                the default behavior is to use the value of ``state``. Using the value ``all`` will cause the callback
                to get triggered for any change in state, and the new/old values used for the callback will be the
                entire state dict rather than the individual value of an attribute.
            timeout (str | int | float | timedelta, optional): If given, the callback will be automatically removed
                after that amount of time. If activity for the listened state has occurred that would trigger a
                duration timer, the duration timer will still be fired even though the callback has been removed.
            immediate (bool, optional): If given, it enables the countdown for a delay parameter to start at the time.
                If the ``duration`` parameter is not given, the callback runs immediately. What this means is that
                after the callback is registered, rather than requiring one or more state changes before it runs, it
                immediately checks the entity's states based on given parameters. If the conditions are right, the
                callback runs immediately at the time of registering. This can be useful if, for instance, you want the
                callback to be triggered immediately if a light is already `on`, or after a ``duration`` if given.

                If ``immediate`` is in use, and ``new`` and ``duration`` are both set, AppDaemon will check
                if the entity is already set to the new state and if so it will start the clock
                immediately. If ``new`` and ``duration`` are not set, ``immediate`` will trigger the callback
                immediately and report in its callback the new parameter as the present state of the
                entity. If ``attribute`` is specified, the state of the attribute will be used instead of
                state. In these cases, ``old`` will be ignored and when the callback is triggered, its
                state will be set to ``None``.
            oneshot (bool, optional): If ``True``, the callback will be automatically removed after the first time it
                gets invoked.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number. The ID numbers start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Note:
            The ``old`` and ``new`` args can be used singly or together.

        Returns:
            A string that uniquely identifies the callback and can be used to cancel it later if necessary. Since
            variables created within object methods are local to the function they are created in, it's recommended to
            store the handles in the app's instance variables, e.g. ``self.handle``.

        Examples:
            Listen for any state change and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback)

            Listen for any state change involving a light and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light")

            Listen for a state change involving `light.office1` and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, entity_id="light.office_1")

            Listen for a state change involving `light.office1` and return the entire state as a dict.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "all")

            Listen for a change involving the brightness attribute of `light.office1` and return the brightness
            attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "brightness")

            Listen for a state change involving `light.office1` turning on and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on")

            Listen for a state change involving `light.office1` turning on when the previous state was not unknown or
            unavailable, and return the state attribute.

            >>> self.handle = self.listen_state(
                self.my_callback,
                "light.office_1",
                new="on",
                old=lambda x: x.lower() not in {"unknown", "unavailable"}
            )

            Listen for a change involving `light.office1` changing from brightness 100 to 200 and return the
            brightness attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute="brightness", old="100", new="200")

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new="on", duration=60)

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute
            trigger the delay immediately if the light is already on.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new="on", duration=60, immediate=True)

            Listen for a state change involving `light.office1` and `light.office2` changing to state on.

            >>> self.handle = self.listen_state(self.my_callback, ["light.office_1", "light.office2"], new="on")

        """
        kwargs = dict(new=new, old=old, duration=duration, attribute=attribute, **kwargs)
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        namespace = namespace or self.namespace

        # pre-fill some arguments here
        add_callback = functools.partial(
            self.AD.state.add_state_callback, name=self.name, namespace=namespace, cb=callback, timeout=timeout, oneshot=oneshot, immediate=immediate, pin=pin, pin_thread=pin_thread, kwargs=kwargs
        )

        match entity_id:
            case str() | None:
                self._check_entity(namespace, entity_id)
                return await add_callback(entity=entity_id)
            case Iterable():
                for e in entity_id:
                    self._check_entity(namespace, e)
                return [await add_callback(entity=e) for e in entity_id]

    @utils.sync_decorator
    async def cancel_listen_state(self, handle: str, name: str | None = None, silent: bool = False) -> bool:
        """Cancel a ``listen_state()`` callback.

        This will prevent any further calls to the callback function. Other state callbacks will not be affected.

        Args:
            handle: The handle returned when the ``listen_state()`` call was made.
            name (str, optional): The name of the app that registered the callback. Defaults to the name of the current
                app. This is useful if you want to get the information of a callback registered by another app.
            silent (bool, optional): If ``True``, no warning will be issued if the handle is not found.

        Returns:
            Boolean.

        Examples:
            >>> self.cancel_listen_state(self.office_light_handle)

            Don't display a warning if the handle is not found.

            >>> self.cancel_listen_state(self.dummy_handle, silent=True)

        """
        name = name or self.name
        self.logger.debug("Canceling listen_state for %s", name)
        return bool(await self.AD.state.cancel_state_callback(handle=handle, name=name, silent=silent))

    @utils.sync_decorator
    async def info_listen_state(self, handle: str, name: str | None = None) -> tuple[str, str, Any, dict[str, Any]]:
        """Get information on state a callback from its handle.

        Args:
            handle (str): The handle returned when the ``listen_state()`` call was made.
            name (str, optional): The name of the app that registered the callback. Defaults to the name of the current
                app. This is useful if you want to get the information of a callback registered by another app.

        Returns:
            The values supplied for ``namespace``, ``entity``, ``attribute``, and ``kwargs`` when
            the callback was initially created.

        Examples:
            >>> namespace, entity, attribute, kwargs = self.info_listen_state(self.handle)

        """
        name = name or self.name
        self.logger.debug("Calling info_listen_state for %s", name)
        return await self.AD.state.info_state_callback(handle=handle, name=name)

    @utils.sync_decorator
    async def get_state(
        self,
        entity_id: str | None = None,
        attribute: str | Literal["all"] | None = None,
        default: Any | None = None,
        namespace: str | None = None,
        copy: bool = True,
        **kwargs,  # left in intentionally for compatibility
    ) -> Any | dict[str, Any] | None:
        """Get the state of an entity from AppDaemon's internals.

        Home Assistant emits a ``state_changed`` event for every state change, which it sends to AppDaemon over the
        websocket connection made by the plugin. Appdaemon uses the data in these events to update its internal state.
        This method returns values from this internal state, so it does **not** make any external requests to Home
        Assistant.

        Other plugins that emit ``state_changed`` events will also have their states tracked internally by AppDaemon.

        It's common for entities to have a state that's always one of ``on``, ``off``, or ``unavailable``. This applies
        to entities in the ``light``, ``switch``, ``binary_sensor``, and ``input_boolean`` domains in Home Assistant,
        among others.

        Args:
            entity_id (str, optional): Full entity ID or just a domain. If a full entity ID is provided, the result
                will be for that entity only. If a domain is provided, the result will be a dict that maps the entity
                IDs to their respective results.
            attribute (str, optional): Optionally specify an attribute to return. If not used, the state of the entity
                will be returned. The value ``all`` can be used to return the entire state dict rather than a single
                value.
            default (any, optional): The value to return when the entity or the attribute doesn't exist.
            namespace (str, optional): Optional namespace to use. Defaults to using the app's current namespace. The
                current namespace can be changed using ``self.set_namespace``. See the
                `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.
            copy (bool, optional): Whether to return a copy of the internal data. This is ``True`` by default in order
                to protect the user from accidentally modifying AppDaemon's internal data structures, which is dangerous
                and can cause undefined behavior. Only set this to ``False`` for read-only operations.

        Returns:
            The state or attribute of the entity ID provided or a dict of that maps entity IDs to their respective
            results. If called with no parameters, this will return the entire state dict.

        Examples:
            Get the state of the entire system.

            >>> state = self.get_state()

            Get the state of all switches in the system.

            >>> state = self.get_state("switch")

            Get the state attribute of `light.office_1`.

            >>> state = self.get_state("light.office_1")

            Get the brightness attribute of `light.office_1`.

            >>> state = self.get_state("light.office_1", attribute="brightness")

            Get the entire state of `light.office_1`.

            >>> state = self.get_state("light.office_1", attribute="all")

        """
        if kwargs:
            self.logger.warning(f"Extra kwargs passed to get_state, will be ignored: {kwargs}")

        return await self.AD.state.get_state(name=self.name, namespace=namespace or self.namespace, entity_id=entity_id, attribute=attribute, default=default, copy=copy)

    @utils.sync_decorator
    async def set_state(
        self, entity_id: str, state: Any | None = None, namespace: str | None = None, attributes: dict[str, Any] | None = None, replace: bool = False, check_existence: bool = True, **kwargs: Any
    ) -> dict[str, Any]:
        """Update the state of the specified entity.

        This causes a ``state_changed`` event to be emitted in the entity's namespace. If that namespace is associated
        with a Home Assistant plugin, it will use the ``/api/states/<entity_id>`` endpoint of the
        `REST API <https://developers.home-assistant.io/docs/api/rest/>`__ to update the state of the entity. This
        method can be useful to create entities in Home Assistant, but they won't persist across restarts.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            state: New state value to be set.
            namespace(str, optional): Optional namespace to use. Defaults to using the app's current namespace. See
                the `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.
            attributes (dict[str, Any], optional): Optional dictionary to use for the attributes. If replace is
                ``False``, then the attribute dict will use the built-in update method on this dict. If replace is
                ``True``, then the attribute dict will be entirely replaced with this one.
            replace(bool, optional): Whether to replace rather than update the attributes. Defaults to ``False``. For
                plugin based entities, this is not recommended, as the plugin will mostly replace the new values, when
                next it updates.
            check_existence(bool, optional): Whether to check if the entity exists before setting the state. Defaults to
                ``True``, but it can be useful to set to ``False`` when using this method to create an entity.
            **kwargs (optional): Zero or more keyword arguments. Extra keyword arguments will be assigned as attributes.

        Returns:
            A dictionary that represents the new state of the updated entity.

        Examples:
            Update the state of an entity.

            >>> self.set_state("light.office_1", state="off")

            Update the state and attribute of an entity.

            >>> self.set_state(entity_id="light.office_1", state="on", attributes={"color_name": "red"})

            Update the state of an entity within the specified namespace.

            >>> self.set_state("light.office_1", state="off", namespace="hass")

        """
        namespace = namespace or self.namespace
        if check_existence:
            self._check_entity(namespace, entity_id)
        return await self.AD.state.set_state(name=self.name, namespace=namespace, entity=entity_id, state=state, attributes=attributes, replace=replace, **kwargs)

    #
    # Services
    #

    @staticmethod
    def _check_service(service: str) -> None:
        """Check if the service name is formatted correctly.

        Raises:
            ValueError: If the service name is invalid.

        """
        if not isinstance(service, str) and len(str.split("/")) == 2:
            raise ValueError(f"Invalid Service Name: {service}")

    def register_service(self, service: str, cb: Callable, namespace: str | None = None, **kwargs) -> None:
        """Register a service that can be called from other apps, the REST API, and the event stream.

        This makes a function available to be called in other apps using ``call_service(...)``. The service function can
        accept arbitrary keyword arguments.

        Registering services in namespaces that already have plugins is not recommended, as it can lead to some
        unpredictable behavior. Instead, it's recommended to use a user-defined namespace or one that is not tied to
        plugin.

        Args:
            service: Name of the service, in the format ``domain/service``. If the domain does not exist it will be
                created.
            cb: The function to use for the service. This will accept both sync and async functions. Async functions are
                not recommended, as AppDaemon's threading model makes them unnecessary. Async functions run in the event
                loop along with AppDaemon internal functions, so any blocking or delays, can cause AppDaemon itself to
                hang.
            namespace (str, optional): Optional namespace to use. Defaults to using the app's current namespace. See the
                `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.
            **kwargs (optional): Zero or more keyword arguments. Extra keyword arguments will be stored alongside the
                service definition.

        Returns:
            None

        Examples:
            >>> self.register_service("myservices/service1", self.mycallback)

            >>> async def mycallback(self, namespace: str, domain: str, service: str, kwargs):
            >>>     self.log("Service called")

        """
        self._check_service(service)
        self.logger.debug("register_service: %s, %s", service, kwargs)

        namespace = namespace or self.namespace
        self.AD.services.register_service(namespace, *service.split("/"), cb, __async="auto", name=self.name, **kwargs)

    def deregister_service(self, service: str, namespace: str | None = None) -> bool:
        """Deregister a service that had been previously registered.

        This will immediately remove the service from AppDaemon's internal service registry, which will make it
        unavailable to other apps using the ``call_service()`` API call, as well as published as a service in the REST
        API

        Using this function, an App can deregister a service call, it has initially registered in the service registry.
        This will automatically make it unavailable to other apps using the `call_service()` API call, as well as published
        as a service in the REST API and make it unavailable to the `call_service` command in the event stream.
        This function can only be used, within the app that registered it in the first place

        Args:
            service: Name of the service, in the format ``domain/service``.
            namespace (str, optional): Optional namespace to use. Defaults to using the app's current namespace. See the
                `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.

        Returns:
            ``True`` if the service was successfully deregistered, ``False`` otherwise.

        Examples:
            >>> self.deregister_service("myservices/service1")

        """
        namespace = namespace or self.namespace
        self.logger.debug("deregister_service: %s, %s", service, namespace)
        self._check_service(service)
        return self.AD.services.deregister_service(namespace, *service.split("/"), name=self.name)

    def list_services(self, namespace: str = "global") -> list[dict[str, str]]:
        """List all services available within AppDaemon

        Args:
            namespace (str, optional): Optional namespace to use. The default is ``flobal``, which will return services
                across all namespaces. See the `namespace documentation <APPGUIDE.html#namespaces>`__ for more
                information.

        Returns:
            List of dicts with keys ``namespace``, ``domain``, and ``service``.

        Examples:
            >>> services = self.list_services()

            >>> services = self.list_services("default")

            >>> services = self.list_services("mqtt")

        """

        self.logger.debug("list_services: %s", namespace)
        return self.AD.services.list_services(namespace)

    @utils.sync_decorator
    async def call_service(
        self,
        service: str,
        namespace: str | None = None,
        timeout: str | int | float | None = None,  # Used by utils.sync_decorator
        callback: Callable[[Any], Any] | None = None,
        **data: Any,
    ) -> Any:
        """Calls a Service within AppDaemon.

        Services represent specific actions, and are generally registered by plugins or provided by AppDaemon itself.
        The app calls the service only by referencing the service with a string in the format ``<domain>/<service>``, so
        there is no direct coupling between apps and services. This allows any app to call any service, even ones from
        other plugins.

        Services often require additional parameters, such as ``entity_id``, which AppDaemon will pass to the service
        call as appropriate, if used when calling this function. This allows arbitrary data to be passed to the service
        calls.

        Apps can also register their own services using their ``self.regsiter_service`` method.

        Args:
            service (str): The service name in the format `<domain>/<service>`. For example, `light/turn_on`.
            namespace (str, optional): It's safe to ignore this parameter in most cases because the default namespace
                will be used. However, if a `namespace` is provided, the service call will be made in that namespace. If
                there's a plugin associated with that namespace, it will do the service call. If no namespace is given,
                AppDaemon will use the app's namespace, which can be set using the ``self.set_namespace`` method. See
                the section on `namespaces <APPGUIDE.html#namespaces>`__ for more information.
            timeout (str | int | float, optional): The internal AppDaemon timeout for the service call. If no value is
                specified, the default timeout is 60s. The default value can be changed using the
                ``appdaemon.internal_function_timeout`` config setting.
            callback (callable): The non-async callback to be executed when complete. It should accept a single
                argument, which will be the result of the service call. This is the recommended method for calling
                services which might take a long time to complete. This effectively bypasses the ``timeout`` argument
                because it only applies to this function, which will return immediately instead of waiting for the
                result if a `callback` is specified.
            service_data (dict, optional): Used as an additional dictionary to pass arguments into the ``service_data``
                field of the JSON that goes to Home Assistant. This is useful if you have a dictionary that you want to
                pass in that has a key like ``target`` which is otherwise used for the ``target`` argument.
            **data: Any other keyword arguments get passed to the service call as ``service_data``. Each service takes
                different parameters, so this will vary from service to service. For example, most services require
                ``entity_id``. The parameters for each service can be found in the actions tab of developer tools in
                the Home Assistant web interface.

        Returns:
            Result of the `call_service` function if any, see
            `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            HASS
            ^^^^

            >>> self.call_service("light/turn_on", entity_id="light.office_lamp", color_name="red")
            >>> self.call_service("notify/notify", title="Hello", message="Hello World")
            >>> events = self.call_service(
                    "calendar/get_events",
                    entity_id="calendar.home",
                    start_date_time="2024-08-25 00:00:00",
                    end_date_time="2024-08-27 00:00:00",
                )["result"]["response"]["calendar.home"]["events"]

            MQTT
            ^^^^

            >>> self.call_service("mqtt/subscribe", topic="homeassistant/living_room/light", qos=2)
            >>> self.call_service("mqtt/publish", topic="homeassistant/living_room/light", payload="on")

            Utility
            ^^^^^^^

            It's important that the ``namespace`` arg is set to ``admin`` for these services, as they do not exist
            within the default namespace, and apps cannot exist in the ``admin`` namespace. If the namespace is not
            specified, calling the method will raise an exception.

            >>> self.call_service("app/restart", app="notify_app", namespace="admin")
            >>> self.call_service("app/stop", app="lights_app", namespace="admin")
            >>> self.call_service("app/reload", namespace="admin")

        """
        self.logger.debug("call_service: %s, %s", service, data)
        self._check_service(service)
        namespace = namespace or self.namespace

        # Check the entity_id if it exists
        if eid := data.get("entity_id"):
            match eid:
                case str():
                    self._check_entity(namespace, eid)
                case Iterable():
                    for e in eid:
                        self._check_entity(namespace, e)

        domain, service_name = service.split("/", 2)
        coro = self.AD.services.call_service(namespace=namespace, domain=domain, service=service_name, data=data)
        if callback is None:
            return await coro
        else:
            task = self.AD.loop.create_task(coro)
            task.add_done_callback(lambda f: callback(f.result()))

    # Sequences

    @utils.sync_decorator
    async def run_sequence(self, sequence: str | list[dict[str, dict[str, str]]], namespace: str | None = None) -> Any:
        """Run an AppDaemon Sequence.

        Sequences are defined in a valid apps.yaml file or inline, and are sequences of service calls.

        Args:
            sequence: The sequence name, referring to the correct entry in apps.yaml, or a list containing actual
                commands to run
            namespace(str, optional): If a ``namespace`` is provided, AppDaemon will change
                the state of the given entity in the given namespace. On the other hand,
                if no namespace is given, AppDaemon will use the last specified namespace
                or the default namespace. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.

        Returns:
            A handle that can be used with `cancel_sequence()` to terminate the script.

        Examples:
            Run a yaml-defined sequence called "sequence.front_room_scene".

            >>> handle = self.run_sequence("sequence.front_room_scene")

            >>> handle = self.run_sequence("front_room_scene")

            Run an inline sequence.

            >>> handle = self.run_sequence([
                    {"light/turn_on": {"entity_id": "light.office_1"}},
                    {"sleep": 5},
                    {"light.turn_off": {"entity_id": "light.office_1"}}
                ])

        """
        namespace = namespace or self.namespace
        self.logger.debug("Calling run_sequence() for %s from %s", sequence, self.name)

        try:
            task = self.AD.sequences.run_sequence(self.name, namespace, deepcopy(sequence))
            return await task
        except ade.AppDaemonException as e:
            new_exc = ade.SequenceExecutionFail(f"run_sequence() failed from app '{self.name}'")
            raise new_exc from e

    @utils.sync_decorator
    async def cancel_sequence(self, sequence: str | list[str] | Future) -> None:
        """Cancel an already running AppDaemon Sequence.

        Args:
            sequence: The sequence as configured to be cancelled, or the sequence entity_id or future object

        Returns:
            None.

        Examples:

            >>> self.cancel_sequence("sequence.living_room_lights")

        """

        self.logger.debug("Calling cancel_sequence() for %s, from %s", sequence, self.name)
        await self.AD.sequences.cancel_sequence(sequence)

    #
    # Events
    #

    @overload
    @utils.sync_decorator
    async def listen_event(
        self,
        callback: EventCallback,
        event: str | None = None,
        *,
        namespace: str | None = None,
        timeout: str | int | float | timedelta | None = None,
        oneshot: bool = False,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs: Any | Callable[[Any], bool],
    ) -> str: ...

    @overload
    @utils.sync_decorator
    async def listen_event(
        self,
        callback: EventCallback,
        event: list[str],
        *,
        namespace: str | None = None,
        timeout: str | int | float | timedelta | None = None,
        oneshot: bool = False,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs: Any | Callable[[Any], bool],
    ) -> list[str]: ...

    @utils.sync_decorator
    async def listen_event(
        self,
        callback: EventCallback,
        event: str | Iterable[str] | None = None,
        *,
        namespace: str | Literal["global"] | None = None,
        timeout: str | int | float | timedelta | None = None,
        oneshot: bool = False,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs: Any | Callable[[Any], bool],
    ) -> str | list[str]:
        """Register a callback for a specific event, multiple events, or any event.


        The callback needs to have the following form:

        >>> def my_callback(self, event_name: str, event_data: dict[str, Any], **kwargs: Any) -> None: ...

        Args:
            callback: Function that will be called when the event is fired. It must conform to the standard event
                callback format documented `here <APPGUIDE.html#event-callbacks>`__
            event (str | list[str], optional): Name of the event to subscribe to. Can be a standard Home Assistant
                event such as ``service_registered``, an arbitrary custom event such as ``MODE_CHANGE`` or a list of
                events `["pressed", "released"]`. If no event is specified, `listen_event()` will subscribe to all
                events.
            namespace (str, optional): Optional namespace to use. Defaults to using the app's current namespace. The
                value ``global`` will register the callback for all namespaces. See the
                `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.
            timeout (str, int, float, timedelta, optional): If supplied, the callback will be created as normal, but the
                callback will be removed after the timeout.
            oneshot (bool, optional): If ``True``, the callback will be automatically cancelled after the first state
                change that results in a callback. Defaults to ``False``.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number. The ID numbers start at 0 and go through (number of threads - 1).
            **kwargs (optional): One or more keyword value pairs representing app-specific parameters to supply to the
                callback. If the event has data that matches one of these keywords, it will be filtered by the value
                passed in with this function. This means that if the value in the event data does not match, the
                callback will not be called. If the values provided are callable (lambda, function, etc), then they'll
                be invoked with the events content, and if they return ``True``, they'll be considered to match.

                Filtering will work with any event type, but it will be necessary to figure out the data associated
                with the event to understand what values can be filtered on. This can be achieved by examining Home
                Assistant's ``logfiles`` when the event fires.

        Returns:
            A handle that can be used to cancel the callback.

        Examples:
            Listen all `"MODE_CHANGE"` events.

            >>> self.listen_event(self.mode_event, "MODE_CHANGE")

            Listen for a `minimote` event activating scene 3.

            >>> self.listen_event(self.generic_event, "zwave.scene_activated", scene_id=3)

            Listen for a `minimote` event activating scene 3 from a specific `minimote` .

            >>> self.listen_event(self.generic_event, "zwave.scene_activated", entity_id="minimote_31", scene_id=3)

            Listen for a `minimote` event activating scene 3 from certain `minimote` (starting with 3), matched with
            code.

            >>> self.listen_event(
                    self.generic_event,
                    "zwave.scene_activated",
                    entity_id=lambda x: x.starts_with("minimote_3"),
                    scene_id=3
                )

            Listen for some custom events of a button being pressed.

            >>> self.listen_event(self.button_event, ["pressed", "released"])

        """
        self.logger.debug(f"Calling listen_event() for {self.name} for {event}: {kwargs}")

        # pre-fill some arguments here
        add_callback = functools.partial(
            self.AD.events.add_event_callback, name=self.name, namespace=namespace or self.namespace, cb=callback, timeout=timeout, oneshot=oneshot, pin=pin, pin_thread=pin_thread, kwargs=kwargs
        )

        match event:
            case str() | None:
                return await add_callback(event=event)
            case Iterable():
                return [await add_callback(event=e) for e in event]
            case _:
                self.logger.warning(f"Invalid event: {event}")

    @overload
    @utils.sync_decorator
    async def cancel_listen_event(self, handle: str, *, silent: bool = False) -> bool: ...

    @overload
    @utils.sync_decorator
    async def cancel_listen_event(self, handle: Iterable[str], *, silent: bool = False) -> dict[str, bool]: ...

    @utils.sync_decorator
    async def cancel_listen_event(self, handle: str | Iterable[str], *, silent: bool = False) -> bool | dict[str, bool]:
        """Cancel a callback for a specific event.

        Args:
            handle (str, Iterable[str]): Handle(s) returned from a previous call to ``listen_event()``.
            silent (bool, optional): If ``True``, no warning will be issued if the handle is not found. Defaults to
                ``False``. This is useful if you want to cancel a callback that may or may not exist.

        Returns:
            A single boolean if a single handle is passed, or a dict mapping the handles to boolean values. Each boolean
            value will be the result of canceling the corresponding handle.

        Examples:
            Cancel a single callback.
            >>> self.cancel_listen_event(handle)
            True

            Cancel multiple callbacks.
            >>> result = self.cancel_listen_event([handle1, handle2])
            >>> all(result.values())  # Check if all handles were canceled successfully
            True

        """
        cancel_callback = functools.partial(self.AD.events.cancel_event_callback, name=self.name, silent=silent)

        match handle:
            case str():
                self.logger.debug("Canceling listen_event for %s", self.name)
                return await cancel_callback(handle=handle)
            case Iterable():
                assert all(isinstance(h, str) for h in handle), "All handles must be strings"
                self.logger.debug("Canceling %sx listen_event for %s", len(handle), self.name)
                return {h: await cancel_callback(handle=h) for h in handle}
            case _:
                self.logger.warning(f"Invalid handle: {handle}")
                return False

    @utils.sync_decorator
    async def info_listen_event(self, handle: str) -> bool:
        """Gets information on an event callback from its handle.

        Args:
            handle: The handle returned when the ``listen_event()`` call was made.

        Returns:
             The values (service, kwargs) supplied when the callback was initially created.

        Examples:
            >>> service, kwargs = self.info_listen_event(handle)

        """
        self.logger.debug("Calling info_listen_event for %s", self.name)
        return await self.AD.events.info_event_callback(self.name, handle)

    @utils.sync_decorator
    async def fire_event(self, event: str, namespace: str | None = None, **kwargs) -> None:
        """Fires an event on the AppDaemon bus, for apps and plugins.

        Args:
            event: Name of the event. Can be a standard Home Assistant event such as ``service_registered`` or an
                arbitrary custom event such as "MODE_CHANGE".
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description. In most cases, it is safe to
                ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments that will be supplied as part of the event.

        Returns:
            None.

        Examples:
            >>> self.fire_event("MY_CUSTOM_EVENT", jam="true")

        """
        namespace = namespace or self.namespace
        await self.AD.events.fire_event(namespace, event, **kwargs)

    #
    # Time
    #

    def parse_utc_string(self, utc_string: str) -> float:
        """Convert a UTC to its string representation.

        Args:
            utc_string (str): A string that contains a date and time to convert.

        Returns:
            An POSIX timestamp that is equivalent to the date and time contained in `utc_string`.

        """
        nums = list(
            map(
                int,
                re.split(r"[^\d]", utc_string)[:-1],  # split by anything that's not a number and skip the last part for AM/PM
            )
        )[:7]  # Use a max of 7 parts
        return dt.datetime(*nums).timestamp() + self.get_tz_offset() * 60

    def get_tz_offset(self) -> float:
        """Returns the timezone difference between UTC and Local Time in minutes."""
        return self.AD.tz.utcoffset(self.datetime()).total_seconds() / 60

    def convert_utc(self, utc: str) -> dt.datetime:
        """Gets a `datetime` object for the specified UTC.

        Home Assistant provides timestamps of several different sorts that can be used to gain additional insight into
        state changes. These timestamps are in UTC and are coded as `ISO 8601` combined date and time strings. This
        function will accept one of these strings and convert it to a localised Python ``datetime`` object representing
        the timestamp.

        Args:
            utc: An `ISO 8601` encoded date and time string in the following format: `2016-07-13T14:24:02.040658-04:00`

        Returns:
             A localised Python `datetime` object representing the timestamp.

        """
        return dt.datetime.fromisoformat(utc).astimezone(self.AD.tz)

    @utils.sync_decorator
    async def sun_up(self) -> bool:
        """Determines if the sun is currently up.

        Returns:
             bool: ``True`` if the sun is up, ``False`` otherwise.

        Examples:
            >>> if self.sun_up():
            >>>    #do something

        """
        return await self.AD.sched.sun_up()

    @utils.sync_decorator
    async def sun_down(self) -> bool:
        """Determines if the sun is currently down.

        Returns:
            bool: ``True`` if the sun is down, ``False`` otherwise.

        Examples:
            >>> if self.sun_down():
            >>>    #do something

        """
        return await self.AD.sched.sun_down()

    @utils.sync_decorator
    async def parse_time(self, time_str: str, name: str | None = None, aware: bool = False, today: bool = False, days_offset: int = 0) -> dt.time:
        """Creates a `time` object from its string representation.

        This functions takes a string representation of a time, or sunrise,
        or sunset offset and converts it to a datetime.time object.

        Args:
            time_str (str): A string representation of the datetime with one of the
                following formats:

                    a. ``HH:MM:SS[.ss]`` - the time in Hours Minutes, Seconds and Microseconds, 24 hour format.

                    b. ``sunrise|sunset [+|- HH:MM:SS[.ss]]`` - time of the next sunrise or sunset
                    with an optional positive or negative offset in Hours Minutes, Seconds and Microseconds.

                    c. ``N deg rising|setting`` - time the sun will be at N degrees of elevation
                    while either rising or setting

                If the ``HH:MM:SS.ss`` format is used, the resulting datetime object will have
                today's date.
            name (str, optional): Name of the calling app or module. It is used only for logging purposes.
            aware (bool, optional): If ``True`` the created datetime object will be aware
                of timezone.
            today (bool, optional): Instead of the default behavior which is to return the
                next sunrise/sunset that will occur, setting this flag to true will return
                today's sunrise/sunset even if it is in the past
            days_offset (int, optional): Specify the number of days (positive or negative)
                for the sunset/sunrise. This can only be used in combination with the today flag


        Returns:
            A `time` object, representing the time given in the `time_str` argument.

        Examples:
            >>> self.parse_time("17:30:00")
            17:30:00

            >>> time = self.parse_time("sunrise")
            04:33:17

            >>> time = self.parse_time("sunset + 00:30:00")
            19:18:48

            >>> time = self.parse_time("sunrise + 01:00:00")
            05:33:17

        """
        return await self.AD.sched.parse_time(time_str=time_str, name=name or self.name, aware=aware, today=today, days_offset=days_offset)

    @utils.sync_decorator
    async def parse_datetime(self, time_str: str, name: str | None = None, aware: bool = False, today: bool = False, days_offset: int = 0) -> dt.datetime:
        """Creates a `datetime` object from its string representation.

        This function takes a string representation of a date and time, or sunrise,
        or sunset offset and converts it to a `datetime` object.

        Args:
            time_str (str): A string representation of the datetime with one of the
                following formats:

                    a. ``YY-MM-DD-HH:MM:SS[.ss]`` - the date and time in Year, Month, Day, Hours,
                    Minutes, Seconds and Microseconds, 24 hour format.

                    b. ``HH:MM:SS[.ss]`` - the time in Hours Minutes, Seconds and Microseconds, 24 hour format.

                    c. ``sunrise|sunset [+|- HH:MM:SS[.ss]]`` - time of the next sunrise or sunset
                    with an optional positive or negative offset in Hours Minutes, Seconds and Microseconds.

                If the ``HH:MM:SS.ss`` format is used, the resulting datetime object will have
                today's date.
            name (str, optional): Name of the calling app or module. It is used only for logging purposes.
            aware (bool, optional): If ``True`` the created datetime object will be aware
                of timezone.
            today (bool, optional): Instead of the default behavior which is to return the next
                sunrise/sunset that will occur, setting this flag to true will return today's
                sunrise/sunset even if it is in the past
            days_offset (int, optional): Specify the number of days (positive or negative)
                for the sunset/sunrise. This can only be used in combination with the today flag

        Returns:
            A `datetime` object, representing the time and date given in the
            `time_str` argument.

        Examples:
            >>> self.parse_datetime("2018-08-09 17:30:00")
            2018-08-09 17:30:00

            >>> self.parse_datetime("17:30:00.01")
            2019-08-15 17:30:00.010000

            >>> self.parse_datetime("sunrise")
            2019-08-16 05:33:17

            >>> self.parse_datetime("sunset + 00:30:00")
            2019-08-16 19:18:48

            >>> self.parse_datetime("sunrise + 01:00:00")
            2019-08-16 06:33:17
        """
        return await self.AD.sched.parse_datetime(time_str=time_str, name=name or self.name, aware=aware, today=today, days_offset=days_offset)

    @utils.sync_decorator
    async def get_now(self, aware: bool = True) -> dt.datetime:
        """Returns the current Local Date and Time.

        Examples:
            >>> self.get_now()
            2019-08-16 21:17:41.098813-04:00

        """
        now = await self.AD.sched.get_now()
        return now.astimezone(self.AD.tz) if aware else self.AD.sched.make_naive(now)

    @utils.sync_decorator
    async def get_now_ts(self, aware: bool = False) -> float:
        """Returns the current Local Timestamp.

        Examples:
             >>> self.get_now_ts()
             1565990318.728324

        """
        return (await self.get_now(aware)).timestamp()

    @overload
    @utils.sync_decorator
    async def now_is_between(self, start_time: str, end_time: str) -> bool: ...

    @overload
    @utils.sync_decorator
    async def now_is_between(self, start_time: str, end_time: str, name: str) -> bool: ...

    @overload
    @utils.sync_decorator
    async def now_is_between(self, start_time: str, end_time: str, now: str) -> bool: ...

    @utils.sync_decorator
    async def now_is_between(self, start_time: str | dt.datetime, end_time: str | dt.datetime, name: str | None = None, now: str | None = None) -> bool:
        """Determine if the current `time` is within the specified start and end times.

        This function takes two string representations of a ``time`` ()or ``sunrise`` or ``sunset`` offset) and returns
        ``true`` if the current time is between those 2 times. Its implementation can correctly handle transitions
        across midnight.

        Args:
            start_time (str): A string representation of the start time.
            end_time (str): A string representation of the end time.
            name (str, optional): Name of the calling app or module. It is used only for logging purposes.
            now (str, optional): If specified, `now` is used as the time for comparison instead of the current time.
                Useful for testing.

        Returns:
            bool: ``True`` if the current time is within the specified start and end times, otherwise ``False``.

        Note:
            The string representation of the ``start_time`` and ``end_time`` should follows
            one of these formats:

                a. ``HH:MM:SS`` - the time in Hours Minutes and Seconds, 24 hour format.

                b. ``sunrise|sunset [+|- HH:MM:SS]``- time of the next sunrise or sunset
                with an optional positive or negative offset in Hours Minutes,
                and Seconds.

        Examples:
            >>> if self.now_is_between("17:30:00", "08:00:00"):
            >>>     #do something

            >>> if self.now_is_between("sunset - 00:45:00", "sunrise + 00:45:00"):
            >>>     #do something

        """
        return await self.AD.sched.now_is_between(start_time, end_time, name or self.name, now)

    @utils.sync_decorator
    async def sunrise(self, aware: bool = False, today: bool = False, days_offset: int = 0) -> dt.datetime:
        """Return a `datetime` object that represent when a sunrise will occur.

        Args:
            aware (bool, optional): Whether the resulting datetime object will be aware of timezone.
            today (bool, optional): Defaults to ``False``, which will return the first sunrise in the future,
                regardless of the day. If set to ``True``, the function will return the sunrise for the current day,
                even if it is in the past.
            days_offset (int, optional): Specify the number of days (positive or negative) for the sunrise. This can
                only be used in combination with the today flag

        Examples:
            >>> self.sunrise()
            2023-02-02 07:11:50.150554

            >>> self.sunrise(today=True)
            2023-02-01 07:12:20.272403

        """
        return await self.AD.sched.sunrise(aware, today, days_offset)

    @utils.sync_decorator
    async def sunset(self, aware: bool = False, today: bool = False, days_offset: int = 0) -> dt.datetime:
        """Return a `datetime` object that represent when a sunset will occur.

        Args:
            aware (bool, optional): Whether the resulting datetime object will be aware of timezone.
            today (bool, optional): Defaults to ``False``, which will return the first sunset in the future,
                regardless of the day. If set to ``True``, the function will return the sunset for the current day,
                even if it is in the past.
            days_offset (int, optional): Specify the number of days (positive or negative) for the sunset. This can
                only be used in combination with the today flag

        Examples:
            >>> self.sunset()
            2023-02-01 18:09:00.730704

            >>> self.sunset(today=True, days_offset=1)
            2023-02-02 18:09:46.252314

        """
        return await self.AD.sched.sunset(aware, today, days_offset)

    @utils.sync_decorator
    async def datetime(self, aware: bool = False) -> dt.datetime:
        """Get a ``datetime`` object representing the current local date and time.

        Use this instead of the standard Python methods in order to correctly account for the time when using the time
        travel feature, which is usually done for testing.

        Args:
            aware (bool, optional): Whether the resulting datetime object will be aware of timezone.

        Examples:
            >>> self.datetime()
            2019-08-15 20:15:55.549379

        """
        return await self.get_now(aware=aware)

    @utils.sync_decorator
    async def time(self) -> dt.time:
        """Get a ``time`` object representing the current local time.

        Use this instead of the standard Python methods in order to correctly account for the time when using the time
        travel feature, which is usually done for testing.

        Examples:
            >>> self.time()
            20:15:31.295751

        """
        return (await self.get_now(aware=True)).time()

    @utils.sync_decorator
    async def date(self) -> dt.date:
        """Get a ``date`` object representing the current local date.

        Use this instead of the standard Python methods in order to correctly account for the time when using the time
        travel feature, which is usually done for testing.

        Examples:
            >>> self.date()
            2019-08-15

        """
        return (await self.get_now(aware=True)).date()

    def get_timezone(self) -> str:
        """Returns the current time zone."""
        return self.AD.time_zone

    #
    # Scheduler
    #

    @utils.sync_decorator
    async def timer_running(self, handle: str) -> bool:
        """Check if a previously created timer is still running.

        Args:
            handle (str): The handle returned from the original call to create the timer.

        Returns:
            Boolean representing whether the timer is still running.

        Examples:
            >>> self.timer_running(handle)
            True

        """
        name = self.name
        self.logger.debug("Checking timer with handle %s for %s", handle, self.name)
        return self.AD.sched.timer_running(name, handle)

    @utils.sync_decorator
    async def cancel_timer(self, handle: str, silent: bool = False) -> bool:
        """Cancel a previously created timer.

        Args:
            handle (str): The handle returned from the original call to create the timer.
            silent (bool, optional): Set to ``True`` to suppress warnings if the handle is not found. Defaults to
                ``False``.

        Returns:
            Boolean representing whether the timer was successfully canceled.

        Examples:
            >>> self.cancel_timer(handle)
            True

            >>> self.cancel_timer(handle, silent=True)

        """
        self.logger.debug("Canceling timer with handle %s for %s", handle, self.name)
        return await self.AD.sched.cancel_timer(self.name, handle, silent)

    @utils.sync_decorator
    async def reset_timer(self, handle: str) -> bool:
        """Reset a previously created timer.

        The timer must be actively running, and not a sun-related one like sunrise/sunset for it to be reset.

        Args:
            handle (str): The handle returned from the original call to create the timer.

        Returns:
            Boolean representing whether the timer reset was successful.

        Examples:
            >>> self.reset_timer(handle)
            True

        """
        self.logger.debug("Resetting timer with handle %s for %s", handle, self.name)
        return await self.AD.sched.reset_timer(self.name, handle)

    @utils.sync_decorator
    async def info_timer(self, handle: str) -> tuple[dt.datetime, int, dict] | None:
        """Get information about a previously created timer.

        Args:
            handle (str): The handle returned from the original call to create the timer.

        Returns:
            A tuple with the following values or ``None`` if handle is invalid or timer no longer exists.

            - `time` - datetime object representing the next time the callback will be fired
            - `interval` - repeat interval if applicable, `0` otherwise.
            - `kwargs` - the values supplied when the callback was initially created.

        Examples:
            >>> if (info := self.info_timer(handle)) is not None:
            >>>     time, interval, kwargs = info

        """
        return await self.AD.sched.info_timer(handle, self.name)

    @utils.sync_decorator
    async def run_in(
        self,
        callback: Callable,
        delay: str | int | float | timedelta,
        *args,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Run a function after a specified delay.

        This method should always be used instead of ``time.sleep()``.

        Args:
            callback: Function that will be called after the specified delay. It must conform to the standard scheduler
                callback format documented `here <APPGUIDE.html#scheduler-callbacks>`__.
            delay (str, int, float, datetime.timedelta): Delay before the callback is executed. Numbers will be
                interpreted as seconds. Strings can be in the format of ``HH:MM``, ``HH:MM:SS``, or
                ``DD days, HH:MM:SS``. If a ``timedelta`` object is given, it will be used as is.
            *args: Arbitrary positional arguments to be provided to the callback function when it is triggered.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number. The ID numbers start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer later before it's been executed.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value, they can be negative
            to denote a random offset before and event, or positive to denote a random offset after an event.

        Examples:
            Run the specified callback after 0.5 seconds.

            >>> def delayed_callback(self, **kwargs): ... # example callback
            >>> self.handle = self.run_in(self.delayed_callback, 0.5)

            Run the specified callback after 2.7 seconds with a custom keyword arg ``title``.

            >>> def delayed_callback(self, title: str, **kwargs): ... # example callback
            >>> self.handle = self.run_in(self.delayed_callback, 2.7, title="Delayed Callback Title")


        """
        delay = delay if isinstance(delay, timedelta) else utils.parse_timedelta(delay)
        assert isinstance(delay, timedelta), f"Invalid delay: {delay}"
        self.logger.debug(f"Registering run_in in {delay.total_seconds():.1f}s for {self.name}")
        exec_time = (await self.get_now()) + delay
        sched_func = functools.partial(callback, *args, **kwargs)
        return await self.AD.sched.insert_schedule(
            name=self.name,
            aware_dt=exec_time,
            callback=sched_func,
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
        )

    @utils.sync_decorator
    async def run_once(
        self,
        callback: Callable,
        start: str | dt.time | dt.datetime | None = None,
        *args,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Run a function once, at the specified time of day. This is essentially an alias for ``run_at()``.

        Args:
            callback: Function that will be called at the specified time. It must conform to the standard scheduler
                callback format documented `here <APPGUIDE.html#scheduler-callbacks>`__.
            start (str, datetime.time): Time the callback will be triggered. It should be either a Python ``time``
                object, ``datetime`` object, or a ``parse_time()`` formatted string that specifies when the callback
                will occur. If the time specified is in the past, the callback will occur the `next day` at the
                specified time.
            *args: Arbitrary positional arguments to be provided to the callback function when it is triggered.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number. The ID numbers start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer later before it's been executed.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value, they can be negative
            to denote a random offset before and event, or positive to denote a random offset after an event.

        Examples:
            Run at 10:30am today, or 10:30am tomorrow if it is already after 10:30am.

            >>> def delayed_callback(self, **kwargs): ...  # example callback
            >>> handle = self.run_once(self.delayed_callback, datetime.time(10, 30, 0))

            Run today at 04:00pm using the ``parse_time()`` function.

            >>> def delayed_callback(self, **kwargs): ...  # example callback
            >>> handle = self.run_once(self.delayed_callback, "04:00:00 PM")

            Run at sunset.

            >>> def delayed_callback(self, **kwargs): ...  # example callback
            >>> handle = self.run_once(self.delayed_callback, "sunset")

            Run an hour after sunrise.

            >>> def delayed_callback(self, **kwargs): ...  # example callback
            >>> handle = self.run_once(self.delayed_callback, "sunrise + 01:00:00")

        """
        return await self.run_at(callback, start, *args, random_start=random_start, random_end=random_end, pin=pin, pin_thread=pin_thread, **kwargs)

    @utils.sync_decorator
    async def run_at(
        self,
        callback: Callable,
        start: str | dt.time | dt.datetime | None = None,
        *args,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Run a function once, at the specified time of day.

        Args:
            callback: Function that will be called at the specified time. It must conform to the standard scheduler
                callback format documented `here <APPGUIDE.html#scheduler-callbacks>`__.
            start (str, datetime.time): Time the callback will be triggered. It should be either a Python ``time``
                object, ``datetime`` object, or a ``parse_time()`` formatted string that specifies when the callback
                will occur. If the time specified is in the past, the callback will occur the `next day` at the
                specified time.
            *args: Arbitrary positional arguments to be provided to the callback function when it is triggered.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number. The ID numbers start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer later before it's been executed.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value, they can be negative
            to denote a random offset before and event, or positive to denote a random offset after an event.

        Examples:
            Run at 10:30am today, or 10:30am tomorrow if it is already after 10:30am.

            >>> def delayed_callback(self, **kwargs): ...  # example callback
            >>> handle = self.run_once(self.delayed_callback, datetime.time(10, 30, 0))

            Run today at 04:00pm using the `parse_time()` function.

            >>> def delayed_callback(self, **kwargs): ...  # example callback
            >>> handle = self.run_once(self.delayed_callback, "04:00:00 PM")

            Run at sunset.

            >>> def delayed_callback(self, **kwargs): ...  # example callback
            >>> handle = self.run_once(self.delayed_callback, "sunset")

            Run an hour after sunrise.

            >>> def delayed_callback(self, **kwargs): ...  # example callback
            >>> handle = self.run_once(self.delayed_callback, "sunrise + 01:00:00")

        """
        match start:
            case str():
                info = await self.AD.sched._parse_time(start, self.name)
                start = info["datetime"]
            case dt.time():
                start = dt.datetime.combine(await self.date(), start).astimezone(self.AD.tz)
            case dt.datetime():
                ...
            case _:
                raise ValueError("Invalid type for start")

        self.logger.debug("Registering run_at at %s for %s", start, self.name)

        return await self.AD.sched.insert_schedule(
            name=self.name,
            aware_dt=start,
            callback=functools.partial(callback, *args, **kwargs),
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
        )

    @utils.sync_decorator
    async def run_daily(
        self,
        callback: Callable,
        start: str | dt.time | dt.datetime | None = None,
        *args,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Run a function at the same time every day.

        Args:
            callback: Function that will be called every day at the specified time. It must conform to the standard
                scheduler callback format documented `here <APPGUIDE.html#scheduler-callbacks>`__.
            start (str, datetime.time, datetime.datetime, optional): Start time for the interval calculation. If this is
                in the future, this will be the first time the callback is triggered. If this is in the past, the
                intervals will be calculated forward from the start time, and the first trigger will be the first
                interval in the future.

                - If this is a ``str`` it will be parsed with :meth:`~appdaemon.adapi.ADAPI.parse_time()`.
                - If this is a ``datetime.time`` object, the current date will be assumed.
                - If this is a ``datetime.datetime`` object, it will be used as is.

            *args: Arbitrary positional arguments to be provided to the callback function when it is triggered.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number, which start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer later before it's been executed.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value, they can be negative
            to denote a random offset before and event, or positive to denote a random offset after an event.

        Examples:
            Run every day at 10:30am.

            >>> self.run_daily(self.daily_callback, datetime.time(10, 30))

            Run at 7:30pm every day using the ``parse_time()`` function.

            >>> handle = self.run_daily(self.daily_callback, "07:30:00 PM")

            Run every day at sunrise.

            >>> handle = self.run_daily(self.daily_callback, "sunrise")

            Run every day an hour after sunset.

            >>> handle = self.run_daily(self.daily_callback, "sunset + 01:00:00")

        """
        offset = 0
        sun: Literal["sunrise", "sunset"] | None = None
        match start:
            case str():
                info = await self.AD.sched._parse_time(start, self.name)
                start, offset, sun = info["datetime"], info["offset"], info["sun"]
            case dt.time():
                date = await self.date()
                start = dt.datetime.combine(date, start).astimezone(self.AD.tz)
            case dt.datetime():
                ...
            case _:
                raise ValueError("Invalid type for start")

        ad_kwargs = dict(
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
        )

        match sun:
            case None:
                return await self.run_every(callback, start, timedelta(days=1), *args, **ad_kwargs, **kwargs)
            case "sunrise":
                return await self.run_at_sunrise(callback, *args, repeat=True, offset=offset, **ad_kwargs, **kwargs)
            case "sunset":
                return await self.run_at_sunset(callback, *args, repeat=True, offset=offset, **ad_kwargs, **kwargs)

    @utils.sync_decorator
    async def run_hourly(
        self,
        callback: Callable,
        start: str | dt.time | dt.datetime | None = None,
        *args,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Run a function at the same time every hour.

        Args:
            callback: Function that will be called every hour starting at the specified time. It must conform to the
                standard scheduler callback format documented `here <APPGUIDE.html#scheduler-callbacks>`__.
            start (str, datetime.time, datetime.datetime, optional): Start time for the interval calculation. If this is
                in the future, this will be the first time the callback is triggered. If this is in the past, the
                intervals will be calculated forward from the start time, and the first trigger will be the first
                interval in the future.

                - If this is a ``str`` it will be parsed with :meth:`~appdaemon.adapi.ADAPI.parse_time()`.
                - If this is a ``datetime.time`` object, the current date will be assumed.
                - If this is a ``datetime.datetime`` object, it will be used as is.

            *args: Arbitrary positional arguments to be provided to the callback function when it is triggered.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number, which start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer later before it's been executed.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value, they can be negative
            to denote a random offset before and event, or positive to denote a random offset after an event.

        Examples:
            Run every hour, on the hour.

            >>> runtime = datetime.time(0, 0, 0)
            >>> self.run_hourly(self.run_hourly_c, runtime)

        """
        return await self.run_every(callback, start, timedelta(hours=1), *args, random_start=random_start, random_end=random_end, pin=pin, pin_thread=pin_thread, **kwargs)

    @utils.sync_decorator
    async def run_minutely(
        self,
        callback: Callable,
        start: str | dt.time | dt.datetime | None = None,
        *args,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Run the callback at the same time every minute.

        Args:
            callback: Function that will be called every hour starting at the specified time. It must conform to the
                standard scheduler callback format documented `here <APPGUIDE.html#scheduler-callbacks>`__.
            start (str, datetime.time, datetime.datetime, optional): Start time for the interval calculation. If this is
                in the future, this will be the first time the callback is triggered. If this is in the past, the
                intervals will be calculated forward from the start time, and the first trigger will be the first
                interval in the future.

                - If this is a ``str`` it will be parsed with :meth:`~appdaemon.adapi.ADAPI.parse_time()`.
                - If this is a ``datetime.time`` object, the current date will be assumed.
                - If this is a ``datetime.datetime`` object, it will be used as is.

            *args: Arbitrary positional arguments to be provided to the callback function when it is triggered.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number, which start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer later before it's been executed.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value, they can be negative
            to denote a random offset before and event, or positive to denote a random offset after an event.


        Examples:
            Run every minute on the minute.

            >>> time = datetime.time(0, 0, 0)
            >>> self.run_minutely(self.run_minutely_c, time)

        """
        return await self.run_every(callback, start, timedelta(minutes=1), *args, random_start=random_start, random_end=random_end, pin=pin, pin_thread=pin_thread, **kwargs)

    @utils.sync_decorator
    async def run_every(
        self,
        callback: Callable,
        start: str | dt.time | dt.datetime | None = None,
        interval: str | int | float | dt.timedelta = 0,
        *args,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Run a function at a regular time interval.

        Args:
            callback: Function that will be called at the specified time interval. It must conform to the standard
                scheduler callback format documented `here <APPGUIDE.html#scheduler-callbacks>`__.
            start (str, datetime.time, datetime.datetime, optional): Start time for the interval calculation. If this is
                in the future, this will be the first time the callback is triggered. If this is in the past, the
                intervals will be calculated forward from the start time, and the first trigger will be the first
                interval in the future.

                - If this is a ``str`` it will be parsed with :meth:`~appdaemon.adapi.ADAPI.parse_time()`.
                - If this is a ``datetime.time`` object, the current date will be assumed.
                - If this is a ``datetime.datetime`` object, it will be used as is.

            interval (str, int, float, datetime.timedelta): Time interval between callback triggers.

                - If this is an ``int`` or ``float``, it will be interpreted as seconds.
                - If this is a ``str`` it will be parsed with ``parse_timedelta()``

                    - ``HH:MM``
                    - ``HH:MM:SS``
                    - ``DD days, HH:MM:SS``

                - If this is a ``timedelta`` object, the current date will be assumed.

            *args: Arbitrary positional arguments to be provided to the callback function when it is triggered.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number, which start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer later before it's been executed.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value, they can be negative
            to denote a random offset before an event, or positive to denote a random offset after an event.

        Examples:
            Run every 10 minutes starting now.

            .. code-block:: python
              :emphasize-lines: 3

                class MyApp(ADAPI):
                    def initialize(self):
                        self.run_every(self.timed_callback, interval=datetime.timedelta(minutes=10))

                    def timed_callback(self, **kwargs): ...  # example callback

            Run every 5 minutes starting in 5 seconds.

            .. code-block:: python
              :emphasize-lines: 3

                class MyApp(ADAPI):
                    def initialize(self):
                        self.run_every(self.timed_callback, "now+5", 5 * 60)

                    def timed_callback(self, **kwargs): ...  # example callback

            Run every 17 minutes starting in 2 hours time.

            .. code-block:: python
              :emphasize-lines: 5

                class MyApp(ADAPI):
                    def initialize(self):
                        start = self.get_now() + datetime.timedelta(hours=2)
                        interval = datetime.timedelta(minutes=17)
                        self.run_every(self.timed_callback, start, interval)

                    def timed_callback(self, **kwargs): ...  # example callback

        """
        interval = utils.parse_timedelta(interval)
        assert isinstance(interval, dt.timedelta)

        match start:
            case str():
                if not start.startswith("now"):
                    info = await self.AD.sched._parse_time(start, self.name)
                    start = info["datetime"]
            case dt.time():
                date = await self.date()
                start = dt.datetime.combine(date, start).astimezone(self.AD.tz)
            case dt.datetime():
                ...
            case None:
                pass  # This will be handled by get_next_period
            case _:
                raise ValueError("Invalid type for start")

        next_period = await self.AD.sched.get_next_period(interval, start)

        self.logger.debug(
            "Registering %s for run_every in %s intervals, starting %s",
            callback.__name__,
            interval,
            next_period,
        )

        return await self.AD.sched.insert_schedule(
            name=self.name,
            aware_dt=next_period,
            callback=functools.partial(callback, *args, **kwargs),
            repeat=True,
            interval=interval.total_seconds(),
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
        )

    @utils.sync_decorator
    async def run_at_sunset(
        self,
        callback: Callable,
        *args,
        repeat: bool = False,
        offset: int | None = None,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Runs a callback every day at or around sunset.

        Args:
            callback: Function to be invoked at or around sunset. It must conform to the
                standard Scheduler Callback format documented `here <APPGUIDE.html#about-schedule-callbacks>`__.
            *args: Arbitrary positional arguments to be provided to the callback function when it is triggered.
            offset (int, optional): The time in seconds that the callback should be delayed after
                sunset. A negative value will result in the callback occurring before sunset.
                This parameter cannot be combined with ``random_start`` or ``random_end``.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number. The ID numbers start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Example using timedelta.

            >>> self.run_at_sunset(self.sun, offset = datetime.timedelta(minutes = -45).total_seconds())

            Or you can just do the math yourself.

            >>> self.run_at_sunset(self.sun, offset = 30 * 60)

            Run at a random time +/- 60 minutes from sunset.

            >>> self.run_at_sunset(self.sun, random_start = -60*60, random_end = 60*60)

            Run at a random time between 30 and 60 minutes before sunset.

            >>> self.run_at_sunset(self.sun, random_start = -60*60, random_end = 30*60)

        """
        sunset = await self.AD.sched.next_sunset()
        td = utils.parse_timedelta(offset)
        self.logger.debug(f"Registering run_at_sunset at {sunset + td} with {args}, {kwargs}")
        return await self.AD.sched.insert_schedule(
            name=self.name,
            aware_dt=sunset,
            callback=functools.partial(callback, *args, **kwargs),
            repeat=repeat,
            type_="next_setting",
            offset=offset,
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
        )

    @utils.sync_decorator
    async def run_at_sunrise(
        self,
        callback: Callable,
        *args,
        repeat: bool = False,
        offset: int | None = None,
        random_start: int | None = None,
        random_end: int | None = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs,
    ) -> str:
        """Runs a callback every day at or around sunrise.

        Args:
            callback: Function to be invoked at or around sunrise. It must conform to the
                standard Scheduler Callback format documented `here <APPGUIDE.html#about-schedule-callbacks>`__.
            *args: Arbitrary positional arguments to be provided to the callback function
                when it is invoked.
            offset (int, optional): The time in seconds that the callback should be delayed after
                sunrise. A negative value will result in the callback occurring before sunrise.
                This parameter cannot be combined with ``random_start`` or ``random_end``.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): Optional setting to override the default thread pinning behavior. By default, this is
                effectively ``True``, and ``pin_thread`` gets set when the app starts.
            pin_thread (int, optional): Specify which thread from the worker pool will run the callback. The threads
                each have an ID number. The ID numbers start at 0 and go through (number of threads - 1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback function when it is triggered.

        Returns:
            A handle that can be used to cancel the timer.

        Note:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Run 45 minutes before sunrise.

            >>> self.run_at_sunrise(self.sun, offset = datetime.timedelta(minutes = -45).total_seconds())

            Or you can just do the math yourself.

            >>> self.run_at_sunrise(self.sun, offset = 30 * 60)

            Run at a random time +/- 60 minutes from sunrise.

            >>> self.run_at_sunrise(self.sun, random_start = -60*60, random_end = 60*60)

            Run at a random time between 30 and 60 minutes before sunrise.

            >>> self.run_at_sunrise(self.sun, random_start = -60*60, random_end = 30*60)

        """
        sunrise = await self.AD.sched.sunrise(today=False, aware=True)
        td = utils.parse_timedelta(offset)
        self.logger.debug(f"Registering run_at_sunrise at {sunrise + td} with {args}, {kwargs}")
        return await self.AD.sched.insert_schedule(
            name=self.name,
            aware_dt=sunrise,
            callback=functools.partial(callback, *args, **kwargs),
            repeat=repeat,
            type_="next_rising",
            offset=offset,
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
        )

    #
    # Dashboard
    #

    def dash_navigate(self, target: str, timeout: int = -1, ret: str | None = None, sticky: int = 0, deviceid: str | None = None, dashid: str | None = None) -> None:
        """Forces all connected Dashboards to navigate to a new URL.

        Args:
            target (str): Name of the new Dashboard to navigate to (e.g., ``/SensorPanel``).
                Note that this value is not a URL.
            timeout (int): Length of time to stay on the new dashboard before returning
                to the original. This argument is optional and if not specified, the
                navigation will be permanent. Note that if there is a click or touch on
                the new panel before the timeout expires, the timeout will be cancelled.
            ret (str): Dashboard to return to after the timeout has elapsed.
            sticky (int): Specifies whether or not to return to the original dashboard
                after it has been clicked on. The default behavior (``sticky=0``) is to remain
                on the new dashboard if clicked, or return to the original otherwise.
                By using a different value (sticky= 5), clicking the dashboard will extend
                the amount of time (in seconds), but it will return to the original dashboard
                after a period of inactivity equal to timeout.
            deviceid (str): If set, only the device which has the same deviceid will navigate.
            dashid (str): If set, all devices currently on a dashboard which the title contains
                the substring dashid will navigate. ex: if dashid is "kichen", it will match
                devices which are on "kitchen lights", "kitchen sensors", "ipad - kitchen", etc.

        Returns:
            None.

        Examples:
            Switch to AlarmStatus Panel then return to current panel after 10 seconds.

            >>> self.dash_navigate("/AlarmStatus", timeout=10)

            Switch to Locks Panel then return to Main panel after 10 seconds.

            >>> self.dash_navigate("/Locks", timeout=10, ret="/SensorPanel")

        """
        kwargs = {"command": "navigate", "target": target, "sticky": sticky}

        if timeout != -1:
            kwargs["timeout"] = timeout
        if ret is not None:
            kwargs["return"] = ret
        if deviceid is not None:
            kwargs["deviceid"] = deviceid
        if dashid is not None:
            kwargs["dashid"] = dashid
        self.fire_event("ad_dashboard", **kwargs)

    #
    # Async
    #

    async def run_in_executor(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Run a sync function from within an async function using a thread from AppDaemon's internal thread pool.

        This essentially converts a sync function into an async function, which allows async functions to use it. This
        is useful for even short-ish functions (even <1s execution time) because it allows the event loop to continue
        processing other events while waiting for the function to complete. Blocking the event loop prevents AppDaemon's
        internals from running, which interferes with all other apps, and can cause issues with connection timeouts.

        Args:
            func: The function to be executed.
            *args (optional): Any additional arguments to be used by the function
            **kwargs (optional): Any additional keyword arguments to be used by the function

        Returns:
            None

        Examples:
            >>> await self.run_in_executor(self.run_request)

        """
        preloaded_function = functools.partial(func, *args, **kwargs)
        future = self.AD.loop.run_in_executor(self.AD.executor, preloaded_function)
        return await future

    def submit_to_executor(self, func: Callable[..., T], *args, callback: Callable | None = None, **kwargs) -> Future[T]:
        """Submit a sync function from within another sync function to be executed using a thread from AppDaemon's
        internal thread pool.

        This function does not wait for the result of the submitted function and immediately returns a Future object.
        This is useful for executing long-running functions without blocking the thread for other callbacks. The result
        can be retrieved later using the Future object, but it's recommended to use a callback to handle the result
        instead.

        Args:
            func: The function to be executed.
            *args (optional): Any additional arguments to be used by the function
            callback (optional): A callback function to be executed when the function has completed.
            **kwargs (optional): Any additional keyword arguments to be used by the function.

        Returns:
            A Future object representing the result of the function.

        Examples:
            Submit a long-running function to be executed in the background

            >>> def initialize(self):
                    self.long_future = self.submit_to_executor(self.long_request, url, callback=self.result_callback)

            Long running function:

            >>> def long_request(self, url: str):
                    import requests
                    res = requests.get(url)
                    return res.json()

            Callback to handle the result:

            >>> def result_callback(self, result: dict, **kwargs):
                    # Set the attributes of a sensor with the result
                    self.set_state("sensor.url_result", state="ready", attributes=result, replace=True)

        """

        # get stuff we'll need to fake scheduler call
        sched_data = {
            "id": uuid.uuid4().hex,
            "name": self.name,
            "objectid": self.AD.app_management.objects[self.name].id,
            "type": "scheduler",
            "function": callback,
            "pin_app": self.get_app_pin(),
            "pin_thread": self.get_pin_thread(),
        }

        def callback_inner(f: Future):
            try:
                sched_data["kwargs"] = {"result": f.result()}
                self.create_task(self.AD.threading.dispatch_worker(self.name, sched_data))

                # callback(f.result(), kwargs)
            except Exception as e:
                self.error(str(e), level="ERROR")

        future = self.AD.executor.submit(func, *args, **kwargs)

        if callback is not None:
            self.logger.debug("Adding add_done_callback for future %s for %s", future, self.name)
            future.add_done_callback(callback_inner)

        self.AD.futures.add_future(self.name, future)
        return future

    @utils.sync_decorator
    async def create_task(self, coro: Coroutine[Any, Any, T], callback: Callable | None = None, name: str | None = None, **kwargs) -> asyncio.Task[T]:
        """Wrap the `coro` coroutine into a ``Task`` and schedule its execution. Return the ``Task`` object.

        Uses AppDaemon's internal event loop to run the task, so the task will be run in the same thread as the app.
        Running an async method like this is useful for long-running tasks because it bypasses the timeout that
        AppDaemon otherwise imposes on callbacks.

        The callback will be run in the app's thread, like other AppDaemon callbacks, and will have the normal timeout
        imposed on it.

        See `creating tasks <https://docs.python.org/3/library/asyncio-task.html#creating-tasks>`_ for in the python
        documentation for more information.

        Args:
            coro: The coroutine object (`not coroutine function`) to be executed.
            callback: The non-async callback to be executed when complete.
            **kwargs (optional): Any additional keyword arguments to send the callback.

        Returns:
            A ``Task`` object, which can be cancelled by calling f.cancel().

        Examples:
            Define your callback

            >>> def my_callback(self, **kwargs: Any) -> Any: ...

            Create the task

            >>> task = self.create_task(asyncio.sleep(3), callback=self.my_callback)

            Keyword Arguments
            ^^^^^^^^^^^^^^^^^
            Define your callback with a custom keyword argument ``my_kwarg``

            >>> def my_callback(self, result: Any, my_kwarg: str, **kwargs: Any) -> Any:
                    self.log(f"Result: {result}, my_kwarg: {my_kwarg}")

            Use the custom keyword argument when creating the task

            >>> task = self.create_task(asyncio.sleep(3), callback=self.my_callback, my_kwarg="special value")

        """
        managed_object = self.AD.app_management.objects[self.name]
        # get stuff we'll need to fake scheduler call
        sched_data = {
            "id": uuid.uuid4().hex,
            "name": self.name,
            "objectid": managed_object.id,
            "type": "scheduler",
            "function": callback,
            "pin_app": managed_object.pin_app,
            "pin_thread": managed_object.pin_thread,
        }

        def callback_inner(f: asyncio.Task[T]) -> None:
            """This wraps the user-provided callback to ensure that it's run by the AppDaemon internals."""
            try:
                kwargs["result"] = f.result()
                sched_data["kwargs"] = kwargs
                self.create_task(self.AD.threading.dispatch_worker(self.name, sched_data))
            except asyncio.CancelledError:
                pass

        task = self.AD.loop.create_task(coro, name=name)
        if callback is not None:
            self.logger.debug("Adding add_done_callback for future %s for %s", task, self.name)
            # Use the native python mechanism to add a callback to the task.
            task.add_done_callback(callback_inner)

        self.AD.futures.add_future(self.name, task)
        return task

    @staticmethod
    async def sleep(delay: float, result=None) -> None:
        """Pause execution for a certain time span
        (not available in sync apps)

        Args:
            delay (float): Number of seconds to pause.
            result (optional): Result to return upon delay completion.

        Returns:
            Result or `None`.

        Note:
            This function is not available in sync apps.

        Examples:
            >>> async def myfunction(self):
            >>>     await self.sleep(5)
        """
        is_async = None
        try:
            asyncio.get_event_loop()
            is_async = True
        except RuntimeError:
            is_async = False

        if not is_async:
            raise RuntimeError("The sleep method is for use in ASYNC methods only")

        return await asyncio.sleep(delay, result=result)

    #
    # Other
    #

    def get_entity(self, entity: str, namespace: str | None = None, check_existence: bool = True) -> Entity:
        namespace = namespace or self.namespace
        if check_existence:
            self._check_entity(namespace, entity)
        return Entity(self, namespace, entity)

    def run_in_thread(self, callback: Callable, thread: int, **kwargs) -> None:
        """Schedules a callback to be run in a different thread from the current one.

        Args:
            callback: Function to be run on the new thread.
            thread (int): Thread number (0 - number of threads).
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Returns:
            None.

        Examples:
            >>> self.run_in_thread(my_callback, 8)

        """
        self.run_in(callback, delay=0, pin=False, pin_thread=thread, **kwargs)

    @utils.sync_decorator
    async def get_thread_info(self) -> Any:
        """Gets information on AppDaemon worker threads.

        Returns:
            A dictionary containing all the information for AppDaemon worker threads.

        Examples:
            >>> thread_info = self.get_thread_info()

        """
        return await self.AD.threading.get_thread_info()

    @utils.sync_decorator
    async def get_scheduler_entries(self):
        """Gets information on AppDaemon scheduler entries.

        Returns:
            A dictionary containing all the information for entries in the AppDaemon scheduler.

        Examples:
            >>> schedule = self.get_scheduler_entries()

        """
        return await self.AD.sched.get_scheduler_entries()

    @utils.sync_decorator
    async def get_callback_entries(self) -> list:
        """Gets information on AppDaemon callback entries.

        Returns:
            A dictionary containing all the information for entries in the AppDaemon state,
            and event callback table.

        Examples:
            >>> callbacks = self.get_callback_entries()

        """
        return await self.AD.callbacks.get_callback_entries()

    def get_entity_callbacks(self, entity_id: str) -> dict[str, dict[str, Any]]:
        return self.get_entity(entity_id).get_callbacks()

    @utils.sync_decorator
    async def depends_on_module(self, *modules: list[str]) -> None:
        """Registers a global_modules dependency for an app.

        Args:
            *modules: Modules to register a dependency on.

        Returns:
            None.

        Examples:
            >>> import some_module
            >>> import another_module
            >>> # later
            >>> self.depends_on_module('some_module')

        """
        self.log("depends_on_module is deprecated", level="WARNING")

    #
    # Dependencies
    #

    def get_app_python_dependencies(self, app_name: str | None = None) -> list[Path]:
        """Get a list of paths to python files that this app depends on, even indirectly. If any of the files for these
        modules change, the app will be reloaded.

        Args:
            app_name (str): Name of the app to get dependencies for. If not provided, uses the current app's name.

        Returns:
            Sorted list of paths to Python files that the given app depends on.
        """
        app_name = app_name or self.name

        # Include any apps that the given one depends on
        apps = {app_name} | dependency.find_all_dependents(
            app_name,
            self.AD.app_management.dependency_manager.app_deps.dep_graph,
        )  # fmt: skip

        # Get all the python modules for the included apps
        modules = {
            self.AD.app_management.app_config[app_name].module_name
            for app_name in apps
        }  # fmt: skip

        # Get the transitive closure of all those modules
        graph = self.AD.app_management.dependency_manager.python_deps.dep_graph
        modules |= dependency.find_all_dependents(modules, graph)

        # Filter for modules whose files are in the app directory
        deps = sorted(
            p for d in modules
            if ((mod := sys.modules.get(d)) is not None) and
            (file := mod.__file__) is not None and
            (p := Path(file)).is_relative_to(self.AD.app_dir)
        )  # fmt: skip

        return deps
