import sys
import os
import traceback
import datetime
import asyncio
import async_timeout

from appdaemon.appdaemon import AppDaemon

class PluginBase:

    """
    Base class for plugins to set up _logging
    """

    def __init__(self, ad: AppDaemon, name, args):

        self.AD = ad
        self.logger = self.AD.logging.get_child(name)


    def set_log_level(self, level):
        self.logger.setLevel(self.AD.logging.log_levels[level])


class Plugins:

    required_meta = ["latitude", "longitude", "elevation", "time_zone"]

    def __init__(self, ad: AppDaemon, kwargs):

        self.AD = ad
        self.plugins = kwargs
        self.stopping = False

        self.plugin_meta = {}
        self.plugin_objs = {}
        self.last_plugin_state = {}

        self.logger = ad.logging.get_child("_plugin_management")
        self.error = self.AD.logging.get_error()

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
                if "disable" in self.plugins[name] and self.plugins[name]["disable"] is True:
                    self.logger.info("Plugin '%s' disabled", name)
                else:

                    if "refresh_delay" not in self.plugins[name]:
                        self.plugins[name]["refresh_delay"] = 600

                    if "refresh_timeout" not in self.plugins[name]:
                        self.plugins[name]["refresh_timeout"] = 30

                    basename = self.plugins[name]["type"]
                    type = self.plugins[name]["type"]
                    module_name = "{}plugin".format(basename)
                    class_name = "{}Plugin".format(basename.capitalize())

                    full_module_name = None
                    for plugin in plugins:
                        if os.path.basename(plugin) == type:
                            full_module_name = "{}".format(module_name)
                            self.logger.info("Loading Custom Plugin %s using class %s from module %s", name, class_name, module_name)
                            break

                    if full_module_name is None:
                        #
                        # Not a custom plugin, assume it's a built in
                        #
                        full_module_name = "{}".format(module_name)
                        self.logger.info("Loading Plugin %s using class %s from module %s", name, class_name, module_name)
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
                        self.logger.warning("error loading plugin: %s - ignoring", name)
                        self.logger.warning('-' * 60)
                        self.logger.warning(traceback.format_exc())
                        self.logger.warning('-' * 60)

    def stop(self):
        self.logger.debug("stop() called for plugin_management")
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

    async def get_plugin_object(self, name):
        if name in self.plugin_objs:
            return self.plugin_objs[name]["object"]
        else:
            return None

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
        self.logger.debug("Plugin started: %s", name)
        try:
            self.last_plugin_state[namespace] = datetime.datetime.now()

            self.logger.debug("Plugin started meta: %s = %s", name, meta)

            self.process_meta(meta, namespace)

            if not self.stopping:
                self.plugin_meta[namespace] = meta
                self.AD.state.set_namespace_state(namespace, state)

                if not first_time:
                    await self.AD.app_management.check_app_updates(self.get_plugin_from_namespace(namespace), mode="init")
                else:
                    self.logger.info("Got initial state from namespace %s", namespace)

                self.plugin_objs[namespace]["active"] = True
                await self.AD.events.process_event(namespace, {"event_type": "plugin_started", "data": {"name": name}})
        except:
            self.error.warning('-' * 60)
            self.error.warning("WARNING", "Unexpected error during notify_plugin_started()")
            self.error.warning("WARNING", '-' * 60)
            self.error.warning("WARNING", traceback.format_exc())
            self.error.warning("WARNING", '-' * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning("Logged an error to %s", self.AD.logging.get_filename("error_log"))

    async def notify_plugin_stopped(self, name, namespace):
        self.plugin_objs[namespace]["active"] = False
        await self.AD.events.process_event(namespace, {"event_type": "plugin_stopped", "data": {"name": name}})

    async def get_plugin_meta(self, namespace):
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

                name = self.get_plugin_from_namespace(plugin)
                if datetime.datetime.now() - self.last_plugin_state[plugin] > datetime.timedelta(
                        seconds=self.plugins[name]["refresh_delay"]):
                    try:
                        self.logger.debug("Refreshing %s state", name)

                        with async_timeout.timeout(self.plugins[name]["refresh_timeout"], loop=self.AD.loop) as t:
                            state = await self.plugin_objs[plugin]["object"].get_complete_state()

                        if state is not None:
                            self.AD.state.update_namespace_state(plugin, state)

                    except asyncio.TimeoutError:
                        self.logger.warning("Timeout refreshing %s state - retrying in 10 minutes", plugin)
                    except:
                        self.logger.warning("Unexpected error refreshing %s state - retrying in 10 minutes", plugin)
                    finally:
                        self.last_plugin_state[plugin] = datetime.datetime.now()

    def required_meta_check(self):
        OK = True
        for key in self.required_meta:
            if getattr(self.AD, key) == None:
                # No value so bail
                self.logger.error("Required attribute not set or obtainable from any plugin: %s", key)
                OK = False
        return OK

    async def get_plugin_api(self, plugin_name, name, _logging, args, config, app_config, global_vars):
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            module_name = "{}api".format(plugin["type"])
            mod = __import__(module_name, globals(), locals(), [module_name], 0)
            app_class = getattr(mod, plugin["type"].title())
            api = app_class(self.AD, name, _logging, args, config, app_config, global_vars)
            if "namespace" in plugin:
                api.set_namespace(plugin["namespace"])
            else:
                api.set_namespace("default")
            return api

        else:
            self.logger.warning("Unknown Plugin Configuration in get_plugin_api()")
            return None
