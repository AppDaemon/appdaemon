import asyncio
import copy
import cProfile
import importlib
import io
import logging
import os
import pstats
import subprocess
import sys
import traceback
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from logging import Logger
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Literal, Optional, Union

import appdaemon.utils as utils

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class UpdateMode(Enum):
    """Used as an argument for :meth:`AppManagement.check_app_updates` to set the mode of the check.

    INIT
        Triggers AppManagement._init_update_mode to run during check_app_updates
    NORMAL
        Normal update mode, for when :meth:`AppManagement.check_app_updates` is called by :meth:`.utility_loop.Utility.loop`
    TERMINATE
        Terminate all apps
    """

    INIT = 0
    NORMAL = 1
    TERMINATE = 2


@dataclass
class ModuleLoad:
    """Dataclass containing settings for calls to :meth:`AppManagement.read_app`

    Attributes:
        path: Filepath of the module or path to the `__init__.py` of a package.
        reload: Whether to reload the app using `importlib.reload`
        name: Importable name of the module/package
    """

    path: Path
    reload: bool = False
    name: str = field(init=False, repr=True)

    def __post_init__(self):
        self.path = Path(self.path).resolve()

        if self.path.name == "__init__.py":
            self.name = self.path.parent.name
        else:
            self.name = self.path.stem


@dataclass
class AppActions:
    """Stores which apps to initialize and terminate, as well as the total number of apps and the number of active apps.

    Attributes:
        init: Dictionary of apps to initialize, which ultimately happens in :meth:`AppManagement._load_apps` as part of :meth:`AppManagement.check_app_updates`
        term: Dictionary of apps to terminate, which ultimately happens in :meth:`AppManagement._terminate_apps` as part of :meth:`AppManagement.check_app_updates`
        total: Total number of apps
        active: Number of active apps
    """

    init: Dict[str, int] = field(default_factory=dict)
    term: Dict[str, int] = field(default_factory=dict)
    total: int = 0
    active: int = 0

    def mark_app_for_initialization(self, appname: str):
        self.init[appname] = 1

    def mark_app_for_termination(self, appname: str):
        self.term[appname] = 1


