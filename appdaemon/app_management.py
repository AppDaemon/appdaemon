import sys
import traceback
import uuid
import os
import importlib
import subprocess
import cProfile
import io
import pstats
import logging
import asyncio
import copy
from collections import OrderedDict

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon


class AppManagement:
    def __init__(self, ad: AppDaemon, use_toml):
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
            await self.check_app_updates(mode="term")

    async def dump_objects(self):
        self.diag.info("--------------------------------------------------")
        self.diag.info("Objects")
        self.diag.info("--------------------------------------------------")
        for object_ in self.objects.keys():
            self.diag.info("%s: %s", object_, self.objects[object_])
        self.diag.info("--------------------------------------------------")

    async def get_app(self, name):
        if name in self.objects:
            return self.objects[name]["object"]
        else:
            return None

    def get_app_info(self, name):
        if name in self.objects:
            return self.objects[name]
        else:
            return None

    async def get_app_instance(self, name, id):
        if name in self.objects and self.objects[name]["id"] == id:
            return self.AD.app_management.objects[name]["object"]
        else:
            return None

    async def initialize_app(self, name):
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

    async def terminate_app(self, name, delete=True):
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

    async def stop_app(self, app, delete=False):
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

    async def init_object(self, name):
        app_args = self.app_config[name]
        self.logger.info(
            "Initializing app %s using class %s from module %s",
            name,
            app_args["class"],
            app_args["module"],
        )

        if self.get_file_from_module(app_args["module"]) is not None:
            if "pin_thread" in app_args:
                if app_args["pin_thread"] < 0 or app_args["pin_thread"] >= self.AD.threading.total_threads:
                    self.logger.warning(
                        "pin_thread out of range ({}) in app definition for {} - app will be discarded".format(
                            app_args["pin_thread"], name
                        )
                    )
                    return
                else:
                    pin = app_args["pin_thread"]

            elif name in self.objects and "pin_thread" in self.objects[name]:
                pin = self.objects[name]["pin_thread"]

            else:
                pin = -1

            modname = await utils.run_in_executor(self, __import__, app_args["module"])

            app_class = getattr(modname, app_args["class"], None)
            if app_class is None:
                self.logger.warning(
                    "Unable to find class %s in module %s - '%s' is not initialized",
                    app_args["class"],
                    app_args["module"],
                    name,
                )
                await self.increase_inactive_apps(name)

            else:
                self.objects[name] = {
                    "type": "app",
                    "object": app_class(
                        self.AD,
                        name,
                        self.AD.logging,
                        app_args,
                        self.AD.config,
                        self.app_config,
                        self.AD.global_vars,
                    ),
                    "id": uuid.uuid4().hex,
                    "pin_app": self.AD.threading.app_should_be_pinned(name),
                    "pin_thread": pin,
                    "running": True,
                }

                # load the module path into app entity
                module_path = await utils.run_in_executor(self, os.path.abspath, modname.__file__)
                await self.set_state(name, module_path=module_path)

        else:
            self.logger.warning(
                "Unable to find module module %s - '%s' is not initialized",
                app_args["module"],
                name,
            )
            await self.increase_inactive_apps(name)

    def init_plugin_object(self, name, object):
        self.objects[name] = {
            "type": "plugin",
            "object": object,
            "id": uuid.uuid4().hex,
            "pin_app": False,
            "pin_thread": -1,
            "running": False,
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

    async def read_config(self):  # noqa: C901
        new_config = None

        for root, subdirs, files in await utils.run_in_executor(self, os.walk, self.AD.app_dir):
            subdirs[:] = [d for d in subdirs if d not in self.AD.exclude_dirs and "." not in d]
            if root[-11:] != "__pycache__" and root[0] != ".":
                for file in files:
                    if file[-5:] == self.ext and file[0] != ".":
                        path = os.path.join(root, file)
                        self.logger.debug("Reading %s", path)
                        config = await utils.run_in_executor(self, self.read_config_file, path)
                        valid_apps = {}
                        if type(config).__name__ == "dict":
                            for app in config:
                                if config[app] is not None:
                                    app_valid = True
                                    if app == "global_modules":
                                        self.logger.warning(
                                            "global_modules directive has been deprecated and will be removed in a future release"
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
                                                    "global_modules should be a list or a string in File '%s' - ignoring",
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
        for root, subdirs, files in os.walk(self.AD.app_dir):
            subdirs[:] = [d for d in subdirs if d not in self.AD.exclude_dirs and "." not in d]
            if root[-11:] != "__pycache__" and root[0] != ".":
                for file in files:
                    if file[-5:] == self.ext and file[0] != ".":
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

    # Run in executor
    def read_config_file(self, file):
        try:
            return utils.read_config_file(file)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error loading config file: %s", file)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

    # noinspection PyBroadException
    async def check_config(self, silent=False, add_threads=True):  # noqa: C901
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
                    self.total_apps_sensor, state=active_apps + inactive, attributes={"friendly_name": "Total Apps"}
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

            return {
                "init": initialize_apps,
                "term": terminate_apps,
                "total": total_apps,
                "active": active_apps,
            }
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
        module = self.get_module_from_path(file)
        for app in self.app_config:
            if "module" in self.app_config[app] and self.app_config[app]["module"] == module:
                return app
        return None

    # noinspection PyBroadException
    # Run in executor
    def read_app(self, file, reload=False):
        name = os.path.basename(file)
        module_name = os.path.splitext(name)[0]
        # Import the App
        if reload:
            self.logger.info("Reloading Module: %s", file)

            file, ext = os.path.splitext(name)
            #
            # Reload
            #
            try:
                importlib.reload(self.modules[module_name])
            except KeyError:
                if name not in sys.modules:
                    # Probably failed to compile on initial load
                    # so we need to re-import not reload
                    self.read_app(file)
                else:
                    # A real KeyError!
                    raise
        else:
            app = self.get_app_from_file(file)
            if app is not None:
                if "global" in self.app_config[app] and self.app_config[app]["global"] is True:
                    # It's a new style global module
                    self.logger.info("Loading Global Module: %s", file)
                    self.modules[module_name] = importlib.import_module(module_name)
                else:
                    # A regular app
                    self.logger.info("Loading App Module: %s", file)
                    if module_name not in self.modules:
                        self.modules[module_name] = importlib.import_module(module_name)
                    else:
                        # We previously imported it so we need to reload to pick up any potential changes
                        importlib.reload(self.modules[module_name])
            elif "global_modules" in self.app_config and module_name in self.app_config["global_modules"]:
                self.logger.info("Loading Global Module: %s", file)
                self.modules[module_name] = importlib.import_module(module_name)
            # elif "global" in
            else:
                if self.AD.missing_app_warnings:
                    self.logger.warning("No app description found for: %s - ignoring", file)

    @staticmethod
    def get_module_from_path(path):
        name = os.path.basename(path)
        module_name = os.path.splitext(name)[0]
        return module_name

    def get_file_from_module(self, mod):
        for file in self.monitored_files:
            module_name = self.get_module_from_path(file)
            if module_name == mod:
                return file

        return None

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
    def file_in_modules(file, modules):
        for mod in modules:
            if mod["name"] == file:
                return True
        return False

    @staticmethod
    def check_file(file):
        fh = open(file)
        fh.close()

    # @_timeit
    async def check_app_updates(self, plugin: str = None, mode: str = "normal"):  # noqa: C901
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

            # Get list of apps we need to terminate and/or initialize

            apps = await self.check_config()

            found_files = []
            modules = []
            for root, subdirs, files in await utils.run_in_executor(self, os.walk, self.AD.app_dir, topdown=True):
                # print(root, subdirs, files)
                #
                # Prune dir list
                #
                subdirs[:] = [d for d in subdirs if d not in self.AD.exclude_dirs and "." not in d]

                if root[-11:] != "__pycache__" and root[0] != ".":
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
                            modules.append({"name": file, "reload": True})
                            self.monitored_files[file] = modified
                    else:
                        self.logger.debug("Found module %s", file)
                        modules.append({"name": file, "reload": False})
                        self.monitored_files[file] = modified
                except IOError as err:
                    self.logger.warning("Unable to read app %s: %s - skipping", file, err)

            # Check for deleted modules and add them to the terminate list
            deleted_modules = []
            for file in self.monitored_files:
                if file not in found_files or mode == "term":
                    deleted_modules.append(file)
                    self.logger.info("Removing module %s", file)

            for file in deleted_modules:
                del self.monitored_files[file]
                for app in self.apps_per_module(self.get_module_from_path(file)):
                    apps["term"][app] = 1

            # Add any apps we need to reload because of file changes

            for module in modules:
                for app in self.apps_per_module(self.get_module_from_path(module["name"])):
                    if module["reload"]:
                        apps["term"][app] = 1
                    apps["init"][app] = 1

                for gm in self.get_global_modules():
                    if gm == self.get_module_from_path(module["name"]):
                        for app in self.apps_per_global_module(gm):
                            if module["reload"]:
                                apps["term"][app] = 1
                            apps["init"][app] = 1

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
                        apps["term"][app] = 1
                        apps["init"][app] = 1

            # Terminate apps

            apps_terminated = {}  # store apps properly terminated is any
            if apps is not None and apps["term"]:
                prio_apps = self.get_app_deps_and_prios(apps["term"], mode)

                # Mark dependant global modules for reload
                for app in sorted(prio_apps, key=prio_apps.get):
                    found = False
                    for module in modules:
                        if module["name"] == self.get_path_from_app(app):
                            found = True
                            module["reload"] = True
                    if found is False:
                        if self.get_path_from_app(app) is not None:
                            modules.append({"name": self.get_path_from_app(app), "reload": True})

                # Terminate Apps
                for app in sorted(prio_apps, key=prio_apps.get, reverse=True):
                    executed = await self.stop_app(app)
                    apps_terminated[app] = executed

            # Load/reload modules

            for mod in modules:
                try:
                    await utils.run_in_executor(self, self.read_app, mod["name"], mod["reload"])
                except Exception:
                    self.error.warning("-" * 60)
                    self.error.warning("Unexpected error loading module: %s:", mod["name"])
                    self.error.warning("-" * 60)
                    self.error.warning(traceback.format_exc())
                    self.error.warning("-" * 60)
                    if self.AD.logging.separate_error_log() is True:
                        self.logger.warning("Unexpected error loading module: %s:", mod["name"])

                    self.logger.warning("Removing associated apps:")
                    module = self.get_module_from_path(mod["name"])
                    for app in self.app_config:
                        if "module" in self.app_config[app] and self.app_config[app]["module"] == module:
                            if apps["init"] and app in apps["init"]:
                                del apps["init"][app]
                                self.logger.warning("%s", app)
                                await self.set_state(app, state="compile_error")

            if apps is not None and apps["init"]:
                prio_apps = self.get_app_deps_and_prios(apps["init"], mode)

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

            if self.AD.check_app_updates_profile is True:
                pr.disable()

            s = io.StringIO()
            sortby = "cumulative"
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            self.check_app_updates_profile_stats = s.getvalue()

            self.apps_initialized = True

    def get_path_from_app(self, app):
        module = self.app_config[app]["module"]
        return self.get_file_from_module(module)

    def get_app_deps_and_prios(self, applist, mode):
        # Build a list of modules and their dependencies

        deplist = []
        for app in applist:
            if app not in deplist:
                deplist.append(app)
            self.get_dependent_apps(app, deplist)

        # Need to give the topological sort a full list of apps or it will fail
        full_list = list(self.app_config.keys())

        deps = []

        for app in full_list:
            dependees = []
            for dep in self.get_app_dependencies(app):
                if dep in self.app_config:
                    dependees.append(dep)
                else:
                    self.logger.warning("Unable to find app %s in dependencies for %s", dep, app)
                    self.logger.warning("Ignoring app %s", app)
            deps.append((app, dependees))

        prio_apps = {}
        prio = float(50.1)
        try:
            for app in self.topological_sort(deps):
                if (
                    "dependencies" in self.app_config[app]
                    or app in self.global_module_dependencies
                    or self.app_has_dependents(app)
                ):
                    prio_apps[app] = prio
                    prio += float(0.0001)
                else:
                    if mode == "init" and "priority" in self.app_config[app]:
                        prio_apps[app] = float(self.app_config[app]["priority"])
                    else:
                        prio_apps[app] = float(50)
        except ValueError:
            pass

        # now we remove the ones we aren't interested in

        final_apps = {}
        for app in prio_apps:
            if app in deplist:
                final_apps[app] = prio_apps[app]

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

    def apps_per_module(self, module):
        apps = []
        for app in self.app_config:
            if app not in self.non_apps and self.app_config[app]["module"] == module:
                apps.append(app)

        return apps

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

    def create_app(self, app=None, **kwargs):  # @next-release create_app()
        """Used to create an app, which is written to a Yaml file"""

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
            app_file = os.path.join(app_directory, f"{app}.yaml")
            self.logger.info("Creating app using filename %s", app_file)

        else:
            if app_file[4:] != ".yaml":
                app_file = f"{app_file}.yaml"

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
            utils.write_to_file(app_file, **new_config)

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

    def edit_app(self, app, **kwargs):  # @next-release edit_app()
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
            utils.write_to_file(app_file, **new_config)

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

    def remove_app(self, app, **kwargs):  # @next-release remove_app()
        """Used to remove an app"""

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
                utils.write_to_file(app_file, **file_config)

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
            asyncio.ensure_future(self.check_app_updates(mode="init"))

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

    async def increase_active_apps(self, name):
        if name not in self.active_apps:
            self.active_apps.append(name)

        if name in self.inactive_apps:
            self.inactive_apps.remove(name)

        active_apps = len(self.active_apps)
        inactive_apps = len(self.inactive_apps)

        await self.set_state(self.active_apps_sensor, state=active_apps)
        await self.set_state(self.inactive_apps_sensor, state=inactive_apps)

    async def increase_inactive_apps(self, name):
        if name not in self.inactive_apps:
            self.inactive_apps.append(name)

        if name in self.active_apps:
            self.active_apps.remove(name)

        inactive_apps = len(self.inactive_apps)
        active_apps = len(self.active_apps)

        await self.set_state(self.active_apps_sensor, state=active_apps)
        await self.set_state(self.inactive_apps_sensor, state=inactive_apps)
