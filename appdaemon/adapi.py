import asyncio
import datetime
import inspect
import iso8601
import re
from datetime import timedelta
from copy import deepcopy
from typing import Any, Optional, Callable, Union

# needed for fake coro cb that looks like scheduler
import uuid

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.entity import Entity


class ADAPI:
    """AppDaemon API class.

       This class includes all native API calls to AppDaemon

    """

    #
    # Internal parameters
    #
    def __init__(self, ad: AppDaemon, name, logging_obj, args, config, app_config, global_vars):
        # Store args

        self.AD = ad
        self.name = name
        self._logging = logging_obj
        self.config = config
        self.app_config = app_config
        self.args = deepcopy(args)
        self.app_dir = self.AD.app_dir
        self.config_dir = self.AD.config_dir
        self.dashboard_dir = None

        if self.AD.http is not None:
            self.dashboard_dir = self.AD.http.dashboard_dir

        self.global_vars = global_vars
        self._namespace = "default"
        self.logger = self._logging.get_child(name)
        self.err = self._logging.get_error().getChild(name)
        self.user_logs = {}
        if "log_level" in args:
            self.logger.setLevel(args["log_level"])
            self.err.setLevel(args["log_level"])
        if "log" in args:
            userlog = self.get_user_log(args["log"])
            if userlog is not None:
                self.logger = userlog
        self.dialogflow_v = 2

    @staticmethod
    def _sub_stack(msg):
        # If msg is a data structure of some type, don't sub
        if type(msg) is str:
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
    # Logging
    #

    def _log(self, logger, msg, *args, **kwargs):
        #
        # Internal
        #
        if "level" in kwargs:
            level = kwargs.pop("level", "INFO")
        else:
            level = "INFO"
        ascii_encode = kwargs.pop("ascii_encode", True)
        if ascii_encode is True:
            msg = str(msg).encode("utf-8", "replace").decode("ascii", "replace")

        logger.log(self._logging.log_levels[level], msg, *args, **kwargs)

    def log(self, msg, *args, **kwargs):
        """Logs a message to AppDaemon's main logfile.

        Args:
            msg (str): The message to log.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            level (str, optional): The log level of the message - takes a string representing the
                standard logger levels (Default: ``"WARNING"``).
            ascii_encode (bool, optional): Switch to disable the encoding of all log messages to
                ascii. Set this to true if you want to log UTF-8 characters (Default: ``True``).
            log (str, optional): Send the message to a specific log, either system or user_defined.
                System logs are ``main_log``, ``error_log``, ``diag_log`` or ``access_log``.
                Any other value in use here must have a corresponding user-defined entity in
                the ``logs`` section of appdaemon.yaml.
            stack_info (bool, optional): If ``True`` the stack info will included.

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
        if "log" in kwargs:
            # Its a user defined log
            logger = self.get_user_log(kwargs["log"])
            kwargs.pop("log")
        else:
            logger = self.logger

        try:
            msg = self._sub_stack(msg)
        except IndexError as i:
            rargs = deepcopy(kwargs)
            rargs["level"] = "ERROR"
            self._log(self.err, i, *args, **rargs)

        self._log(logger, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Logs a message to AppDaemon's error logfile.

        Args:
            msg (str): The message to log.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            level (str, optional): The log level of the message - takes a string representing the
                standard logger levels.
            ascii_encode (bool, optional): Switch to disable the encoding of all log messages to
                ascii. Set this to true if you want to log UTF-8 characters (Default: ``True``).
            log (str, optional): Send the message to a specific log, either system or user_defined.
                System logs are ``main_log``, ``error_log``, ``diag_log`` or ``access_log``.
                Any other value in use here must have a corresponding user-defined entity in
                the ``logs`` section of appdaemon.yaml.

        Returns:
            None.

        Examples:
            Log an error message to the error logfile of the system.

            >>> self.error("Some Warning string")

            Log an error message with critical-level to the error logfile of the system.

            >>> self.error("Some Critical string", level = "CRITICAL")

        """
        self._log(self.err, msg, *args, **kwargs)

    @utils.sync_wrapper
    async def listen_log(self, callback, level="INFO", **kwargs):
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
        namespace = kwargs.pop("namespace", "admin")

        return await self.AD.logging.add_log_callback(namespace, self.name, callback, level, **kwargs)

    @utils.sync_wrapper
    async def cancel_listen_log(self, handle):
        """Cancels the log callback for the App.

        Args:
            handle: The handle returned when the `listen_log` call was made.

        Returns:
            Boolean.

        Examples:
              >>> self.cancel_listen_log(handle)

        """
        self.logger.debug("Canceling listen_log for %s", self.name)
        return await self.AD.logging.cancel_log_callback(self.name, handle)

    def get_main_log(self):
        """Returns the underlying logger object used for the main log.

        Examples:
            Log a critical message to the `main` logfile of the system.

            >>> log = self.get_main_log()
            >>> log.critical("Log a critical error")

        """
        return self.logger

    def get_error_log(self):
        """Returns the underlying logger object used for the error log.

        Examples:
            Log an error message to the `error` logfile of the system.

            >>> error_log = self.get_error_log()
            >>> error_log.error("Log an error", stack_info=True, exc_info=True)

        """
        return self.err

    def get_user_log(self, log):
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

    def set_log_level(self, level):
        """Sets a specific log level for the App.

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
        self.logger.setLevel(self._logging.log_levels[level])
        self.err.setLevel(self._logging.log_levels[level])
        for log in self.user_logs:
            self.user_logs[log].setLevel(self._logging.log_levels[level])

    def set_error_level(self, level):
        """Sets the log level to send to the `error` logfile of the system.

        Args:
            level (str): Error level.

        Returns:
            None.

        Notes:
            Supported log levels: ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``,
            ``DEBUG``, ``NOTSET``.

        """
        self.err.setLevel(self._logging.log_levels[level])

    #
    # Threading
    #

    @utils.sync_wrapper
    async def set_app_pin(self, pin):
        """Sets an App to be pinned or unpinned.

        Args:
            pin (bool): Sets whether the App becomes pinned or not.

        Returns:
            None.

        Examples:
            The following line should be put inside the `initialize()` function.

            >>> self.set_app_pin(True)

        """
        await self.AD.threading.set_app_pin(self.name, pin)

    @utils.sync_wrapper
    async def get_app_pin(self):
        """Finds out if the current App is currently pinned or not.

        Returns:
            bool: ``True`` if the App is pinned, ``False`` otherwise.

        Examples:
            >>> if self.get_app_pin(True):
            >>>     self.log("App pinned!")

        """
        return await self.AD.threading.get_app_pin(self.name)

    @utils.sync_wrapper
    async def set_pin_thread(self, thread):
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
        return await self.AD.threading.set_pin_thread(self.name, thread)

    @utils.sync_wrapper
    async def get_pin_thread(self):
        """Finds out which thread the App is pinned to.

        Returns:
            int: The thread number or -1 if the App is not pinned.

        Examples:
            >>> thread = self.get_pin_thread():
            >>> self.log(f"I'm pinned to thread: {thread}")

        """
        return await self.AD.threading.get_pin_thread(self.name)

    #
    # Namespace
    #

    def set_namespace(self, namespace):
        """Sets a new namespace for the App to use from that point forward.

        Args:
            namespace (str): Name of the new namespace

        Returns:
            None.

        Examples:
            >>> self.set_namespace("hass1")

        """
        self._namespace = namespace

    def get_namespace(self):
        """Returns the App's namespace."""
        return self._namespace

    @utils.sync_wrapper
    async def namespace_exists(self, namespace):
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
        return await self.AD.state.namespace_exists(namespace)

    @utils.sync_wrapper
    async def add_namespace(self, namespace, **kwargs):
        """Used to add a user-defined namespaces from apps, which has a database file associated with it.

        This way, when AD restarts these entities will be reloaded into AD with its
        previous states within the namespace. This can be used as a basic form of
        non-volatile storage of entity data. Depending on the configuration of the
        namespace, this function can be setup to constantly be running automatically
        or only when AD shutdown. This function also allows for users to manually
        execute the command as when needed.

        Args:
            namespace (str): The namespace to be newly created, which must not be same as the operating namespace
            writeback (optional): The writeback to be used.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            writeback (str, optional): The writeback to be used. WIll be safe by default
            persist (bool, optional): If to make the namespace persistent. So if AD reboots
                it will startup will all the created entities being intact. It is persistent by default



        Returns:
            The file path to the newly created namespace. WIll be None if not persistent

        Examples:
            Add a new namespace called `storage`.

            >>> self.add_namespace("storage")

        """
        if namespace == self.get_namespace():  # if it belongs to this app's namespace
            raise ValueError("Cannot add namespace with the same name as operating namespace")

        writeback = kwargs.get("writeback", "safe")
        persist = kwargs.get("persist", True)

        return await self.AD.state.add_namespace(namespace, writeback, persist, self.name)

    @utils.sync_wrapper
    async def remove_namespace(self, namespace):
        """Used to remove a previously user-defined namespaces from apps, which has a database file associated with it.

        Args:
            namespace (str): The namespace to be removed, which must not be same as the operating namespace


        Returns:
            The data within that namespace

        Examples:
            Removes the namespace called `storage`.

            >>> self.remove_namespace("storage")

        """
        if namespace == self.get_namespace():  # if it belongs to this app's namespace
            raise ValueError("Cannot remove namespace with the same name as operating namespace")

        return await self.AD.state.remove_namespace(namespace)

    @utils.sync_wrapper
    async def list_namespaces(self):
        """Returns a list of available namespaces.

        Examples:
            >>> self.list_namespaces()

        """
        return await self.AD.state.list_namespaces()

    @utils.sync_wrapper
    async def save_namespace(self, **kwargs):
        """Saves entities created in user-defined namespaces into a file.

        This way, when AD restarts these entities will be reloaded into AD with its
        previous states within the namespace. This can be used as a basic form of
        non-volatile storage of entity data. Depending on the configuration of the
        namespace, this function can be setup to constantly be running automatically
        or only when AD shutdown. This function also allows for users to manually
        execute the command as when needed.

        Args:
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            None.

        Examples:
            Save all entities of the default namespace.

            >>> self.save_namespace()

        """
        namespace = self._get_namespace(**kwargs)
        await self.AD.state.save_namespace(namespace)

    #
    # Utility
    #

    @utils.sync_wrapper
    async def get_app(self, name):
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
        return await self.AD.app_management.get_app(name)

    @utils.sync_wrapper
    async def _check_entity(self, namespace, entity):
        if "." not in entity:
            raise ValueError(f"{self.name}: Invalid entity ID: {entity}")
        if not await self.AD.state.entity_exists(namespace, entity):
            self.logger.warning("%s: Entity %s not found in namespace %s", self.name, entity, namespace)

    @staticmethod
    def get_ad_version():
        """Returns a string with the current version of AppDaemon.

        Examples:
            >>> version = self.get_ad_version()

        """
        return utils.__version__

    #
    # Entity
    #

    @utils.sync_wrapper
    async def add_entity(
        self, entity_id: str, state: Any = None, attributes: dict = None, **kwargs: Optional[dict]
    ) -> None:
        """Adds a non-existent entity, by creating it within a namespaces.

         If an entity doesn't exists and needs to be created, this function can be used to create it locally.
         Please note this only creates the entity locally.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            state (str): The state the entity is to have
            attributes (dict): The attributes the entity is to have
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        namespace = self._get_namespace(**kwargs)

        await self.get_entity_api(namespace, entity_id).add(state, attributes)

    @utils.sync_wrapper
    async def entity_exists(self, entity_id: str, **kwargs: Optional[dict]) -> bool:
        """Checks the existence of an entity in AD.

        When working with multiple AD namespaces, it is possible to specify the
        namespace, so that it checks within the right namespace in in the event the app is
        working in a different namespace. Also when using this function, it is also possible
        to check if an AppDaemon entity exists.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        namespace = self._get_namespace(**kwargs)
        return await self.get_entity_api(namespace, entity_id).exists()

    @utils.sync_wrapper
    async def split_entity(self, entity_id, **kwargs):
        """Splits an entity into parts.

        This utility function will take a fully qualified entity id of the form ``light.hall_light``
        and split it into 2 values, the device and the entity, e.g. light and hall_light.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        await self._check_entity(self._get_namespace(**kwargs), entity_id)
        return entity_id.split(".")

    @utils.sync_wrapper
    async def remove_entity(self, entity_id, **kwargs):
        """Deletes an entity created within a namespaces.

         If an entity was created, and its deemed no longer needed, by using this function,
         the entity can be removed from AppDaemon permanently.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        namespace = self._get_namespace(**kwargs)
        await self.AD.state.remove_entity(namespace, entity_id)
        return None

    @staticmethod
    def split_device_list(devices):
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

    @utils.sync_wrapper
    async def get_plugin_config(self, **kwargs):
        """Gets any useful metadata that the plugin may have available.

        For instance, for the HASS plugin, this will return Home Assistant configuration
        data such as latitude and longitude.

        Args:
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            namespace (str): Select the namespace of the plugin for which data is desired.

        Returns:
            A dictionary containing all the configuration information available
            from the Home Assistant ``/api/config`` endpoint.

        Examples:
            >>> config = self.get_plugin_config()
            >>> self.log(f'My current position is {config["latitude"]}(Lat), {config["longitude"]}(Long)')
            My current position is 50.8333(Lat), 4.3333(Long)

        """
        namespace = self._get_namespace(**kwargs)
        return await self.AD.plugins.get_plugin_meta(namespace)

    @utils.sync_wrapper
    async def friendly_name(self, entity_id, **kwargs):
        """Gets the Friendly Name of an entity.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        await self._check_entity(self._get_namespace(**kwargs), entity_id)
        state = await self.get_state(**kwargs)
        if entity_id in state:
            if "friendly_name" in state[entity_id]["attributes"]:
                return state[entity_id]["attributes"]["friendly_name"]
            else:
                return entity_id
        return None

    @utils.sync_wrapper
    async def set_production_mode(self, mode=True):
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
            return None
        await self.AD.utility.set_production_mode(mode)
        return mode

    #
    # Internal Helper functions
    #

    def start_app(self, app, **kwargs):
        """Starts an App which can either be running or not.

        This Api call cannot start an app which has already been disabled in the App Config.
        It essentially only runs the initialize() function in the app, and changes to attributes
        like class name or app config is not taken into account.

        Args:
            app (str): Name of the app.
            **kwargs (optional): Zero or more keyword arguments.

        Returns:
            None.

        Examples:
            >>> self.start_app("lights_app")

        """
        kwargs["app"] = app
        kwargs["namespace"] = "admin"
        kwargs["__name"] = self.name
        self.call_service("app/start", **kwargs)
        return None

    def stop_app(self, app, **kwargs):
        """Stops an App which is running.

        Args:
            app (str): Name of the app.
            **kwargs (optional): Zero or more keyword arguments.

        Returns:
            None.

        Examples:
            >>> self.stop_app("lights_app")

        """
        kwargs["app"] = app
        kwargs["namespace"] = "admin"
        kwargs["__name"] = self.name
        self.call_service("app/stop", **kwargs)
        return None

    def restart_app(self, app, **kwargs):
        """Restarts an App which can either be running or not.

        Args:
            app (str): Name of the app.
            **kwargs (optional): Zero or more keyword arguments.

        Returns:
            None.

        Examples:
            >>> self.restart_app("lights_app")

        """
        kwargs["app"] = app
        kwargs["namespace"] = "admin"
        kwargs["__name"] = self.name
        self.call_service("app/restart", **kwargs)
        return None

    def reload_apps(self, **kwargs):
        """Reloads the apps, and loads up those that have changes made to their .yaml or .py files.

        This utility function can be used if AppDaemon is running in production mode, and it is
        needed to reload apps that changes have been made to.

        Args:
            **kwargs (optional): Zero or more keyword arguments.

        Returns:
            None.

        Examples:
            >>> self.reload_apps()

        """
        kwargs["namespace"] = "admin"
        kwargs["__name"] = self.name
        self.call_service("app/reload", **kwargs)
        return None

    #
    # Dialogflow
    #

    def get_dialogflow_intent(self, data):
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
        else:
            return None

    @staticmethod
    def get_dialogflow_slot_value(data, slot=None):
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

    def format_dialogflow_response(self, speech=None):
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
    def format_alexa_response(speech=None, card=None, title=None):
        """Formats a response to be returned to Alex including speech and a card.

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
    def get_alexa_error(data):
        """Gets the error message from the Alexa API response.

        Args:
            data: Response received from the Alexa API .

        Returns:
            A string representing the value of message, or ``None`` if no error message was received.

        """
        if "request" in data and "err" in data["request"] and "message" in data["request"]["err"]:
            return data["request"]["err"]["message"]
        else:
            return None

    @staticmethod
    def get_alexa_intent(data):
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
    def get_alexa_slot_value(data, slot=None):
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

    @utils.sync_wrapper
    async def register_endpoint(
        self, callback: Callable[[Any, dict], Any], endpoint: str = None, **kwargs: Optional[dict]
    ) -> str:
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
            the function will generate an error each time it is processed.

            >>> self.register_endpoint(self.my_callback)
            >>> self.register_endpoint(self.alexa_cb, "alexa")

            >>> async def alexa_cb(self, request, kwargs):
            >>>     data = await request.json()
            >>>     self.log(data)
            >>>     response = {"message": "Hello World"}
            >>>     return response, 200

        """
        if endpoint is None:
            endpoint = self.name

        if self.AD.http is not None:
            return await self.AD.http.register_endpoint(callback, endpoint, self.name, **kwargs)
        else:
            self.logger.warning(
                "register_endpoint for %s failed - HTTP component is not configured", endpoint,
            )

    @utils.sync_wrapper
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

    @utils.sync_wrapper
    async def register_route(
        self, callback: Callable[[Any, dict], Any], route: str = None, **kwargs: Optional[dict]
    ) -> str:
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
            It should be noted that the register function, should return a string (can be empty),
            and an HTTP OK status response (e.g., `200`. If this is not added as a returned response,
            the function will generate an error each time it is processed.

            >>> self.register_route(my_callback)
            >>> self.register_route(stream_cb, "camera")

        """
        if route is None:
            route = self.name

        if self.AD.http is not None:
            return await self.AD.http.register_route(callback, route, self.name, **kwargs)

        else:
            self.logger.warning("register_route for %s filed - HTTP component is not configured", route)

    @utils.sync_wrapper
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

    @utils.sync_wrapper
    async def listen_state(
        self, callback: Callable, entity_id: Union[str, list] = None, **kwargs: Optional[dict]
    ) -> Union[str, list]:
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
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            attribute (str, optional): Name of an attribute within the entity state object. If this
                parameter is specified in addition to a fully qualified ``entity_id``. ``listen_state()``
                will subscribe to changes for just that attribute within that specific entity.
                The ``new`` and ``old`` parameters in the callback function will be provided with
                a single value representing the attribute.

                The value ``all`` for attribute has special significance and will listen for any
                state change within the specified entity, and supply the callback functions with
                the entire state dictionary for the specified entity rather than an individual
                attribute value.
            new (optional): If ``new`` is supplied as a parameter, callbacks will only be made if the
                state of the selected attribute (usually state) in the new state match the value
                of ``new``. The parameter type is defined by the namespace or plugin that is responsible
                for the entity. If it looks like a float, list, or dictionary, it may actually be a string.
            old (optional): If ``old`` is supplied as a parameter, callbacks will only be made if the
                state of the selected attribute (usually state) in the old state match the value
                of ``old``. The same caveats on types for the ``new`` parameter apply to this parameter.

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
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description. In most cases,
                it is safe to ignore this parameter. The value ``global`` for namespace has special
                significance and means that the callback will listen to state updates from any plugin.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Sets which thread from the worker pool the callback will be
                run by (0 - number of threads -1).
            *kwargs (optional): Zero or more keyword arguments that will be supplied to the callback
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

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1")

            Listen for a state change involving `light.office1` and return the entire state as a dict.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "all")

            Listen for a change involving the brightness attribute of `light.office1` and return the
            brightness attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "brightness")

            Listen for a state change involving `light.office1` turning on and return the state attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on")

            Listen for a change involving `light.office1` changing from brightness 100 to 200 and return the
            brightness attribute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "brightness", old = "100", new = "200")

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on", duration = 60)

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute
            trigger the delay immediately if the light is already on.

            >>> self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on", duration = 60, immediate = True)

            Listen for a state change involving `light.office1` and `light.office2` changing to state on.

            >>> self.handle = self.listen_state(self.my_callback, ["light.office_1", "light.office2"], new = "on")

        """
        namespace = self._get_namespace(**kwargs)

        if isinstance(entity_id, list):
            handles = []
            for e in entity_id:
                if e is not None and "." in e:
                    await self._check_entity(namespace, e)

                handle = await self.get_entity_api(namespace, e).listen_state(callback, **kwargs)
                handles.append(handle)

            return handles

        else:
            if entity_id is not None and "." in entity_id:
                await self._check_entity(namespace, entity_id)

            return await self.get_entity_api(namespace, entity_id).listen_state(callback, **kwargs)

    @utils.sync_wrapper
    async def cancel_listen_state(self, handle):
        """Cancels a ``listen_state()`` callback.

        This will mean that the App will no longer be notified for the specific
        state change that has been cancelled. Other state changes will continue
        to be monitored.

        Args:
            handle: The handle returned when the ``listen_state()`` call was made.

        Returns:
            Boolean.

        Examples:
            >>> self.cancel_listen_state(self.office_light_handle)

        """
        self.logger.debug("Canceling listen_state for %s", self.name)
        return await self.AD.state.cancel_state_callback(handle, self.name)

    @utils.sync_wrapper
    async def info_listen_state(self, handle):
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

    @utils.sync_wrapper
    async def get_state(self, entity_id=None, attribute=None, default=None, copy=True, **kwargs):
        """Gets the state of any component within Home Assistant.

        State updates are continuously tracked, so this call runs locally and does not require
        AppDaemon to call back to Home Assistant. In other words, states are updated using a
        push-based approach instead of a pull-based one.

        Args:
            entity_id (str, optional): This is the name of an entity or device type. If just
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
            copy (bool, optional): By default, a copy of the stored state object is returned.
                When you set ``copy`` to ``False``, you get the same object as is stored
                internally by AppDaemon. Avoiding the copying brings a small performance gain,
                but also gives you write-access to the internal AppDaemon data structures,
                which is dangerous. Only disable copying when you can guarantee not to modify
                the returned state object, e.g., you do read-only operations.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter.

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
        namespace = self._get_namespace(**kwargs)

        return await self.get_entity_api(namespace, entity_id).get_state(attribute, default, copy, **kwargs)

    @utils.sync_wrapper
    async def set_state(self, entity_id, **kwargs):
        """Updates the state of the specified entity.

        Args:
            entity_id (str): The fully qualified entity id (including the device type).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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

        Returns:
            A dictionary that represents the new state of the updated entity.

        Examples:
            Update the state of an entity.

            >>> self.set_state("light.office_1", state="off")

            Update the state and attribute of an entity.

            >>> self.set_state("light.office_1", state = "on", attributes = {"color_name": "red"})

            Update the state of an entity within the specified namespace.

            >>> self.set_state("light.office_1", state="off", namespace ="hass")

        """

        namespace = self._get_namespace(**kwargs)
        await self._check_entity(namespace, entity_id)

        return await self.get_entity_api(namespace, entity_id).set_state(**kwargs)

    #
    # Service
    #

    @staticmethod
    def _check_service(service: str) -> None:
        if service.find("/") == -1:
            raise ValueError("Invalid Service Name: %s", service)

    def register_service(
        self, service: str, cb: Callable[[str, str, str, dict], Any], **kwargs: Optional[dict]
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
        Keyword Args:
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter.

        Returns:
            None

        Examples:
            >>> self.register_service("myservices/service1", self.mycallback)

            >>> async def mycallback(self, namespace, domain, service, kwargs):
            >>>     self.log("Service called")

        """
        self._check_service(service)
        d, s = service.split("/")
        self.logger.debug("register_service: %s/%s, %s", d, s, kwargs)

        namespace = self._get_namespace(**kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        kwargs["__name"] = self.name

        self.AD.services.register_service(namespace, d, s, cb, __async="auto", **kwargs)

    def deregister_service(self, service: str, **kwargs: Optional[dict]) -> bool:
        """Deregisters a service that had been previously registered

        Using this function, an App can deregister a service call, it has initially registered in the service registry.
        This will automatically make it unavailable to other apps using the `call_service()` API call, as well as published
        as a service in the REST API and make it unavailable to the `call_service` command in the event stream.
        This function can only be used, within the app that registered it in the first place

        Args:
            service: Name of the service, in the format `domain/service`.
        Keyword Args:
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter.

        Returns:
            Bool

        Examples:
            >>> self.deregister_service("myservices/service1")

        """
        self._check_service(service)
        d, s = service.split("/")
        self.logger.debug("deregister_service: %s/%s, %s", d, s, kwargs)

        namespace = self._get_namespace(**kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        kwargs["__name"] = self.name

        return self.AD.services.deregister_service(namespace, d, s, **kwargs)

    def list_services(self, **kwargs: Optional[dict]) -> list:
        """List all services available within AD

        Using this function, an App can request all available services within AD

        Args:
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            **kwargs: Each service has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `namespace = global`.
            namespace(str, optional): If a `namespace` is provided, AppDaemon will request
                the services within the given namespace. On the other hand, if no namespace is given,
                AppDaemon will use the last specified namespace or the default namespace.
                To get all services across AD, pass `global`. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.

        Returns:
            All services within the requested namespace

        Examples:
            >>> self.list_services(namespace="global")

        """

        self.logger.debug("list_services: %s", kwargs)

        namespace = kwargs.get("namespace", "global")

        return self.AD.services.list_services(namespace)  # retrieve services

    @utils.sync_wrapper
    async def call_service(self, service: str, **kwargs: Optional[dict]) -> Any:
        """Calls a Service within AppDaemon.

        This function can call any service and provide any required parameters.
        By default, there are standard services that can be called within AD. Other
        services that can be called, are dependent on the plugin used, or those registered
        by individual apps using the `register_service` api.
        In a future release, all available services can be found using AD's Admin UI.
        For `listed services`, the part before the first period is the ``domain``,
        and the part after is the ``service name`. For instance, `light/turn_on`
        has a domain of `light` and a service name of `turn_on`.

        The default behaviour of the call service api is not to wait for any result, typically
        known as "fire and forget". If it is required to get the results of the call, keywords
        "return_result" or "callback" can be added.

        Args:
            service (str): The service name.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            **kwargs: Each service has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `entity_id = light.office_1`. These parameters will be different for
                every service and can be discovered using the developer tools. Most all
                service calls require an ``entity_id``.
            namespace(str, optional): If a `namespace` is provided, AppDaemon will change
                the state of the given entity in the given namespace. On the other hand,
                if no namespace is given, AppDaemon will use the last specified namespace
                or the default namespace. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.
            return_result(str, option): If `return_result` is provided and set to `True` AD will attempt
                to wait for the result, and return it after execution
            callback: The non-async callback to be executed when complete.

        Returns:
            Result of the `call_service` function if any

        Examples:
            HASS

            >>> self.call_service("light/turn_on", entity_id = "light.office_lamp", color_name = "red")
            >>> self.call_service("notify/notify", title = "Hello", message = "Hello World")

            MQTT

            >>> call_service("mqtt/subscribe", topic="homeassistant/living_room/light", qos=2)
            >>> call_service("mqtt/publish", topic="homeassistant/living_room/light", payload="on")

            Utility

            >>> call_service("app/restart", app="notify_app", namespace="appdaemon")
            >>> call_service("app/stop", app="lights_app", namespace="appdaemon")
            >>> call_service("app/reload", namespace="appdaemon")

            For Utility, it is important that the `namespace` arg is set to ``appdaemon``
            as no app can work within that `namespace`. If not namespace is specified,
            calling this function will rise an error.

        """
        self._check_service(service)
        d, s = service.split("/")
        self.logger.debug("call_service: %s/%s, %s", d, s, kwargs)

        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        kwargs["__name"] = self.name

        return await self.AD.services.call_service(namespace, d, s, kwargs)

    @utils.sync_wrapper
    async def run_sequence(self, sequence: Union[str, list], **kwargs: Optional[dict]):
        """Run an AppDaemon Sequence. Sequences are defined in a valid apps.yaml file or inline, and are sequences of
        service calls.

        Args:
            sequence: The sequence name, referring to the correct entry in apps.yaml, or a list containing
                actual commands to run
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            namespace(str, optional): If a `namespace` is provided, AppDaemon will change
                the state of the given entity in the given namespace. On the other hand,
                if no namespace is given, AppDaemon will use the last specified namespace
                or the default namespace. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.

        Returns:
            A handle that can be used with `cancel_sequence()` to terminate the script.

        Examples:
            Run a yaml-defined sequence called "sequence.front_room_scene".

            >>> handle = self.run_sequence("sequence.front_room_scene")

            Run an inline sequence.

            >>> handle = self.run_sequence([{"light/turn_on": {"entity_id": "light.office_1"}}, {"sleep": 5}, {"light.turn_off":
            {"entity_id": "light.office_1"}}])

        """
        namespace = self._get_namespace(**kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        _name = self.name
        self.logger.debug("Calling run_sequence() for %s from %s", sequence, self.name)
        return await self.AD.sequences.run_sequence(_name, namespace, sequence, **kwargs)

    @utils.sync_wrapper
    async def cancel_sequence(self, sequence: Any) -> None:
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

    @utils.sync_wrapper
    async def listen_event(
        self, callback: Callable, event: Union[str, list] = None, **kwargs: Optional[dict]
    ) -> Union[str, list]:
        """Registers a callback for a specific event, or any event.

        Args:
            callback: Function to be invoked when the event is fired.
                It must conform to the standard Event Callback format documented `here <APPGUIDE.html#about-event-callbacks>`__
            event (str|list, optional): Name of the event to subscribe to. Can be a standard
                Home Assistant event such as `service_registered`, an arbitrary
                custom event such as `"MODE_CHANGE"` or a list of events `["pressed", "released"]`. If no event is specified,
                `listen_event()` will subscribe to all events.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            oneshot (bool, optional): If ``True``, the callback will be automatically cancelled
                after the first state change that results in a callback.
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter. The value ``global``
                for namespace has special significance, and means that the callback will
                listen to state updates from any plugin.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.

            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).

            timeout (int, optional): If ``timeout`` is supplied as a parameter, the callback will be created as normal,
                 but after ``timeout`` seconds, the callback will be removed.

            **kwargs (optional): One or more keyword value pairs representing App specific
                parameters to supply to the callback. If the keywords match values within the
                event data, they will act as filters, meaning that if they don't match the
                values, the callback will not fire.

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

            Listen for a `minimote` event activating scene 3 from a specific `minimote`.

            >>> self.listen_event(self.generic_event, "zwave.scene_activated", entity_id = "minimote_31", scene_id = 3)

            Listen for some custom events of a button being pressed.

            >>> self.listen_event(self.button_event, ["pressed", "released"])

        """
        namespace = self._get_namespace(**kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        _name = self.name
        self.logger.debug("Calling listen_event for %s", self.name)

        if isinstance(event, list):
            handles = []
            for e in event:
                handle = await self.AD.events.add_event_callback(_name, namespace, callback, e, **kwargs)
                handles.append(handle)

            return handles

        else:
            return await self.AD.events.add_event_callback(_name, namespace, callback, event, **kwargs)

    @utils.sync_wrapper
    async def cancel_listen_event(self, handle):
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

    @utils.sync_wrapper
    async def info_listen_event(self, handle):
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

    @utils.sync_wrapper
    async def fire_event(self, event, **kwargs):
        """Fires an event on the AppDaemon bus, for apps and plugins.

        Args:
            event: Name of the event. Can be a standard Home Assistant event such as
                `service_registered` or an arbitrary custom event such as "MODE_CHANGE".
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        namespace = self._get_namespace(**kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        await self.AD.events.fire_event(namespace, event, **kwargs)

    #
    # Time
    #

    def parse_utc_string(self, utc_string):
        """Converts a UTC to its string representation.

        Args:
            utc_string (str): A string that contains a date and time to convert.

        Returns:
            An POSIX timestamp that is equivalent to the date and time contained in `utc_string`.

        """
        return datetime.datetime(*map(int, re.split(r"[^\d]", utc_string)[:-1])).timestamp() + self.get_tz_offset() * 60

    def get_tz_offset(self):
        """Returns the timezone difference between UTC and Local Time in minutes."""
        return self.AD.tz.utcoffset(self.datetime()).total_seconds() / 60

    @staticmethod
    def convert_utc(utc):
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

    @utils.sync_wrapper
    async def sun_up(self):
        """Determines if the sun is currently up.

        Returns:
             bool: ``True`` if the sun is up, ``False`` otherwise.

        Examples:
            >>> if self.sun_up():
            >>>    #do something

        """
        return await self.AD.sched.sun_up()

    @utils.sync_wrapper
    async def sun_down(self):
        """Determines if the sun is currently down.

        Returns:
            bool: ``True`` if the sun is down, ``False`` otherwise.

        Examples:
            >>> if self.sun_down():
            >>>    #do something

        """
        return await self.AD.sched.sun_down()

    @utils.sync_wrapper
    async def parse_time(self, time_str, name=None, aware=False):
        """Creates a `time` object from its string representation.

        This functions takes a string representation of a time, or sunrise,
        or sunset offset and converts it to a datetime.time object.

        Args:
            time_str (str): A representation of the time in a string format with one
                of the following formats:

                    a. ``HH:MM:SS`` - the time in Hours Minutes and Seconds, 24 hour format.

                    b. ``sunrise|sunset [+|- HH:MM:SS]`` - time of the next sunrise or sunset
                    with an optional positive or negative offset in Hours Minutes and seconds.
            name (str, optional): Name of the calling app or module. It is used only for logging purposes.
            aware (bool, optional): If ``True`` the created time object will be aware of timezone.

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
        return await self.AD.sched.parse_time(time_str, name, aware)

    @utils.sync_wrapper
    async def parse_datetime(self, time_str, name=None, aware=False):
        """Creates a `datetime` object from its string representation.

        This function takes a string representation of a date and time, or sunrise,
        or sunset offset and converts it to a `datetime` object.

        Args:
            time_str (str): A string representation of the datetime with one of the
                following formats:

                    a. ``YY-MM-DD-HH:MM:SS`` - the date and time in Year, Month, Day, Hours,
                    Minutes, and Seconds, 24 hour format.

                    b. ``HH:MM:SS`` - the time in Hours Minutes and Seconds, 24 hour format.

                    c. ``sunrise|sunset [+|- HH:MM:SS]`` - time of the next sunrise or sunset
                    with an optional positive or negative offset in Hours Minutes and seconds.

                If the ``HH:MM:SS`` format is used, the resulting datetime object will have
                today's date.
            name (str, optional): Name of the calling app or module. It is used only for logging purposes.
            aware (bool, optional): If ``True`` the created datetime object will be aware
                of timezone.

        Returns:
            A `datetime` object, representing the time and date given in the
            `time_str` argument.

        Examples:
            >>> self.parse_datetime("2018-08-09 17:30:00")
            2018-08-09 17:30:00

            >>> self.parse_datetime("17:30:00")
            2019-08-15 17:30:00

            >>> self.parse_datetime("sunrise")
            2019-08-16 05:33:17

            >>> self.parse_datetime("sunset + 00:30:00")
            2019-08-16 19:18:48

            >>> self.parse_datetime("sunrise + 01:00:00")
            2019-08-16 06:33:17
        """
        return await self.AD.sched.parse_datetime(time_str, name, aware)

    @utils.sync_wrapper
    async def get_now(self):
        """Returns the current Local Date and Time.

        Examples:
            >>> self.get_now()
            2019-08-16 21:17:41.098813+00:00

        """
        now = await self.AD.sched.get_now()
        return now.astimezone(self.AD.tz)

    @utils.sync_wrapper
    async def get_now_ts(self):
        """Returns the current Local Timestamp.

        Examples:
             >>> self.get_now_ts()
             1565990318.728324

        """
        return await self.AD.sched.get_now_ts()

    @utils.sync_wrapper
    async def now_is_between(self, start_time, end_time, name=None):
        """Determines if the current `time` is within the specified start and end times.

        This function takes two string representations of a ``time``, or ``sunrise`` or ``sunset``
        offset and returns ``true`` if the current time is between those 2 times. Its
        implementation can correctly handle transitions across midnight.

        Args:
            start_time (str): A string representation of the start time.
            end_time (str): A string representation of the end time.
            name (str, optional): Name of the calling app or module. It is used only for logging purposes.

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
        return await self.AD.sched.now_is_between(start_time, end_time, name)

    @utils.sync_wrapper
    async def sunrise(self, aware=False):
        """Returns a `datetime` object that represents the next time Sunrise will occur.

        Args:
            aware (bool, optional): Specifies if the created datetime object will be
                `aware` of timezone or `not`.

        Examples:
            >>> self.sunrise()
            2019-08-16 05:33:17

        """
        return await self.AD.sched.sunrise(aware)

    @utils.sync_wrapper
    async def sunset(self, aware=False):
        """Returns a `datetime` object that represents the next time Sunset will occur.

        Args:
           aware (bool, optional): Specifies if the created datetime object will be
                `aware` of timezone or `not`.

        Examples:
            >>> self.sunset()
            2019-08-16 19:48:48

        """
        return await self.AD.sched.sunset(aware)

    @utils.sync_wrapper
    async def time(self):
        """Returns a localised `time` object representing the current Local Time.

        Use this in preference to the standard Python ways to discover the current time,
        especially when using the "Time Travel" feature for testing.

        Examples:
            >>> self.time()
            20:15:31.295751

        """
        now = await self.AD.sched.get_now()
        return now.astimezone(self.AD.tz).time()

    @utils.sync_wrapper
    async def datetime(self, aware=False):
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
        if aware is True:
            now = await self.AD.sched.get_now()
            return now.astimezone(self.AD.tz)
        else:
            return await self.AD.sched.get_now_naive()

    @utils.sync_wrapper
    async def date(self):
        """Returns a localised `date` object representing the current Local Date.

        Use this in preference to the standard Python ways to discover the current date,
        especially when using the "Time Travel" feature for testing.

        Examples:
            >>> self.date()
            2019-08-15

        """
        now = await self.AD.sched.get_now()
        return now.astimezone(self.AD.tz).date()

    def get_timezone(self):
        """Returns the current time zone."""
        return self.AD.time_zone

    #
    # Scheduler
    #

    @utils.sync_wrapper
    async def timer_running(self, handle):
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

    @utils.sync_wrapper
    async def cancel_timer(self, handle):
        """Cancels a previously created timer.

        Args:
            handle: A handle value returned from the original call to create the timer.

        Returns:
            Boolean.

        Examples:
            >>> self.cancel_timer(handle)

        """
        name = self.name
        self.logger.debug("Canceling timer with handle %s for %s", handle, self.name)
        return await self.AD.sched.cancel_timer(name, handle)

    @utils.sync_wrapper
    async def info_timer(self, handle):
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

    @utils.sync_wrapper
    async def run_in(self, callback, delay, **kwargs):
        """Runs the callback in a defined number of seconds.

        This is used to add a delay, for instance, a 60 second delay before
        a light is turned off after it has been triggered by a motion detector.
        This callback should always be used instead of ``time.sleep()`` as
        discussed previously.

        Args:
            callback: Function to be invoked when the requested state change occurs.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            delay (int): Delay, in seconds before the callback is invoked.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
            Run the specified callback after 10 seconds.

            >>> self.handle = self.run_in(self.run_in_c, 10)

            Run the specified callback after 10 seconds with a keyword arg (title).

            >>> self.handle = self.run_in(self.run_in_c, 5, title = "run_in5")

        """
        name = self.name
        self.logger.debug("Registering run_in in %s seconds for %s", delay, name)
        # convert seconds to an int if possible since a common pattern is to
        # pass this through from the config file which is a string
        exec_time = await self.get_now() + timedelta(seconds=int(delay))
        handle = await self.AD.sched.insert_schedule(name, exec_time, callback, False, None, **kwargs)

        return handle

    @utils.sync_wrapper
    async def run_once(self, callback, start, **kwargs):
        """Runs the callback once, at the specified time of day.

        Args:
            callback: Function to be invoked at the specified time of day.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: Should be either a Python ``time`` object or a ``parse_time()`` formatted
                string that specifies when the callback will occur. If the time
                specified is in the past, the callback will occur the ``next day`` at
                the specified time.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        if type(start) == datetime.time:
            when = start
        elif type(start) == str:
            start_time_obj = await self.AD.sched._parse_time(start, self.name)
            when = start_time_obj["datetime"].time()
        else:
            raise ValueError("Invalid type for start")
        name = self.name

        self.logger.debug("Registering run_once at %s for %s", when, name)

        now = await self.get_now()
        today = now.date()
        event = datetime.datetime.combine(today, when)
        aware_event = self.AD.sched.convert_naive(event)
        if aware_event < now:
            one_day = datetime.timedelta(days=1)
            aware_event = aware_event + one_day
        handle = await self.AD.sched.insert_schedule(name, aware_event, callback, False, None, **kwargs)
        return handle

    @utils.sync_wrapper
    async def run_at(self, callback, start, **kwargs):
        """Runs the callback once, at the specified time of day.

        Args:
            callback: Function to be invoked at the specified time of day.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: Should be either a Python ``time`` object or a ``parse_time()`` formatted
                string that specifies when the callback will occur.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        if type(start) == datetime.datetime:
            when = start
        elif type(start) == str:
            start_time_obj = await self.AD.sched._parse_time(start, self.name)
            when = start_time_obj["datetime"]
        else:
            raise ValueError("Invalid type for start")
        aware_when = self.AD.sched.convert_naive(when)
        name = self.name

        self.logger.debug("Registering run_at at %s for %s", when, name)

        now = await self.get_now()
        if aware_when < now:
            raise ValueError("{}: run_at() Start time must be " "in the future".format(self.name))
        handle = await self.AD.sched.insert_schedule(name, aware_when, callback, False, None, **kwargs)
        return handle

    @utils.sync_wrapper
    async def run_daily(self, callback, start, **kwargs):
        """Runs the callback at the same time every day.

        Args:
            callback: Function to be invoked every day at the specified time.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: Should be either a Python ``time`` object or a ``parse_time()`` formatted
                string that specifies when the callback will occur. If the time
                specified is in the past, the callback will occur the ``next day`` at
                the specified time.
                When specifying sunrise or sunset relative times using the ``parse_datetime()``
                format, the time of the callback will be adjusted every day to track the actual
                value of sunrise or sunset.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        info = None
        when = None
        if type(start) == datetime.time:
            when = start
        elif type(start) == str:
            info = await self.AD.sched._parse_time(start, self.name)
        else:
            raise ValueError("Invalid type for start")

        if info is None or info["sun"] is None:
            if when is None:
                when = info["datetime"].time()
            aware_now = await self.get_now()
            now = self.AD.sched.make_naive(aware_now)
            today = now.date()
            event = datetime.datetime.combine(today, when)
            if event < now:
                event = event + datetime.timedelta(days=1)
            handle = await self.run_every(callback, event, 24 * 60 * 60, **kwargs)
        elif info["sun"] == "sunrise":
            kwargs["offset"] = info["offset"]
            handle = await self.run_at_sunrise(callback, **kwargs)
        else:
            kwargs["offset"] = info["offset"]
            handle = await self.run_at_sunset(callback, **kwargs)
        return handle

    @utils.sync_wrapper
    async def run_hourly(self, callback, start, **kwargs):
        """Runs the callback at the same time every hour.

        Args:
            callback: Function to be invoked every hour at the specified time.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: A Python ``time`` object that specifies when the callback will occur,
                the hour component of the time object is ignored. If the time specified
                is in the past, the callback will occur the ``next hour`` at the specified
                time. If time is not supplied, the callback will start an hour from the
                time that ``run_hourly()`` was executed.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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

        Examples:
            Run every hour, on the hour.

            >>> runtime = datetime.time(0, 0, 0)
            >>> self.run_hourly(self.run_hourly_c, runtime)

        """
        now = await self.get_now()
        if start is None:
            event = now + datetime.timedelta(hours=1)
        else:
            event = now
            event = event.replace(minute=start.minute, second=start.second)
            if event < now:
                event = event + datetime.timedelta(hours=1)
        handle = await self.run_every(callback, event, 60 * 60, **kwargs)
        return handle

    @utils.sync_wrapper
    async def run_minutely(self, callback, start, **kwargs):
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
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
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
        now = await self.get_now()
        if start is None:
            event = now + datetime.timedelta(minutes=1)
        else:
            event = now
            event = event.replace(second=start.second)
            if event < now:
                event = event + datetime.timedelta(minutes=1)
        handle = await self.run_every(callback, event, 60, **kwargs)
        return handle

    @utils.sync_wrapper
    async def run_every(self, callback, start, interval, **kwargs):
        """Runs the callback with a configurable delay starting at a specific time.

        Args:
            callback: Function to be invoked when the time interval is reached.
                It must conform to the standard Scheduler Callback format documented
                `here <APPGUIDE.html#about-schedule-callbacks>`__.
            start: A Python ``datetime`` object that specifies when the initial callback
                will occur, or can take the `now` string alongside an added offset. If given
                in the past, it will be executed in the next interval time.
            interval: Frequency (expressed in seconds) in which the callback should be executed.
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Keyword Args:
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).


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
        name = self.name
        now = await self.get_now()

        if isinstance(start, str) and "now" in start:  # meaning immediate time required
            now_offset = 0
            if "+" in start:  # meaning time to be added
                now_offset = int(re.findall(r"\d+", start)[0])

            aware_start = await self.get_now()
            aware_start = aware_start + datetime.timedelta(seconds=now_offset)

        else:
            aware_start = self.AD.sched.convert_naive(start)

        if aware_start < now:
            aware_start = now + datetime.timedelta(seconds=interval)

        self.logger.debug(
            "Registering run_every starting %s in %ss intervals for %s", aware_start, interval, name,
        )

        handle = await self.AD.sched.insert_schedule(
            name, aware_start, callback, True, None, interval=interval, **kwargs
        )
        return handle

    @utils.sync_wrapper
    async def _schedule_sun(self, name, type_, callback, **kwargs):

        if type_ == "next_rising":
            event = self.AD.sched.next_sunrise()
        else:
            event = self.AD.sched.next_sunset()

        handle = await self.AD.sched.insert_schedule(name, event, callback, True, type_, **kwargs)
        return handle

    @utils.sync_wrapper
    async def run_at_sunset(self, callback, **kwargs):
        """Runs a callback every day at or around sunset.

        Args:
            callback: Function to be invoked at or around sunset. It must conform to the
                standard Scheduler Callback format documented `here <APPGUIDE.html#about-schedule-callbacks>`__.
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Keyword Args:
            offset (int, optional): The time in seconds that the callback should be delayed after
                sunset. A negative value will result in the callback occurring before sunset.
                This parameter cannot be combined with ``random_start`` or ``random_end``.
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).

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
        name = self.name
        self.logger.debug("Registering run_at_sunset with kwargs = %s for %s", kwargs, name)
        handle = await self._schedule_sun(name, "next_setting", callback, **kwargs)
        return handle

    @utils.sync_wrapper
    async def run_at_sunrise(self, callback, **kwargs):
        """Runs a callback every day at or around sunrise.

        Args:
            callback: Function to be invoked at or around sunrise. It must conform to the
                standard Scheduler Callback format documented `here <APPGUIDE.html#about-schedule-callbacks>`__.
            **kwargs: Arbitrary keyword parameters to be provided to the callback
                function when it is invoked.

        Keyword Args:
            offset (int, optional): The time in seconds that the callback should be delayed after
                sunrise. A negative value will result in the callback occurring before sunrise.
                This parameter cannot be combined with ``random_start`` or ``random_end``.
            random_start (int): Start of range of the random time.
            random_end (int): End of range of the random time.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Specify which thread from the worker pool the callback
                will be run by (0 - number of threads -1).

        Returns:
            A handle that can be used to cancel the timer.


        Notes:
            The ``random_start`` value must always be numerically lower than ``random_end`` value,
            they can be negative to denote a random offset before and event, or positive to
            denote a random offset after an event.

        Examples:
            Run 45 minutes before sunset.

            >>> self.run_at_sunrise(self.sun, offset = datetime.timedelta(minutes = -45).total_seconds())

            Or you can just do the math yourself.

            >>> self.run_at_sunrise(self.sun, offset = 30 * 60)

            Run at a random time +/- 60 minutes from sunrise.

            >>> self.run_at_sunrise(self.sun, random_start = -60*60, random_end = 60*60)

            Run at a random time between 30 and 60 minutes before sunrise.

            >>> self.run_at_sunrise(self.sun, random_start = -60*60, random_end = 30*60)

        """
        name = self.name
        self.logger.debug("Registering run_at_sunrise with kwargs = %s for %s", kwargs, name)
        handle = await self._schedule_sun(name, "next_rising", callback, **kwargs)
        return handle

    #
    # Dashboard
    #

    def dash_navigate(self, target, timeout=-1, ret=None, sticky=0, deviceid=None, dashid=None):
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

    async def run_in_executor(self, func, *args, **kwargs):
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

    def submit_to_executor(self, func, *args, **kwargs):
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
            >>> f = self.submit_to_executor(self.run_request, callback=self.callback)
            >>>
            >>> def callback(self, kwargs):
        """

        callback = kwargs.pop("callback", None)

        # get stuff we'll need to fake scheduler call
        sched_data = {
            "id": uuid.uuid4().hex,
            "name": self.name,
            "objectid": self.AD.app_management.objects[self.name]["id"],
            "type": "scheduler",
            "function": callback,
            "pin_app": self.get_app_pin(),
            "pin_thread": self.get_pin_thread(),
        }

        def callback_inner(f):
            try:
                # TODO: use our own callback type instead of borrowing
                # from scheduler
                rargs = {}
                rargs["result"] = f.result()
                sched_data["kwargs"] = rargs
                self.create_task(self.AD.threading.dispatch_worker(self.name, sched_data))

                # callback(f.result(), kwargs)
            except Exception as e:
                self.error(e, level="ERROR")

        f = self.AD.executor.submit(func, *args, **kwargs)

        if callback is not None:
            self.logger.debug("Adding add_done_callback for future %s for %s", f, self.name)
            f.add_done_callback(callback_inner)

        self.AD.futures.add_future(self.name, f)
        return f

    @utils.sync_wrapper
    async def create_task(self, coro, callback=None, **kwargs):
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
        # get stuff we'll need to fake scheduler call
        sched_data = {
            "id": uuid.uuid4().hex,
            "name": self.name,
            "objectid": self.AD.app_management.objects[self.name]["id"],
            "type": "scheduler",
            "function": callback,
            "pin_app": await self.get_app_pin(),
            "pin_thread": await self.get_pin_thread(),
        }

        def callback_inner(f):
            try:
                # TODO: use our own callback type instead of borrowing
                # from scheduler
                kwargs["result"] = f.result()
                sched_data["kwargs"] = kwargs
                self.create_task(self.AD.threading.dispatch_worker(self.name, sched_data))

                # callback(f.result(), kwargs)
            except asyncio.CancelledError:
                pass

        f = asyncio.create_task(coro)
        if callback is not None:
            self.logger.debug("Adding add_done_callback for future %s for %s", f, self.name)
            f.add_done_callback(callback_inner)

        self.AD.futures.add_future(self.name, f)
        return f

    @staticmethod
    async def sleep(delay, result=None):
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

    def get_entity(self, entity: str, **kwargs: Optional[dict]) -> Entity:
        namespace = self._get_namespace(**kwargs)
        self._check_entity(namespace, entity)
        entity_id = Entity(self.logger, self.AD, self.name, namespace, entity)

        return entity_id

    def get_entity_api(self, namespace: str, entity_id: str) -> Entity:
        api = Entity.entity_api(self.logger, self.AD, self.name, namespace, entity_id)

        return api

    def run_in_thread(self, callback, thread, **kwargs):
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
        self.run_in(callback, 0, pin=False, pin_thread=thread, **kwargs)

    @utils.sync_wrapper
    async def get_thread_info(self):
        """Gets information on AppDaemon worker threads.

        Returns:
            A dictionary containing all the information for AppDaemon worker threads.

        Examples:
            >>> thread_info = self.get_thread_info()

        """
        return await self.AD.threading.get_thread_info()

    @utils.sync_wrapper
    async def get_scheduler_entries(self):
        """Gets information on AppDaemon scheduler entries.

        Returns:
            A dictionary containing all the information for entries in the AppDaemon scheduler.

        Examples:
            >>> schedule = self.get_scheduler_entries()

        """
        return await self.AD.sched.get_scheduler_entries()

    @utils.sync_wrapper
    async def get_callback_entries(self):
        """Gets information on AppDaemon callback entries.

        Returns:
            A dictionary containing all the information for entries in the AppDaemon state,
            and event callback table.

        Examples:
            >>> callbacks = self.get_callback_entries()

        """
        return await self.AD.callbacks.get_callback_entries()

    @utils.sync_wrapper
    async def depends_on_module(self, *modules):
        """Registers a global_modules dependency for an app.

        Args:
            *modules: Modules to register a dependency on.

        Returns:
            None.

        Examples:
            >>> import somemodule
            >>> import anothermodule
            >>> # later
            >>> self.depends_on_module([somemodule)

        """
        return await self.AD.app_management.register_module_dependency(self.name, *modules)
