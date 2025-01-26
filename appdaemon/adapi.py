import asyncio
import datetime as dt
import functools
import inspect
import logging
import re
import uuid
from collections.abc import Coroutine, Iterable, Mapping
from concurrent.futures import Future
from datetime import timedelta
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, overload

import iso8601

from appdaemon import utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.entity import Entity
from appdaemon.logging import Logging

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
    name: str
    """The app name, which is set by the top-level key in the YAML file
    """
    config_model: "AppConfig"
    """Pydantic model of the app configuration
    """
    config: Dict[str, Any]
    """Dictionary of the AppDaemon configuration
    """
    app_config: Dict[str, Any]
    """Dictionary of the full app configuration, which includes all apps
    """
    args: Dict[str, Any]
    """Dictionary of this app's configuration
    """

    app_dir: Path
    config_dir: Path
    _logging: Logging
    """Reference to the Logging subsystem object
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

        self.config = self.AD.config.model_dump(by_alias=True, exclude_unset=True)
        self.args = self.config_model.model_dump(by_alias=True, exclude_unset=True)

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

    @property
    def plugin_config(self) -> dict:
        self.get_plugin_config()
        return self.AD.plugins.config

    #
    # Logging
    #

    @overload
    def _log(self,
             logger: Logger,
             msg: str,
             level: str | int = "INFO",
             *args,
             ascii_encode: bool = True,
             exc_info: bool = False,
             stack_info: bool = False,
             stacklevel: int = 1,
             extra: Mapping[str, object] | None = None
    ) -> None: ...

    def _log(
        self,
        logger: Logger,
        msg: str,
        level: str | int = "INFO",
        *args,
        ascii_encode: bool = True,
        **kwargs
    ) -> None:
        if ascii_encode:
            msg = str(msg).encode("utf-8", "replace").decode("ascii", "replace")

        match level:
            case str():
                level = logging._nameToLevel[level]
            case int():
                assert level in logging._levelToName

        logger.log(level, msg, *args, **kwargs)

    @overload
    def log(
        self,
        msg: str,
        *args,
        level: str | int = "INFO",
        log: str | None = None,
        ascii_encode: bool = True,
        exc_info: bool = False,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None
    ) -> None: ...

    def log(
        self,
        msg: str,
        *args,
        level: str | int = "INFO",
        log: str | None = None,
        **kwargs
    ) -> None:
        """Logs a message to AppDaemon's main logfile.

        Args:
            msg (str): The message to log.
            level (str, optional): The log level of the message - takes a string representing the
                standard logger levels (Default: ``"WARNING"``).
            log (str, optional): Send the message to a specific log, either system or user_defined.
                System logs are ``main_log``, ``error_log``, ``diag_log`` or ``access_log``.
                Any other value in use here must have a corresponding user-defined entity in
                the ``logs`` section of appdaemon.yaml.
            ascii_encode (bool, optional): Switch to disable the encoding of all log messages to
                ascii. Set this to false if you want to log UTF-8 characters (Default: ``True``).
            exc_info (bool, optional):
            stack_info (bool, optional): If ``True`` the stack info will included.
            stacklevel (int, optional):
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

        try:
            msg = self._sub_stack(msg)
        except IndexError as i:
            self._log(self.err, i, "ERROR", *args, **kwargs)

        self._log(logger, msg, level, *args, **kwargs)

    @overload
    def error(
        self,
        msg: str,
        *args,
        level: str | int = "INFO",
        ascii_encode: bool = True,
        exc_info: bool = False,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None
    ) -> None: ...

    def error(
        self,
        msg: str,
        *args,
        level: str | int = "INFO",
        **kwargs
    ) -> None:
        """Logs a message to AppDaemon's error logfile.

        Args:
            msg (str): The message to log.
            *args: Positional arguments for populating the msg fields
            level (str, optional): The log level of the message - takes a string representing the
                standard logger levels.
            ascii_encode (bool, optional): Switch to disable the encoding of all log messages to
                ascii. Set this to false if you want to log UTF-8 characters (Default: ``True``).
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
        self._log(self.err, msg, level, *args, **kwargs)

    @overload
    async def listen_log(
        self,
        callback: Callable,
        level: str | int,
        namespace: str,
        log: str,
        pin: bool,
        pin_thread: int,
        **kwargs
    ) -> str: ...

    @utils.sync_decorator
    async def listen_log(
        self,
        callback: Callable,
        level: str | int = "INFO",
        namespace: str = "admin",
        **kwargs
    ) -> str:
        """Registers the App to receive a callback every time an App logs a message.

        Args:
            callback (function): Function to be called when a message is logged.
            level (str): Logging level to be used - lower levels will not be forwarded
                to the app (Default: ``"INFO"``).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            log (str, optional): Name of the log to listen to, default is all logs. The name
                should be one of the 4 built in types ``main_log``, ``error_log``, ``diag_log``
                or ``access_log`` or a user defined log entry.
            pin (bool, optional): If True, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).

        Returns:
            A unique identifier that can be used to cancel the callback if required.
            Since variables created within object methods are local to the function they are
            created in, and in all likelihood, the cancellation will be invoked later in a
            different function, it is recommended that handles are stored in the object
            namespace, e.g., self.handle.

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


        return await self.AD.logging.add_log_callback(namespace, self.name, callback, level, **kwargs)

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
            log (str): The name of the log you want to get the underlying logger object from,
                as described in the ``logs`` section of ``appdaemon.yaml``.

        Returns:
            The underlying logger object used for the error log.

        Examples:
            Log an error message to a user-defined logfile.

            >>> log = self.get_user_log("test_log")
            >>> log.error("Log an error", stack_info=True, exc_info=True)

        """
        logger = None
        if log in self.user_logs:
            # Did we use it already?
            logger = self.user_logs[log]
        else:
            # Build it on the fly
            parent = self.AD.logging.get_user_log(self, log)
            if parent is not None:
                logger = parent.getChild(self.name)
                self.user_logs[log] = logger
                if "log_level" in self.args:
                    logger.setLevel(self.args["log_level"])

        return logger

    def set_log_level(self, level: str | int) -> None:
        """Sets the log level for this App, which applies to the main log, error log, and all user logs.

        Args:
            level (str): Log level.

        Returns:
            None.

        Notes:
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

        Notes:
            Supported log levels: ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``,
            ``DEBUG``, ``NOTSET``.

        """
        self.err.setLevel(level)

    #
    # Threading
    #

    def set_app_pin(self, pin: bool) -> None:
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

    def get_app_pin(self) -> bool:
        """Finds out if the current App is currently pinned or not.

        Returns:
            bool: ``True`` if the App is pinned, ``False`` otherwise.

        Examples:
            >>> if self.get_app_pin(True):
            >>>     self.log("App pinned!")

        """
        return self.AD.app_management.get_app_pin(self.name)

    def set_pin_thread(self, thread: int) -> None:
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

    def get_pin_thread(self) -> int:
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

    def set_namespace(self, namespace: str) -> None:
        """Sets a new namespace for the App to use from that point forward.

        Args:
            namespace (str): Name of the new namespace

        Returns:
            None.

        Examples:
            >>> self.set_namespace("hass1")

        """
        # Keeping namespace get/set functions for legacy compatibility
        self.namespace = namespace

    def get_namespace(self) -> str:
        """Returns the App's namespace."""
        # Keeping namespace get/set functions for legacy compatibility
        return self.namespace

    def namespace_exists(self, namespace: str) -> bool:
        """Checks the existence of a namespace in AppDaemon.

        Args:
            namespace (str): The namespace to be checked if it exists.

        Returns:
            bool: ``True`` if the namespace exists, ``False`` otherwise.

        Examples:
            Check if the namespace ``storage`` exists within AD

            >>> if self.namespace_exists("storage"):
            >>>     #do something like create it

        """
        return self.AD.state.namespace_exists(namespace)

    @utils.sync_decorator
    async def add_namespace(
        self,
        namespace: str,
        writeback: str = 'safe',
        persist: bool = True
    ) -> str | None:
        """Used to add a user-defined namespaces from apps, which has a database file associated with it.

        This way, when AD restarts these entities will be reloaded into AD with its
        previous states within the namespace. This can be used as a basic form of
        non-volatile storage of entity data. Depending on the configuration of the
        namespace, this function can be setup to constantly be running automatically
        or only when AD shutdown. This function also allows for users to manually
        execute the command as when needed.

        Args:
            namespace (str): The namespace to be newly created, which must not be same as the operating namespace
            writeback (optional): The writeback to be used. Will be ``safe`` by default
            persist (bool, optional): If to make the namespace persistent. So if AD reboots
                it will startup will all the created entities being intact. It is persistent by default

        Returns:
            The file path to the newly created namespace. WIll be None if not persistent

        Examples:
            Add a new namespace called `storage`.

            >>> self.add_namespace("storage")

        """
        if namespace == self.namespace:  # if it belongs to this app's namespace
            raise ValueError("Cannot add namespace with the same name as operating namespace")

        return await self.AD.state.add_namespace(namespace, writeback, persist, self.name)

    @utils.sync_decorator
    async def remove_namespace(self, namespace: str) -> dict[str, Any] | None:
        """Used to remove a previously user-defined namespaces from apps, which has a database file associated with it.

        Args:
            namespace (str): The namespace to be removed, which must not be same as the operating namespace

        Returns:
            The data within that namespace

        Examples:
            Removes the namespace called `storage`.

            >>> self.remove_namespace("storage")

        """
        if namespace == self.namespace:  # if it belongs to this app's namespace
            raise ValueError("Cannot remove namespace with the same name as operating namespace")

        return await self.AD.state.remove_namespace(namespace)

    @utils.sync_decorator
    async def list_namespaces(self) -> list[str]:
        """Returns a list of available namespaces.

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
    async def get_app(self, name: str) -> 'ADAPI':
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

    def _check_entity(self, namespace: str, entity_id: str):
        """Ensures that the entity exists in the given namespace"""
        if "." in entity_id and not self.AD.state.entity_exists(namespace, entity_id):
            self.logger.warning("%s: Entity %s not found in namespace %s", self.name, entity_id, namespace)

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
    async def add_entity(
        self,
        entity_id: str,
        state: Any | None = None,
        attributes: dict | None= None,
        namespace: str | None = None
    ) -> None:
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
        namespace = namespace or self.namespace
        await self.get_entity_api(namespace, entity_id).add(state, attributes)

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

    def get_plugin_config(self, namespace: str | None = None) -> Any:
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

    def friendly_name(self, entity_id: str, namespace: str | None = None) -> str:
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

        return self.get_state(
            entity_id=entity_id,
            attribute="friendly_name",
            default=entity_id,
            namespace=namespace,
            copy=False
        )
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
        if not isinstance(mode, bool):
            self.logger.warning("%s not a valid parameter for Production Mode", mode)
            return
        await self.AD.utility.set_production_mode(mode)
        return mode

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
    def format_alexa_response(speech=None, card=None, title=None) -> dict:
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
        response = {"shouldEndSession": True}

        if speech is not None:
            response["outputSpeech"] = {"type": "PlainText", "text": speech}

        if card is not None:
            response["card"] = {"type": "Simple", "title": title, "content": card}

        speech = {"version": "1.0", "response": response, "sessionAttributes": {}}

        return speech

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
    async def register_endpoint(self, callback: Callable[[Any, dict], Any], endpoint: str = None, **kwargs) -> str | None:
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
    async def register_route(self, callback: Callable[[Any, dict], Any], route: str = None, **kwargs) -> str | None:
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

    @overload
    async def listen_state(
        self,
        callback: Callable,
        entity_id: str | Iterable[str],
        namespace: str,
        new: str | Callable,
        old: str | Callable,
        duration: int,
        attribute: str,
        timeout: int,
        immediate: bool,
        oneshot: bool,
        pin: bool,
        pin_thread: int,
        **kwargs
    ) -> str | list[str]: ...

    @utils.sync_decorator
    async def listen_state(
        self,
        callback: Callable,
        entity_id: str | Iterable[str],
        namespace: str | None = None,
        **kwargs
    ) -> str | list[str]:
        """Registers a callback to react to state changes.

        This function allows the user to register a callback for a wide variety of state changes.

        Args:
            callback: Function to be invoked when the requested state change occurs. It must conform
                to the standard State Callback format documented `here <APPGUIDE.html#state-callbacks>`__
            entity_id (str|list, optional): name of an entity or device type. If just a device type is provided,
                e.g., `light`, or `binary_sensor`. ``listen_state()`` will subscribe to state changes of all
                devices of that type. If a fully qualified entity_id is provided, ``listen_state()`` will
                listen for state changes for just that entity. If a list of entities, it will subscribe for those
                entities, and return their handles
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description. In most cases,
                it is safe to ignore this parameter. The value ``global`` for namespace has special
                significance and means that the callback will listen to state updates from any plugin.
            new (str, Callable, optional): If ``new`` is supplied as a parameter, callbacks will only be made if the
                state of the selected attribute (usually state) in the new state match the value
                of ``new``. The parameter type is defined by the namespace or plugin that is responsible
                for the entity. If it looks like a float, list, or dictionary, it may actually be a string.
                If ``new`` is a callable (lambda, function, etc), then it will be invoked with the new state,
                and if it returns ``True``, it will be considered to match.
            old (str, Callable, optional): If ``old`` is supplied as a parameter, callbacks will only be made if the
                state of the selected attribute (usually state) in the old state match the value
                of ``old``. The same caveats on types for the ``new`` parameter apply to this parameter.
                If ``old`` is a callable (lambda, function, etc), then it will be invoked with the old state,
                and if it returns a ``True``, it will be considered to match.
            duration (int, optional): If ``duration`` is supplied as a parameter, the callback will not
                fire unless the state listened for is maintained for that number of seconds. This
                requires that a specific attribute is specified (or the default of ``state`` is used),
                and should be used in conjunction with the ``old`` or ``new`` parameters, or both. When
                the callback is called, it is supplied with the values of ``entity``, ``attr``, ``old``,
                and ``new`` that were current at the time the actual event occurred, since the assumption
                is that none of them have changed in the intervening period.

                If you use ``duration`` when listening for an entire device type rather than a specific
                entity, or for all state changes, you may get unpredictable results, so it is recommended
                that this parameter is only used in conjunction with the state of specific entities.
            attribute (str, optional): Name of an attribute within the entity state object. If this
                parameter is specified in addition to a fully qualified ``entity_id``. ``listen_state()``
                will subscribe to changes for just that attribute within that specific entity.
                The ``new`` and ``old`` parameters in the callback function will be provided with
                a single value representing the attribute.

                The value ``all`` for attribute has special significance and will listen for any
                state change within the specified entity, and supply the callback functions with
                the entire state dictionary for the specified entity rather than an individual
                attribute value.
            timeout (int, optional): If ``timeout`` is supplied as a parameter, the callback will be created as normal,
                 but after ``timeout`` seconds, the callback will be removed. If activity for the listened state has
                 occurred that would trigger a duration timer, the duration timer will still be fired even though the
                 callback has been deleted.
            immediate (bool, optional): It enables the countdown for a delay parameter to start
                at the time, if given. If the ``duration`` parameter is not given, the callback runs immediately.
                What this means is that after the callback is registered, rather than requiring one or more
                state changes before it runs, it immediately checks the entity's states based on given
                parameters. If the conditions are right, the callback runs immediately at the time of
                registering. This can be useful if, for instance, you want the callback to be triggered
                immediately if a light is already `on`, or after a ``duration`` if given.

                If ``immediate`` is in use, and ``new`` and ``duration`` are both set, AppDaemon will check
                if the entity is already set to the new state and if so it will start the clock
                immediately. If ``new`` and ``duration`` are not set, ``immediate`` will trigger the callback
                immediately and report in its callback the new parameter as the present state of the
                entity. If ``attribute`` is specified, the state of the attribute will be used instead of
                state. In these cases, ``old`` will be ignored and when the callback is triggered, its
                state will be set to ``None``.
            oneshot (bool, optional): If ``True``, the callback will be automatically cancelled
                after the first state change that results in a callback.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Sets which thread from the worker pool the callback will be
                run by (0 - number of threads -1).
            **kwargs (optional): Zero or more keyword arguments that will be supplied to the callback
                when it is called.

        Notes:
            The ``old`` and ``new`` args can be used singly or together.

        Returns:
            A unique identifier that can be used to cancel the callback if required. Since variables
            created within object methods are local to the function they are created in, and in all
            likelihood, the cancellation will be invoked later in a different function, it is
            recommended that handles are stored in the object namespace, e.g., `self.handle`.

        Examples:
            Listen for any state change and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback)

            Listen for any state change involving a light and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light")

            Listen for a state change involving `light.office1` and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, entity_id="light.office_1")

            Listen for a state change involving `light.office1` and return the entire state as a dict.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "all")

            Listen for a change involving the brightness attribute of `light.office1` and return the
            brightness attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "brightness")

            Listen for a state change involving `light.office1` turning on and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on")

            Listen for a state change involving `light.office1` turning on when the previous state was not unknown or unavailable, and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on", old=lambda x: x not in ["unknown", "unavailable"])

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
        namespace = namespace or self.namespace

        match entity_id:
            case str():
                self._check_entity(namespace, entity_id)
                return await self.get_entity_api(namespace, entity_id).listen_state(callback, **kwargs)
            case Iterable():
                for e in entity_id:
                    self._check_entity(namespace, e)
                return [
                    await self.get_entity_api(namespace, e).listen_state(callback, **kwargs)
                    for e in entity_id
                ]

    @utils.sync_decorator
    async def cancel_listen_state(self, handle: str, silent: bool = False) -> bool:
        """Cancels a ``listen_state()`` callback.

        This will mean that the App will no longer be notified for the specific
        state change that has been cancelled. Other state changes will continue
        to be monitored.

        Args:
            handle: The handle returned when the ``listen_state()`` call was made.
            silent (bool, optional): If ``True``, no warning will be issued if the handle is not found.

        Returns:
            Boolean.

        Examples:
            >>> self.cancel_listen_state(self.office_light_handle)

            Don't display a warning if the handle is not found.

            >>> self.cancel_listen_state(self.dummy_handle, silent=True)

        """
        self.logger.debug("Canceling listen_state for %s", self.name)
        return bool(await self.AD.state.cancel_state_callback(handle, self.name, silent))

    @utils.sync_decorator
    async def info_listen_state(self, handle: str) -> dict:
        """Gets information on state a callback from its handle.

        Args:
            handle: The handle returned when the ``listen_state()`` call was made.

        Returns:
            The values supplied for ``entity``, ``attribute``, and ``kwargs`` when
            the callback was initially created.

        Examples:
            >>> entity, attribute, kwargs = self.info_listen_state(self.handle)

        """
        self.logger.debug("Calling info_listen_state for %s", self.name)
        return await self.AD.state.info_state_callback(handle, self.name)

    def get_state(
        self,
        entity_id: str,
        attribute: str | None = None,
        default: Any | None = None,
        namespace: str | None = None,
        copy: bool = True
    ) -> Any:
        """Gets the state of any component within Home Assistant.

        State updates are continuously tracked, so this call runs locally and does not require
        AppDaemon to call back to Home Assistant. In other words, states are updated using a
        push-based approach instead of a pull-based one.

        Args:
            entity_id (str): This is the name of an entity or device type. If just
                a device type is provided, e.g., `light` or `binary_sensor`, `get_state()`
                will return a dictionary of all devices of that type, indexed by the ``entity_id``,
                containing all the state for each entity. If a fully qualified ``entity_id``
                is provided, ``get_state()`` will return the state attribute for that entity,
                e.g., ``on`` or ``off`` for a light.
            attribute (str, optional): Name of an attribute within the entity state object.
                If this parameter is specified in addition to a fully qualified ``entity_id``,
                a single value representing the attribute will be returned. The value ``all``
                for attribute has special significance and will return the entire state
                dictionary for the specified entity rather than an individual attribute value.
            default (any, optional): The value to return when the requested attribute or the
                whole entity doesn't exist (Default: ``None``).
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter.
            copy (bool, optional): By default, a copy of the stored state object is returned.
                When you set ``copy`` to ``False``, you get the same object as is stored
                internally by AppDaemon. Avoiding the copying brings a small performance gain,
                but also gives you write-access to the internal AppDaemon data structures,
                which is dangerous. Only disable copying when you can guarantee not to modify
                the returned state object, e.g., you do read-only operations.

        Returns:
            The entire state of Home Assistant at that given time, if  if ``get_state()``
            is called with no parameters. This will consist of a dictionary with a key
            for each entity. Under that key will be the standard entity state information.

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
        namespace = namespace or self.namespace
        self._check_entity(namespace, entity_id)
        entity_api = self.get_entity_api(namespace, entity_id)
        return entity_api.get_state(attribute, default, copy)

    @overload
    async def set_state(
        self,
        entity_id: str,
        state: Any | None,
        namespace: str | None,
        attributes: dict,
        replace: bool,
        **kwargs
    ) -> dict: ...

    @utils.sync_decorator
    async def set_state(
        self,
        entity_id: str,
        state: Any | None = None,
        namespace: str | None = None,
        check_existence: bool = True,
        **kwargs
    ) -> dict:
        """Updates the state of the specified entity.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            state: New state value to be set.
            attributes (optional): Entity's attributes to be updated.
            namespace(str, optional): If a `namespace` is provided, AppDaemon will change
                the state of the given entity in the given namespace. On the other hand,
                if no namespace is given, AppDaemon will use the last specified namespace
                or the default namespace. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.
            replace(bool, optional): If a `replace` flag is given and set to ``True`` and ``attributes``
                is provided, AD will attempt to replace its internal entity register with the newly
                supplied attributes completely. This can be used to replace attributes in an entity
                which are no longer needed. Do take note this is only possible for internal entity state.
                For plugin based entities, this is not recommended, as the plugin will mostly replace
                the new values, when next it updates.
            check_existence(bool, optional): Set to False to suppress a warning about the entity not
                existing when using set_state to create an entity. Defaults to True.
            **kwargs (optional): Zero or more keyword arguments. Extra keyword arguments will be assigned as attributes.

        Returns:
            A dictionary that represents the new state of the updated entity.

        Examples:
            Update the state of an entity.

            >>> self.set_state("light.office_1", state="off")

            Update the state and attribute of an entity.

            >>> self.set_state(entity_id="light.office_1", state = "on", attributes = {"color_name": "red"})

            Update the state of an entity within the specified namespace.

            >>> self.set_state("light.office_1", state="off", namespace ="hass")

        """

        namespace = namespace or self.namespace
        entity_api = self.get_entity_api(namespace, entity_id, check_existence=check_existence)
        return await entity_api.set_state(state=state, **kwargs)

    #
    # Services
    #

    @staticmethod
    def _check_service(service: str) -> None:
        if service.find("/") == -1:
            raise ValueError(f"Invalid Service Name: {service}")

    def register_service(
        self,
        service: str,
        cb: Callable,
        namespace: str | None = None,
        **kwargs
    ) -> None:
        """Registers a service that can be called from other apps, the REST API and the Event Stream

        Using this function, an App can register a function to be available in the service registry.
        This will automatically make it available to other apps using the `call_service()` API call, as well as publish
        it as a service in the REST API and make it available to the `call_service` command in the event stream.
        It should be noted that registering services within a plugin's namespace is a bad idea. It could work, but not always reliable
        It is recommended to make use of this api, within a user definded namespace, or one not tied to a plugin.

        Args:
            service: Name of the service, in the format `domain/service`. If the domain does not exist it will be created
            cb: A reference to the function to be called when the service is requested. This function may be a regular
                function, or it may be async. Note that if it is an async function, it will run on AppDaemon's main loop
                meaning that any issues with the service could result in a delay of AppDaemon's core functions.
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments. Extra keyword arguments will be stored alongside the service definition.

        Returns:
            None

        Examples:
            >>> self.register_service("myservices/service1", self.mycallback)

            >>> async def mycallback(self, namespace, domain, service, kwargs):
            >>>     self.log("Service called")

        """
        self._check_service(service)
        self.logger.debug("register_service: %s, %s", service, kwargs)

        namespace = namespace or self.namespace
        self.AD.services.register_service(
            namespace,
            *service.split("/"),
            cb,
            __async="auto",
            __name=self.name,
            **kwargs
        )

    def deregister_service(self, service: str, namespace: str | None = None) -> bool:
        """Deregisters a service that had been previously registered

        Using this function, an App can deregister a service call, it has initially registered in the service registry.
        This will automatically make it unavailable to other apps using the `call_service()` API call, as well as published
        as a service in the REST API and make it unavailable to the `call_service` command in the event stream.
        This function can only be used, within the app that registered it in the first place

        Args:
            service: Name of the service, in the format `domain/service`.
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter.

        Returns:
            Bool

        Examples:
            >>> self.deregister_service("myservices/service1")

        """
        self.logger.debug("deregister_service: %s, %s", service, namespace)
        namespace = namespace or self.namespace
        self._check_service(service)
        return self.AD.services.deregister_service(namespace, *service.split("/"), __name=self.name)

    def list_services(self, namespace: str = 'global') -> list[dict[str, str]]:
        """List all services available within AD

        Using this function, an App can request all available services within AD

        Args:
            namespace(str, optional): If a `namespace` is provided, AppDaemon will request
                the services within the given namespace. On the other hand, if no namespace is given,
                AppDaemon will use the last specified namespace or the default namespace.
                To get all services across AD, pass `global`. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.

        Returns:
            List of dictionary with keys ``namespace``, ``domain``, and ``service``.

        Examples:
            >>> self.list_services(namespace="global")

        """

        self.logger.debug("list_services: %s", namespace)
        return self.AD.services.list_services(namespace)  # retrieve services

    @overload
    async def call_service(
        self,
        service: str,
        namespace: str | None = None,
        timeout: int | float | None = None,
        return_result: bool = True,
        callback: Callable | None = None,
        hass_result: bool = True,
        hass_timeout: float = True,
        suppress_log_messages: bool = False,
        **data
    ) -> Any: ...

    @utils.sync_decorator
    async def call_service(
        self,
        service: str,
        namespace: str | None = None,
        timeout: int | float | None = None, # Used by utils.sync_decorator
        **data: Optional[Any]
    ) -> Any:
        """Calls a Service within AppDaemon.

        This function can call any service and provide any required parameters.
        By default, there are standard services that can be called within AD. Other
        services that can be called, are dependent on the plugin used, or those registered
        by individual apps using the `register_service` api.
        In a future release, all available services can be found using AD's Admin UI.
        For `listed services`, the part before the first period is the ``domain``,
        and the part after is the `service name`. For instance, `light/turn_on`
        has a domain of `light` and a service name of `turn_on`.

        The default behaviour of the call service api is not to wait for any result, typically
        known as "fire and forget". If it is required to get the results of the call, keywords
        "return_result" or "callback" can be added.

        Args:
            service (str): The service name.
            namespace(str, optional): If a `namespace` is provided, AppDaemon will change
                the state of the given entity in the given namespace. On the other hand,
                if no namespace is given, AppDaemon will use the last specified namespace
                or the default namespace. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.
            return_result(str, option): If `return_result` is provided and set to `True` AD will attempt
                to wait for the result, and return it after execution. In the case of Home Assistant calls that do not
                return values this may seem pointless, but it does force the call to be synchronous with respect to Home Assistant
                whcih can in turn highlight slow performing services if they timeout or trigger thread warnings.
            callback: The non-async callback to be executed when complete.
            hass_result (False, Home Assistant Specific): Mark the service call to Home Assistant as returnng a
                value. If set to ``True``, the call to Home Assistant will specifically request a return result.
                If this flag is set for a service that does not return a result, Home Assistant will respond with an error,
                which AppDaemon will log. If this flag is NOT set for a service that does returns a result,
                Home Assistant will respond with an error, which AppDaemon will log. Note: if you specify ``hass_result``
                you must also set ``return_result`` or the result from HomeAssistant will not be
                propagated to your app. See `Some Notes on Service Calls <APPGUIDE.html#some-notes-on-service-calls>`__
            hass_timeout (Home Assistant Specific): time in seconds to wait for Home Assistant's
                response for this specific service call. If not specified defaults to the value of
                the ``q_timeout`` parameter in the HASS plugin configuration, which itself defaults
                to 30 seconds. See `Some Notes on Service Calls <APPGUIDE.html#some-notes-on-service-calls>`__
            suppress_log_messages (Home Assistant Specific, False): if set to ``True`` Appdaemon will suppress
                logging of warnings for service calls to Home Assistant, specifically timeouts and
                non OK statuses. Use this flag and set it to ``True`` to supress these log messages
                if you are performing your own error checking as described
                `here <APPGUIDE.html#some-notes-on-service-calls>`__
            **data: Each service has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `entity_id = light.office_1`. These parameters will be different for
                every service and can be discovered using the developer tools. Most all
                service calls require an ``entity_id``.

        Returns:
            Result of the `call_service` function if any, see `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            HASS

            >>> self.call_service("light/turn_on", entity_id = "light.office_lamp", color_name = "red")
            >>> self.call_service("notify/notify", title = "Hello", message = "Hello World")
            >>> self.call_service(
                    "calendar/get_events",
                    entity_id="calendar.home",
                    start_date_time="2024-08-25 00:00:00",
                    end_date_time="2024-08-27 00:00:00",
                    return_result=True,
                    hass_result=True,
                    hass_timeout=10
                )

            MQTT

            >>> call_service("mqtt/subscribe", topic="homeassistant/living_room/light", qos=2)
            >>> call_service("mqtt/publish", topic="homeassistant/living_room/light", payload="on")

            Utility

            >>> call_service("app/restart", app="notify_app", namespace="appdaemon")
            >>> call_service("app/stop", app="lights_app", namespace="appdaemon")
            >>> call_service("app/reload", namespace="appdaemon")

            For Utility, it is important that the `namespace` arg is set to ``appdaemon``
            as no app can work within that `namespace`. If namespace is not specified,
            calling this function will raise an error.
        """
        self.logger.debug("call_service: %s, %s", service, data)
        self._check_service(service)
        namespace = namespace or self.namespace

        # Check the entity_id if it exists
        if eid := data.get('entity_id'):
            match eid:
                case str():
                    self._check_entity(namespace, eid)
                case Iterable():
                    for e in eid:
                        self._check_entity(namespace, e)

        return await self.AD.services.call_service(namespace, *service.split("/", 2), name=self.name, data=data)

    # Sequences

    @utils.sync_decorator
    async def run_sequence(self, sequence: str | list[str], namespace: str | None = None) -> Any:
        """Run an AppDaemon Sequence. Sequences are defined in a valid apps.yaml file or inline, and are sequences of
        service calls.

        Args:
            sequence: The sequence name, referring to the correct entry in apps.yaml, or a list containing
                actual commands to run
            namespace(str, optional): If a `namespace` is provided, AppDaemon will change
                the state of the given entity in the given namespace. On the other hand,
                if no namespace is given, AppDaemon will use the last specified namespace
                or the default namespace. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments.

        Returns:
            A handle that can be used with `cancel_sequence()` to terminate the script.

        Examples:
            Run a yaml-defined sequence called "sequence.front_room_scene".

            >>> handle = self.run_sequence("sequence.front_room_scene")

            Run an inline sequence.

            >>> handle = self.run_sequence([{"light/turn_on": {"entity_id": "light.office_1"}}, {"sleep": 5}, {"light.turn_off":
            {"entity_id": "light.office_1"}}])

        """
        namespace = namespace or self.namespace
        self.logger.debug("Calling run_sequence() for %s from %s", sequence, self.name)
        return await self.AD.sequences.run_sequence(self.name, namespace, sequence)

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
    async def listen_event(
        self,
        callback: Callable,
        event: str | list[str],
        namespace: str | None,
        timeout: int,
        oneshot: bool,
        pin: bool,
        pin_thread: int,
        **kwargs
    ) -> str | list[str]: ...

    @utils.sync_decorator
    async def listen_event(
        self,
        callback: Callable,
        event: str | list[str] = None,
        namespace: str | None = None,
        **kwargs
    ) -> str | list[str]:
        """Registers a callback for a specific event, or any event.

        Args:
            callback: Function to be invoked when the event is fired.
                It must conform to the standard Event Callback format documented `here <APPGUIDE.html#about-event-callbacks>`__
            event (str|list, optional): Name of the event to subscribe to. Can be a standard
                Home Assistant event such as `service_registered`, an arbitrary
                custom event such as `"MODE_CHANGE"` or a list of events `["pressed", "released"]`. If no event is specified,
                `listen_event()` will subscribe to all events.
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter. The value ``global``
                for namespace has special significance, and means that the callback will
                listen to state updates from any plugin.
            oneshot (bool, optional): If ``True``, the callback will be automatically cancelled
                after the first state change that results in a callback.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            timeout (int, optional): If ``timeout`` is supplied as a parameter, the callback will be created as normal,
                 but after ``timeout`` seconds, the callback will be removed.
            **kwargs (optional): One or more keyword value pairs representing App specific
                parameters to supply to the callback. If the keywords match values within the
                event data, they will act as filters, meaning that if they don't match the
                values, the callback will not fire. If the values provided are callable (lambda,
                function, etc), then they'll be invoked with the events content, and if they return
                ``True``, they'll be considered to match.

                As an example of this, a `Minimote` controller when activated will generate
                an event called zwave.scene_activated, along with 2 pieces of data that are
                specific to the event - entity_id and scene. If you include keyword values
                for either of those, the values supplied to the `listen_event()` call must
                match the values in the event or it will not fire. If the keywords do not
                match any of the data in the event they are simply ignored.

                Filtering will work with any event type, but it will be necessary to figure
                out the data associated with the event to understand what values can be
                filtered on. This can be achieved by examining Home Assistant's `logfiles`
                when the event fires.

        Returns:
            A handle that can be used to cancel the callback.

        Examples:
            Listen all `"MODE_CHANGE"` events.

            >>> self.listen_event(self.mode_event, "MODE_CHANGE")

            Listen for a `minimote` event activating scene 3.

            >>> self.listen_event(self.generic_event, "zwave.scene_activated", scene_id = 3)

            Listen for a `minimote` event activating scene 3 from a specific `minimote` .

            >>> self.listen_event(self.generic_event, "zwave.scene_activated", entity_id = "minimote_31", scene_id = 3)

            Listen for a `minimote` event activating scene 3 from certain `minimote` (starting with 3), matched with code.

            >>> self.listen_event(self.generic_event, "zwave.scene_activated", entity_id = lambda x: x.starts_with("minimote_3"), scene_id = 3)

            Listen for some custom events of a button being pressed.

            >>> self.listen_event(self.button_event, ["pressed", "released"])

        """
        self.logger.debug(f"Calling listen_event for {self.name} for {event}: {kwargs}")
        namespace = namespace or self.namespace

        match event:
            case str():
                return await self.AD.events.add_event_callback(self.name, namespace, callback, event, **kwargs)
            case Iterable():
                return [
                    await self.AD.events.add_event_callback(self.name, namespace, callback, e, **kwargs)
                    for e in event
                ]

    @utils.sync_decorator
    async def cancel_listen_event(self, handle: str) -> bool:
        """Cancels a callback for a specific event.

        Args:
            handle: A handle returned from a previous call to ``listen_event()``.

        Returns:
            Boolean.

        Examples:
            >>> self.cancel_listen_event(handle)

        """
        self.logger.debug("Canceling listen_event for %s", self.name)
        return await self.AD.events.cancel_event_callback(self.name, handle)

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
            event: Name of the event. Can be a standard Home Assistant event such as
                `service_registered` or an arbitrary custom event such as "MODE_CHANGE".
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments that will be supplied as
                part of the event.

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

    def parse_utc_string(self, utc_string: str) -> dt.datetime:
        """Converts a UTC to its string representation.

        Args:
            utc_string (str): A string that contains a date and time to convert.

        Returns:
            An POSIX timestamp that is equivalent to the date and time contained in `utc_string`.

        """
        return dt.datetime(*map(int, re.split(r"[^\d]", utc_string)[:-1])).timestamp() + self.get_tz_offset() * 60

    def get_tz_offset(self) -> float:
        """Returns the timezone difference between UTC and Local Time in minutes."""
        return self.AD.tz.utcoffset(self.datetime()).total_seconds() / 60

    @staticmethod
    def convert_utc(utc: str) -> dt.datetime:
        """Gets a `datetime` object for the specified UTC.

        Home Assistant provides timestamps of several different sorts that may be
        used to gain additional insight into state changes. These timestamps are
        in UTC and are coded as `ISO 8601` combined date and time strings. This function
        will accept one of these strings and convert it to a localised Python
        `datetime` object representing the timestamp.

        Args:
            utc: An `ISO 8601` encoded date and time string in the following
                format: `2016-07-13T14:24:02.040658-04:00`

        Returns:
             A localised Python `datetime` object representing the timestamp.

        """
        return iso8601.parse_date(utc)

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

    @overload
    async def parse_time(
        self,
        time_str: str,
        name: str | None = None,
        aware: bool = False,
        today: bool = False,
        days_offset: int = 0
    ) -> dt.time: ...

    @utils.sync_decorator
    async def parse_time(self, time_str: str, name: str | None = None, *args, **kwargs) -> dt.time:
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
        name = name or self.name
        return await self.AD.sched.parse_time(time_str, name, *args, **kwargs)

    @overload
    async def parse_datetime(
        self,
        time_str: str,
        name: str | None = None,
        aware: bool = False,
        today: bool = False,
        days_offset: int = 0
    ) -> dt.time: ...

    @utils.sync_decorator
    async def parse_datetime(self, time_str: str, name: str | None = None, *args, **kwargs) -> dt.datetime:
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
        name = name or self.name
        return await self.AD.sched.parse_datetime(time_str, name, *args, **kwargs)

    @utils.sync_decorator
    async def get_now(self, aware: bool = True) -> dt.datetime:
        """Returns the current Local Date and Time.

        Examples:
            >>> self.get_now()
            2019-08-16 21:17:41.098813+00:00

        """
        now = await self.AD.sched.get_now()
        now = now.astimezone(self.AD.tz)
        if not aware:
            now = now.replace(tzinfo=None)
        return now

    @utils.sync_decorator
    async def get_now_ts(self, aware: bool = False) -> float:
        """Returns the current Local Timestamp.

        Examples:
             >>> self.get_now_ts()
             1565990318.728324

        """
        return (await self.get_now(aware)).timestamp()

    @overload
    async def now_is_between(self, start_time: str, end_time: str, name: str | None = None, now: str | None = None) -> bool: ...

    @utils.sync_decorator
    async def now_is_between(self, *args, **kwargs) -> bool:
        """Determines if the current `time` is within the specified start and end times.

        This function takes two string representations of a ``time``, or ``sunrise`` or ``sunset``
        offset and returns ``true`` if the current time is between those 2 times. Its
        implementation can correctly handle transitions across midnight.

        Args:
            start_time (str): A string representation of the start time.
            end_time (str): A string representation of the end time.
            name (str, optional): Name of the calling app or module. It is used only for logging purposes.
            now (str, optional): If specified, `now` is used as the time for comparison instead of the current time. Useful for testing.

        Returns:
            bool: ``True`` if the current time is within the specified start and end times,
            ``False`` otherwise.

        Notes:
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
        return await self.AD.sched.now_is_between(*args, **kwargs)

    @utils.sync_decorator
    async def sunrise(self, aware: bool = False, today: bool = False, days_offset: int = 0) -> dt.datetime:
        """Returns a `datetime` object that represents the next time Sunrise will occur.

        Args:
            aware (bool, optional): Specifies if the created datetime object will be
                `aware` of timezone or `not`.
            today (bool, optional): Instead of the default behavior which is to return the next sunrise that will occur, setting this flag to true will return
                 today's sunrise even if it is in the past
            days_offset (int, optional): Specify the number of days (positive or negative) for the sunset. This can only be used in combination with the today
                 flag

        Examples:
            >>> self.sunrise()
            2023-02-02 07:11:50.150554
            >>> self.sunrise(today=True)
            2023-02-01 07:12:20.272403

        """
        return await self.AD.sched.sunrise(aware, today, days_offset)

    @utils.sync_decorator
    async def sunset(self, aware: bool = False, today: bool = False, days_offset: int = 0) -> dt.datetime:
        """Returns a `datetime` object that represents the next time Sunset will occur.

        Args:
            aware (bool, optional): Specifies if the created datetime object will be
                `aware` of timezone or `not`.
            today (bool, optional): Instead of the default behavior which is to return
                the next sunset that will occur, setting this flag to true will return
                today's sunset even if it is in the past
            days_offset (int, optional): Specify the number of days (positive or negative)
                for the sunset. This can only be used in combination with the today flag

        Examples:
            >>> self.sunset()
            2023-02-01 18:09:00.730704
            >>> self.sunset(today=True, days_offset=1)
            2023-02-02 18:09:46.252314

        """
        return await self.AD.sched.sunset(aware, today, days_offset)

    @utils.sync_decorator
    async def datetime(self, aware: bool = False) -> dt.datetime:
        """Returns a `datetime` object representing the current Local Date and Time.

        Use this in preference to the standard Python ways to discover the current
        datetime, especially when using the "Time Travel" feature for testing.

        Args:
            aware (bool, optional): Specifies if the created datetime object will be
                `aware` of timezone or `not`.

        Examples:
            >>> self.datetime()
            2019-08-15 20:15:55.549379

        """
        return await self.get_now(aware)

    @utils.sync_decorator
    async def time(self) -> dt.time:
        """Returns a localised `time` object representing the current Local Time.

        Use this in preference to the standard Python ways to discover the current time,
        especially when using the "Time Travel" feature for testing.

        Examples:
            >>> self.time()
            20:15:31.295751

        """
        return (await self.datetime(aware=True)).time()

    @utils.sync_decorator
    async def date(self) -> dt.date:
        """Returns a localised `date` object representing the current Local Date.

        Use this in preference to the standard Python ways to discover the current date,
        especially when using the "Time Travel" feature for testing.

        Examples:
            >>> self.date()
            2019-08-15

        """
        return (await self.datetime(aware=True)).date()

    def get_timezone(self) -> str:
        """Returns the current time zone."""
        return self.AD.time_zone

    #
    # Scheduler
    #

    @utils.sync_decorator
    async def timer_running(self, handle: str) -> bool:
        """Checks if a previously created timer is still running.

        Args:
            handle: A handle value returned from the original call to create the timer.

        Returns:
            Boolean.

        Examples:
            >>> self.timer_running(handle)

        """
        name = self.name
        self.logger.debug("Checking timer with handle %s for %s", handle, self.name)
        return self.AD.sched.timer_running(name, handle)

    @utils.sync_decorator
    async def cancel_timer(self, handle: str, silent: bool = False) -> bool:
        """Cancels a previously created timer.

        Args:
            handle: A handle value returned from the original call to create the timer.
            silent: (boolean, optional) don't issue a warning if the handle is invalid.
                This can sometimes occur due to race conditions and is usually harmless.
                Defaults to False

        Returns:
            Boolean.

        Examples:
            >>> self.cancel_timer(handle)
            >>> self.cancel_timer(handle, True)

        """
        self.logger.debug("Canceling timer with handle %s for %s", handle, self.name)
        return await self.AD.sched.cancel_timer(self.name, handle, silent)

    @utils.sync_decorator
    async def reset_timer(self, handle: str) -> bool:
        """Resets a previously created timer.

        Args:
            handle: A valid handle value returned from the original call to create the timer.
                The timer must be actively running, and not a Sun related one like sunrise/sunset for it to be resetted.

        Returns:
            Boolean, true if the reset succeeded.

        Examples:
            >>> self.reset_timer(handle)

        """
        self.logger.debug("Resetting timer with handle %s for %s", handle, self.name)
        return await self.AD.sched.reset_timer(self.name, handle)

    @utils.sync_decorator
    async def info_timer(self, handle: str) -> tuple[dt.datetime, int, dict] | None:
        """Gets information on a scheduler event from its handle.

        Args:
            handle: The handle returned when the scheduler call was made.

        Returns:
            `time` - datetime object representing the next time the callback will be fired

            `interval` - repeat interval if applicable, `0` otherwise.

            `kwargs` - the values supplied when the callback was initially created.

            or ``None`` - if handle is invalid or timer no longer exists.

        Examples:
            >>> time, interval, kwargs = self.info_timer(handle)

        """
        return await self.AD.sched.info_timer(handle, self.name)

    @utils.sync_decorator
    async def run_in(
        self,
        callback: Callable,
        delay: float,
        *args,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs
    ) -> str:
        """Runs the callback in a defined number of seconds.

        This is used to add a delay, for instance, a 60 second delay before
        a light is turned off after it has been triggered by a motion detector.
        This callback should always be used instead of ``time.sleep()`` as
        discussed previously.

        Args:
            callback: Function to be invoked when the requested state change occurs.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            delay (float): Delay, in seconds before the callback is invoked.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): If True, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Run the specified callback after 10 seconds.

            >>> self.handle = self.run_in(self.run_in_c, 10)

            Run the specified callback after 10 seconds with a keyword arg (title).

            >>> self.handle = self.run_in(self.run_in_c, 5, title = "run_in5")

        """
        match delay:
            case int() | float():
                delay = timedelta(seconds=delay)

        assert isinstance(delay, timedelta), f'Invalid delay: {delay}'
        self.logger.debug(f"Registering run_in in {delay.total_seconds():.1f}s for {self.name}")
        exec_time = (await self.get_now()) + delay
        return await self.AD.sched.insert_schedule(
            name=self.name,
            aware_dt=exec_time,
            callback=functools.partial(callback, *args, **kwargs),
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
        )

    @utils.sync_decorator
    async def run_once(
        self,
        callback: Callable,
        start: dt.time | str | None = None,
        *args,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs
    ) -> str:
        """Runs the callback once, at the specified time of day.

        Args:
            callback: Function to be invoked at the specified time of day.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: Should be either a Python ``time`` object or a ``parse_time()`` formatted
                string that specifies when the callback will occur. If the time
                specified is in the past, the callback will occur the ``next day`` at
                the specified time.
            *args: Arbitrary positional arguments to be provided to the callback function
                when it is invoked.
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If True, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Run at 4pm today, or 4pm tomorrow if it is already after 4pm.

            >>> runtime = datetime.time(16, 0, 0)
            >>> handle = self.run_once(self.run_once_c, runtime)

            Run today at 10:30 using the `parse_time()` function.

            >>> handle = self.run_once(self.run_once_c, "10:30:00")

            Run at sunset.

            >>> handle = self.run_once(self.run_once_c, "sunset")

            Run an hour after sunrise.

            >>> handle = self.run_once(self.run_once_c, "sunrise + 01:00:00")

        """
        return await self.run_at(
            callback, start, *args,
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
            **kwargs
        )

    @utils.sync_decorator
    async def run_at(
        self,
        callback: Callable,
        start: dt.time | str | None = None,
        *args,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs
    ) -> str:
        """Runs the callback once, at the specified time of day.

        Args:
            callback: Function to be invoked at the specified time of day.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: Should be either a Python ``datetime`` object or a ``parse_time()`` formatted
                string that specifies when the callback will occur.
            *args: Arbitrary positional arguments to be provided to the callback function
                when it is invoked.
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

            The ``run_at()`` function will ``raise`` an exception if the specified time is in the ``past``.

        Examples:
            Run at 4pm today.

            >>> runtime = datetime.time(16, 0, 0)
            >>> today = datetime.date.today()
            >>> event = datetime.datetime.combine(today, runtime)
            >>> handle = self.run_at(self.run_at_c, event)

            Run today at 10:30 using the `parse_time()` function.

            >>> handle = self.run_at(self.run_at_c, "10:30:00")

            Run on a specific date and time.

            >>> handle = self.run_at(self.run_at_c, "2018-12-11 10:30:00")

            Run at the next sunset.

            >>> handle = self.run_at(self.run_at_c, "sunset")

            Run an hour after the next sunrise.

            >>> handle = self.run_at(self.run_at_c, "sunrise + 01:00:00")

        """
        match start:
            case str():
                info = await self.AD.sched._parse_time(start, self.name)
                start = info['datetime']
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
        start: dt.time | str | None = None,
        *args,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **cb_kwargs
    ) -> str:
        """Runs the callback at the same time every day.

        Args:
            callback: Function to be invoked every day at the specified time.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: A Python ``time`` object that specifies when the callback will occur,
                the hour and minute components of the time object are ignored. If the
                time specified is in the past, the callback will occur the ``next minute`` at
                the specified time. If time is not supplied, the callback will start a
                minute from the time that ``run_daily()`` was executed.
            *args: Arbitrary positional arguments to be provided to the callback function
                when it is invoked.
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If True, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **cb_kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Run daily at 7pm.

            >>> runtime = datetime.time(19, 0, 0)
            >>> self.run_daily(self.run_daily_c, runtime)

            Run at 10:30 every day using the `parse_time()` function.

            >>> handle = self.run_daily(self.run_daily_c, "10:30:00")

            Run every day at sunrise.

            >>> handle = self.run_daily(self.run_daily_c, "sunrise")

            Run every day an hour after sunset.

            >>> handle = self.run_daily(self.run_daily_c, "sunset + 01:00:00")

        """
        offset = 0
        sun = None
        match start:
            case str():
                info = await self.AD.sched._parse_time(start, self.name)
                start, offset, sun = info['datetime'], info['offset'], info['sun']
            case dt.time():
                start = dt.datetime.combine(await self.date(), start).astimezone(self.AD.tz)
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
                return await self.run_every(
                    callback,
                    start,
                    timedelta(days=1),
                    *args,
                    **ad_kwargs,
                    **cb_kwargs
                )
            case "sunrise":
                return await self.run_at_sunrise(
                    callback,
                    *args,
                    repeat=True,
                    offset=offset,
                    **ad_kwargs,
                    **cb_kwargs
                )
            case "sunset":
                return await self.run_at_sunset(
                    callback,
                    *args,
                    repeat=True,
                    offset=offset,
                    **ad_kwargs,
                    **cb_kwargs
                )

    @utils.sync_decorator
    async def run_hourly(
        self,
        callback: Callable,
        start: dt.time | dt.datetime | str | None = None,
        *args,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs
    ) -> str:
        """Runs the callback at the same time every hour.

        Args:
            callback: Function to be invoked every hour at the specified time.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: A Python ``time`` object that specifies when the callback will occur,
                the hour and minute components of the time object are ignored. If the
                time specified is in the past, the callback will occur the ``next minute`` at
                the specified time. If time is not supplied, the callback will start a
                minute from the time that ``run_hourly()`` was executed.
            *args: Arbitrary positional arguments to be provided to the callback function
                when it is invoked.
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If True, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Run every hour, on the hour.

            >>> runtime = datetime.time(0, 0, 0)
            >>> self.run_hourly(self.run_hourly_c, runtime)

        """
        return await self.run_every(
            callback,
            start,
            timedelta(hours=1),
            *args,
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
            **kwargs
        )

    @utils.sync_decorator
    async def run_minutely(
        self,
        callback: Callable,
        start: dt.time | dt.datetime | str | None = None,
        *args,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs
    ) -> str:
        """Runs the callback at the same time every minute.

        Args:
            callback: Function to be invoked every minute.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: A Python ``time`` object that specifies when the callback will occur,
                the hour and minute components of the time object are ignored. If the
                time specified is in the past, the callback will occur the ``next minute`` at
                the specified time. If time is not supplied, the callback will start a
                minute from the time that ``run_minutely()`` was executed.
            *args: Arbitrary positional arguments to be provided to the callback function
                when it is invoked.
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If True, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Run every minute on the minute.

            >>> time = datetime.time(0, 0, 0)
            >>> self.run_minutely(self.run_minutely_c, time)

        """
        return await self.run_every(
            callback,
            start,
            timedelta(minutes=1),
            *args,
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread,
            **kwargs
        )

    @utils.sync_decorator
    async def run_every(
        self,
        callback: Callable,
        start: dt.time | dt.datetime | str | None = None,
        interval: int | float | dt.timedelta = 0,
        *args,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs
    ) -> str:
        """Runs the callback with a configurable delay starting at a specific time.

        Args:
            callback: Function to be invoked when the time interval is reached.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: A Python ``datetime`` object that specifies when the initial callback
                will occur, or can take the `now` string alongside an added offset. If given
                in the past, it will be executed in the next interval time.
            interval (int): Frequency (expressed in seconds) in which the callback should be executed.
            *args: Arbitrary positional arguments to be provided to the callback function
                when it is invoked.
            random_start (int, optional): Start of range of the random time.
            random_end (int, optional): End of range of the random time.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Run every 17 minutes starting in 2 hours time.

            >>> self.run_every(self.run_every_c, time, 17 * 60)

            Run every 10 minutes starting now.

            >>> self.run_every(self.run_every_c, "now", 10 * 60)

            Run every 5 minutes starting now plus 5 seconds.

            >>> self.run_every(self.run_every_c, "now+5", 5 * 60)

        """
        match interval:
            case int() | float():
                interval = dt.timedelta(seconds=interval)
            case dt.timedelta():
                ...
            case _:
                raise ValueError(f'Bad value for interval: {interval}')

        assert isinstance(interval, dt.timedelta)

        aware_start = await self.AD.sched.get_next_period(interval, start)

        self.logger.debug(
            "Registering %s for run_every in %s intervals, starting %s",
            callback.__name__,
            interval,
            aware_start,
        )

        return await self.AD.sched.insert_schedule(
            name=self.name,
            aware_dt=aware_start,
            callback=functools.partial(callback, *args, **kwargs),
            repeat=True,
            interval=interval.total_seconds(),
            random_start=random_start,
            random_end=random_end,
            pin=pin,
            pin_thread=pin_thread
        )

    @utils.sync_decorator
    async def run_at_sunset(
        self,
        callback: Callable,
        *args,
        repeat: bool = False,
        offset: int | None = None,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs
    ) -> str:
        """Runs a callback every day at or around sunset.

        Args:
            callback: Function to be invoked at or around sunset. It must conform to the
                standard Scheduler Callback format documented `here <APPGUIDE.html#about-schedule-callbacks>`__.
            *args: Arbitrary positional arguments to be provided to the callback function
                when it is invoked.
            offset (int, optional): The time in seconds that the callback should be delayed after
                sunset. A negative value will result in the callback occurring before sunset.
                This parameter cannot be combined with ``random_start`` or ``random_end``.
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **kwargs: Arbitrary keyword arguments to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
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
        td = timedelta(seconds=offset)
        self.logger.debug(f"Registering run_at_sunset at {sunset+td} with {args}, {kwargs}")
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
            pin_thread=pin_thread
        )

    @utils.sync_decorator
    async def run_at_sunrise(
        self,
        callback: Callable,
        *args,
        repeat: bool = False,
        offset: int | None = None,
        random_start: int = None,
        random_end: int = None,
        pin: bool | None = None,
        pin_thread: int | None = None,
        **kwargs
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
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).
            **kwargs: Arbitrary keyword arguments to be provided to the callback
                function when it is invoked.

        Returns:
            A handle that can be used to cancel the timer.

        Notes:
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
        sunrise = await self.AD.sched.next_sunrise()
        td = timedelta(seconds=offset)
        self.logger.debug(f"Registering run_at_sunrise at {sunrise+td} with {args}, {kwargs}")
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
            pin_thread=pin_thread
        )

    #
    # Dashboard
    #

    def dash_navigate(
        self,
        target: str,
        timeout: int = -1,
        ret: str | None = None,
        sticky: int = 0,
        deviceid: str | None = None,
        dashid: str | None = None
    ) -> None:
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

    async def run_in_executor(self, func: Callable, *args, **kwargs) -> Callable:
        """Runs a Sync function from within an Async function using Executor threads.
            The function is actually awaited during execution

        Args:
            func: The function to be executed.
            *args (optional): Any additional arguments to be used by the function
            **kwargs (optional): Any additional keyword arguments to be used by the function

        Returns:
            None
        Examples:
            >>> await self.run_in_executor(self.run_request)

        """

        return await utils.run_in_executor(self, func, *args, **kwargs)

    def submit_to_executor(self, func: Callable, *args, callback: Callable | None = None, **kwargs) -> Future:
        """Submits a Sync function from within another Sync function to be executed using Executor threads.
            The function is not waited to be executed. As it submits and continues the rest of the code.
            This can be useful if wanting to execute a long running code, and don't want it to hold up the
            thread for other callbacks.

        Args:
            func: The function to be executed.
            *args (optional): Any additional arguments to be used by the function
            **kwargs (optional): Any additional keyword arguments to be used by the function.
            Part of the keyword arguments will be the ``callback``, which will be ran when the function has completed execution

        Returns:
            A Future, which can be cancelled by calling f.cancel().

        Examples:
            >>>
            >>> def state_cb(self, *args, **kwargs): # callback from an entity
            >>>     # need to run a 30 seconds task, so need to free up the thread
            >>>     # need to get results, so will pass a callback for it
            >>>     # callback can be ignored, if the result is not needed
            >>>     f = self.submit_to_executor(self.run_request, url, callback=self.result_callback)
            >>>
            >>> def run_request(self, url): # long running function
            >>>     import requests
            >>>     res = requests.get(url)
            >>>     return res.json()
            >>>
            >>> def result_callback(self, kwargs):
            >>>     result = kwargs["result"]
            >>>     self.set_state("sensor.something", state="ready", attributes=result, replace=True) # picked up by another app
            >>>     # <other processing that is needed>

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
                sched_data["kwargs"] = {'result': f.result()}
                self.create_task(self.AD.threading.dispatch_worker(self.name, sched_data))

                # callback(f.result(), kwargs)
            except Exception as e:
                self.error(e, level="ERROR")

        future = self.AD.executor.submit(func, *args, **kwargs)

        if callback is not None:
            self.logger.debug("Adding add_done_callback for future %s for %s", future, self.name)
            future.add_done_callback(callback_inner)

        self.AD.futures.add_future(self.name, future)
        return future

    @utils.sync_decorator
    async def create_task(self, coro: Coroutine, callback: Callable | None = None, **kwargs) -> Future:
        """Schedules a Coroutine to be executed.

        Args:
            coro: The coroutine object (`not coroutine function`) to be executed.
            callback: The non-async callback to be executed when complete.
            **kwargs (optional): Any additional keyword arguments to send the callback.

        Returns:
            A Future, which can be cancelled by calling f.cancel().

        Examples:
            >>> f = self.create_task(asyncio.sleep(3), callback=self.coro_callback)
            >>>
            >>> def coro_callback(self, kwargs):

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

        def callback_inner(f):
            try:
                kwargs["result"] = f.result()
                sched_data["kwargs"] = kwargs
                self.create_task(self.AD.threading.dispatch_worker(self.name, sched_data))

                # callback(f.result(), kwargs)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(coro)
        if callback is not None:
            self.logger.debug("Adding add_done_callback for future %s for %s", task, self.name)
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

        Notes:
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

    def get_entity(self, entity: str, namespace: str | None = None) -> Entity:
        namespace = namespace or self.namespace
        self._check_entity(namespace, entity)
        return Entity(self.logger, self.AD, self.name, namespace, entity)

    def get_entity_api(self, namespace: str, entity_id: str, check_existence: bool = True) -> Entity:
        """Sometimes this gets called when creating a new entity, so the check needs to be suppressed
        """
        namespace = namespace or self.namespace
        if check_existence:
            self._check_entity(namespace, entity_id)
        return Entity.entity_api(self.logger, self.AD, self.name, namespace, entity_id)

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
    async def depends_on_module(self, *modules: List[str]) -> None:
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
