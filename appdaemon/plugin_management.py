import abc
import asyncio
import datetime
import importlib
import sys
import traceback
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Type, Union

import async_timeout

from .app_management import UpdateMode
from .models.ad_config import PluginConfig

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class PluginBase(abc.ABC):
    """
    Base class for plugins to set up _logging
    """

    AD: "AppDaemon"
    name: str
    config: PluginConfig
    logger: Logger
    plugin_meta: Dict[str, Dict]
    plugins: Dict[str, Dict]

    bytes_sent: int
    bytes_recv: int
    requests_sent: int
    updates_recv: int
    last_check_ts: int

    stopping: bool

    def __init__(self, ad: "AppDaemon", name: str, config: PluginConfig):
        self.AD = ad
        self.name = name
        self.config = config
        self.logger = self.AD.logging.get_child(name)
        self.error = self.logger
        self.stopping = False

        # Performance Data
        self.bytes_sent = 0
        self.bytes_recv = 0
        self.requests_sent = 0
        self.updates_recv = 0
        self.last_check_ts = 0

    def get_namespace(self):
        return self.config.namespace

    @property
    def namespace(self) -> str:
        return self.config.namespace

    @namespace.setter
    def namespace(self, new: str):
        self.config.namespace = new

    def set_log_level(self, level):
        self.logger.setLevel(self.AD.logging.log_levels[level])

    async def perf_data(self) -> Dict[str, Union[int, float]]:
        data = {
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "requests_sent": self.requests_sent,
            "updates_recv": self.updates_recv,
            "duration": await self.AD.sched.get_now_ts() - self.last_check_ts,
        }

        self.bytes_sent = 0
        self.bytes_recv = 0
        self.requests_sent = 0
        self.updates_recv = 0
        self.last_check_ts = await self.AD.sched.get_now_ts()

        return data

    def update_perf(self, **kwargs):
        self.bytes_sent += kwargs.get("bytes_sent", 0)
        self.bytes_recv += kwargs.get("bytes_recv", 0)
        self.requests_sent += kwargs.get("requests_sent", 0)
        self.updates_recv += kwargs.get("updates_recv", 0)

    @abc.abstractmethod
    async def get_updates(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def get_complete_state(self):
        raise NotImplementedError

    # @abc.abstractmethod
    async def remove_entity(self, namespace: str, entity: str) -> None:
        pass

    # @abc.abstractmethod
    async def set_plugin_state(self):
        raise NotImplementedError

    # @abc.abstractmethod
    async def fire_plugin_event(self):
        raise NotImplementedError


class PluginManagement:
    """Subsystem container for managing plugins"""

    AD: "AppDaemon"
    """Reference to the top-level AppDaemon container object
    """
    config: dict[str, PluginConfig]
    """Config as defined in the appdaemon.plugins section of appdaemon.yaml
    """
    logger: Logger
    """Standard python logger named ``AppDaemon._plugin_management``
    """
    error: Logger
    """Standard python logger named ``Error``
    """
    stopping: bool
    plugin_meta: Dict[str, dict]
    """Dictionary storing the metadata for the loaded plugins
    """
    plugin_objs: Dict[str, Any]
    """Dictionary storing the instantiated plugin objects
    """
    required_meta = ["latitude", "longitude", "elevation", "time_zone"]
    last_plugin_state: dict[str, datetime.datetime]
    stopping: bool
    """Flag for if PluginManagement should be shutting down
    """

    def __init__(self, ad: "AppDaemon", config: dict[str, PluginConfig]):
        self.AD = ad
        self.config = config
        self.stopping = False

        self.plugin_meta = {}
        self.plugin_objs = {}
        self.last_plugin_state = {}

        self.perf_count = 0

        self.logger = ad.logging.get_child("_plugin_management")
        self.error = self.AD.logging.get_error()

        # Add built in plugins to path
        for plugin in self.plugin_paths:
            sys.path.insert(0, plugin.as_posix())
            assert (plugin / f"{plugin.name}plugin.py").exists(), "Plugin module does not exist"

        # Now custom plugins
        custom_plugin_dir = self.AD.config_dir / "custom_plugins"
        if custom_plugin_dir.exists() and custom_plugin_dir.is_dir():
            custom_plugins = [
                p for p in custom_plugin_dir.iterdir() if p.is_dir(follow_symlinks=True) and not p.name.startswith("_")
            ]
        else:
            custom_plugins = []
        for plugin in custom_plugins:
            sys.path.insert(0, plugin.as_posix())
            assert (plugin / f"{plugin.name}plugin.py").exists(), "Plugin module does not exist"

        # get the names up here to avoid some unnecessary iteration later
        built_ins = self.plugin_names

        for name, cfg in self.config.items():
            if self.config[name].disabled:
                self.logger.info("Plugin '%s' disabled", name)
            else:
                if name.lower() in built_ins:
                    msg = "Loading Plugin %s using class %s from module %s"
                else:
                    msg = "Loading Custom Plugin %s using class %s from module %s"
                self.logger.info(
                    msg,
                    name,
                    cfg.class_name,
                    cfg.module_name,
                )

                try:
                    module = importlib.import_module(cfg.module_name)
                    plugin_class: Type[PluginBase] = getattr(module, cfg.class_name)
                    plugin: PluginBase = plugin_class(self.AD, name, self.config[name])
                    namespace = plugin.config.namespace

                    if namespace in self.plugin_objs:
                        raise ValueError(f"Duplicate namespace: {namespace}")

                    self.plugin_objs[namespace] = {"object": plugin, "active": False, "name": name}

                    #
                    # Create app entry for the plugin so we can listen_state/event
                    #
                    self.AD.app_management.add_plugin_object(name, plugin, self.config[name].use_dictionary_unpacking)

                    self.AD.loop.create_task(plugin.get_updates())
                except Exception:
                    self.logger.warning("error loading plugin: %s - ignoring", name)
                    self.logger.warning("-" * 60)
                    self.logger.warning(traceback.format_exc())
                    self.logger.warning("-" * 60)

    @property
    def plugin_dir(self) -> Path:
        """Built-in plugin base directory"""
        return Path(__file__).parent / "plugins"

    @property
    def plugin_paths(self) -> list[Path]:
        """Paths to the built-in plugins"""
        return [d for d in self.plugin_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]

    @property
    def plugin_names(self) -> set[str]:
        """Names of the built-in plugins"""
        return set(p.name.lower() for p in self.plugin_paths)

    @property
    def namespaces(self) -> list[str]:
        return self.AD.namespaces

    def stop(self):
        self.logger.debug("stop() called for plugin_management")
        self.stopping = True
        for plugin in self.plugin_objs:
            stop_func = self.plugin_objs[plugin]["object"].stop

            if asyncio.iscoroutinefunction(stop_func):
                self.AD.loop.create_task(stop_func())
            else:
                stop_func()

            name = self.plugin_objs[plugin]["name"]
            self.AD.loop.create_task(self.AD.callbacks.clear_callbacks(name))
            self.AD.futures.cancel_futures(name)

    def run_plugin_utility(self):
        for plugin in self.plugin_objs:
            if hasattr(self.plugin_objs[plugin]["object"], "utility"):
                self.plugin_objs[plugin]["object"].utility()

    async def get_plugin_perf_data(self):
        # Grab stats every 10th time we are called (this will be roughly a 10 second average)
        self.perf_count += 1

        if self.perf_count < 10:
            return

        self.perf_count = 0

        for plugin in self.plugin_objs:
            if hasattr(self.plugin_objs[plugin]["object"], "perf_data"):
                p_data = await self.plugin_objs[plugin]["object"].perf_data()
                await self.AD.state.set_state(
                    "plugin",
                    "admin",
                    f"plugin.{self.get_plugin_from_namespace(plugin)}",
                    bytes_sent_ps=round(p_data["bytes_sent"] / p_data["duration"], 1),
                    bytes_recv_ps=round(p_data["bytes_recv"] / p_data["duration"], 1),
                    requests_sent_ps=round(p_data["requests_sent"] / p_data["duration"], 1),
                    updates_recv_ps=round(p_data["updates_recv"] / p_data["duration"], 1),
                )

    def process_meta(self, meta, namespace):
        if meta is not None:
            for key in self.required_meta:
                if getattr(self.AD, key) is None:
                    if key in meta:
                        # We have a value so override
                        setattr(self.AD, key, meta[key])

    def get_plugin_cfg(self, plugin: str) -> PluginConfig:
        return self.config[plugin]

    async def get_plugin_object(self, namespace: str) -> PluginBase:
        if namespace in self.plugin_objs:
            return self.plugin_objs[namespace]["object"]
        else:
            for _, cfg in self.config.items():
                if namespace in cfg.namespaces:
                    return self.plugin_objs[cfg.namespace]["object"]

    def get_plugin_from_namespace(self, namespace: str) -> str:
        for name, cfg in self.config.items():
            if namespace == cfg.namespace or namespace in cfg.namespaces:
                return name
            elif namespace not in self.config and namespace == "default":
                return name
        else:
            raise NameError(f"Bad namespace: {namespace}")

            # elif "namespaces" in self.config[name] and namespace in self.config[name]["namespaces"]:
            #     return name
            # elif "namespace" not in self.config[name] and namespace == "default":
            #     return name

    async def notify_plugin_started(self, name: str, ns: str, meta: dict, state, first_time: bool = False):
        """Notifys the AD internals that the plugin has started

        - sets the namespace state in self.AD.state
        - adds the plugin entity in self.AD.state
        - sets the pluginobject to active
        - fires a ``plugin_started`` event

        Arguments:
            first_time: if True, then it runs ``self.AD.app_management.check_app_updates`` with UpdateMode.INIT
        """
        self.logger.debug("Plugin started: %s", name)
        try:
            namespaces = []
            if isinstance(ns, dict):  # its a dictionary, so there is namespace mapping involved
                namespace = ns["namespace"]
                namespaces.extend(ns["namespaces"])
                self.config[name].namespaces = namespaces

            else:
                namespace = ns

            self.last_plugin_state[namespace] = datetime.datetime.now()

            self.logger.debug("Plugin started meta: %s = %s", name, meta)

            self.process_meta(meta, namespace)

            if not self.stopping:
                self.plugin_meta[namespace] = meta

                if namespaces != []:  # there are multiple namesapces
                    for namesp in namespaces:
                        if state[namesp] is not None:
                            await self.AD.state.set_namespace_state(
                                namesp, state[namesp], self.config[name].persist_entities
                            )

                    # now set the main namespace
                    await self.AD.state.set_namespace_state(
                        namespace,
                        state[namespace],
                        self.config[name].persist_entities,
                    )

                else:
                    await self.AD.state.set_namespace_state(
                        namespace,
                        state,
                        self.config[name].persist_entities,
                    )

                if not first_time:
                    await self.AD.app_management.check_app_updates(
                        self.get_plugin_from_namespace(namespace), mode=UpdateMode.INIT
                    )
                else:
                    #
                    # Create plugin entity
                    #
                    await self.AD.state.add_entity(
                        "admin",
                        f"plugin.{name}",
                        "active",
                        {
                            "bytes_sent_ps": 0,
                            "bytes_recv_ps": 0,
                            "requests_sent_ps": 0,
                            "updates_recv_ps": 0,
                            "totalcallbacks": 0,
                            "instancecallbacks": 0,
                        },
                    )

                    self.logger.info("Got initial state from namespace %s", namespace)

                self.plugin_objs[namespace]["active"] = True
                await self.AD.events.process_event(namespace, {"event_type": "plugin_started", "data": {"name": name}})
        except Exception:
            self.error.warning("-" * 60)
            self.error.warning("Unexpected error during notify_plugin_started()")
            self.error.warning("-" * 60)
            self.error.warning(traceback.format_exc())
            self.error.warning("-" * 60)
            if self.AD.logging.separate_error_log() is True:
                self.logger.warning("Logged an error to %s", self.AD.logging.get_filename("error_log"))

    async def notify_plugin_stopped(self, name, namespace):
        self.plugin_objs[namespace]["active"] = False
        await self.AD.events.process_event(namespace, {"event_type": "plugin_stopped", "data": {"name": name}})

    async def get_plugin_meta(self, namespace: str):
        try:
            return self.plugin_meta[namespace]
        except Exception:
            for _, cfg in self.config.items():
                return cfg.namespace

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
                    seconds=self.config[name].refresh_delay
                ):
                    try:
                        self.logger.debug("Refreshing %s state", name)

                        with async_timeout.timeout(self.config[name].refresh_timeout):
                            obj = await self.get_plugin_object(plugin)
                            state = await obj.get_complete_state()

                        if state is not None:
                            if (
                                "namespaces" in self.config[name]
                            ):  # its a plugin using namespace mapping like adplugin so expecting a list
                                namespace = self.config[name].namespaces
                                # add the main namespace
                                namespace.append(self.config[name].namespace)
                            else:
                                namespace = plugin

                            self.AD.state.update_namespace_state(namespace, state)

                    except asyncio.TimeoutError:
                        self.logger.warning(
                            "Timeout refreshing %s state - retrying in %s seconds",
                            plugin,
                            self.config[name].refresh_delay,
                        )
                    except Exception:
                        self.logger.warning(
                            "Timeout refreshing %s state - retrying in %s seconds",
                            plugin,
                            self.config[name].refresh_delay,
                        )
                    finally:
                        self.last_plugin_state[plugin] = datetime.datetime.now()

    def required_meta_check(self):
        OK = True
        for key in self.required_meta:
            if getattr(self.AD, key) is None:
                # No value so bail
                self.logger.error("Required attribute not set or obtainable from any plugin: %s", key)
                OK = False
        return OK

    async def get_plugin_api(self, plugin_name, name, _logging, args, config, app_config, global_vars):
        if plugin_name in self.config:
            plugin = self.config[plugin_name]
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