class AppManagement:
    """Subsystem container for managing app lifecycles"""

    AD: "AppDaemon"
    """Reference to the top-level AppDaemon container object
    """
    use_toml: bool
    """Whether to use TOML files for configuration
    """
    ext: Literal[".yaml", ".toml"]
    logger: Logger
    """Standard python logger named ``AppDaemon._app_management``
    """
    error: Logger
    """Standard python logger named ``Error``
    """
    monitored_files: Dict[Union[str, Path], float]
    """Dictionary of the Python files that are being watched for changes and their last modified times
    """
    filter_files: Dict[str, float]
    """Dictionary of the modified times of the filter files and their paths.
    """
    modules: Dict[str, ModuleType]
    """Dictionary of the loaded modules and their names
    """
    objects: Dict[str, Dict[str, Any]]
    """Dictionary of dictionaries with the instantiated apps, plugins, and sequences along with some metadata. Gets populated by

    - ``self.init_object``, which instantiates the app classes
    - ``self.init_plugin_object``
    - ``self.init_sequence_object``
    """
    app_config: Dict[str, Dict[str, Dict[str, bool]]]
    """Keeps track of which module and class each app comes from, along with any associated global modules. Gets set at the end of :meth:`~appdaemon.app_management.AppManagement.check_config`.
    """
    active_apps: List[str]
    inactive_apps: List[str]
    non_apps: List[str]

    def __init__(self, ad: "AppDaemon", use_toml: bool):
        self.AD = ad
        self.use_toml = use_toml
        self.ext = ".toml" if use_toml is True else ".yaml"
        self.logger = ad.logging.get_child("_app_management")
        self.error = ad.logging.get_error()
        self.diag = ad.logging.get_diag()
        self.monitored_files = {}
        self.filter_files = {}
        self.modules = {}
        self.objects = {}
        self.check_app_updates_profile_stats = None
        self.check_updates_lock = None

        # Initialize config file tracking

        self.app_config_file_modified = 0
        self.app_config_files = {}
        self.module_dirs = []

        # Keeps track of the name of the module and class to load for each app name
        self.app_config = {}
        self.global_module_dependencies = {}

        self.apps_initialized = False

        # first declare sensors
        self.active_apps_sensor = "sensor.active_apps"
        self.inactive_apps_sensor = "sensor.inactive_apps"
        self.total_apps_sensor = "sensor.total_apps"

        # Add Path for adbase

        sys.path.insert(0, os.path.dirname(__file__))

        #
        # Register App Services
        #
        self.AD.services.register_service("admin", "app", "start", self.manage_services)
        self.AD.services.register_service("admin", "app", "stop", self.manage_services)
        self.AD.services.register_service("admin", "app", "restart", self.manage_services)
        self.AD.services.register_service("admin", "app", "disable", self.manage_services)
        self.AD.services.register_service("admin", "app", "enable", self.manage_services)
        self.AD.services.register_service("admin", "app", "reload", self.manage_services)
        self.AD.services.register_service("admin", "app", "create", self.manage_services)
        self.AD.services.register_service("admin", "app", "edit", self.manage_services)
        self.AD.services.register_service("admin", "app", "remove", self.manage_services)

        self.active_apps = []
        self.inactive_apps = []
        self.non_apps = ["global_modules", "sequence"]

    async def set_state(self, name, **kwargs):
        # not a fully qualified entity name
        if name.find(".") == -1:
            entity_id = "app.{}".format(name)
        else:
            entity_id = name

        await self.AD.state.set_state("_app_management", "admin", entity_id, _silent=True, **kwargs)

    async def get_state(self, name, **kwargs):
        # not a fully qualified entity name
        if name.find(".") == -1:
            entity_id = "app.{}".format(name)
        else:
            entity_id = name

        return await self.AD.state.get_state("_app_management", "admin", entity_id, **kwargs)

    async def add_entity(self, name, state, attributes):
        # not a fully qualified entity name
        if name.find(".") == -1:
            entity_id = "app.{}".format(name)
        else:
            entity_id = name

        await self.AD.state.add_entity("admin", entity_id, state, attributes)

    async def remove_entity(self, name):
        await self.AD.state.remove_entity("admin", "app.{}".format(name))

    async def init_admin_stats(self):
        # store lock
        self.check_updates_lock = asyncio.Lock()

        # create sensors
        await self.add_entity(self.active_apps_sensor, 0, {"friendly_name": "Active Apps"})
        await self.add_entity(self.inactive_apps_sensor, 0, {"friendly_name": "Inactive Apps"})
        await self.add_entity(self.total_apps_sensor, 0, {"friendly_name": "Total Apps"})

    async def terminate(self):
        self.logger.debug("terminate() called for app_management")
        if self.apps_initialized is True:
            await self.check_app_updates(mode=UpdateMode.TERMINATE)

    async def dump_objects(self):
        self.diag.info("--------------------------------------------------")
        self.diag.info("Objects")
        self.diag.info("--------------------------------------------------")
        for object_ in self.objects.keys():
            self.diag.info("%s: %s", object_, self.objects[object_])
        self.diag.info("--------------------------------------------------")

    async def get_app(self, name: str):
        if name in self.objects:
            return self.objects[name]["object"]

    def get_app_info(self, name: str):
        if name in self.objects:
            return self.objects[name]

    async def get_app_instance(self, name: str, id):
        if name in self.objects and self.objects[name]["id"] == id:
            return self.AD.app_management.objects[name]["object"]

    async def initialize_app(self, name: str):
        if name in self.objects:
            init = getattr(self.objects[name]["object"], "initialize", None)
            if init is None:
                self.logger.warning("Unable to find initialize() function in module %s - skipped", name)
                self.objects[name]["running"] = False
                await self.increase_inactive_apps(name)
                return
        else:
            self.logger.warning("Unable to find module %s - initialize() skipped", name)
            await self.increase_inactive_apps(name)
            if name in self.objects:
                self.objects[name]["running"] = False
            return

        # Call its initialize function
        try:
            await self.set_state(name, state="initializing")
            self.logger.info(f"Calling initialize() for {name}")
            if asyncio.iscoroutinefunction(init):
                await init()
            else:
                await utils.run_in_executor(self, init)
            await self.set_state(name, state="idle")
            await self.increase_active_apps(name)

            event_data = {"event_type": "app_initialized", "data": {"app": name}}

            await self.AD.events.process_event("admin", event_data)

        except TypeError:
            self.AD.threading.report_callback_sig(name, "initialize", init, {})
        except Exception:
            error_logger = logging.getLogger("Error.{}".format(name))
            error_logger.warning("-" * 60)
            error_logger.warning("Unexpected error running initialize() for %s", name)
            error_logger.warning("-" * 60)
            error_logger.warning(traceback.format_exc())
            error_logger.warning("-" * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning("Logged an error to %s", self.AD.logging.get_filename("error_log"))
            await self.set_state(name, state="initialize_error")
            await self.increase_inactive_apps(name)

    async def terminate_app(self, name, delete: bool = True) -> bool:
        term = None
        executed = True
        if name in self.objects and hasattr(self.objects[name]["object"], "terminate"):
            self.logger.info("Calling terminate() for {}".format(name))

            # Call terminate directly rather than via worker thread
            # so we know terminate has completed before we move on
            term = self.objects[name]["object"].terminate

        if term is not None:
            try:
                if asyncio.iscoroutinefunction(term):
                    await term()
                else:
                    await utils.run_in_executor(self, term)

            except TypeError:
                self.AD.threading.report_callback_sig(name, "terminate", term, {})
                executed = False

            except BaseException:
                error_logger = logging.getLogger("Error.{}".format(name))
                error_logger.warning("-" * 60)
                error_logger.warning("Unexpected error running terminate() for %s", name)
                error_logger.warning("-" * 60)
                error_logger.warning(traceback.format_exc())
                error_logger.warning("-" * 60)
                if self.AD.logging.separate_error_log() is True:
                    self.logger.warning(
                        "Logged an error to %s",
                        self.AD.logging.get_filename("error_log"),
                    )

                executed = False

        if delete:
            if name in self.objects:
                del self.objects[name]

            # if name in self.global_module_dependencies:
            #    del self.global_module_dependencies[name]

        else:
            if name in self.objects:
                self.objects[name]["running"] = False

        await self.increase_inactive_apps(name)

        await self.AD.callbacks.clear_callbacks(name)

        self.AD.futures.cancel_futures(name)

        self.AD.services.clear_services(name)

        await self.AD.sched.terminate_app(name)

        await self.set_state(name, state="terminated")
        await self.set_state(name, instancecallbacks=0)

        event_data = {"event_type": "app_terminated", "data": {"app": name}}

        await self.AD.events.process_event("admin", event_data)

        if self.AD.http is not None:
            await self.AD.http.terminate_app(name)

        return executed

    async def start_app(self, app):
        # first we check if running already
        if app in self.objects and self.objects[app]["running"] is True:
            self.logger.warning("Cannot start app %s, as it is already running", app)
            return

        await self.init_object(app)

        if "disable" in self.app_config[app] and self.app_config[app]["disable"] is True:
            pass
        else:
            await self.initialize_app(app)

    async def stop_app(self, app, delete: bool = False) -> bool:
        executed = False
        try:
            if "global" in self.app_config[app] and self.app_config[app]["global"] is True:
                pass
            else:
                self.logger.info("Terminating %s", app)
            executed = await self.terminate_app(app, delete)
        except Exception:
            error_logger = logging.getLogger("Error.{}".format(app))
            error_logger.warning("-" * 60)
            error_logger.warning("Unexpected error terminating app: %s:", app)
            error_logger.warning("-" * 60)
            error_logger.warning(traceback.format_exc())
            error_logger.warning("-" * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning("Logged an error to %s", self.AD.logging.get_filename("error_log"))

        return executed

    async def restart_app(self, app):
        await self.stop_app(app, delete=False)
        await self.start_app(app)

    def get_app_debug_level(self, app):
        if app in self.objects:
            return self.AD.logging.get_level_from_int(self.objects[app]["object"].logger.getEffectiveLevel())
        else:
            return "None"

    async def init_object(self, app_name: str):
        """Instantiates an app by name and stores it in ``self.objects``

        Args:
            app_name (str): Name of the app, as defined in a config file
        """
        app_args = self.app_config[app_name]

        # as it appears in the YAML definition of the app
        module_name = self.app_config[app_name]["module"]
        class_name = self.app_config[app_name]["class"]

        self.logger.info(
            "Loading app %s using class %s from module %s",
            app_name,
            class_name,
            module_name,
        )

        if self.get_file_from_module(module_name) is not None:
            if "pin_thread" in app_args:
                if app_args["pin_thread"] < 0 or app_args["pin_thread"] >= self.AD.threading.total_threads:
                    self.logger.warning(
                        "pin_thread out of range ({}) in app definition for {} - app will be discarded".format(
                            app_args["pin_thread"], app_name
                        )
                    )
                    return
                else:
                    pin = app_args["pin_thread"]

            elif app_name in self.objects and "pin_thread" in self.objects[app_name]:
                pin = self.objects[app_name]["pin_thread"]

            else:
                pin = -1

            # mod_obj = await utils.run_in_executor(self, importlib.import_module, module_name)
            mod_obj = importlib.import_module(module_name)

            app_class = getattr(mod_obj, class_name, None)
            if app_class is None:
                self.logger.warning(
                    "Unable to find class %s in module %s - '%s' is not initialized",
                    app_args["class"],
                    app_args["module"],
                    app_name,
                )
                await self.increase_inactive_apps(app_name)

            else:
                self.objects[app_name] = {
                    "type": "app",
                    "object": app_class(
                        self.AD,
                        app_name,
                        self.AD.logging,
                        app_args,
                        self.AD.config,
                        self.app_config,
                        self.AD.global_vars,
                    ),
                    "id": uuid.uuid4().hex,
                    "pin_app": self.AD.threading.app_should_be_pinned(app_name),
                    "pin_thread": pin,
                    "running": True,
                }

                # load the module path into app entity
                module_path = await utils.run_in_executor(self, os.path.abspath, mod_obj.__file__)
                await self.set_state(app_name, module_path=module_path)

        else:
            self.logger.warning(
                "Unable to find module module %s - '%s' is not loaded",
                app_args["module"],
                app_name,
            )
            await self.increase_inactive_apps(app_name)

    def init_plugin_object(self, name: str, object: object, use_dictionary_unpacking: bool = False) -> None:
        self.objects[name] = {
            "type": "plugin",
            "object": object,
            "id": uuid.uuid4().hex,
            "pin_app": False,
            "pin_thread": -1,
            "running": False,
            "use_dictionary_unpacking": use_dictionary_unpacking,
        }

    def init_sequence_object(self, name, object):
        """Initialize the sequence"""

        self.objects[name] = {
            "type": "sequence",
            "object": object,
            "id": uuid.uuid4().hex,
            "pin_app": False,
            "pin_thread": -1,
            "running": False,
        }

    async def terminate_sequence(self, name: str) -> bool:
        """Terminate the sequence"""

        if name in self.objects:
            del self.objects[name]

        await self.AD.callbacks.clear_callbacks(name)
        self.AD.futures.cancel_futures(name)

        return True

    async def read_config(self) -> Dict[str, Dict[str, Any]]:  # noqa: C901
        """Walks the apps directory and reads all the config files with :func:`~.utils.read_config_file`, which reads individual config files and runs in the :attr:`~.appdaemon.AppDaemon.executor`.

        Returns:
            Dict[str, Dict[str, Any]]: Loaded app configuration
        """
        new_config = None

        for root, subdirs, files in await utils.run_in_executor(self, os.walk, self.AD.app_dir):
            subdirs[:] = [d for d in subdirs if d not in self.AD.exclude_dirs and "." not in d]
            if utils.is_valid_root_path(root):
                previous_configs = []
                for file in files:
                    if self.is_valid_config(file, previous_configs):
                        path = os.path.join(root, file)
                        self.logger.debug("Reading %s", path)
                        config: Dict[str, Dict] = await utils.run_in_executor(self, self.read_config_file, path)
                        valid_apps = {}
                        if type(config).__name__ == "dict":
                            for app in config:
                                if config[app] is not None:
                                    app_valid = True
                                    if app == "global_modules":
                                        self.logger.warning(
                                            "global_modules directive has been deprecated and will be removed"
                                            " in a future release"
                                        )
                                        #
                                        # Check the parameter format for string or list
                                        #
                                        if isinstance(config[app], str):
                                            valid_apps[app] = [config[app]]
                                        elif isinstance(config[app], list):
                                            valid_apps[app] = config[app]
                                        else:
                                            if self.AD.invalid_config_warnings:
                                                self.logger.warning(
                                                    (
                                                        "global_modules should be a list or a string in File"
                                                        " '%s' - ignoring"
                                                    ),
                                                    file,
                                                )
                                    elif app == "sequence":
                                        #
                                        # We don't care what it looks like just pass it through
                                        #
                                        valid_apps[app] = config[app]
                                    elif "." in app:
                                        #
                                        # We ignore any app containing a dot.
                                        #
                                        pass
                                    elif (
                                        isinstance(config[app], dict)
                                        and "class" in config[app]
                                        and "module" in config[app]
                                    ):
                                        valid_apps[app] = config[app]
                                        valid_apps[app]["config_path"] = path
                                    elif (
                                        isinstance(config[app], dict)
                                        and "module" in config[app]
                                        and "global" in config[app]
                                        and config[app]["global"] is True
                                    ):
                                        valid_apps[app] = config[app]
                                        valid_apps[app]["config_path"] = path
                                    else:
                                        app_valid = False
                                        if self.AD.invalid_config_warnings:
                                            self.logger.warning(
                                                "App '%s' missing 'class' or 'module' entry - ignoring",
                                                app,
                                            )

                                    if app_valid is True:
                                        # now add app to the path
                                        if path not in self.app_config_files:
                                            self.app_config_files[path] = []

                                        self.app_config_files[path].append(app)
                        else:
                            if self.AD.invalid_config_warnings:
                                self.logger.warning(
                                    "File '%s' invalid structure - ignoring",
                                    os.path.join(root, file),
                                )

                        if new_config is None:
                            new_config = {}
                        for app in valid_apps:
                            if app == "global_modules":
                                if app in new_config:
                                    new_config[app].extend(valid_apps[app])
                                    continue
                            if app == "sequence":
                                if app in new_config:
                                    new_config[app] = {
                                        **new_config[app],
                                        **valid_apps[app],
                                    }
                                    continue

                            if app in new_config:
                                self.logger.warning(
                                    "File '%s' duplicate app: %s - ignoring",
                                    os.path.join(root, file),
                                    app,
                                )
                            else:
                                new_config[app] = valid_apps[app]

        await self.check_sequence_update(new_config.get("sequence", {}))

        return new_config

    async def check_sequence_update(self, sequence_config):
        if self.app_config.get("sequences", {}) != sequence_config:
            #
            # now remove the old ones no longer needed
            #
            deleted_sequences = []
            for sequence, config in self.app_config.get("sequence", {}).items():
                if sequence not in sequence_config:
                    deleted_sequences.append(sequence)

            if deleted_sequences != []:
                await self.AD.sequences.remove_sequences(deleted_sequences)

            modified_sequences = {}

            #
            # now load up the modified one
            #
            for sequence, config in sequence_config.items():
                if (sequence not in self.app_config.get("sequence", {})) or self.app_config.get("sequence", {}).get(
                    sequence
                ) != sequence_config.get(sequence):
                    # meaning it has been modified
                    modified_sequences[sequence] = config

            if modified_sequences != {}:
                await self.AD.sequences.add_sequences(modified_sequences)

    # Run in executor
    def check_later_app_configs(self, last_latest):
        later_files = {}
        app_config_files = []
        later_files["files"] = []
        later_files["latest"] = last_latest
        later_files["deleted"] = []
        previous_configs = []
        for root, subdirs, files in os.walk(self.AD.app_dir):
            subdirs[:] = [d for d in subdirs if d not in self.AD.exclude_dirs and "." not in d]
            if utils.is_valid_root_path(root):
                for file in files:
                    if self.is_valid_config(file, previous_configs, quiet=True):
                        path = os.path.join(root, file)
                        app_config_files.append(path)
                        ts = os.path.getmtime(path)
                        if ts > last_latest:
                            later_files["files"].append(path)
                        if ts > later_files["latest"]:
                            later_files["latest"] = ts

        for file in self.app_config_files:
            if file not in app_config_files:
                later_files["deleted"].append(file)

        if self.app_config_files != {}:
            for file in app_config_files:
                if file not in self.app_config_files:
                    later_files["files"].append(file)

                    self.app_config_files[file] = []

        # now remove the unused files from the files
        for file in later_files["deleted"]:
            del self.app_config_files[file]

        return later_files

    def is_valid_config(self, file, previous_configs, quiet=False):

        valid_types = [".toml", ".yaml"]

        filename, file_extension = os.path.splitext(file)

        if file_extension not in valid_types:
            return False

        if filename in previous_configs:
            if quiet is False:
                self.logger.warning(f"Duplicate configuration file {file} - ignoring")
                return False

        previous_configs.append(filename)

        return True

    # Run in executor
    def read_config_file(self, file) -> Dict[str, Dict]:
        """Reads a single YAML or TOML file."""
        try:
            return utils.read_config_file(file)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error loading config file: %s", file)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

    # noinspection PyBroadException
    async def check_config(self, silent: bool = False, add_threads: bool = True) -> Optional[AppActions]:  # noqa: C901
        """Wraps :meth:`~AppManagement.read_config`

        Args:
            silent (bool, optional): _description_. Defaults to False.
            add_threads (bool, optional): _description_. Defaults to True.

        Returns:
            AppActions object with information about which apps to initialize and/or terminate
        """
        terminate_apps = {}
        initialize_apps = {}
        total_apps = len(self.app_config)

        try:
            latest = await utils.run_in_executor(self, self.check_later_app_configs, self.app_config_file_modified)
            self.app_config_file_modified = latest["latest"]

            if latest["files"] or latest["deleted"]:
                if silent is False:
                    self.logger.info("Reading config")
                new_config = await self.read_config()
                if new_config is None:
                    if silent is False:
                        self.logger.warning("New config not applied")
                    return

                for file in latest["deleted"]:
                    if silent is False:
                        self.logger.info("%s deleted", file)

                for file in latest["files"]:
                    if silent is False:
                        self.logger.info("%s added or modified", file)

                # Check for changes

                for name in self.app_config:
                    if name in self.non_apps:
                        continue

                    if name in new_config:
                        # first we need to remove thhe config path if it exists
                        config_path = new_config[name].pop("config_path", None)

                        if self.app_config[name] != new_config[name]:
                            # Something changed, clear and reload

                            if silent is False:
                                self.logger.info("App '%s' changed", name)
                            terminate_apps[name] = 1
                            initialize_apps[name] = 1

                        if config_path:
                            config_path = await utils.run_in_executor(self, os.path.abspath, config_path)

                            # now we update the entity
                            await self.set_state(name, config_path=config_path)
                    else:
                        # Section has been deleted, clear it out

                        if silent is False:
                            self.logger.info("App '{}' deleted".format(name))
                        #
                        # Since the entry has been deleted we can't sensibly determine dependencies
                        # So just immediately terminate it
                        #
                        await self.terminate_app(name, delete=True)
                        await self.remove_entity(name)

                for name in new_config:
                    if name in self.non_apps:
                        continue

                    if name not in self.app_config:
                        #
                        # New section added!
                        #

                        if "class" in new_config[name] and "module" in new_config[name]:
                            # first we need to remove thhe config path if it exists
                            config_path = await utils.run_in_executor(
                                self, os.path.abspath, new_config[name].pop("config_path")
                            )

                            self.logger.info("App '%s' added", name)
                            initialize_apps[name] = 1
                            await self.add_entity(
                                name,
                                "loaded",
                                {
                                    "totalcallbacks": 0,
                                    "instancecallbacks": 0,
                                    "args": new_config[name],
                                    "config_path": config_path,
                                },
                            )
                        elif name in self.non_apps:
                            pass
                        else:
                            if self.AD.invalid_config_warnings:
                                if silent is False:
                                    self.logger.warning(
                                        "App '%s' missing 'class' or 'module' entry - ignoring",
                                        name,
                                    )

                self.app_config = new_config
                total_apps = len(self.app_config)

                for name in self.non_apps:
                    if name in self.app_config:
                        total_apps -= 1  # remove one

                active_apps, inactive, glbl = self.get_active_app_count()

                # if silent is False:
                await self.set_state(
                    self.total_apps_sensor,
                    state=active_apps + inactive,
                    attributes={"friendly_name": "Total Apps"},
                )

                self.logger.info("Found %s active apps", active_apps)
                self.logger.info("Found %s inactive apps", inactive)
                self.logger.info("Found %s global libraries", glbl)

            # Now we know if we have any new apps we can create new threads if pinning

            active_apps, inactive, glbl = self.get_active_app_count()

            if add_threads is True and self.AD.threading.auto_pin is True:
                if active_apps > self.AD.threading.thread_count:
                    for i in range(active_apps - self.AD.threading.thread_count):
                        await self.AD.threading.add_thread(False, True)

            return AppActions(init=initialize_apps, term=terminate_apps, total=total_apps, active=active_apps)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error:")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

    def get_active_app_count(self):
        active = 0
        inactive = 0
        glbl = 0
        for name in self.app_config:
            if "disable" in self.app_config[name] and self.app_config[name]["disable"] is True:
                inactive += 1
            elif "global" in self.app_config[name] and self.app_config[name]["global"] is True:
                glbl += 1
            elif name in self.non_apps:
                pass
            else:
                active += 1
        return active, inactive, glbl

    def get_app_from_file(self, file):
        """Finds the apps that depend on a given file"""
        module_name = self.get_module_from_path(file)
        for app_name, cfg in self.app_config.items():
            if "module" in cfg and cfg["module"].startswith(module_name):
                return app_name
        return None

    # noinspection PyBroadException
    # Run in executor
    def read_app(self, reload_cfg: ModuleLoad):
        """Reads an app into memory by importing or reloading the module it needs"""
        module_name = reload_cfg.name

        if reload_cfg.reload:
            try:
                module = self.modules[module_name]
            except KeyError:
                if module_name not in sys.modules:
                    # Probably failed to compile on initial load
                    # so we need to re-import not reload
                    reload_cfg.reload = False
                    self.read_app(reload_cfg)
                else:
                    # A real KeyError!
                    raise
            else:
                self.logger.info("Recursively reloading module: %s", module.__name__)
                utils.recursive_reload(module)
        else:
            app = self.get_app_from_file(module_name)
            if app is not None:
                if "global" in self.app_config[app] and self.app_config[app]["global"] is True:
                    # It's a new style global module
                    self.logger.info("Loading Global Module: %s", module_name)
                    self.modules[module_name] = importlib.import_module(module_name)
                else:
                    # A regular app
                    self.logger.info("Loading App Module: %s", module_name)
                    if module_name not in self.modules:
                        self.modules[module_name] = importlib.import_module(module_name)
                    else:
                        # We previously imported it so we need to reload to pick up any potential changes
                        importlib.reload(self.modules[module_name])
            elif "global_modules" in self.app_config and module_name in self.app_config["global_modules"]:
                self.logger.info("Loading Global Module: %s", module_name)
                self.modules[module_name] = importlib.import_module(module_name)
            else:
                if self.AD.missing_app_warnings:
                    self.logger.warning("No app description found for: %s - ignoring", module_name)

    @staticmethod
    def get_module_from_path(path):
        return Path(path).stem

    def get_file_from_module(self, module_name: str) -> Optional[Path]:
        """Gets the module __file__ based on the module name.

        Args:
            mod (str): Module name

        Returns:
            Optional[Path]: Path of the __file__
        """
        module_name = module_name.split(".")[0]
        try:
            module_obj = self.modules[module_name]
        except KeyError:
            self.logger.warning("No file for module: %s", module_name)
            return None
        else:
            module_path = Path(module_obj.__file__)
            if self.monitored_files and all(isinstance(f, Path) for f in self.monitored_files):
                assert module_path in self.monitored_files, f"{module_path} is not being monitored"
            return module_path

    def get_path_from_app(self, app_name: str) -> Path:
        """Gets the module path based on the app_name

        Used in self._terminate_apps
        """
        module_name = self.app_config[app_name]["module"]
        return self.get_file_from_module(module_name)

    # Run in executor
    def process_filters(self):
        if "filters" in self.AD.config:
            for filter in self.AD.config["filters"]:
                for root, subdirs, files in os.walk(self.AD.app_dir, topdown=True):
                    # print(root, subdirs, files)
                    #
                    # Prune dir list
                    #
                    subdirs[:] = [d for d in subdirs if d not in self.AD.exclude_dirs and "." not in d]

                    ext = filter["input_ext"]
                    extlen = len(ext) * -1

                    for file in files:
                        run = False
                        if file[extlen:] == ext:
                            infile = os.path.join(root, file)
                            modified = os.path.getmtime(infile)
                            if infile in self.filter_files:
                                if self.filter_files[infile] < modified:
                                    run = True
                            else:
                                self.logger.info("Found new filter file %s", infile)
                                run = True

                            if run is True:
                                self.logger.info("Running filter on %s", infile)
                                self.filter_files[infile] = modified

                                # Run the filter

                                outfile = utils.rreplace(infile, ext, filter["output_ext"], 1)
                                command_line = filter["command_line"].replace("$1", infile)
                                command_line = command_line.replace("$2", outfile)
                                try:
                                    subprocess.Popen(command_line, shell=True)
                                except Exception:
                                    self.logger.warning("-" * 60)
                                    self.logger.warning("Unexpected running filter on: %s:", infile)
                                    self.logger.warning("-" * 60)
                                    self.logger.warning(traceback.format_exc())
                                    self.logger.warning("-" * 60)

    @staticmethod
    def check_file(file: str):
        with open(file, "r"):
            pass

    def add_to_import_path(self, path: Union[str, Path]):
        path = str(path)
        self.logger.info("Adding directory to import path: %s", path)
        sys.path.insert(0, path)
        self.module_dirs.append(path)

    # @_timeit
    async def check_app_updates(self, plugin: str = None, mode: UpdateMode = UpdateMode.NORMAL):  # noqa: C901
        """Checks the states of the Python files that define the apps, reloading when necessary.

        Called as part of :meth:`.utility_loop.Utility.loop`

        Args:
            plugin (str, optional): Plugin to restart, if necessary. Defaults to None.
            mode (UpdateMode, optional): Defaults to UpdateMode.NORMAL.

        Check Process:
            - Refresh modified times of monitored files.
            - Checks for deleted files
            - Marks the apps for reloading or removal as necessary
            - Restarts the plugin, if specified
            - Terminates apps as necessary
            - Loads or reloads modules/pacakges as necessary
            - Loads apps from the modules/packages
        """
        async with self.check_updates_lock:
            if self.AD.apps is False:
                return

            # Lets add some profiling
            pr = None
            if self.AD.check_app_updates_profile is True:
                pr = cProfile.Profile()
                pr.enable()

            # Process filters
            await utils.run_in_executor(self, self.process_filters)

            if mode == UpdateMode.INIT:
                await self._init_update_mode()

            modules: List[ModuleLoad] = []
            await self._refresh_monitored_files(modules)

            # Refresh app config
            apps = await self.check_config()

            await self._check_for_deleted_modules(mode, apps)

            self._add_reload_apps(apps, modules)

            await self._restart_plugin(plugin, apps)

            apps_terminated = await self._terminate_apps(mode, apps, modules)

            await self._load_reload_modules(apps, modules)

            if mode == UpdateMode.INIT and self.AD.import_method == "expert":
                self.logger.info(f"Loaded modules: {self.modules}")

            await self._load_apps(mode, apps, apps_terminated)

            if self.AD.check_app_updates_profile is True:
                pr.disable()

            s = io.StringIO()
            sortby = "cumulative"
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            self.check_app_updates_profile_stats = s.getvalue()

            self.apps_initialized = True

    async def _init_update_mode(self):
        """Process one time static path additions"""
        self.logger.info("Initializing import method: %s", self.AD.import_method)
        if self.AD.import_method == "expert":
            python_file_parents = set(f.parent.resolve() for f in Path(self.AD.app_dir).rglob("*.py"))
            module_parents = set(p for p in python_file_parents if not (p / "__init__.py").exists())

            package_dirs = set(p for p in python_file_parents if (p / "__init__.py").exists())
            top_packages_dirs = set(p for p in package_dirs if not (p.parent / "__init__.py").exists())
            package_parents = set(p.parent for p in top_packages_dirs)

            import_dirs = module_parents | package_parents

            for path in sorted(import_dirs):
                self.add_to_import_path(path)

            # keeps track of which modules go to which packages
            self.mod_pkg_map: Dict[Path, str] = {
                module_file: dir.stem for dir in top_packages_dirs for module_file in dir.rglob("*.py")
            }

        # Add any aditional import paths
        for path in self.AD.import_paths:
            if os.path.isdir(path):
                self.add_to_import_path(path)
            else:
                self.logger.warning(f"import_path {path} does not exist - not adding to path")

    def get_python_files(self) -> List[Path]:
        return [
            f
            for f in Path(self.AD.app_dir).resolve().rglob("*.py")
            # Prune dir list
            if f.parent.name not in self.AD.exclude_dirs and "." not in f.parent.name
        ]

    def module_path_from_file(self, file: Path):
        assert file in self.mod_pkg_map
        pkg_name = self.mod_pkg_map[file]
        module_obj = self.modules[pkg_name]
        module_path = Path(module_obj.__file__)
        return module_path

    async def _refresh_monitored_files(self, modules: List[ModuleLoad]):
        """Refreshes the modified times of the monitored files. Part of self.check_app_updates sequence

        - Refreshes attributes
            - self.monitored_files
            - self.module_dirs
        """
        if self.AD.import_method == "normal":
            found_files: List[str] = []
            for root, subdirs, files in await utils.run_in_executor(self, os.walk, self.AD.app_dir, topdown=True):
                # Prune dir list
                subdirs[:] = [d for d in subdirs if d not in self.AD.exclude_dirs and "." not in d]

                if utils.is_valid_root_path(root):
                    if root not in self.module_dirs:
                        self.logger.info("Adding %s to module import path", root)
                        sys.path.insert(0, root)
                        self.module_dirs.append(root)

                for file in files:
                    if file[-3:] == ".py" and file[0] != ".":
                        found_files.append(os.path.join(root, file))

            for file in found_files:
                if file == os.path.join(self.AD.app_dir, "__init__.py"):
                    continue
                try:
                    # check we can actually open the file
                    await utils.run_in_executor(self, self.check_file, file)

                    modified = await utils.run_in_executor(self, os.path.getmtime, file)

                    if file in self.monitored_files:
                        if self.monitored_files[file] < modified:
                            modules.append(ModuleLoad(path=file, reload=True))
                            self.monitored_files[file] = modified
                    else:
                        self.logger.debug("Found module %s", file)
                        modules.append(ModuleLoad(path=file, reload=False))
                        self.monitored_files[file] = modified
                except IOError as err:
                    self.logger.warning("Unable to read app %s: %s - skipping", file, err)

        elif self.AD.import_method == "expert":
            found_files: List[Path] = await utils.run_in_executor(self, self.get_python_files)
            for file in found_files:
                # check we can actually open the file
                try:
                    await utils.run_in_executor(self, self.check_file, file)
                except IOError as err:
                    self.logger.warning("Unable to read app %s: %s - skipping", file, err)

                # file was readable during the check
                else:
                    modified = await utils.run_in_executor(self, os.path.getmtime, file)

                    file: Path
                    # if the file is being monitored
                    if file in self.monitored_files:
                        # if the monitored file has been modified
                        if self.monitored_files[file] < modified:
                            # update the modified time
                            self.monitored_files[file] = modified
                            # if the file is associated with a package
                            if file in self.mod_pkg_map:
                                modules.append(ModuleLoad(path=self.module_path_from_file(file), reload=True))
                            else:
                                modules.append(ModuleLoad(path=file, reload=True))
                    else:
                        # start monitoring
                        self.monitored_files[file] = modified

                        # if it's not part of a package, add a module load config for it
                        if not file.with_name("__init__.py").exists():
                            self.logger.info("Found module %s", file)
                            modules.append(ModuleLoad(path=file, reload=False))
                        else:
                            pkg_name: str = self.mod_pkg_map[file]
                            names = [mod.name for mod in modules]
                            if pkg_name not in names:
                                modules.append(ModuleLoad(path=pkg_name, reload=False))

    async def _check_for_deleted_modules(self, mode: UpdateMode, apps: AppActions):
        """Check for deleted modules and add them to the terminate list in the apps dict. Part of self.check_app_updates sequence"""
        deleted_modules = []

        for file in list(self.monitored_files.keys()):
            if not Path(file).exists() or mode == UpdateMode.TERMINATE:
                self.logger.info("Removing module %s", file)
                del self.monitored_files[file]
                for app in self.apps_per_module(self.get_module_from_path(file)):
                    apps.term[app] = 1

                deleted_modules.append(file)

        return deleted_modules

    def _add_reload_apps(self, apps: AppActions, modules: List[ModuleLoad]):
        """Add any apps we need to reload because of file changes. Part of self.check_app_updates sequence

        If the module an app is based on will be reloaded, the app will need to be terminated first and
        re-initialized afterwards.
        """
        for module in modules:
            app_names = self.apps_per_module(module.name)
            self.logger.info("%s apps come from %s", len(app_names), module.name)
            for app in app_names:
                apps.mark_app_for_initialization(app)
                if module.reload:
                    apps.mark_app_for_termination(app)

            for gm in self.get_global_modules():
                if gm == self.get_module_from_path(module.name):
                    for app in self.apps_per_global_module(gm):
                        apps.mark_app_for_initialization(app)
                        if module.reload:
                            apps.mark_app_for_termination(app)

    async def _restart_plugin(self, plugin, apps: AppActions):
        if plugin is not None:
            self.logger.info("Processing restart for %s", plugin)
            # This is a restart of one of the plugins so check which apps need to be restarted
            for app in self.app_config:
                reload = False
                if app in self.non_apps:
                    continue
                if "plugin" in self.app_config[app]:
                    for this_plugin in utils.single_or_list(self.app_config[app]["plugin"]):
                        if this_plugin == plugin:
                            # We got a match so do the reload
                            reload = True
                            break
                        elif plugin == "__ALL__":
                            reload = True
                            break
                else:
                    # No plugin dependency specified, reload to error on the side of caution
                    reload = True

                if reload is True:
                    apps.mark_app_for_termination(app)
                    apps.mark_app_for_initialization(app)

    async def _terminate_apps(self, mode: UpdateMode, apps: AppActions, modules: List[ModuleLoad]) -> Dict[str, bool]:
        """Terminate apps. Part of self.check_app_updates sequence"""
        apps_terminated: Dict[str, bool] = {}  # stores properly terminated apps
        if apps is not None and apps.term:
            prio_apps = self.get_app_deps_and_prios(apps.term, mode)

            # Mark dependant global modules for reload
            for app_name in sorted(prio_apps, key=prio_apps.get):
                app_path = self.get_path_from_app(app_name)

                # If it's already in the list, set it to reload
                for module in modules:
                    if module.path == app_path:
                        module.reload = True
                        break

                # Otherwise, append a reload for that path
                else:
                    if app_path is not None:
                        modules.append(ModuleLoad(path=app_path, reload=True))

            # Terminate Apps
            for app in sorted(prio_apps, key=prio_apps.get, reverse=True):
                executed = await self.stop_app(app)
                apps_terminated[app] = executed

        return apps_terminated

    async def _load_reload_modules(self, apps: AppActions, modules: List[ModuleLoad]):
        """Calls self.read_app for each module in the list"""
        for mod in modules:
            try:
                await utils.run_in_executor(self, self.read_app, mod)
            except Exception:
                self.error.warning("-" * 60)
                self.error.warning("Unexpected error loading module: %s:", mod.name)
                self.error.warning("-" * 60)
                self.error.warning(traceback.format_exc())
                self.error.warning("-" * 60)
                if self.AD.logging.separate_error_log() is True:
                    self.logger.warning("Unexpected error loading module: %s:", mod.name)

                self.logger.warning("Removing associated apps:")
                module = self.get_module_from_path(mod.name)
                for app in self.app_config:
                    if "module" in self.app_config[app] and self.app_config[app]["module"] == module:
                        if apps.init and app in apps.init:
                            del apps.init[app]
                            self.logger.warning("%s", app)
                            await self.set_state(app, state="compile_error")

    async def _load_apps(self, mode: UpdateMode, apps: AppActions, apps_terminated: Dict[str, bool]):
        """Loads apps from imported modules/packages. Part of self.check_app_updates sequence"""
        if apps is not None and apps.init:
            self.logger.info(f"{len(apps.init)} apps to initialize")
            prio_apps = self.get_app_deps_and_prios(apps.init, mode)

            # Load Apps

            for app in sorted(prio_apps, key=prio_apps.get):
                try:
                    if "disable" in self.app_config[app] and self.app_config[app]["disable"] is True:
                        self.logger.info("%s is disabled", app)
                        await self.set_state(app, state="disabled")
                        await self.increase_inactive_apps(app)
                    elif "global" in self.app_config[app] and self.app_config[app]["global"] is True:
                        await self.set_state(app, state="global")
                        await self.increase_inactive_apps(app)
                    else:
                        if apps_terminated.get(app, True) is True:  # the app terminated properly
                            await self.init_object(app)

                        else:
                            self.logger.warning("Cannot initialize app %s, as it didn't terminate properly", app)

                except Exception:
                    error_logger = logging.getLogger("Error.{}".format(app))
                    error_logger.warning("-" * 60)
                    error_logger.warning("Unexpected error initializing app: %s:", app)
                    error_logger.warning("-" * 60)
                    error_logger.warning(traceback.format_exc())
                    error_logger.warning("-" * 60)
                    if self.AD.logging.separate_error_log() is True:
                        self.logger.warning(
                            "Logged an error to %s",
                            self.AD.logging.get_filename("error_log"),
                        )

            await self.AD.threading.calculate_pin_threads()

            # Call initialize() for apps

            for app in sorted(prio_apps, key=prio_apps.get):
                if "disable" in self.app_config[app] and self.app_config[app]["disable"] is True:
                    pass
                elif "global" in self.app_config[app] and self.app_config[app]["global"] is True:
                    pass
                else:
                    if apps_terminated.get(app, True) is True:  # the app terminated properly
                        await self.initialize_app(app)

                    else:
                        self.logger.debug("Cannot initialize app %s, as it didn't terminate properly", app)

    def get_app_deps_and_prios(self, applist: Iterable[str], mode: UpdateMode) -> Dict[str, float]:
        """Gets the dependencies and priorities for the given apps

        Args:
            applist (Iterable[str]): Iterable of app names
            mode (UpdateMode): UpdateMode

        Returns:
            _type_: _description_
        """
        # Build a list of modules and their dependencies
        deplist = []
        for app_name in applist:
            if app_name not in deplist:
                deplist.append(app_name)
            self.get_dependent_apps(app_name, deplist)

        # Need to give the topological sort a full list of apps or it will fail
        full_list = list(self.app_config.keys())

        deps = []

        for app_name in full_list:
            dependees = []
            for dep in self.get_app_dependencies(app_name):
                if dep in self.app_config:
                    dependees.append(dep)
                else:
                    self.logger.warning("Unable to find app %s in dependencies for %s", dep, app_name)
                    self.logger.warning("Ignoring app %s", app_name)
            deps.append((app_name, dependees))

        prio_apps = {}
        prio = float(50.1)
        try:
            for app_name in self.topological_sort(deps):
                if (
                    "dependencies" in self.app_config[app_name]
                    or app_name in self.global_module_dependencies
                    or self.app_has_dependents(app_name)
                ):
                    prio_apps[app_name] = prio
                    prio += float(0.0001)
                else:
                    if mode == UpdateMode.INIT and "priority" in self.app_config[app_name]:
                        prio_apps[app_name] = float(self.app_config[app_name]["priority"])
                    else:
                        prio_apps[app_name] = float(50)
        except ValueError:
            pass

        # now we remove the ones we aren't interested in

        final_apps = {}
        for app_name in prio_apps:
            if app_name in deplist:
                final_apps[app_name] = prio_apps[app_name]

        return final_apps

    def app_has_dependents(self, name):
        for app in self.app_config:
            for dep in self.get_app_dependencies(app):
                if dep == name:
                    return True
        return False

    def get_dependent_apps(self, dependee, deps):
        for app in self.app_config:
            for dep in self.get_app_dependencies(app):
                # print("app= {} dep = {}, dependee = {} deps = {}".format(app, dep, dependee, deps))
                if dep == dependee and app not in deps:
                    deps.append(app)
                    new_deps = self.get_dependent_apps(app, deps)
                    if new_deps is not None:
                        deps.append(new_deps)

    def topological_sort(self, source):
        pending = [(name, set(deps)) for name, deps in source]  # copy deps so we can modify set in-place
        emitted = []
        while pending:
            next_pending = []
            next_emitted = []
            for entry in pending:
                name, deps = entry
                deps.difference_update(emitted)  # remove deps we emitted last pass
                if deps:  # still has deps? recheck during next pass
                    next_pending.append(entry)
                else:  # no more deps? time to emit
                    yield name
                    emitted.append(name)  # <-- not required, but helps preserve original ordering
                    next_emitted.append(name)  # remember what we emitted for difference_update() in next pass
            if not next_emitted:
                # all entries have unmet deps, we have cyclic redundancies
                # since we already know all deps are correct
                self.logger.warning("Cyclic or missing app dependencies detected")
                for pend in next_pending:
                    deps = ""
                    for dep in pend[1]:
                        deps += "{} ".format(dep)
                    self.logger.warning("%s depends on %s", pend[0], deps)
                raise ValueError("cyclic dependency detected")
            pending = next_pending
            emitted = next_emitted

    def apps_per_module(self, module_name: str):
        """Finds which apps came from a given module name"""
        return [
            app_name
            for app_name, app_cfg in self.app_config.items()
            if app_name not in self.non_apps and app_cfg["module"].split(".")[0] == module_name
        ]

    def apps_per_global_module(self, module):
        apps = []
        for app in self.app_config:
            if "global_dependencies" in self.app_config[app]:
                for gm in utils.single_or_list(self.app_config[app]["global_dependencies"]):
                    if gm == module:
                        apps.append(app)

            if "dependencies" in self.app_config[app]:
                for gm in utils.single_or_list(self.app_config[app]["dependencies"]):
                    if gm == module:
                        apps.append(app)

        return apps

    def get_app_dependencies(self, app):
        deps = []
        if "dependencies" in self.app_config[app]:
            for dep in utils.single_or_list(self.app_config[app]["dependencies"]):
                deps.append(dep)

        if app in self.global_module_dependencies:
            for dep in self.global_module_dependencies[app]:
                deps.append(dep)

        return deps

    def create_app(self, app=None, **kwargs):
        """Used to create an app, which is written to a config file"""

        executed = True
        app_file = kwargs.pop("app_file", None)
        app_directory = kwargs.pop("app_dir", None)
        app_config = {}
        new_config = OrderedDict()

        app_module = kwargs.get("module")
        app_class = kwargs.get("class")

        if app is None:  # app name not given
            # use the module name as the app's name
            app = app_module

            app_config[app] = kwargs

        else:
            if app_module is None and app in kwargs:
                app_module = kwargs[app].get("module")
                app_class = kwargs[app].get("class")

                app_config[app] = kwargs[app]

            else:
                app_config[app] = kwargs

        if app_module is None or app_class is None:
            self.logger.error("Could not create app %s, as module and class is required", app)
            return False

        if app_directory is None:
            app_directory = os.path.join(self.AD.app_dir, "ad_apps")

        else:
            app_directory = os.path.join(self.AD.app_dir, app_directory)

        if app_file is None:
            app_file = os.path.join(app_directory, f"{app}{self.ext}")
            self.logger.info("Creating app using filename %s", app_file)

        else:
            if app_file[-5:] != self.ext:
                app_file = f"{app_file}{self.ext}"

            app_file = os.path.join(app_directory, app_file)

            # in case the given app_file is multi level
            filename = app_file.split("/")[-1]
            app_directory = app_file.replace(f"/{filename}", "")

        if os.path.isfile(app_file):
            # the file exists so there might be apps there already so read to update
            # now open the file and edit the yaml
            new_config.update(self.read_config_file(app_file))

        elif not os.path.isdir(app_directory):
            self.logger.info("The given app filename %s doesn't exist, will be creating it", app_file)
            # now create the directory
            try:
                os.makedirs(app_directory)
            except Exception:
                self.logger.error("Could not create directory %s", app_directory)
                return False

        # now load up the new config
        new_config.update(app_config)
        new_config.move_to_end(app)

        # at this point now to create write to file
        try:
            utils.write_config_file(app_file, **new_config)

            data = {
                "event_type": "app_created",
                "data": {"app": app, **app_config[app]},
            }
            self.AD.loop.create_task(self.AD.events.process_event("admin", data))

        except Exception:
            self.error.warning("-" * 60)
            self.error.warning("Unexpected error while writing to file: %s", app_file)
            self.error.warning("-" * 60)
            self.error.warning(traceback.format_exc())
            self.error.warning("-" * 60)
            executed = False

        return executed

    def edit_app(self, app, **kwargs):
        """Used to edit an app, which is already in Yaml. It is expecting the app's name"""

        executed = True
        app_config = copy.deepcopy(self.app_config[app])
        new_config = OrderedDict()

        # now update the app config
        app_config.update(kwargs)

        # now get the app's file
        app_file = self.get_app_file(app)
        if app_file is None:
            self.logger.warning("Unable to find app %s's file. Cannot edit the app", app)
            return False

        # now open the file and edit the yaml
        new_config.update(self.read_config_file(app_file))

        # now load up the new config
        new_config[app].update(app_config)

        # now update the file with the new data
        try:
            utils.write_config_file(app_file, **new_config)

            data = {
                "event_type": "app_edited",
                "data": {"app": app, **app_config},
            }
            self.AD.loop.create_task(self.AD.events.process_event("admin", data))

        except Exception:
            self.error.warning("-" * 60)
            self.error.warning("Unexpected error while writing to file: %s", app_file)
            self.error.warning("-" * 60)
            self.error.warning(traceback.format_exc())
            self.error.warning("-" * 60)
            executed = False

        return executed

    def remove_app(self, app, **kwargs):
        """Used to remove an app

        Seems to be unreferenced?
        """

        result = None
        # now get the app's file
        app_file = self.get_app_file(app)
        if app_file is None:
            self.logger.warning("Unable to find app %s's file. Cannot remove the app", app)
            return False

        # now open the file and edit the yaml
        file_config = self.read_config_file(app_file)

        # now now delete the app's config
        result = file_config.pop(app)

        # now update the file with the new data
        try:
            if len(file_config) == 0:  # meaning no more apps in file
                # delete it
                os.remove(app_file)

            else:
                utils.write_config_file(app_file, **file_config)

            data = {
                "event_type": "app_removed",
                "data": {"app": app},
            }
            self.AD.loop.create_task(self.AD.events.process_event("admin", data))

        except Exception:
            self.error.warning("-" * 60)
            self.error.warning("Unexpected error while writing to file: %s", app_file)
            self.error.warning("-" * 60)
            self.error.warning(traceback.format_exc())
            self.error.warning("-" * 60)

        return result

    def get_app_file(self, app):
        """Used to get the file an app is located"""

        app_file = utils.run_coroutine_threadsafe(self, self.get_state(app, attribute="config_path"))
        return app_file

    async def register_module_dependency(self, name, *modules):
        for module in modules:
            module_name = None
            if isinstance(module, str):
                module_name = module
            elif isinstance(module, object) and module.__class__.__name__ == "module":
                module_name = module.__name__

            if module_name is not None:
                if (
                    "global_modules" in self.app_config and module_name in self.app_config["global_modules"]
                ) or self.is_global_module(module_name):
                    if name not in self.global_module_dependencies:
                        self.global_module_dependencies[name] = []

                    if module_name not in self.global_module_dependencies[name]:
                        self.global_module_dependencies[name].append(module_name)
                else:
                    self.logger.warning(
                        "Module %s not a global_modules in register_module_dependency() for %s",
                        module_name,
                        name,
                    )

    def get_global_modules(self):
        gms = []
        if "global_modules" in self.app_config:
            for gm in utils.single_or_list(self.app_config["global_modules"]):
                gms.append(gm)

        for app in self.app_config:
            if "global" in self.app_config[app] and self.app_config[app]["global"] is True:
                gms.append(self.app_config[app]["module"])

        return gms

    def is_global_module(self, module):
        return module in self.get_global_modules()

    async def manage_services(self, namespace, domain, service, kwargs):
        app = kwargs.pop("app", None)
        __name = kwargs.pop("__name", None)

        if service in ["reload", "create"]:
            pass

        elif app is None:
            self.logger.warning("App not specified when calling '%s' service from %s. Specify App", service, __name)
            return None

        if service not in ["reload", "create"] and app not in self.app_config:
            self.logger.warning("Specified App '%s' is not a valid App from %s", app, __name)
            return None

        if service == "start":
            asyncio.ensure_future(self.start_app(app))

        elif service == "stop":
            asyncio.ensure_future(self.stop_app(app, delete=False))

        elif service == "restart":
            asyncio.ensure_future(self.restart_app(app))

        elif service == "reload":
            asyncio.ensure_future(self.check_app_updates(mode=UpdateMode.INIT))

        elif service in ["create", "edit", "remove", "enable", "disable"]:
            # first the check app updates needs to be stopped if on
            mode = copy.deepcopy(self.AD.production_mode)

            if mode is False:  # it was off
                self.AD.production_mode = True
                await asyncio.sleep(0.5)

            if service == "enable":
                result = await utils.run_in_executor(self, self.edit_app, app, disable=False)

            elif service == "disable":
                result = await utils.run_in_executor(self, self.edit_app, app, disable=True)

            else:
                func = getattr(self, f"{service}_app")
                result = await utils.run_in_executor(self, func, app, **kwargs)

            if mode is False:  # meaning it was not in production mode
                await asyncio.sleep(1)
                self.AD.production_mode = mode

            return result

        return None

    async def increase_active_apps(self, name: str):
        if name not in self.active_apps:
            self.active_apps.append(name)

        if name in self.inactive_apps:
            self.inactive_apps.remove(name)

        active_apps = len(self.active_apps)
        inactive_apps = len(self.inactive_apps)

        await self.set_state(self.active_apps_sensor, state=active_apps)
        await self.set_state(self.inactive_apps_sensor, state=inactive_apps)

    async def increase_inactive_apps(self, name: str):
        if name not in self.inactive_apps:
            self.inactive_apps.append(name)

        if name in self.active_apps:
            self.active_apps.remove(name)

        inactive_apps = len(self.inactive_apps)
        active_apps = len(self.active_apps)

        await self.set_state(self.active_apps_sensor, state=active_apps)
        await self.set_state(self.inactive_apps_sensor, state=inactive_apps)
