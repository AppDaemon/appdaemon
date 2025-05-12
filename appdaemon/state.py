from datetime import timedelta
import threading
import traceback
import uuid
from copy import copy, deepcopy
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Set, Union, overload

from . import exceptions as ade
from . import utils

if TYPE_CHECKING:
    from .adbase import ADBase
    from .appdaemon import AppDaemon


class StateCallback(Protocol):
    def __call__(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> None: ...


class State:
    """Subsystem container for tracking states

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"
    logger: Logger
    name: str = "_state"
    state: dict[str, dict[str, Any]]

    app_added_namespaces: Set[str]

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

    # @property
    # def namespace_db_path(self) -> Path:
    #     return self.namespace_path /

    def namespace_db_path(self, namespace: str) -> Path:
        return self.namespace_path / f"{namespace}.db"

    async def add_namespace(
        self,
        namespace: str,
        writeback: str,
        persist: bool,
        name: str = None
    ) -> Union[bool, Path]:
        """Used to Add Namespaces from Apps"""

        if self.namespace_exists(namespace):
            self.logger.warning("Namespace %s already exists. Cannot process add_namespace from %s", namespace, name)
            return False

        if persist:
            nspath_file = await self.add_persistent_namespace(namespace, writeback)
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

    def namespace_exists(self, namespace: str) -> bool:
        return namespace in self.state

    async def remove_namespace(self, namespace: str) -> dict[str, Any] | None:
        """Used to Remove Namespaces from Apps

        Fires an ``__AD_NAMESPACE_REMOVED`` event in the ``admin`` namespace if it's actually removed.
        """

        if self.state.pop(namespace, False):
            nspath_file = await self.remove_persistent_namespace(namespace)
            self.app_added_namespaces.remove(namespace)

            self.logger.warning("Namespace %s, has ben removed", namespace)

            data = {
                "event_type": "__AD_NAMESPACE_REMOVED",
                "data": {"namespace": namespace, "database_filename": nspath_file},
            }

            await self.AD.events.process_event("admin", data)

        elif namespace in self.state:
            self.logger.warning("Cannot delete namespace %s, as not an app defined namespace", namespace)

        else:
            self.logger.warning("Namespace %s doesn't exists", namespace)

    # @utils.warning_decorator(error_text='Unexpected error in add_persistent_namespace')
    async def add_persistent_namespace(self, namespace: str, writeback: str) -> Path:
        """Used to add a database file for a created namespace.

        Needs to be an async method to make sure it gets run from the event loop in the
        main thread. Otherwise, the DbfilenameShelf can get messed up because it's not
        thread-safe. In some systems, it'll complain about being accessed from multiple
        threads."""

        if isinstance(self.state.get(namespace), utils.PersistentDict):
            self.logger.info(f"Persistent namespace '{namespace}' already initialized")
            return

        ns_db_path = self.namespace_db_path(namespace)
        safe = writeback == "safe"
        try:
            self.state[namespace] = utils.PersistentDict(ns_db_path, safe)
        except Exception as exc:
            raise ade.PersistentNamespaceFailed(namespace, ns_db_path) from exc
        current_thread = threading.current_thread().getName()
        self.logger.info(f"Persistent namespace '{namespace}' initialized from {current_thread}")
        return ns_db_path

    @utils.executor_decorator
    def remove_persistent_namespace(self, namespace: str) -> Path:
        """Used to remove the file for a created namespace"""

        try:
            ns_db_path = self.namespace_db_path(namespace)
            if ns_db_path.exists():
                ns_db_path.unlink()
            return ns_db_path
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in namespace removal")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

    def list_namespaces(self) -> List[str]:
        return list(self.state.keys())

    def list_namespace_entities(self, namespace: str) -> List[str]:
        if entity_dict := self.state.get(namespace):
            return list(entity_dict.keys())

    def terminate(self):
        self.logger.debug("terminate() called for state")
        self.logger.info("Saving all namespaces")
        self.save_all_namespaces()

    async def add_state_callback(
        self,
        name: str,
        namespace: str,
        entity: str | None,
        cb: StateCallback,
        timeout: str | int | float | timedelta | None = None,
        oneshot: bool = False,
        immediate: bool = False,
        pin: bool | None = None,
        pin_thread: int | None = None,
        kwargs: dict[str, Any] = None
    ):  # noqa: C901
        """Add a state callback to AppDaemon's internal dicts.

        Uses the internal callback lock to ensure that the callback is added in a thread-safe manner.

        Args:
            name: Name of the app registering the callback. This is important because all callbacks have to be
                associated with an app.
            namespace: Namespace of the entity to listen to.
            entity (str, optional): Entity ID for listening to state changes. If ``None``, the callback will be invoked
                for all state changes in the namespace.
            cb (StateCallback): Callback function to be invoked when the state changes.
            oneshot (bool, optional): If ``True``, the callback will be removed after it is executed once. Defaults to
                ``False``.
            immediate (bool, optional): If ``True``, the callback will be executed immediately if the entity is already
                in the new state. Defaults to ``False``.
            kwargs (dict, optional): Additional parameters arguments to be passed to the callback function.

        Returns:
            A string made from ``uuid4().hex`` that is used to identify the callback. This can be used to cancel the
            callback later.
        """
        if oneshot: # this is still a little awkward, but it works until this can be refactored
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
                    ):
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
                "function": cb.__name__,
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
            )

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
                (app_callbacks := self.AD.callbacks.callbacks.get(name, False)) and # This app has callbacks
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
                    ):
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

    def entity_exists(self, namespace: str, entity: str):
        return namespace in self.state and entity in self.state[namespace]

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

        if hasattr(plugin, "remove_entity"):
            # We assume that the event will come back to us via the plugin
            return await plugin.remove_entity(namespace, entity)

    async def remove_entity_simple(self, namespace: str, entity_id: str) -> None:
        """Used to remove an internal AD entity

        Fires the ``__AD_ENTITY_REMOVED`` event in a new task
        """

        if entity_id in self.state[namespace]:
            self.state[namespace].pop(entity_id)
            data = {"event_type": "__AD_ENTITY_REMOVED", "data": {"entity_id": entity_id}}
            self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

    async def add_entity(
        self,
        namespace: str,
        entity: str,
        state: str | dict,
        attributes: Optional[dict] = None
    ):
        """Adds an entity to the internal state registry and fires the ``__AD_ENTITY_ADDED`` event"""
        if self.entity_exists(namespace, entity):
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
        }

    def parse_state(
        self,
        namespace: str,
        entity: str,
        state: Any | None = None,
        attributes: dict | None = None,
        replace: bool = False,
        **kwargs
    ):
        self.logger.debug(f"parse_state: {entity}, {kwargs}")

        if entity in self.state[namespace]:
            new_state = deepcopy(self.state[namespace][entity])
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

    async def state_services(self, namespace, domain, service, kwargs):
        self.logger.debug("state_services: %s, %s, %s, %s", namespace, domain, service, kwargs)
        if service in ["add_entity", "remove_entity", "set"]:
            if "entity_id" not in kwargs:
                self.logger.warning("Entity not specified in %s service call: %s", service, kwargs)
                return

            else:
                entity_id = kwargs["entity_id"]
                del kwargs["entity_id"]

        elif service in ["add_namespace", "remove_namespace"]:
            if "namespace" not in kwargs:
                self.logger.warning("Namespace not specified in %s service call: %s", service, kwargs)
                return

            else:
                namespace = kwargs["namespace"]
                del kwargs["namespace"]

        if service == "set":
            await self.set_state(domain, namespace, entity_id, **kwargs)

        elif service == "remove_entity":
            await self.remove_entity(namespace, entity_id)

        elif service == "add_entity":
            state = kwargs.get("state")
            attributes = kwargs.get("attributes")
            await self.add_entity(namespace, entity_id, state, attributes)

        elif service == "add_namespace":
            writeback = kwargs.get("writeback")
            persist = kwargs.get("persist")
            await self.add_namespace(namespace, writeback, persist, kwargs.get("name"))

        elif service == "remove_namespace":
            await self.remove_namespace(namespace)

        else:
            self.logger.warning("Unknown service in state service call: %s", kwargs)

    @overload
    async def set_state(
        self,
        name: str,
        namespace: str,
        entity: str,
        _silent: bool = False,
        state: Any | None = None,
        attributes: dict | None = None,
        replace: bool = False,
        **kwargs
    ) -> None: ...

    async def set_state(self, name: str, namespace: str, entity: str, _silent: bool = False, **kwargs):
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
        new_state["last_changed"] = utils.dt_to_str((await self.AD.sched.get_now()).replace(microsecond=0), self.AD.tz)
        self.logger.debug("Old state: %s", old_state)
        self.logger.debug("New state: %s", new_state)

        if not self.entity_exists(namespace, entity):
            await self.add_entity(namespace, entity, new_state.get("state"), new_state.get("attributes"))
            if not _silent:
                self.logger.info("%s: Entity %s created in namespace: %s", name, entity, namespace)

        # Fire the plugin's state update if it has one

        plugin = self.AD.plugins.get_plugin_object(namespace)

        if set_plugin_state := getattr(plugin, "set_plugin_state", False):
            # We assume that the state change will come back to us via the plugin
            self.logger.debug("sending event to plugin")

            result = await set_plugin_state(
                namespace,
                entity,
                state=new_state["state"],
                attributes=new_state["attributes"]
            )
            if result is not None:
                if "entity_id" in result:
                    result.pop("entity_id")
                self.state[namespace][entity] = self.parse_state(namespace, entity, **result)
        else:
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

    async def set_namespace_state(self, namespace: str, state: Dict, persist: bool = False):
        if persist:
            await self.add_persistent_namespace(namespace, "safe")
            self.state[namespace].update(state)
        else:
            # first in case it had been created before, it should be deleted
            await self.remove_persistent_namespace(namespace)
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

    async def save_namespace(self, namespace: str) -> None:
        if isinstance((ns := self.state[namespace]), utils.PersistentDict):
            ns.sync()
        else:
            self.logger.warning("Namespace: %s cannot be saved", namespace)

    def save_all_namespaces(self):
        for ns, state in self.state.items():
            if isinstance(state, utils.PersistentDict):
                self.state[ns].sync()

    def save_hybrid_namespaces(self):
        for ns, cfg in self.AD.namespaces.items():
            if cfg.writeback == "hybrid":
                self.state[ns].sync()

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
