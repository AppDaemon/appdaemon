import abc
import asyncio
import datetime
import importlib
import sys
import traceback
from collections.abc import Generator, Iterable
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Type

from . import utils
from .app_management import UpdateMode
from .models.config import AppConfig
from .models.config.plugin import PluginConfig

if TYPE_CHECKING:
    from .adapi import ADAPI
    from .appdaemon import AppDaemon


class PluginBase(abc.ABC):
    """
    Base class for plugins to set up _logging
    """

    AD: "AppDaemon"
    name: str
    config: PluginConfig
    logger: Logger
    diag: Logger
    plugin_meta: Dict[str, Dict]
    plugins: Dict[str, Dict]

    bytes_sent: int
    bytes_recv: int
    requests_sent: int
    updates_recv: int
    last_check_ts: float

    connect_event: asyncio.Event
    ready_event: asyncio.Event

    constraints: list

    first_time: bool = True
    """Flag for this being the first time the plugin has made a connection.

    The first connection a plugin makes is handled a little differently
    because it'll be at startup and it'll be before any apps have been
    loaded.
    """

    stopping: bool = False
    """Flag that indicates whether AppDaemon is currently shutting down."""

    def __init__(self, ad: "AppDaemon", name: str, config: PluginConfig):
        self.AD = ad
        self.name = name
        self.config = config
        self.logger = self.AD.logging.get_child(name)
        self.diag = self.AD.logging.get_diag()
        self.error = self.logger
        self.connect_event = asyncio.Event()
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
        """Main namespace of the plugin"""
        return self.config.namespace

    @namespace.setter
    def namespace(self, new: str):
        self.config.namespace = new

    @property
    def namespaces(self) -> list[str]:
        """Extra namespaces for the plugin"""
        return self.config.namespaces

    @namespaces.setter
    def namespaces(self, new: Iterable[str]):
        match new:
            case str():
                new = [new]
            case Iterable():
                new = new if isinstance(new, list) else list(new)
        self.config.namespaces = new

    @property
    def all_namespaces(self) -> list[str]:
        """A list of namespaces that includes the main namespace as well as any
        extra ones."""
        return [self.namespace] + self.namespaces

    @property
    def is_ready(self) -> bool:
        return self.ready_event.is_set()

    def set_log_level(self, level):
        self.logger.setLevel(self.AD.logging.log_levels[level])

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
    # async def set_plugin_state(
    #     self,
    #     namespace: str,
    #     entity_id: str,
    #     state: Any | None = None,
    #     attributes: Any | None = None,
    # ) -> dict[str, Any] | None:
    #     pass

    # @abc.abstractmethod
    async def fire_plugin_event(self):
        raise NotImplementedError

    @utils.warning_decorator(error_text="Unexpected error during notify_plugin_started()")
    async def notify_plugin_started(self, meta: dict, state: dict):
        """Notifys the AD internals that the plugin has started

        - sets the namespace state in self.AD.state
        - adds the plugin entity in self.AD.state
        - sets the plugin object to active
        - fires a ``plugin_started`` event

        Arguments:
            meta (dict):
            state (dict):
        """
        if self.AD.stopping:
            return  # return early if stopping

        await self.AD.plugins.refresh_update_time(self.name)
        self.AD.plugins.process_meta(meta, self.name)

        event = {"event_type": "plugin_started", "data": {"name": self.name}}
        for ns in self.all_namespaces:
            event_coro = self.AD.events.process_event(ns, event)
            self.AD.loop.create_task(event_coro)
            self.AD.plugins.plugin_meta[ns] = meta
            await self.AD.state.set_namespace_state(
                namespace=ns,
                state=state,
                persist=self.config.persist_entities
            )

            # This accounts for the case where there's not a plugin associated with the object
            if po := self.AD.plugins.plugin_objs.get(ns):
                po["active"] = True

        admin_entity = f"plugin.{self.name}"
        if not self.AD.state.entity_exists("admin", admin_entity):
            await self.AD.state.add_entity(
                namespace="admin",
                entity=admin_entity,
                state="active",
                attributes={
                    "bytes_sent_ps": 0,
                    "bytes_recv_ps": 0,
                    "requests_sent_ps": 0,
                    "updates_recv_ps": 0,
                    "totalcallbacks": 0,
                    "instancecallbacks": 0,
                },
            )

        if not self.first_time:
            self.AD.loop.create_task(
                self.AD.app_management.check_app_updates(
                    plugin_ns=self.namespace,
                    mode=UpdateMode.PLUGIN_RESTART
            ))


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
    plugin_meta: Dict[str, dict[str, Any]]
    """Dictionary storing the metadata for the loaded plugins.
    {<namespace>: <metadata dict>}
    """
    plugin_objs: Dict[str, PluginBase]
    """Dictionary storing the instantiated plugin objects.
    ``{<namespace>: {
    "object": <PluginBase>,
    "active": <bool>,
    "name": <str>
    }}``
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
                    cfg.plugin_class,
                    cfg.plugin_module,
                )

                try:
                    module = importlib.import_module(cfg.plugin_module)
                    plugin_class: Type[PluginBase] = getattr(module, cfg.plugin_class)
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

    def process_meta(self, meta: dict, name: str):
        """Looks for certain keys in the metadata dict to override ones in the
        original AD config. For example, latitude and longitude from a Hass plugin
        """
        if meta is not None:
            for key in self.required_meta:
                if getattr(self.AD, key) is None:
                    if key in meta:
                        # We have a value so override
                        setattr(self.AD.config, key, meta[key])
                        self.logger.info(f"Overrode {key} in AD config from plugin {name}")

    def get_plugin_cfg(self, plugin: str) -> PluginConfig:
        return self.config[plugin]

    def get_plugin_object(self, namespace: str) -> PluginBase | None:
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

    async def notify_plugin_stopped(self, name: str, namespace: str):
        self.plugin_objs[namespace]["active"] = False
        data = {"event_type": "plugin_stopped", "data": {"name": name}}
        await self.AD.events.process_event(namespace, data)
        self.AD.loop.create_task(
            self.AD.app_management.check_app_updates(
                plugin_ns=namespace,
                mode=UpdateMode.PLUGIN_FAILED
        ))

    def get_plugin_meta(self, namespace: str) -> dict:
        return self.plugin_meta.get(namespace, {})

    async def wait_for_plugins(self, timeout: float | None = None):
        """Waits for the user-configured plugin startup conditions.

        Specifically, this waits for each of their ready events
        """
        self.logger.info('Waiting for plugins to be ready')
        events: Generator[asyncio.Event, None, None] = (
            plugin['object'].ready_event for plugin in self.plugin_objs.values()
        )
        tasks = [self.AD.loop.create_task(e.wait()) for e in events]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)
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

    async def refresh_update_time(self, plugin_name: str):
        """Updates the internal time for when the plugin's state was last updated"""
        self.last_plugin_state[plugin_name] = await self.AD.sched.get_now()

    async def time_since_plugin_update(self, plugin_name: str) -> datetime.timedelta:
        return await self.AD.sched.get_now() - self.last_plugin_state[plugin_name]

    async def update_plugin_state(self):
        for plugin, cfg in self.active_plugins:
            if await self.time_since_plugin_update(plugin.name) > cfg.refresh_delay:
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
                    await self.refresh_update_time(plugin)

    def required_meta_check(self):
        OK = True
        for key in self.required_meta:
            if getattr(self.AD, key) is None:
                # No value so bail
                self.logger.error("Required attribute not set or obtainable from any plugin: %s", key)
                OK = False
        return OK

    def get_plugin_api(self, plugin_name: str, app_cfg: AppConfig) -> "ADAPI | None":
        if plugin_cfg := self.config.get(plugin_name):
            module = importlib.import_module(plugin_cfg.api_module)
            api_class: Type["ADAPI"] = getattr(module, plugin_cfg.api_class)
            api = api_class(self.AD, app_cfg)
            api.set_namespace(plugin_cfg.namespace)
            return api
        else:
            self.logger.warning("Unknown Plugin Configuration in get_plugin_api()")
