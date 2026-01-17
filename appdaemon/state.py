import asyncio
import sys
import threading
import traceback
import uuid
from collections.abc import Awaitable, Callable, Mapping
from copy import copy, deepcopy
from enum import Enum
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, Protocol, overload

from . import exceptions as ade
from . import utils
from .types import TimeDeltaLike
from .utils import ADWritebackType

if TYPE_CHECKING:
    from .adbase import ADBase
    from .appdaemon import AppDaemon


class StateCallback(Protocol):
    def __call__(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> None: ...


class AsyncStateCallback(Protocol):
    def __call__(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> Awaitable[None]: ...


StateCallbackType = StateCallback | AsyncStateCallback


class StateServices(str, Enum):
    SET = "set"
    ADD_ENTITY = "add_entity"
    REMOVE_ENTITY = "remove_entity"
    ADD_NAMESPACE = "add_namespace"
    REMOVE_NAMESPACE = "remove_namespace"


class State:
    """Subsystem container for tracking states

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"
    logger: Logger
    name: str = "_state"
    state: dict[str, dict[str, Any] | utils.PersistentDict]

    app_added_namespaces: set[str]

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad

        self.state = {"default": {}, "admin": {}, "rules": {}}
        self.logger = ad.logging.get_child(self.name)
        self.error = ad.logging.get_error()
        self.app_added_namespaces = set()

        # Initialize User Defined Namespaces
        self.namespace_path.mkdir(exist_ok=True)
        for ns_name, ns_cfg in self.AD.namespaces.items():
            if not self.namespace_exists(ns_name):
                decorator = ade.wrap_async(
                    self.error,
                    self.AD.app_dir,
                    f"Namespace '{ns_name}' failed",
                )
                safe_add = decorator(self.add_namespace)
                coro = safe_add(
                    ns_name,
                    ns_cfg.writeback,
                    ns_cfg.persist,
                )
                self.AD.loop.create_task(coro)

    @property
    def namespace_path(self) -> Path:
        return self.AD.config_dir / "namespaces"

    def start(self) -> None:
        self.AD.loop.create_task(self.periodic_save(1.0), name="periodic save of hybrid namespaces")

    def stop(self) -> None:
        self.close_namespaces()

    def namespace_db_path(self, namespace: str) -> Path:
        path = (self.namespace_path / f"{namespace}")
        if sys.version_info.minor < 13:
            path = path.with_suffix("")
        else:
            path = path.with_suffix(".db")
        return path

    def namespace_exists(self, namespace: str) -> bool:
        return namespace in self.state

    async def add_namespace(
        self,
        namespace: str,
        writeback: ADWritebackType,
        persist: bool,
        name: str | None = None,
    ) -> Path | Literal[False] | None:  # fmt: skip
        """Add a state namespace.

        Fires a ``__AD_NAMESPACE_ADDED`` event in the ``admin`` namespace if it's actually added.

        Args:
            namespace (str): Name of the namespace to add.
            writeback (Literal["safe", "hybrid"]): Writeback strategy for the namespace.
            persist (bool): If ``True``, the namespace will be persistent by saving it to a file.
            name (str, optional): Name of the app adding the namespace.

        Returns:
            Path | Literal[False] | None: The path to the namespace database file if added successfully, False if it
                already exists, or None if the namespace isn't persistent.
        """

        if self.namespace_exists(namespace):
            self.logger.warning("App '%s' tried to add a namespace that already exists: %s", name, namespace)
            return False

        if persist:
            nspath_file = await self.add_persistent_namespace(namespace, writeback)
            # This will happen if the namespace already exists
            if nspath_file is None:
                # Warning message will be logged by self.add_persistent_namespace
                return False
        else:
            nspath_file = None
            self.state[namespace] = {}

        if name is not None:
            self.app_added_namespaces.add(namespace)

        await self.AD.events.process_event(
            "admin",
            data={
                "event_type": "__AD_NAMESPACE_ADDED",
                "data": {"namespace": namespace, "writeback": writeback, "database_filename": nspath_file},
            },
        )

        return nspath_file

    async def remove_namespace(self, namespace: str) -> utils.PersistentDict | dict[str, Any] | None:
        """Remove a state namespace. Must not be configured by the appdaemon.yaml file, and must have been added by an
        app.

        Fires an ``__AD_NAMESPACE_REMOVED`` event in the ``admin`` namespace if it's actually removed.
        """

        if namespace in self.AD.config.namespaces:
            self.logger.warning("Cannot delete namespace '%s', because it's configured by file.", namespace)
            return
        elif namespace not in self.app_added_namespaces:
            self.logger.warning("Cannot delete namespace '%s', because it wasn't made by an app.", namespace)
            return

        match state := self.state.pop(namespace, False):
            case utils.PersistentDict():
                nspath_file = await self.remove_persistent_namespace(namespace, state)
            case dict():
                nspath_file = None
            case False | _:
                self.logger.warning("Cannot delete namespace '%s', because it doesn't exist", namespace)
                return

        self.app_added_namespaces.remove(namespace)
        await self.AD.events.process_event(
            "admin", {
                "event_type": "__AD_NAMESPACE_REMOVED",
                "data": {"namespace": namespace, "database_filename": nspath_file},
            },
        )
        return state

    async def add_persistent_namespace(
        self,
        namespace: str,
        writeback: ADWritebackType = ADWritebackType.safe,
    ) -> Path | None:
        """Add a namespace that's stored in a persistent file.

        This needs to be an async method to make sure it gets run from the event loop in the main thread. Otherwise, the
        :py:class:`~shelve.DbfilenameShelf` can get messed up because it's not thread-safe. In some systems, it'll
        complain about being accessed from multiple threads, depending on what database driver is used in the
        background.
        """
        match self.state.get(namespace):
            case utils.PersistentDict():
                self.logger.info(f"Persistent namespace '{namespace}' already initialized")
                return

        ns_db_path = self.namespace_db_path(namespace)
        wb = ADWritebackType(writeback)
        self.logger.debug(
            "Creating persistent namespace '%s' at %s with writeback_strategy=%s",
            namespace,
            ns_db_path.name,
            wb.name
        )  # fmt: skip
        try:
            self.state[namespace] = utils.PersistentDict(ns_db_path, writeback_type=wb)
        except Exception as exc:
            raise ade.PersistentNamespaceFailed(namespace, ns_db_path) from exc
        else:
            current_thread = threading.current_thread().name
            self.logger.info("Persistent namespace '%s' initialized from %s", namespace, current_thread)
            return ns_db_path

    async def remove_persistent_namespace(self, namespace: str, state: utils.PersistentDict) -> Path | None:
        """Used to remove the file for a created namespace"""
        try:
            state.close()
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error closing namespace '%s':", namespace)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
        else:
            for ns_file in state.filepath.parent.iterdir():
                if ns_file.is_file() and ns_file.stem == state.filepath.stem:
                    try:
                        await asyncio.to_thread(ns_file.unlink)
                        self.logger.debug("Removed persistent namespace file '%s'", ns_file.name)
                    except Exception as e:
                        self.logger.error('Error removing namespace file %s: %s', ns_file.name, e)
                        continue

    def list_namespaces(self) -> list[str]:
        return list(self.state.keys())

    def list_namespace_entities(self, namespace: str) -> list[str]:
        if entity_dict := self.state.get(namespace):
            return list(entity_dict.keys())
        else:
            return list()

    async def add_state_callback(
        self,
        name: str,
        namespace: str,
        entity: str | None,
        cb: StateCallbackType,
        timeout: TimeDeltaLike | None = None,
        oneshot: bool = False,
        immediate: bool = False,
        pin: bool | None = None,
        pin_thread: int | None = None,
        kwargs: dict[str, Any] | None = None,
    ):  # noqa: C901
        """Add a state callback to AppDaemon's internal dicts.

        Uses the internal callback lock to ensure that the callback is added in a thread-safe manner.

        Args:
            name: Name of the app registering the callback. This is important because all callbacks have to be
                associated with an app.
            namespace: Namespace of the entity to listen to.
            entity (str, optional): Entity ID for listening to state changes. If ``None``, the callback will be invoked
                for all state changes in the namespace.
            cb (StateCallbackType): Callback function to be invoked when the state changes. Can be sync or async.
            oneshot (bool, optional): If ``True``, the callback will be removed after it is executed once. Defaults to
                ``False``.
            immediate (bool, optional): If ``True``, the callback will be executed immediately if the entity is already
                in the new state. Defaults to ``False``.
            kwargs (dict, optional): Additional parameters arguments to be passed to the callback function.

        Returns:
            A string made from ``uuid4().hex`` that is used to identify the callback. This can be used to cancel the
            callback later.
        """
        if kwargs is None:
            kwargs = {}

        if oneshot:  # this is still a little awkward, but it works until this can be refactored
            # This needs to be in the kwargs dict here that gets passed around later, so that the dispatcher knows to
            # cancel the callback after the first run.
            kwargs["oneshot"] = oneshot

        pin, pin_thread = self.AD.threading.determine_thread(name, pin, pin_thread)

        #
        # Add the callback
        #

        async with self.AD.callbacks.callbacks_lock:
            if name not in self.AD.callbacks.callbacks:
                self.AD.callbacks.callbacks[name] = {}

            handle = uuid.uuid4().hex
            self.AD.callbacks.callbacks[name][handle] = {
                "name": name,
                "id": self.AD.app_management.objects[name].id,
                "type": "state",
                "function": cb,
                "entity": entity,
                "namespace": namespace,
                "pin_app": pin,
                "pin_thread": pin_thread,
                "kwargs": kwargs,
            }

        #
        # If we have a timeout parameter, add a scheduler entry to delete the callback later
        #
        if timeout is not None:
            exec_time = (await self.AD.sched.get_now()) + utils.parse_timedelta(timeout)
            kwargs["__timeout"] = await self.AD.sched.insert_schedule(
                name=name,
                aware_dt=exec_time,
                callback=None,
                repeat=False,
                type_=None,
                __state_handle=handle,
            )
        #
        # In the case of a quick_start parameter,
        # start the clock immediately if the device is already in the new state
        #
        if immediate:
            __new_state = None
            __attribute = None
            run = False

            if entity is not None and entity in self.state[namespace]:
                run = True

                if "attribute" in kwargs:
                    __attribute = kwargs["attribute"]
                if "new" in kwargs:
                    if __attribute is None and self.state[namespace][entity].get("state") == kwargs["new"]:
                        __new_state = kwargs["new"]
                    elif (
                        __attribute is not None
                        and self.state[namespace][entity]["attributes"].get(__attribute) == kwargs["new"]
                    ):  # fmt: skip
                        __new_state = kwargs["new"]
                    else:
                        run = False
                else:  # use the present state of the entity
                    if __attribute is None and "state" in self.state[namespace][entity]:
                        __new_state = self.state[namespace][entity]["state"]
                    elif __attribute is not None:
                        if __attribute in self.state[namespace][entity]["attributes"]:
                            __new_state = self.state[namespace][entity]["attributes"][__attribute]
                        elif __attribute == "all":
                            __new_state = self.state[namespace][entity]

                __duration = utils.parse_timedelta(kwargs.get("duration", 0))
            if run:
                exec_time = await self.AD.sched.get_now() + __duration

                if kwargs.get("oneshot", False):
                    kwargs["__handle"] = handle

                __scheduler_handle = await self.AD.sched.insert_schedule(
                    name=name,
                    aware_dt=exec_time,
                    callback=cb,
                    repeat=False,
                    type_=None,
                    __entity=entity,
                    __attribute=__attribute,
                    __old_state=None,
                    __new_state=__new_state,
                    **kwargs,
                )

                if __duration.total_seconds() >= 1:  # it only stores it when needed
                    kwargs["__duration"] = __scheduler_handle

        await self.AD.state.add_entity(
            "admin",
            f"state_callback.{handle}",
            "active",
            {
                "app": name,
                "listened_entity": entity,
                "function": getattr(cb, "__name__", str(cb)),
                "pinned": pin,
                "pinned_thread": pin_thread,
                "fired": 0,
                "executed": 0,
                "kwargs": kwargs,
            },
        )

        return handle

    async def cancel_state_callback(self, handle: str, name: str, silent: bool = False) -> bool:
        executed = False
        async with self.AD.callbacks.callbacks_lock:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                del self.AD.callbacks.callbacks[name][handle]
                await self.AD.state.remove_entity("admin", f"state_callback.{handle}")
                executed = True

            if name in self.AD.callbacks.callbacks and self.AD.callbacks.callbacks[name] == {}:
                del self.AD.callbacks.callbacks[name]

        if not executed and not silent:
            self.logger.warning(
                f"Invalid callback handle '{handle}' in cancel_state_callback() from app {name}"
            )  # fmt: skip

        return executed

    async def info_state_callback(self, handle: str, name: str) -> tuple[str, str, Any, dict[str, Any]]:
        """Get information about a state callback

        Needs to be async to use the callback lock.

        Args:
            handle (str): Handle from when the callback was registered.
            name (str): Name of the app that registered the callback. Every callback is registered under an app, so this
                is required to find the callback information.

        Returns:
            A tuple with the namespace, entity, attribute, and kwargs of the callback
        """
        async with self.AD.callbacks.callbacks_lock:
            if (
                (app_callbacks := self.AD.callbacks.callbacks.get(name, {})) and    # This app has callbacks
                (callback := app_callbacks.get(handle, False))                      # This callback handle exists for it
            ):  # fmt: skip
                callback = self.AD.callbacks.callbacks[name][handle]
                app_object = self.AD.app_management.objects[name].object
                sanitized_kwargs = self.sanitize_state_kwargs(app_object, callback["kwargs"])
                return (
                    callback["namespace"],
                    callback["entity"],
                    callback["kwargs"].get("attribute", None),
                    sanitized_kwargs,
                )
            else:
                raise ValueError("Invalid handle: {}".format(handle))

    async def process_state_callbacks(self, namespace, state):
        data = state["data"]
        entity_id = data["entity_id"]
        self.logger.debug(data)
        device, entity = entity_id.split(".")

        # Process state callbacks

        removes = []
        async with self.AD.callbacks.callbacks_lock:
            for name in self.AD.callbacks.callbacks.keys():
                for uuid_ in self.AD.callbacks.callbacks[name]:
                    callback = self.AD.callbacks.callbacks[name][uuid_]
                    if callback["type"] == "state" and (
                        callback["namespace"] == namespace or
                        callback["namespace"] == "global" or
                        namespace == "global"
                    ):  # fmt: skip
                        cdevice = None
                        centity = None
                        if callback["entity"] is not None:
                            if "." not in callback["entity"]:
                                cdevice = callback["entity"]
                                centity = None
                            else:
                                cdevice, centity = callback["entity"].split(".")
                        if callback["kwargs"].get("attribute") is None:
                            cattribute = "state"
                        else:
                            cattribute = callback["kwargs"].get("attribute")

                        cold = callback["kwargs"].get("old")
                        cnew = callback["kwargs"].get("new")

                        executed = False
                        if cdevice is None:
                            executed = await self.AD.threading.check_and_dispatch_state(
                                name,
                                callback["function"],
                                entity_id,
                                cattribute,
                                data["new_state"],
                                data["old_state"],
                                cold,
                                cnew,
                                callback["kwargs"],
                                uuid_,
                                callback["pin_app"],
                                callback["pin_thread"],
                            )
                        elif centity is None:
                            if device == cdevice:
                                executed = await self.AD.threading.check_and_dispatch_state(
                                    name,
                                    callback["function"],
                                    entity_id,
                                    cattribute,
                                    data["new_state"],
                                    data["old_state"],
                                    cold,
                                    cnew,
                                    callback["kwargs"],
                                    uuid_,
                                    callback["pin_app"],
                                    callback["pin_thread"],
                                )

                        elif device == cdevice and entity == centity:
                            executed = await self.AD.threading.check_and_dispatch_state(
                                name,
                                callback["function"],
                                entity_id,
                                cattribute,
                                data["new_state"],
                                data["old_state"],
                                cold,
                                cnew,
                                callback["kwargs"],
                                uuid_,
                                callback["pin_app"],
                                callback["pin_thread"],
                            )

                        # Remove the callback if appropriate
                        if executed is True:
                            remove = callback["kwargs"].get("oneshot", False)
                            if remove:
                                removes.append({"name": callback["name"], "uuid": uuid_})

        for remove in removes:
            await self.cancel_state_callback(remove["uuid"], remove["name"])

    def entity_exists(self, namespace: str, entity: str) -> bool:
        match self.state.get(namespace):
            case Mapping() as ns_state:
                return entity in ns_state
        return False

    def get_entity(self, namespace: Optional[str] = None, entity_id: Optional[str] = None, name: Optional[str] = None):
        if namespace is None:
            return deepcopy(self.state)

        if entity_id is None:
            if namespace in self.state:
                return deepcopy(self.state[namespace])
            else:
                self.logger.warning("Unknown namespace: %s requested by %s", namespace, name)
                return None

        if namespace in self.state:
            if entity_id in self.state[namespace]:
                return deepcopy(self.state[namespace][entity_id])
            else:
                self.logger.warning("Unknown entity: %s requested by %s", entity_id, name)
                return None
        else:
            self.logger.warning("Unknown namespace: %s requested by %s", namespace, name)
            return None

    async def remove_entity(self, namespace: str, entity: str) -> None:
        """Removes an entity.

        If the namespace does not have a plugin associated with it, the entity will be removed locally only.
        If a plugin is associated, the entity will be removed via the plugin and locally.

        Args:
            namespace (str): Namespace for the event to be fired in.
            entity (str): Name of the entity.

        Returns:
            None.

        """
        # print("remove {}:{}".format(namespace, entity))

        self.logger.debug("remove_entity() %s %s", namespace, entity)
        await self.remove_entity_simple(namespace, entity)

        plugin = self.AD.plugins.get_plugin_object(namespace)

        if (remove_method := getattr(plugin, "remove_entity", None)) is not None:
            # We assume that the event will come back to us via the plugin
            return await remove_method(namespace, entity)

    async def remove_entity_simple(self, namespace: str, entity_id: str) -> None:
        """Used to remove an internal AD entity

        Fires the ``__AD_ENTITY_REMOVED`` event in a new task
        """

        if self.state[namespace].pop(entity_id, False):
            data = {"event_type": "__AD_ENTITY_REMOVED", "data": {"entity_id": entity_id}}
            self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

    async def add_entity(
        self,
        namespace: str,
        entity: str,
        state: Any,
        attributes: Optional[dict] = None
    ) -> None:  # fmt: skip
        """Adds an entity to the internal state registry and fires the ``__AD_ENTITY_ADDED`` event"""
        if self.entity_exists(namespace, entity):
            # No warning is necessary because this method gets called twice for the app entities because of
            # create_initial_threads and then again during start_app
            # self.logger.warning("%s already exists, will not be adding it", entity)
            return

        state = {
            "entity_id": entity,
            "state": state,
            "last_changed": "never",
            "attributes": attributes or {},
        }

        self.state[namespace][entity] = state

        data = {
            "event_type": "__AD_ENTITY_ADDED",
            "data": {"entity_id": entity, "state": state},
        }

        self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

    def get_state_simple(self, namespace, entity_id):
        # Simple sync version of get_state() primarily for use in entity objects, returns whole state for the entity
        if namespace not in self.state:
            raise ValueError(f"Namespace {namespace} not found for entity.state")
        if entity_id not in self.state[namespace]:
            raise ValueError(f"Entity {entity_id} not found in namespace {namespace} for entity.state")

        return self.state[namespace][entity_id]

    async def get_state(
        self,
        name: str,
        namespace: str,
        entity_id: str | None = None,
        attribute: str | None = None,
        default: Any | None = None,
        copy: bool = True,
    ):
        self.logger.debug("get_state: %s.%s %s %s", entity_id, attribute, default, copy)

        def maybe_copy(data):
            return deepcopy(data) if copy else data

        if entity_id is not None and "." in entity_id:
            if not self.entity_exists(namespace, entity_id):
                return default
            state = self.state[namespace][entity_id]
            if attribute is None and "state" in state:
                return maybe_copy(state["state"])
            if attribute == "all":
                return maybe_copy(state)
            if attribute in state["attributes"]:
                return maybe_copy(state["attributes"][attribute])
            if attribute in state:
                return maybe_copy(state[attribute])
            return default

        if attribute is not None:
            raise ValueError("{}: Querying a specific attribute is only possible for a single entity".format(name))

        if entity_id is None:
            return maybe_copy(self.state[namespace])

        domain = entity_id.split(".", 1)[0]
        return {
            entity_id: maybe_copy(state)
            for entity_id, state in self.state[namespace].items()
            if entity_id.split(".", 1)[0] == domain
        }  # fmt: skip

    def parse_state(
        self,
        namespace: str,
        entity: str,
        state: Any | None = None,
        attributes: dict | None = None,
        replace: bool = False,
        **kwargs
    ):  # fmt: skip
        self.logger.debug(f"parse_state: {entity}, {kwargs}")

        if entity in self.state[namespace]:
            new_state: dict[str, Any] = deepcopy(self.state[namespace][entity])
        else:
            # Its a new state entry
            new_state = {"attributes": {}}

        if state is not None:
            new_state["state"] = state

        new_attrs = attributes or dict()
        new_attrs.update(kwargs)

        if new_attrs:
            if replace:
                new_state["attributes"] = new_attrs
            else:
                new_state["attributes"].update(new_attrs)

        # API created entities won't necessarily have entity_id set
        new_state["entity_id"] = entity

        return new_state

    async def add_to_state(self, name: str, namespace: str, entity_id: str, i):
        value = await self.get_state(name, namespace, entity_id)
        if value is not None:
            value += i
            await self.set_state(name, namespace, entity_id, state=value)

    async def add_to_attr(self, name: str, namespace: str, entity_id: str, attr, i):
        state = await self.get_state(name, namespace, entity_id, attribute="all")
        if state is not None:
            state["attributes"][attr] = copy(state["attributes"][attr]) + i
            await self.set_state(name, namespace, entity_id, attributes=state["attributes"])

    def register_state_services(self, namespace: str) -> None:
        """Register the set of state services for the given namespace."""
        for service_name in StateServices:
            self.AD.services.register_service(namespace, "state", service_name, self.AD.state._state_service)

    async def _state_service(
        self,
        namespace: str,
        domain: str,
        service: str,
        *,
        entity_id: str | None = None,
        persist: bool = False,
        writeback: Literal["safe", "hybrid"] = "safe",
        **kwargs: Any
    ) -> Any | None:
        self.logger.debug("state_services: %s, %s, %s, %s", namespace, domain, service, kwargs)
        match StateServices(service):
            case StateServices.SET | StateServices.ADD_ENTITY | StateServices.REMOVE_ENTITY:  # fmt: skip
                if entity_id is None:
                    self.logger.warning("Entity not specified in %s service call: %s", service, kwargs)
                    return
                match service:
                    case StateServices.SET:
                        return await self.set_state(domain, namespace, entity_id, **kwargs)
                    case StateServices.REMOVE_ENTITY:
                        return await self.remove_entity(namespace, entity_id)
                    case StateServices.ADD_ENTITY:
                        state = kwargs.get("state")
                        attributes = kwargs.get("attributes")
                        return await self.add_entity(namespace, entity_id, state, attributes)
            case StateServices.ADD_NAMESPACE | StateServices.REMOVE_NAMESPACE:
                if namespace is None:
                    self.logger.warning("Namespace not specified in %s service call: %s", service, kwargs)
                    return
                match service:
                    case StateServices.ADD_NAMESPACE:
                        assert isinstance(persist, bool), "persist must be a boolean"
                        assert writeback in ("safe", "hybrid"), "writeback must be 'safe' or 'hybrid'"
                        return await self.add_namespace(namespace, writeback, persist, kwargs.get("name"))
                    case StateServices.REMOVE_NAMESPACE:
                        return await self.remove_namespace(namespace)
            case _:
                self.logger.warning("Unknown service in state service call: %s", kwargs)
                return

    @overload
    async def set_state(
        self,
        name: str,
        namespace: str,
        entity: str,
        _silent: bool = False,
        *,
        state: Any | None = None,
        attributes: dict | None = None,
        replace: bool = False,
        **kwargs: Any
    ) -> dict[str, Any]:  # fmt: skip
        ...

    @overload
    async def set_state(
        self,
        name: str,
        namespace: str,
        entity: str,
        _silent: bool = False,
        **kwargs: Any
    ) -> dict[str, Any]:  # fmt: skip
        ...

    async def set_state(
        self,
        name: str,
        namespace: str,
        entity: str,
        _silent: bool = False,
        **kwargs: Any
    ) -> dict[str, Any]:
        """Sets the internal state of an entity.

        Fires the ``state_changed`` event under the namespace, and uses relevant plugin objects based on namespace.

        Args:
            name: Only used for a log message
            namespace:
            entity:
            __silent:
            state:
            attributes:
            replace:
        """
        self.logger.debug("set_state(): %s, %s", entity, kwargs)
        if entity in self.state[namespace]:
            old_state = deepcopy(self.state[namespace][entity])
        else:
            old_state = {"state": None, "attributes": {}}
        new_state = self.parse_state(namespace, entity, **kwargs)
        now = await self.AD.sched.get_now()
        new_state["last_changed"] = utils.dt_to_str(now, self.AD.tz, round=True)
        self.logger.debug("Old state: %s", old_state)
        self.logger.debug("New state: %s", new_state)

        if not self.entity_exists(namespace, entity):
            await self.add_entity(namespace, entity, new_state.get("state"), new_state.get("attributes"))
            if not _silent:
                self.logger.info("%s: Entity %s created in namespace: %s", name, entity, namespace)

        # Fire the plugin's state update if it has one

        plugin = self.AD.plugins.get_plugin_object(namespace)

        plugin_handled = False
        set_plugin_state: Callable[..., Awaitable[dict[str, Any] | None]] | None
        if (set_plugin_state := getattr(plugin, "set_plugin_state", None)) is not None:
            # We assume that the state change will come back to us via the plugin
            self.logger.debug("sending event to plugin")

            result = await set_plugin_state(
                namespace,
                entity,
                state=new_state["state"],
                attributes=new_state["attributes"],
            )
            if result is not None:
                if "entity_id" in result:
                    result.pop("entity_id")
                self.state[namespace][entity] = self.parse_state(namespace, entity, **result)
                plugin_handled = True

        if not plugin_handled:
            # Set the state locally
            self.state[namespace][entity] = new_state
            # Fire the event locally
            self.logger.debug("sending event locally")
            data = {
                "event_type": "state_changed",
                "data": {"entity_id": entity, "new_state": new_state, "old_state": old_state},
            }

            #
            # Schedule this rather than awaiting to avoid locking ourselves out
            #
            # await self.AD.events.process_event(namespace, data)
            self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

        return new_state

    def set_state_simple(self, namespace: str, entity_id: str, state: Any):
        """Set state without any checks or triggering amy events, and only if the entity exists"""
        if self.entity_exists(namespace, entity_id):
            self.state[namespace][entity_id] = state

    async def set_namespace_state(self, namespace: str, state: dict[str, Any], persist: bool = False):
        if persist:
            await self.add_persistent_namespace(namespace, writeback="safe")
            self.state[namespace].update(state)
        else:
            # first in case it had been created before, it should be deleted
            if isinstance(self.state.get(namespace), utils.PersistentDict):
                await self.remove_persistent_namespace(namespace, self.state[namespace])
            self.state[namespace] = state

    def update_namespace_state(self, namespace: str | list[str], state: dict):
        """Uses the update method of dict

        If the namespace argument is a list, then the state is expected to be a dictionary with each
        """
        if isinstance(namespace, list):  # if its a list, meaning multiple namespaces to be updated
            for ns in namespace:
                if s := state.get(ns):
                    self.state[ns].update(s)
                else:
                    self.logger.warning(f"Attempted to update namespace without data: {ns}")
        else:
            self.state[namespace].update(state)

    async def save_namespace(self, namespace: str) -> bool:
        match self.state.get(namespace):
            case None:
                self.logger.warning("Namespace: %s does not exist", namespace)
                return False
            case utils.PersistentDict() as ns:
                self.logger.debug("Saving persistent namespace: %s", namespace)
                try:
                    # This could take a while if there's been a lot of changes since the last save, so run it in a separate
                    # thread to avoid blocking the async event loop
                    await asyncio.to_thread(ns.sync)
                except Exception:
                    self.logger.warning("Unexpected error saving namespace: %s", namespace)
                    return False
                else:
                    return True
            case _:
                self.logger.warning("Namespace: %s cannot be saved", namespace)
                return False

    def close_namespaces(self) -> None:
        """Close all the persistent namespaces, which includes saving them."""
        self.logger.debug("Closing all namespaces")
        for ns, state in self.state.items():
            try:
                match state:
                    case utils.PersistentDict():
                        self.logger.info("Closing persistent namespace: %s", ns)
                        state.close()
            except Exception:
                self.logger.error("Unexpected error saving namespace: %s", ns)
                self.logger.error(traceback.format_exc())

    async def periodic_save(self, interval: TimeDeltaLike) -> None:
        """Periodically save all namespaces that are persistent with writeback_type 'hybrid'"""
        interval = utils.parse_timedelta(interval).total_seconds()
        while not self.AD.stopping:
            self.save_hybrid_namespaces()
            await self.AD.utility.sleep(interval, timeout_ok=True)

    def save_hybrid_namespaces(self) -> None:
        """Save all the persistent namespaces with the hybrid writeback type"""
        for ns_name, ns_state in self.state.items():
            try:
                match ns_state:
                    case utils.PersistentDict(writeback_type=ADWritebackType.hybrid) as persistent_state:
                        self.logger.debug("Saving hybrid persistent namespace: %s", ns_name)
                        persistent_state.sync()
            except Exception:
                self.logger.error("Unexpected error saving hybrid namespace: %s", ns_name)
                self.logger.error(traceback.format_exc())

    #
    # Utilities
    #
    @staticmethod
    def sanitize_state_kwargs(app: "ADBase", kwargs):
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(
            kwargs_copy,
            [
                "old",
                "new",
                "__attribute",
                "duration",
                "state",
                "__entity",
                "__duration",
                "__old_state",
                "__new_state",
                "oneshot",
                "pin_app",
                "pin_thread",
                "__delay",
                "__silent",
                "attribute",
            ]
            + app.constraints,
        )
