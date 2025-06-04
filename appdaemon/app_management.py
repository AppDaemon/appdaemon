import asyncio
import cProfile
import importlib
import inspect
import io
import logging
import os
import pstats
import subprocess
import sys
import traceback
from collections import OrderedDict
from collections.abc import AsyncGenerator, Iterable
from copy import copy
from functools import partial, reduce, wraps
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from pydantic import ValidationError

from appdaemon.dependency import DependencyResolutionFail, get_full_module_name
from appdaemon.dependency_manager import DependencyManager
from appdaemon.models.config import AllAppConfig, AppConfig, GlobalModule
from appdaemon.models.config.app import SequenceConfig
from appdaemon.models.internal.file_check import FileCheck

from . import exceptions as ade
from . import utils
from .models.internal.app_management import LoadingActions, ManagedObject, UpdateActions, UpdateMode

if TYPE_CHECKING:
    from .appdaemon import AppDaemon
    from .plugin_management import PluginBase

T = TypeVar("T")


class AppManagement:
    """Subsystem container for managing app lifecycles"""

    AD: "AppDaemon"
    """Reference to the top-level AppDaemon container object
    """
    ext: Literal[".yaml", ".toml"]
    logger: Logger
    """Standard python logger named ``AppDaemon._app_management``
    """
    name: str = "_app_management"
    error: Logger
    """Standard python logger named ``Error``
    """
    filter_files: dict[str, float]
    """Dictionary of the modified times of the filter files and their paths.
    """
    objects: dict[str, ManagedObject]
    """Dictionary of dictionaries with the instantiated apps, plugins, and sequences along with some metadata. Gets populated by

    - ``self.init_object``, which instantiates the app classes
    - ``self.init_plugin_object``
    - ``self.init_sequence_object``
    """
    active_apps: set[str]
    inactive_apps: set[str]
    non_apps: set[str] = {"global_modules", "sequence"}
    check_app_updates_profile_stats: str = ""
    check_updates_lock: asyncio.Lock = asyncio.Lock()

    dependency_manager: DependencyManager

    reversed_graph: dict[str, set[str]] = {}
    """Dictionary that maps full module names to sets of those that depend on them
    """

    app_config: AllAppConfig
    """Keeps track of which module and class each app comes from, along with any associated global modules. Gets set at the end of :meth:`~appdaemon.app_management.AppManagement.check_config`.
    """

    active_apps_sensor: str = "sensor.active_apps"
    inactive_apps_sensor: str = "sensor.inactive_apps"
    total_apps_sensor: str = "sensor.total_apps"

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.ext = self.AD.config.ext
        self.logger = ad.logging.get_child(self.name)
        self.error = ad.logging.get_error()
        self.diag = ad.logging.get_diag()
        self.filter_files = {}
        self.objects = {}

        # Add Path for adbase
        sys.path.insert(0, os.path.dirname(__file__))

        #
        # Register App Services
        #
        register = partial(
            self.AD.services.register_service,
            namespace="admin",
            domain="app",
            callback=self.manage_services
        )
        services = {
            "start", "stop", "restart", "disable",
            "enable", "reload", "create", "edit", "remove"
        }
        for service in services:
            register(service=service)

        self.mtimes_python = FileCheck()

        self.active_apps = set()
        self.inactive_apps = set()

        # Apply the profiler_decorator if the config option is enabled
        if self.AD.check_app_updates_profile:
            self.check_app_updates = self.profiler_decorator(self.check_app_updates)

    @property
    def config_filecheck(self) -> FileCheck:
        """Property that aliases the ``FileCheck`` instance for the app config files"""
        return self.dependency_manager.app_deps.files

    @property
    def python_filecheck(self) -> FileCheck:
        """Property that aliases the ``FileCheck`` instance for the app python files"""
        return self.dependency_manager.python_deps.files

    @property
    def module_dependencies(self) -> dict[str, set[str]]:
        return self.dependency_manager.python_deps.dep_graph

    @property
    def app_config(self) -> AllAppConfig:
        return self.dependency_manager.app_deps.app_config

    @property
    def running_apps(self) -> set[str]:
        return set(app_name for app_name, mo in self.objects.items() if mo.running)

    def is_app_running(self, app_name: str) -> bool:
        return (mo := self.objects.get(app_name, False)) and mo.running

    @property
    def loaded_globals(self) -> set[str]:
        return set(
            g
            for g, cfg in self.app_config.root.items()
            if isinstance(cfg, GlobalModule) and cfg.module_name in sys.modules
        )

    @property
    def sequence_config(self) -> SequenceConfig | None:
        return self.app_config.root.get('sequence')

    @property
    def valid_apps(self) -> set[str]:
        return self.running_apps | self.loaded_globals

    async def set_state(self, name: str, **kwargs):
        # not a fully qualified entity name
        if not name.startswith("sensor."):
            entity_id = f"app.{name}"
        else:
            entity_id = name

        await self.AD.state.set_state("_app_management", "admin", entity_id, _silent=True, **kwargs)

    async def get_state(self, name: str, **kwargs):
        # not a fully qualified entity name
        if name.find(".") == -1:
            entity_id = f"app.{name}"
        else:
            entity_id = name

        return await self.AD.state.get_state("_app_management", "admin", entity_id, **kwargs)

    async def add_entity(self, name: str, state, attributes):
        # not a fully qualified entity name
        if "." not in name:
            entity_id = f"app.{name}"
        else:
            entity_id = name

        await self.AD.state.add_entity("admin", entity_id, state, attributes)

    async def remove_entity(self, name: str):
        await self.AD.state.remove_entity("admin", f"app.{name}")

    def app_rel_path(self, app_name: str) -> Path:
        return self.app_config.root[app_name].config_path.relative_to(self.AD.app_dir.parent)

    def err_app_path(self, app_obj: object) -> Path:
        module_path = Path(sys.modules[app_obj.__module__].__file__)
        if module_path.is_relative_to(self.AD.app_dir.parent):
            return module_path.relative_to(self.AD.app_dir.parent)
        return module_path

    async def init_admin_stats(self):
        # create sensors
        await self.add_entity(self.active_apps_sensor, 0, {"friendly_name": "Active Apps"})
        await self.add_entity(self.inactive_apps_sensor, 0, {"friendly_name": "Inactive Apps"})
        await self.add_entity(self.total_apps_sensor, 0, {"friendly_name": "Total Apps"})

    async def increase_active_apps(self, name: str):
        """Marks an app as active and updates the sensors for active/inactive apps."""
        if name not in self.active_apps:
            self.active_apps.add(name)

        if name in self.inactive_apps:
            self.inactive_apps.remove(name)

        await self.set_state(self.active_apps_sensor, state=len(self.active_apps))
        await self.set_state(self.inactive_apps_sensor, state=len(self.inactive_apps))

    async def increase_inactive_apps(self, name: str):
        """Marks an app as inactive and updates the sensors for active/inactive apps."""
        if name not in self.inactive_apps:
            self.inactive_apps.add(name)

        if name in self.active_apps:
            self.active_apps.remove(name)

        await self.set_state(self.active_apps_sensor, state=len(self.active_apps))
        await self.set_state(self.inactive_apps_sensor, state=len(self.inactive_apps))

    async def terminate(self):
        self.logger.debug("terminate() called for app_management")
        await self.check_app_updates(mode=UpdateMode.TERMINATE)

    async def dump_objects(self):
        self.diag.info("--------------------------------------------------")
        self.diag.info("Objects")
        self.diag.info("--------------------------------------------------")
        for object_ in self.objects.keys():
            self.diag.info("%s: %s", object_, self.objects[object_])
        self.diag.info("--------------------------------------------------")

    def get_app(self, name: str):
        if obj := self.objects.get(name):
            return obj.object

    def get_app_info(self, name: str):
        return self.objects.get(name)

    def get_app_instance(self, name: str, id):
        if (obj := self.objects.get(name)) and obj.id == id:
            return obj.object

    def get_app_pin(self, name: str) -> bool:
        return self.objects[name].pin_app

    def set_app_pin(self, name: str, pin: bool):
        self.objects[name].pin_app = pin
        utils.run_coroutine_threadsafe(
            self,
            self.AD.threading.calculate_pin_threads(),
        )

    def get_pin_thread(self, name: str) -> int:
        return self.objects[name].pin_thread

    def set_pin_thread(self, name: str, thread: int):
        self.objects[name].pin_thread = thread

    async def initialize_app(self, app_name: str):
        assert app_name in self.objects, 'Something is very wrong'
        app_obj = self.objects[app_name].object

        # Get the path that will be used for the exception
        err_path = self.err_app_path(app_obj)

        try:
            init_func = app_obj.initialize
        except AttributeError:
            raise ade.NoInitializeMethod(app_obj.__class__, err_path)

        signature = inspect.signature(init_func)
        if len(signature.parameters) != 0:
            raise ade.BadInitializeMethod(app_obj.__class__, err_path, signature)

        # Call its initialize function
        await self.set_state(app_name, state="initializing")
        self.logger.info(f"Calling initialize() for {app_name}")
        if asyncio.iscoroutinefunction(init_func):
            await init_func()
        else:
            await utils.run_in_executor(self, init_func)

    async def terminate_app(self, app_name: str, delete: bool = True) -> bool:
        try:
            if (obj := self.objects.get(app_name)) and (term := getattr(obj.object, "terminate", None)):
                self.logger.info("Calling terminate() for '%s'", app_name)
                if asyncio.iscoroutinefunction(term):
                    await term()
                else:
                    await utils.run_in_executor(self, term)
            return True

        except TypeError:
            self.AD.threading.report_callback_sig(
                app_name, "terminate", term, {})
            return False

        except Exception:
            error_logger = logging.getLogger(f"Error.{app_name}")
            error_logger.warning("-" * 60)
            error_logger.warning(
                "Unexpected error running terminate() for %s", app_name)
            error_logger.warning("-" * 60)
            error_logger.warning(traceback.format_exc())
            error_logger.warning("-" * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning(
                    "Logged an error to %s",
                    self.AD.logging.get_filename("error_log"),
                )
            return False

        finally:
            self.logger.debug("Cleaning up app '%s'", app_name)
            if obj := self.objects.get(app_name):
                if delete:
                    del self.objects[app_name]
                else:
                    obj.running = False

            await self.increase_inactive_apps(app_name)

            await self.AD.callbacks.clear_callbacks(app_name)

            self.AD.futures.cancel_futures(app_name)

            self.AD.services.clear_services(app_name)

            await self.AD.sched.terminate_app(app_name)

            await self.set_state(app_name, state="terminated")
            await self.set_state(app_name, instancecallbacks=0)

            event_data = {"event_type": "app_terminated",
                          "data": {"app": app_name}}

            await self.AD.events.process_event("admin", event_data)

            if self.AD.http is not None:
                await self.AD.http.terminate_app(app_name)

    async def start_app(self, app_name: str):
        """Initializes a new object and runs the initialize function of the app.

        This does not work on global module apps because they only exist as imported modules.

        Args:
            app (str): Name of the app to start
        """
        if self.app_config[app_name].disable:
            self.logger.debug(f"Skip starting disabled app: '{app_name}'")
            return

        # first we check if running already
        if self.is_app_running(app_name):
            self.logger.warning(f"Cannot start app {app_name}, as it is already running")
            return

        # assert dependencies
        dependencies = self.app_config.root[app_name].dependencies
        for dep_name in dependencies:
            rel_path = self.app_rel_path(app_name)
            exc_args = (
                app_name,
                rel_path,
                dep_name,
                dependencies
            )
            if (dep_cfg := self.app_config.root.get(dep_name)):
                match dep_cfg:
                    case AppConfig():
                        # There is a valid app configuration for this dependency
                        if not (obj := self.objects.get(dep_name)) or not obj.running:
                            # If the object isn't in the self.objects dict or it's there, but not running
                            raise ade.DependencyNotRunning(*exc_args)
                    case GlobalModule():
                        module = dep_cfg.module_name
                        if module not in sys.modules:
                            raise ade.GlobalNotLoaded(*exc_args)
            else:
                raise ade.AppDependencyError(*exc_args)

        try:
            await self.initialize_app(app_name)
        except Exception as e:
            self.logger.warning(f"App '{app_name}' failed to start")

            await self.increase_inactive_apps(app_name)
            await self.set_state(app_name, state="initialize_error")
            self.objects[app_name].running = False
            raise ade.InitializationFail(app_name) from e
        else:
            await self.increase_active_apps(app_name)
            await self.set_state(app_name, state="idle")
            self.objects[app_name].running = True

            event_data = {
                "event_type": "app_initialized",
                "data": {"app": app_name}
            }
            await self.AD.events.process_event("admin", event_data)

    async def stop_app(self, app_name: str, delete: bool = False) -> bool:
        """Stops the app

        Returns:
            bool: Whether stopping was successful or not
        """
        try:
            if isinstance(self.app_config[app_name], AppConfig):
                self.logger.debug("Stopping app '%s'", app_name)
            await self.terminate_app(app_name, delete)
        except Exception:
            error_logger = logging.getLogger(f"Error.{app_name}")
            error_logger.warning("-" * 60)
            error_logger.warning("Unexpected error terminating app: %s:", app_name)
            error_logger.warning("-" * 60)
            error_logger.warning(traceback.format_exc())
            error_logger.warning("-" * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning("Logged an error to %s",
                                    self.AD.logging.get_filename("error_log"))
            return False
        else:
            return True

    async def restart_app(self, app: str) -> None:
        await self.stop_app(app, delete=False)
        try:
            await self.start_app(app)
        except ade.AppDaemonException as e:
            self.logger.warning(e)

    def get_app_debug_level(self, name: str):
        if obj := self.objects.get(name):
            logger: Logger = obj.object.logger
            return logging._levelToName[logger.getEffectiveLevel()]

    async def create_app_object(self, app_name: str) -> None:
        """Instantiates an app by name and stores it in ``self.objects``.

        This does not work on global module apps.

        Args:
            app_name (str): Name of the app, as defined in a config file

        Raises:
            PinOutofRange: Caused by passing in an invalid value for pin_thread
            MissingAppClass: When there's a problem getting the class definition from the loaded module
            AppClassSignatureError: When the class has the wrong number of inputs on its __init__ method
            AppInstantiationError: When there's another, unknown error creating the class from its definition
        """
        cfg = self.app_config.root[app_name]
        assert isinstance(cfg, AppConfig), f"Not an AppConfig: {cfg}"

        # as it appears in the YAML definition of the app
        module_name = cfg.module_name
        class_name = cfg.class_name

        self.logger.debug(
            "Loading app %s using class %s from module %s",
            app_name,
            class_name,
            module_name,
        )

        if (pin := cfg.pin_thread) and pin >= self.AD.threading.total_threads:
            raise ade.PinOutofRange(pin_thread=pin, total_threads=self.AD.threading.total_threads)
        elif (obj := self.objects.get(app_name)) and obj.pin_thread is not None:
            pin = obj.pin_thread
        else:
            pin = -1

        # This module should already be loaded and stored in sys.modules
        mod_obj = await utils.run_in_executor(self, importlib.import_module, module_name)

        try:
            app_class = getattr(mod_obj, class_name)
        except AttributeError:
            path = mod_obj.__file__ or mod_obj.__path__._path[0]
            raise ade.MissingAppClass(
                app_name,
                mod_obj.__name__,
                Path(path).relative_to(self.AD.app_dir.parent),
                class_name
            )

        new_obj = app_class(self.AD, cfg)
        assert isinstance(getattr(new_obj, "AD", None), type(self.AD)), 'App objects need to have a reference to the AppDaemon object'
        assert isinstance(getattr(new_obj, "config_model", None), AppConfig), 'App objects need to have a reference to their config model'

        self.objects[app_name] = ManagedObject(
            type="app",
            object=new_obj,
            pin_app=self.AD.threading.app_should_be_pinned(app_name),
            pin_thread=pin,
            running=False,
            module_path=Path(mod_obj.__file__),
        )

        # load the module path into app entity
        module_path = await utils.run_in_executor(self, os.path.abspath, mod_obj.__file__)
        await self.set_state(app_name, state="created", module_path=module_path)

    def get_managed_app_names(self, include_globals: bool = False) -> set[str]:
        apps = set(name for name, o in self.objects.items() if o.type == "app")
        if include_globals:
            globals = set(
                name for name, cfg in self.app_config.root.items()
                if isinstance(cfg, GlobalModule)
            )
            apps |= globals
        return apps

    def add_plugin_object(self, name: str, object: "PluginBase", use_dictionary_unpacking: bool = False) -> None:
        """Add the plugin object to the internal dictionary of ``ManagedObjects``"""
        self.objects[name] = ManagedObject(
            type="plugin",
            object=object,
            pin_app=False,
            pin_thread=-1,
            running=False,
            use_dictionary_unpacking=use_dictionary_unpacking,
        )

    async def terminate_sequence(self, name: str) -> bool:
        """Terminate the sequence"""
        assert self.objects.get(name, {}).get('type') == "sequence", f"'{name}' is not a sequence"

        if name in self.objects:
            del self.objects[name]

        await self.AD.callbacks.clear_callbacks(name)
        self.AD.futures.cancel_futures(name)

        return True

    async def read_all(self, config_files: Iterable[Path] = None) -> AllAppConfig:
        config_files = config_files or self.dependency_manager.config_files

        async def config_model_factory() -> AsyncGenerator[AllAppConfig, None, None]:
            """Creates a generator that sets the config_path of app configs"""
            for path in config_files:
                @ade.wrap_async(self.error, self.AD.app_dir, "Reading user apps")
                async def safe_read(self: "AppManagement", path: Path) -> AllAppConfig:
                    try:
                        return await self.read_config_file(path)
                    except Exception as exc:
                        raise ade.BadAppConfigFile(path) from exc

                new_cfg = await safe_read(self, path)
                if new_cfg is None:
                    continue

                for name, cfg in new_cfg.root.items():
                    if isinstance(cfg, AppConfig):
                        await self.add_entity(
                            name,
                            state="loaded",
                            attributes={
                                "totalcallbacks": 0,
                                "instancecallbacks": 0,
                                "args": cfg.args,
                                "config_path": cfg.config_path,
                            },
                        )
                yield new_cfg

        def update(d1: dict, d2: dict) -> dict:
            """Internal function to log warnings if an app's name gets repeated."""
            if overlap := set(k.lower() for k in d2 if k in d1):
                # There's a special case for the sequences in order to merge them if they're defined in multiple files
                if "sequence" in overlap:
                    d1["sequence"].update(d2.pop("sequence"))
                else:
                    self.logger.warning(f"Apps re-defined: {overlap}")

            return d1.update(d2) or d1

        models = [
            m.model_dump(by_alias=True, exclude_unset=True) async for m in config_model_factory() if m is not None
        ]
        combined_configs = reduce(update, models, {})
        return AllAppConfig.model_validate(combined_configs)

    async def check_app_config_files(self, update_actions: UpdateActions):
        """Updates self.mtimes_config and self.app_config"""
        files = await self.get_app_config_files()
        self.dependency_manager.app_deps.update(files)

        # If there were config file changes
        if self.config_filecheck.there_were_changes:
            self.logger.debug(" Config file changes ".center(75, "="))
            self.config_filecheck.log_changes(self.logger, self.AD.app_dir)

            # Read any new/modified files into a fresh config model
            files_to_read = self.config_filecheck.new | self.config_filecheck.modified
            freshly_read_cfg = await self.read_all(files_to_read)

            # TODO: Move this behavior to the model validation step eventually
            # It has to be here for now because the files get read in multiple places
            for gm in freshly_read_cfg.global_modules():
                rel_path = gm.config_path.relative_to(self.AD.app_dir)
                self.logger.warning(f"Global modules are deprecated: '{gm.name}' defined in {rel_path}")

            if gm := freshly_read_cfg.root.get("global_modules"):
                gm = ", ".join(f"'{g}'" for g in gm)
                self.logger.warning(f"Global modules are deprecated: {gm}")

            current_apps = self.valid_apps
            for name, cfg in freshly_read_cfg.app_definitions():
                if isinstance(cfg, SequenceConfig):
                    self._compare_sequences(update_actions, cfg, files_to_read)
                    continue

                if name in self.non_apps or cfg.disable:
                    continue

                # New config found
                if name not in current_apps:
                    if isinstance(cfg, GlobalModule):
                        self.logger.info(f"New global module: {name}[{cfg.module_name}]")
                    else:
                        self.logger.info(f"New app config: {name}")
                    update_actions.apps.init.add(name)
                else:
                    # If an app exists, compare to the current config
                    prev_app = self.app_config.root[name].model_dump()
                    current_app = cfg.model_dump()
                    if not utils.deep_compare(current_app, prev_app):
                        self.logger.info("App config modified: %s", name)
                        update_actions.apps.reload.add(name)

            prev_apps_from_read_files = self.app_config.apps_from_file(files_to_read) & current_apps
            deleted_apps = set(
                n for n in prev_apps_from_read_files
                if n not in freshly_read_cfg.app_names()
            )
            update_actions.apps.term |= deleted_apps
            for name in deleted_apps:
                # del self.app_config.root[name]
                self.logger.info("App config deleted: %s", name)

            self.app_config.root.update(freshly_read_cfg.root)

        if update_actions.apps.init_set:
            # If there are any new/modified apps, the dependency graph needs to be updated
            self.dependency_manager.app_deps.refresh_dep_graph()

        if self.AD.threading.pin_apps:
            active_apps = self.app_config.active_app_count
            if active_apps > self.AD.threading.thread_count:
                threads_to_add = active_apps - self.AD.threading.thread_count
                self.logger.debug(
                    f"Adding {threads_to_add} threads based on the active app count"
                )
                for _ in range(threads_to_add):
                    await self.AD.threading.add_thread(silent=False, pinthread=True)

    @utils.executor_decorator
    def read_config_file(self, file: Path) -> AllAppConfig:
        """Reads a single YAML or TOML file into a pydantic model. This also sets the ``config_path`` attribute of any AppConfigs.

        This function is primarily used by the create/edit/remove app methods that write yaml files.
        """
        raw_cfg = utils.read_config_file(file, app_config=True)
        if not bool(raw_cfg):
            self.logger.warning(
                f"Loaded an empty config file: {file.relative_to(self.AD.app_dir.parent)}"
            )
        config_model = AllAppConfig.model_validate(raw_cfg)
        return config_model

    @utils.executor_decorator
    def import_module(self, module_name: str) -> int:
        """Reads an app into memory by importing or reloading the module it needs"""
        try:
            if mod := sys.modules.get(module_name):
                self.logger.debug("Reloading '%s'", module_name)
                importlib.reload(mod)
            else:
                # this check is to skip modules that don't come from the app directory
                if not module_name.startswith("appdaemon"):
                    self.logger.debug("Importing '%s'", module_name)
                    importlib.import_module(module_name)
        except Exception as exc:
            match exc:
                case SyntaxError():
                    path = Path(exc.filename)
                case NameError():
                    path = Path(traceback.extract_tb(exc.__traceback__)[-1].filename)
                case _:
                    raise exc
            mtime = self.dependency_manager.python_deps.files.mtimes.get(path)
            self.dependency_manager.python_deps.bad_files.add((path, mtime))
            raise exc

    @utils.executor_decorator
    def _process_filters(self):
        for filter in self.AD.config.filters:
            input_files = self.AD.app_dir.rglob(f"*{filter.input_ext}")
            for file in input_files:
                modified = file.stat().st_mtime

                if file in self.filter_files:
                    if self.filter_files[file] < modified:
                        self.logger.info("Found modified filter file %s", file)
                        run = True
                else:
                    self.logger.info("Found new filter file %s", file)
                    run = True

                if run is True:
                    self.logger.info("Running filter on %s", file)
                    self.filter_files[file] = modified

                    # Run the filter
                    outfile = utils.rreplace(
                        file, filter.input_ext, filter.output_ext, 1)
                    command_line = filter.command_line.replace("$1", file)
                    command_line = command_line.replace("$2", outfile)
                    try:
                        subprocess.Popen(command_line, shell=True)
                    except Exception:
                        self.logger.warning("-" * 60)
                        self.logger.warning(
                            "Unexpected running filter on: %s:", file)
                        self.logger.warning("-" * 60)
                        self.logger.warning(traceback.format_exc())
                        self.logger.warning("-" * 60)

    @staticmethod
    def check_file(file: str):
        with open(file):
            pass

    def add_to_import_path(self, path: str | Path):
        path = str(path)
        self.logger.debug("Adding directory to import path: %s", path)
        sys.path.insert(0, path)

    def profiler_decorator(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            pr = cProfile.Profile()
            pr.enable()

            try:
                return await func(*args, **kwargs)
            finally:
                pr.disable()
                s = io.StringIO()
                sortby = "cumulative"
                ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
                ps.print_stats()
                self.check_app_updates_profile_stats = s.getvalue()

        return wrapper

    # @utils.timeit
    async def check_app_updates(self, plugin_ns: str | None = None, mode: UpdateMode = UpdateMode.NORMAL):
        """Checks the states of the Python files that define the apps, reloading when necessary.

        Called as part of :meth:`.utility_loop.Utility.loop`

        Args:
            plugin_ns (str, optional): Namespace of a plugin to restart, if necessary. Defaults to None.
            mode (UpdateMode, optional): Defaults to UpdateMode.NORMAL.
        """
        if not self.AD.apps:
            return

        async with self.check_updates_lock:
            await self._process_filters()

            update_actions = UpdateActions()

            match mode:
                case UpdateMode.INIT:
                    await self._process_import_paths()
                    await self._init_dep_manager()
                case UpdateMode.RELOAD_APPS:
                    all_apps = self.get_managed_app_names(include_globals=False)
                    modules = self.dependency_manager.modules_from_apps(all_apps)
                    update_actions.apps.reload |= all_apps
                    update_actions.modules.reload |= modules

            await self.check_app_config_files(update_actions)

            await self._handle_sequence_change(update_actions, mode)

            try:
                await self.check_app_python_files(update_actions)
            except DependencyResolutionFail as exc:
                exception_text = utils.format_exception(exc.base_exception)
                self.logger.error(f"Error reading python files: {exception_text}")
                return

            if mode == UpdateMode.TERMINATE:
                update_actions.modules = LoadingActions()
                all_apps = self.get_managed_app_names()
                update_actions.apps = LoadingActions(term=all_apps)
            # else:
            # self._add_reload_apps(update_actions)
            # self._check_for_deleted_modules(update_actions)

            match mode:
                case UpdateMode.PLUGIN_FAILED:
                    await self._stop_plugin_apps(plugin_ns, update_actions)
                case UpdateMode.PLUGIN_RESTART:
                    await self._start_plugin_apps(plugin_ns, update_actions)

            await self._import_modules(update_actions)

            await self._stop_apps(update_actions)

            await self._start_apps(update_actions)

    @utils.executor_decorator
    def _process_import_paths(self):
        """Process one time static additions to sys.path"""
        # Always start with the app_dir
        self.add_to_import_path(self.AD.app_dir)

        match self.AD.config.import_method:
            case 'default' | 'expert' | None:
                # Get unique set of the absolute paths of all the subdirectories containing python files
                python_file_parents = set(
                    f.parent.resolve() for f in Path(self.AD.app_dir).rglob("*.py")
                )

                # Filter out any that have __init__.py files in them
                module_parents = set(
                    p for p in python_file_parents
                    if not (p / "__init__.py").exists()
                )

                #  unique set of the absolute paths of all subdirectories with a __init__.py in them
                package_dirs = set(
                    p for p in python_file_parents
                    if (p / "__init__.py").exists()
                )

                # Filter by ones whose parent directory's don't also contain an __init__.py
                top_packages_dirs = set(
                    p for p in package_dirs
                    if not (p.parent / "__init__.py").exists()
                )

                # Get the parent directories so the ones with __init__.py are importable
                package_parents = set(p.parent for p in top_packages_dirs)

                # Combine import directories. Having the list sorted will prioritize parent folders over children during import
                import_dirs = sorted(module_parents | package_parents, reverse=True)

                for path in import_dirs:
                    self.add_to_import_path(path)

                # Add any additional import paths
                for path in map(Path, self.AD.import_paths):
                    if not path.exists():
                        self.logger.warning(
                            f"import_path {path} does not exist - not adding to path")
                        continue

                    if not path.is_dir():
                        self.logger.warning(
                            f"import_path {path} is not a directory - not adding to path")
                        continue

                    if not path.is_absolute():
                        path = Path(self.AD.config_dir) / path

                    self.add_to_import_path(path)
            case 'legacy':
                for root, subdirs, files in os.walk(self.AD.app_dir):
                    base = os.path.basename(root)
                    valid_root = base != "__pycache__" and not base.startswith(".")
                    if valid_root and root not in sys.path:
                        self.add_to_import_path(root)

    async def _init_dep_manager(self):
        @utils.warning_decorator(error_text="Error while creating dependency manager")
        async def safe_dep_create(self: "AppManagement"):
            try:
                self.dependency_manager = DependencyManager(
                    python_files=await self.get_python_files(),
                    config_files=await self.get_app_config_files()
                )
                self.config_filecheck.mtimes = {}
                self.python_filecheck.mtimes = {}
            except ValidationError as e:
                raise ade.BadAppConfigFile("Error creating dependency manager") from e
            except ade.AppDaemonException as e:
                raise e

        await safe_dep_create(self)

    @utils.executor_decorator
    def get_python_files(self) -> Iterable[Path]:
        """Iterates through ``*.py`` in the app directory. Excludes directory names defined in exclude_dirs and with a "." character. Also excludes files that aren't readable."""
        return set(
            f
            for f in self.AD.app_dir.resolve().rglob("*.py")
            if f.parent.name not in self.AD.exclude_dirs  # apply exclude_dirs
            and "." not in f.parent.name  # also excludes *.egg-info folders
            and os.access(f, os.R_OK)  # skip unreadable files
        )

    @utils.executor_decorator
    def get_app_config_files(self) -> Iterable[Path]:
        """Iterates through config files in the config directory. Excludes directory names defined in exclude_dirs and files with a "." character. Also excludes files that aren't readable."""
        return set(
            f
            for f in self.AD.app_dir.resolve().rglob(f"*{self.ext}")
            if f.parent.name not in self.AD.exclude_dirs  # apply exclude_dirs
            and "." not in f.stem
            and os.access(f, os.R_OK)  # skip unreadable files
        )

    async def check_app_python_files(self, update_actions: UpdateActions):
        """Checks the python files in the app directory. Part of self.check_app_updates sequence"""
        files = await self.get_python_files()
        self.dependency_manager.update_python_files(files)

        # We only need to init the modules necessary for the new apps, not reloaded ones
        new_apps = update_actions.apps.init
        app_modules = self.dependency_manager.modules_from_apps(new_apps, dependents=True)
        update_actions.modules.init |= app_modules

        if self.python_filecheck.there_were_changes:
            self.logger.debug(" Python file changes ".center(75, "="))

            if mod := self.python_filecheck.modified:
                self.logger.info("Modified Python files: %s", len(mod))
                module_names = set(get_full_module_name(f) for f in mod)
                deps = self.dependency_manager.dependent_modules(module_names)
                self.logger.debug("Dependent modules: %s", deps)
                update_actions.modules.reload |= deps

                affected = self.dependency_manager.dependent_apps(module_names)
                self.logger.info("Modification affects apps %s", affected)
                update_actions.apps.reload |= affected

            if deleted := self.python_filecheck.deleted:
                self.logger.info("Deleted Python files: %s", len(deleted))
                module_names = set(get_full_module_name(f) for f in deleted)
                affected = self.dependency_manager.dependent_apps(module_names)
                self.logger.info("Deletion affects apps %s", affected)
                update_actions.apps.term |= affected

    def get_namespace_apps(self, namespace: str) -> set[str]:
        return set(
            app_name
            for app_name, cfg in self.app_config.root.items()   # For each config key
            if isinstance(cfg, AppConfig) and                   # The config key is for an app
            (mo := self.objects.get(app_name)) and              # There's a valid ManagedObject
            mo.object.namespace == namespace                    # Its namespace matches
        )

    async def _stop_plugin_apps(self, plugin_ns: str | None, update_actions: UpdateActions):
        if plugin_ns is not None:
            self.logger.info(f"Stopping apps from namespace '{plugin_ns}' because the plugin failed")
            app_names = self.get_namespace_apps(plugin_ns)
            deps = self.dependency_manager.app_deps.get_dependents(app_names)
            update_actions.apps.term |= deps

    async def _start_plugin_apps(self, plugin_ns: str | None, update_actions: UpdateActions):
        """If a plugin ever re-connects after the initial startup, the apps that use it's plugin
        all need to be started. They should already have been stopped by the plugin disconnecting.
        The apps that belong to the plugin are determined by namespace.
        """
        if plugin_ns is not None:
            self.logger.info(f"Processing restart for plugin namespace '{plugin_ns}'")
            app_names = self.get_namespace_apps(plugin_ns)
            deps = self.dependency_manager.app_deps.get_dependents(app_names)
            update_actions.apps.init |= deps

    async def _stop_apps(self, update_actions: UpdateActions):
        """Terminate apps. Returns the set of app names that failed to properly terminate.

        Part of self.check_app_updates sequence
        """
        stop_order = update_actions.apps.term_sort(self.dependency_manager)
        # stop_order = update_actions.apps.term_sort(self.app_config.depedency_graph())
        if stop_order:
            self.logger.info("Stopping apps: %s", update_actions.apps.term_set)
            self.logger.debug("App stop order: %s", stop_order)

        failed_to_stop = set()  # stores apps that had a problem terminating
        for app_name in stop_order:
            if not await self.stop_app(app_name):
                failed_to_stop.add(app_name)

        if failed_to_stop:
            self.logger.debug(
                "Removing %s apps because they failed to stop cleanly", len(failed_to_stop))
            update_actions.apps.init -= failed_to_stop
            update_actions.apps.reload -= failed_to_stop

    async def _start_apps(self, update_actions: UpdateActions):
        if failed := update_actions.apps.failed:
            self.logger.warning('Failed to start apps: %s', failed)

        start_order = update_actions.apps.start_sort(self.dependency_manager)
        if start_order:
            self.logger.info("Starting apps: %s", update_actions.apps.init_set)
            self.logger.debug("App start order: %s", start_order)

            for app_name in start_order:
                if isinstance((cfg := self.app_config.root[app_name]), AppConfig) and not cfg.disable:
                    @ade.wrap_async(self.error, self.AD.app_dir, f"'{app_name}' instantiation")
                    async def safe_create(self: "AppManagement"):
                        try:
                            await self.create_app_object(app_name)
                        except Exception as exc:
                            update_actions.apps.failed.add(app_name)
                            await self.set_state(app_name, state="compile_error")
                            await self.increase_inactive_apps(app_name)
                            raise ade.AppInstantiationError(app_name) from exc

                    await safe_create(self)

            # Need to have already created the ManagedObjects for the threads to get assigned
            await self.AD.threading.calculate_pin_threads()

            # Need to recalculate start order in case creating the app object fails
            start_order = update_actions.apps.start_sort(self.dependency_manager, self.logger)
            for app_name in start_order:
                if isinstance((cfg := self.app_config.root[app_name]), AppConfig):
                    @ade.wrap_async(
                        self.error, self.AD.app_dir,
                        f"Failed to start '{app_name}'")
                    async def safe_start(self: "AppManagement"):
                        try:
                            await self.start_app(app_name)
                        except Exception as exc:
                            update_actions.apps.failed.add(app_name)
                            raise ade.AppStartFailure(app_name) from exc

                    if await self.get_state(app_name) != "compile_error":
                        await safe_start(self)
                elif isinstance(cfg, GlobalModule):
                    assert cfg.module_name in sys.modules, f'{cfg.module_name} not in sys.modules'

    async def _import_modules(self, update_actions: UpdateActions) -> set[str]:
        """Calls ``self.import_module`` for each module in the list

        This is what handles importing all the modules safely. If any of them fail to import, that failure is cascaded through the dependencies.
        """
        # If any apps defined with "global: true" are in the init set, they need to get added to the module list
        gm_modules = set(
            app_cfg.module_name
            for name, app_cfg in self.app_config.root.items()
            if isinstance(app_cfg, GlobalModule)
            and name in update_actions.apps.init_set
        )
        modules = update_actions.modules.init_set | gm_modules
        load_order = self.dependency_manager.python_sort(modules)
        if load_order:
            self.logger.debug("Determined module load order: %s", load_order)
            for module_name in load_order:

                @ade.wrap_async(self.error, self.AD.app_dir, f"Error importing '{module_name}'")
                async def safe_import(self: "AppManagement"):
                    try:
                        await self.import_module(module_name)
                    except Exception as e:
                        dm: DependencyManager = self.dependency_manager
                        update_actions.modules.failed |= dm.dependent_modules(module_name)
                        update_actions.apps.failed |= dm.dependent_apps(module_name)
                        for app_name in update_actions.apps.failed:
                            await self.set_state(app_name, state="compile_error")
                            await self.increase_inactive_apps(app_name)

                        # Handle this down here to avoid having to repeat all the above logic for
                        # other exceptions.
                        raise ade.FailedImport(module_name, self.AD.app_dir) from e

                await safe_import(self)

    def _compare_sequences(self, update_actions: UpdateActions, cfg: SequenceConfig, changed_files: Iterable[Path]):
        """Adds apps to the update actions based on sequence changes, if need be"""
        # Need to handle new, changed, and deleted sequences
        existing_sequences = set(self.sequence_config.root.keys())
        new_sequences = set(n for n in cfg.root if n not in existing_sequences)
        update_actions.sequences.init |= new_sequences
        for seq in new_sequences:
            self.logger.info(f"New sequence config: {seq}")

        # Find the apps that were previously defined by these files
        prev_apps = set(
            k for k, v in self.sequence_config.root.items()
            if v.config_path in changed_files
        )
        for app in prev_apps:
            if app not in cfg.root:
                update_actions.sequences.term.add(app)
                self.logger.info(f"Sequence config deleted: {app}")

        overlaped_sequences = set(cfg.root.keys()) & existing_sequences
        for seq_name in overlaped_sequences:
            current_seq = self.sequence_config.root[seq_name]
            new_seq = cfg.root[seq_name]
            if not utils.deep_compare(new_seq.model_dump(), current_seq.model_dump()):
                self.logger.info(f"Sequence config modified: {seq_name}")
                update_actions.sequences.reload.add(seq_name)
                seq_eid = self.AD.sequences.normalized(seq_name)
                update_actions.apps.reload |= self.dependency_manager.app_deps.get_dependents(seq_eid)
                update_actions.apps.reload.remove(seq_eid)

    async def _handle_sequence_change(self, update_actions: UpdateActions, update_mode: UpdateMode):
        # Ensure sequences are cancelled if need be
        await self.AD.sequences.remove_sequences(update_actions.sequences.term_set)

        # Update the sequence steps in the internal sequence entity
        if update_actions.sequences.changes or update_mode == UpdateMode.INIT:
            await self.AD.sequences.update_sequence_entities(self.sequence_config)

    @utils.executor_decorator
    def create_app(self, app: str = None, **kwargs):
        """Used to create an app, which is written to a config file"""

        executed = True
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
            self.logger.error(
                "Could not create app %s, as module and class is required", app)
            return False

        app_directory: Path = self.AD.app_dir / kwargs.pop("app_dir", "ad_apps")
        app_file: Path = app_directory / kwargs.pop("app_file", f"{app}{self.ext}")
        app_directory = app_file.parent  # in case the given app_file is multi level

        try:
            app_directory.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.logger.error("Could not create directory %s", app_directory)
            return False

        if app_file.is_file():
            # the file exists so there might be apps there already so read to update
            # now open the file and edit the yaml
            new_config.update(self.read_config_file(app_file))

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
            self.AD.loop.create_task(
                self.AD.events.process_event("admin", data))

        except Exception:
            self.error.warning("-" * 60)
            self.error.warning(
                "Unexpected error while writing to file: %s", app_file)
            self.error.warning("-" * 60)
            self.error.warning(traceback.format_exc())
            self.error.warning("-" * 60)
            executed = False

        return executed

    @utils.executor_decorator
    def edit_app(self, app: str, **kwargs):
        """Used to edit an app, which is already in Yaml. It is expecting the app's name"""

        executed = True
        app_config = copy.deepcopy(self.app_config[app])
        new_config = OrderedDict()

        # now update the app config
        app_config.update(kwargs)

        # now get the app's file
        app_file = self.get_app_file(app)
        if app_file is None:
            self.logger.warning(
                "Unable to find app %s's file. Cannot edit the app", app)
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
            self.AD.loop.create_task(
                self.AD.events.process_event("admin", data))

        except Exception:
            self.error.warning("-" * 60)
            self.error.warning(
                "Unexpected error while writing to file: %s", app_file)
            self.error.warning("-" * 60)
            self.error.warning(traceback.format_exc())
            self.error.warning("-" * 60)
            executed = False

        return executed

    @utils.executor_decorator
    def remove_app(self, app: str, **kwargs):
        """Used to remove an app"""

        result = None
        # now get the app's file
        app_file = self.get_app_file(app)
        if app_file is None:
            self.logger.warning(
                "Unable to find app %s's file. Cannot remove the app", app)
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
            self.AD.loop.create_task(
                self.AD.events.process_event("admin", data))

        except Exception:
            self.error.warning("-" * 60)
            self.error.warning(
                "Unexpected error while writing to file: %s", app_file)
            self.error.warning("-" * 60)
            self.error.warning(traceback.format_exc())
            self.error.warning("-" * 60)

        return result

    def get_app_file(self, app: str) -> str:
        """Used to get the file an app is located"""
        return self.AD.threading.run_coroutine_threadsafe(
            self.get_state(app, attribute="config_path")
        )

    async def manage_services(
        self,
        namespace: str,
        domain: str,
        service: Literal["start", "stop", "restart", "reload", "enable", "disable", "create", "edit", "remove"],
        app: str | None = None,
        __name: str | None = None,
        **kwargs
    ) -> None | bool | Any:
        assert namespace == 'admin' and domain == 'app'
        match service:
            case "reload" | "create":
                pass
            case _:
                if app not in self.get_managed_app_names(include_globals=False):
                    self.logger.warning(
                        "Specified app '%s' for service '%s' is not valid from %s",
                        app,
                        service,
                        __name
                    )
                    return

        match (service, app):
            case ("start", str()):
                asyncio.create_task(self.start_app(app))
            case ("stop", str()):
                asyncio.create_task(self.stop_app(app, delete=False))
            case ("restart", str()):
                asyncio.create_task(self.restart_app(app))
            case ("reload", _):
                asyncio.create_task(self.check_app_updates(mode=UpdateMode.RELOAD_APPS))
            case (_, str()):
                # first the check app updates needs to be stopped if on
                mode = copy.deepcopy(self.AD.production_mode)

                if mode is False:  # it was off
                    self.AD.production_mode = True
                    await asyncio.sleep(0.5)

                match service:
                    case "enable":
                        result = await self.edit_app(app, disable=False)
                    case "disable":
                        result = await self.edit_app(app, disable=True)
                    case "create":
                        result = await self.create_app(app, **kwargs)
                    case "edit":
                        result = await self.edit_app(app, **kwargs)
                    case "remove":
                        result = await self.remove_app(app, **kwargs)

                if mode is False:  # meaning it was not in production mode
                    await asyncio.sleep(1)
                    self.AD.production_mode = mode

                return result
            case _:
                self.logger.warning(
                    "Invalid app service call '%s' with app '%s' from  app %s.",
                    service,
                    app,
                    __name
                )
