import abc
import asyncio
import datetime
import importlib
import sys
import traceback
from collections.abc import Generator, Iterable
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Type, Union

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
    last_check_ts: float

    ready_event: asyncio.Event

    constraints: list

    stopping: bool

    def __init__(self, ad: "AppDaemon", name: str, config: PluginConfig):
        self.AD = ad
        self.name = name
        self.config = config
        self.logger = self.AD.logging.get_child(name)
        self.error = self.logger
        self.ready_event = asyncio.Event()
        self.constraints = []
        self.stopping = False

        # Performance Data
        self.bytes_sent = 0
        self.bytes_recv = 0
        self.requests_sent = 0
        self.updates_recv = 0
        self.last_check_ts = 0
    
    @property
    def namespace(self) -> str:
        return self.config.namespace

    @namespace.setter
    def namespace(self, new: str):
        self.config.namespace = new

    @property
    def is_ready(self) -> bool:
        return self.ready_event.is_set()

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
    """Dictionary storing the instantiated plugin objects. Has namespaces as
    keys and the instantiated plugin objects as values.
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
            plugin_file = plugin / f"{plugin.name}plugin.py"
            if not plugin_file.exists():
                self.logger.warning(f"Plugin module {plugin_file} does not exist")

        # Now custom plugins
        custom_plugin_dir = self.AD.config_dir / "custom_plugins"
        if custom_plugin_dir.exists() and custom_plugin_dir.is_dir():
            custom_plugins = [p for p in custom_plugin_dir.iterdir() if p.is_dir(follow_symlinks=True) and not p.name.startswith("_")]
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

    def get_plugin_object(self, namespace: str) -> PluginBase:
        if not (plugin := self.plugin_objs.get(namespace)):
            for _, cfg in self.config.items():
                if namespace in cfg.namespaces:
                    plugin = self.plugin_objs[namespace]
                    break
            else:
                plugin = {}

        return plugin.get("object")

    def get_plugin_from_namespace(self, namespace: str) -> str:
        """Gets the name of the plugin that's associated with the given namespace.

        This function is needed because plugins can have multiple namespaces associated with them.
        """
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

            self.refresh_update_time(name)

            self.logger.debug("Plugin started meta: %s = %s", name, meta)

            self.process_meta(meta, namespace)

            if not self.stopping:
                self.plugin_meta[namespace] = meta

                if namespaces != []:  # there are multiple namesapces
                    for namesp in namespaces:
                        if state[namesp] is not None:
                            await self.AD.state.set_namespace_state(namesp, state[namesp], self.config[name].persist_entities)

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
                    await self.AD.app_management.check_app_updates(self.get_plugin_from_namespace(namespace), mode=UpdateMode.INIT)
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
        await self.AD.events.process_event(
            namespace,
            {"event_type": "plugin_stopped", "data": {"name": name}}
        )

    async def get_plugin_meta(self, namespace: str):
        try:
            return self.plugin_meta[namespace]
        except Exception:
            for _, cfg in self.config.items():
                return cfg.namespace

    async def wait_for_plugins(self):
        self.logger.info('Waiting for plugins to be ready')
        events: Iterable[asyncio.Event] = (
            plugin['object'].ready_event for plugin in self.plugin_objs.values()
        )
        tasks = (self.AD.loop.create_task(e.wait()) for e in events)
        await asyncio.wait(tasks)
        self.logger.info('All plugins ready')

    def get_config_for_namespace(self, namespace: str) -> PluginConfig:
        plugin_name = self.get_plugin_from_namespace(namespace)
        return self.config[plugin_name]

    @property
    def active_plugins(self) -> Generator[tuple[PluginBase, PluginConfig], None, None]:
        for namespace, plugin_cfg in self.plugin_objs.items():
            if plugin_cfg["active"]:
                cfg = self.get_config_for_namespace(namespace)
                yield plugin_cfg["object"], cfg

    def refresh_update_time(self, plugin_name: str):
        self.last_plugin_state[plugin_name] = datetime.datetime.now()

    def time_since_plugin_update(self, plugin_name: str) -> datetime.timedelta:
        return datetime.datetime.now() - self.last_plugin_state[plugin_name]

    async def update_plugin_state(self):
        for plugin, cfg in self.active_plugins:
            if self.time_since_plugin_update(plugin.name) > cfg.refresh_delay:
                self.logger.debug(f"Refreshing {plugin.name}[{cfg.type}] state")
                try:
                    state = await asyncio.wait_for(
                        plugin.get_complete_state(),
                        timeout=cfg.refresh_timeout
                    )
                except asyncio.TimeoutError:
                    self.logger.warning(
                        "Timeout refreshing %s state - retrying in %s seconds",
                        plugin.name,
                        cfg.refresh_delay.total_seconds(),
                    )
                except Exception:
                    self.logger.warning(
                        "Unexpected error refreshing %s state - retrying in in %s seconds",
                        plugin.name,
                        cfg.refresh_delay.total_seconds(),
                    )
                else:
                    if state is not None:
                        if cfg.namespaces:
                            ns = [cfg.namespace] + cfg.namespaces
                        else:
                            ns = cfg.namespace
                        self.AD.state.update_namespace_state(ns, state)
                finally:
                    self.refresh_update_time(plugin)

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
