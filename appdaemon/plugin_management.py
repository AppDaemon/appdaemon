import sys
import os
import traceback
import datetime
import asyncio

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon

class PluginBase:

    """
    Base class for plugins to set up logging
    """

    def __init__(self, ad: AppDaemon, name, args):

        self.AD = ad
        self._logger = self.AD.logging.get_logger().getChild(name)
        if "log_level" in args:
            self._logger.setLevel(args["log_level"])
        else:
            self._logger.setLevel("INFO")

    def log(self, level, msg, *args, **kwargs):
        self._logger.log(self.AD.logging.log_levels[level], msg, *args, **kwargs)

    def set_log_level(self, level):
        self._logger.setLevel(self.AD.logging.log_levels[level])


class Plugins:

    required_meta = ["latitude", "longitude", "elevation", "time_zone"]

    def __init__(self, ad: AppDaemon, kwargs):

        self.AD = ad
        self.plugins = kwargs
        self.stopping = False

        self.plugin_meta = {}
        self.plugin_objs = {}
        self.last_plugin_state = {}

        # Add built in plugins to path

        moddir = "{}/plugins".format(os.path.dirname(__file__))

        plugins = [f.path for f in os.scandir(moddir) if f.is_dir(follow_symlinks=True)]

        for plugin in plugins:
            sys.path.insert(0, plugin)

        # Now custom plugins

        plugins = []

        if os.path.isdir(os.path.join(self.AD.config_dir, "custom_plugins")):
            plugins = [f.path for f in os.scandir(os.path.join(self.AD.config_dir, "custom_plugins")) if f.is_dir(follow_symlinks=True)]

            for plugin in plugins:
                sys.path.insert(0, plugin)

        if self.plugins is not None:
            for name in self.plugins:
                basename = self.plugins[name]["type"]
                type = self.plugins[name]["type"]
                module_name = "{}plugin".format(basename)
                class_name = "{}Plugin".format(basename.capitalize())

                full_module_name = None
                for plugin in plugins:
                    if os.path.basename(plugin) == type:
                        full_module_name = "{}".format(module_name)
                        self.AD.logging.log("INFO",
                                 "Loading Custom Plugin {} using class {} from module {}".format(name, class_name,
                                                                                          module_name))
                        break

                if full_module_name is None:
                    #
                    # Not a custom plugin, assume it's a built in
                    #
                    full_module_name = "{}".format(module_name)
                    self.AD.logging.log("INFO",
                                "Loading Plugin {} using class {} from module {}".format(name, class_name,
                                                                                         module_name))
                try:

                    mod = __import__(full_module_name, globals(), locals(), [module_name], 0)

                    app_class = getattr(mod, class_name)

                    plugin = app_class(self.AD, name, self.plugins[name])

                    namespace = plugin.get_namespace()

                    if namespace in self.plugin_objs:
                        raise ValueError("Duplicate namespace: {}".format(namespace))

                    self.plugin_objs[namespace] = {"object": plugin, "active": False}

                    self.AD.loop.create_task(plugin.get_updates())
                except:
                    self.AD.logging.log("WARNING", "error loading plugin: {} - ignoring".format(name))
                    self.AD.logging.log("WARNING", '-' * 60)
                    self.AD.logging.log("WARNING", traceback.format_exc())
                    self.AD.logging.log("WARNING", '-' * 60)

    def stop(self):
        self.stopping = True
        for plugin in self.plugin_objs:
            self.plugin_objs[plugin]["object"].stop()


    def run_plugin_utility(self):
        for plugin in self.plugin_objs:
            if hasattr(self.plugin_objs[plugin]["object"].utility(), "utility"):
                self.plugin_objs[plugin]["object"].utility()

    def process_meta(self, meta, namespace):

        if meta is not None:
            for key in self.required_meta:
                if getattr(self.AD, key) == None:
                    if key in meta:
                        # We have a value so override
                        setattr(self.AD, key, meta[key])

    def get_plugin(self, plugin):
        return self.plugins[plugin]

    def get_plugin_from_namespace(self, namespace):
        if self.plugins is not None:
            for name in self.plugins:
                if "namespace" in self.plugins[name] and self.plugins[name]["namespace"] == namespace:
                    return name
                if "namespace" not in self.plugins[name] and namespace == "default":
                    return name
        else:
            return None

    async def notify_plugin_started(self, name, namespace, meta, state, first_time=False):
        self.AD.logging.log("DEBUG", "Plugin started: {}".format(name))
        try:
            self.last_plugin_state[namespace] = datetime.datetime.now()

            self.AD.logging.log("DEBUG", "Plugin started meta: {} = {}".format(name, meta))

            self.process_meta(meta, namespace)

            if not self.stopping:
                self.plugin_meta[namespace] = meta
                self.AD.state.set_namespace_state(namespace, state)

                if not first_time:
                    await utils.run_in_executor(self.AD.loop, self.AD.executor, self.AD.app_management.check_app_updates, self.get_plugin_from_namespace(namespace))
                else:
                    self.AD.logging.log("INFO", "Got initial state from namespace {}".format(namespace))

                self.plugin_objs[namespace]["active"] = True
                self.AD.events.process_event(namespace, {"event_type": "plugin_started", "data": {"name": name}})
        except:
            self.AD.logging.err("WARNING", '-' * 60)
            self.AD.logging.err("WARNING", "Unexpected error during notify_plugin_started()")
            self.AD.logging.err("WARNING", '-' * 60)
            self.AD.logging.err("WARNING", traceback.format_exc())
            self.AD.logging.err("WARNING", '-' * 60)
            if self.AD.errfile != "STDERR" and self.AD.logfile != "STDOUT":
                # When explicitly logging to stdout and stderr, suppress
                # verbose_log messages about writing an error (since they show up anyway)
                self.AD.logging.log(
                    "WARNING",
                    "Logged an error to {}".format(self.AD.errfile)
                )

    def notify_plugin_stopped(self, name, namespace):
        self.plugin_objs[namespace]["active"] = False
        self.AD.events.process_event(namespace, {"event_type": "plugin_stopped", "data": {"name": name}})

    def get_plugin(self, name):
        if name in self.plugin_objs:
            return self.plugin_objs[name]["object"]
        else:
            return None

    def get_plugin_meta(self, namespace):
        for name in self.plugins:
            if "namespace" not in self.plugins[name] and namespace == "default":
                return self.plugin_meta[namespace]
            elif "namespace" in self.plugins[name] and self.plugins[name]["namespace"] == namespace:
                return self.plugin_meta[namespace]

        return None

    async def wait_for_plugins(self):
        initialized = False
        while not initialized and self.stopping is False:
            initialized = True
            for plugin in self.plugin_objs:
                if self.plugin_objs[plugin]["active"] is False:
                    initialized = False
                    break
            await asyncio.sleep(1)

    async def update_plugin_state(self):
        for plugin in self.plugin_objs:
            if self.plugin_objs[plugin]["active"] is True:
                if datetime.datetime.now() - self.last_plugin_state[plugin] > datetime.timedelta(
                        minutes=10):
                    try:
                        self.AD.logging.log("DEBUG",
                                 "Refreshing {} state".format(plugin))

                        state = await self.plugin_objs[plugin]["object"].get_complete_state()

                        if state is not None:
                            self.AD.state.update_namespace_state(plugin, state)

                    except:
                        self.AD.logging.log("WARNING",
                                 "Unexpected error refreshing {} state - retrying in 10 minutes".format(plugin))
                    finally:
                        self.last_plugin_state[plugin] = datetime.datetime.now()

    def required_meta_check(self):
        OK = True
        for key in self.required_meta:
            if getattr(self.AD, key) == None:
                # No value so bail
                self.AD.logging.err("ERROR", "Required attribute not set or obtainable from any plugin: {}".format(key))
                OK = False
        return OK



