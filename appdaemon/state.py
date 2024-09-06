import datetime
import traceback
import uuid
from copy import copy, deepcopy
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Union

import appdaemon.utils as utils

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class State:
    """Subsystem container for tracking states

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"
    logger: Logger
    state: Dict[str, Dict]

    app_added_namespaces: Set[str]

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad

        self.state = {"default": {}, "admin": {}, "rules": {}}
        self.logger = ad.logging.get_child("_state")
        self.app_added_namespaces = set()

        # Initialize User Defined Namespaces
        self.namespace_path.mkdir(exist_ok=True)

        for ns in self.AD.namespaces:
            writeback = self.AD.namespaces[ns].writeback
            self.add_persistent_namespace(ns, writeback)
            self.logger.info("User Defined Namespace '%s' initialized", ns)

    @property
    def namespace_path(self) -> Path:
        return self.AD.config_dir / "namespaces"

    def namespace_db_path(self, namespace: str) -> Path:
        return self.namespace_path / f"{namespace}.db"

    async def add_namespace(self, namespace: str, writeback: str, persist: bool, name: str = None) -> Union[bool, Path]:
        """Used to Add Namespaces from Apps"""

        if self.namespace_exists(namespace):
            self.logger.warning("Namespace %s already exists. Cannot process add_namespace from %s", namespace, name)
            return False

        if persist:
            nspath_file = await self.add_persistent_namespace(namespace, writeback)
        else:
            nspath_file = None
            self.state[namespace] = {}

        self.app_added_namespaces.add(namespace)

        await self.AD.events.process_event(
            "admin",
            data={
                "event_type": "__AD_NAMESPACE_ADDED",
                "data": {"namespace": namespace, "writeback": writeback, "database_filename": nspath_file},
            },
        )

        # TODO need to update and reload the admin page to show the new namespace in real-time

        return nspath_file

    def namespace_exists(self, namespace: str) -> bool:
        return namespace in self.state

    async def remove_namespace(self, namespace: str):
        """Used to Remove Namespaces from Apps"""

        if result := self.state.pop(namespace, False):
            nspath_file = await self.remove_persistent_namespace(namespace)
            self.app_added_namespaces.remove(namespace)

            self.logger.warning("Namespace %s, has ben removed", namespace)

            await self.AD.events.process_event(
                "admin",
                {
                    "event_type": "__AD_NAMESPACE_REMOVED",
                    "data": {"namespace": namespace, "database_filename": nspath_file},
                },
            )
            # TODO need to update and reload the admin page to show the removed namespace in real-time
            return result

        elif namespace in self.state:
            self.logger.warning("Cannot delete namespace %s, as not an app defined namespace", namespace)

        else:
            self.logger.warning("Namespace %s doesn't exists", namespace)

    @utils.executor_decorator
    def add_persistent_namespace(self, namespace: str, writeback: str) -> Path:
        """Used to add a database file for a created namespace"""

        try:
            if namespace in self.state and isinstance(self.state[namespace], utils.PersistentDict):
                self.logger.info("Persistent namespace '%s' already initialized", namespace)
                return

            ns_db_path = self.namespace_db_path(namespace)
            safe = bool(writeback == "safe")
            self.state[namespace] = utils.PersistentDict(ns_db_path, safe)

            self.logger.info("Persistent namespace '%s' initialized", namespace)

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in namespace setup")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

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

    async def add_state_callback(self, name: str, namespace: str, entity: str, cb, kwargs):  # noqa: C901
        if self.AD.threading.validate_pin(name, kwargs) is True:
            if "pin" in kwargs:
                pin_app = kwargs["pin"]
            else:
                pin_app = self.AD.app_management.objects[name].pin_app

            if "pin_thread" in kwargs:
                pin_thread = kwargs["pin_thread"]
                pin_app = True
            else:
                pin_thread = self.AD.app_management.objects[name].pin_thread

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
                    "pin_app": pin_app,
                    "pin_thread": pin_thread,
                    "kwargs": kwargs,
                }

            #
            # If we have a timeout parameter, add a scheduler entry to delete the callback later
            #
            if "timeout" in kwargs:
                timeout = kwargs.pop("timeout")
                exec_time = await self.AD.sched.get_now() + datetime.timedelta(seconds=int(timeout))

                kwargs["__timeout"] = await self.AD.sched.insert_schedule(
                    name,
                    exec_time,
                    None,
                    False,
                    None,
                    __state_handle=handle,
                )
            #
            # In the case of a quick_start parameter,
            # start the clock immediately if the device is already in the new state
            #
            if kwargs.get("immediate") is True:
                __duration = 0  # run it immediately
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

                    if "duration" in kwargs:
                        __duration = int(kwargs["duration"])
                if run:
                    exec_time = await self.AD.sched.get_now() + datetime.timedelta(seconds=__duration)

                    if kwargs.get("oneshot", False):
                        kwargs["__handle"] = handle

                    __scheduler_handle = await self.AD.sched.insert_schedule(
                        name,
                        exec_time,
                        cb,
                        False,
                        None,
                        __entity=entity,
                        __attribute=__attribute,
                        __old_state=None,
                        __new_state=__new_state,
                        **kwargs,
                    )

                    if __duration >= 1:  # it only stores it when needed
                        kwargs["__duration"] = __scheduler_handle

            await self.AD.state.add_entity(
                "admin",
                "state_callback.{}".format(handle),
                "active",
                {
                    "app": name,
                    "listened_entity": entity,
                    "function": cb.__name__,
                    "pinned": pin_app,
                    "pinned_thread": pin_thread,
                    "fired": 0,
                    "executed": 0,
                    "kwargs": kwargs,
                },
            )

            return handle
        else:
            return None

    async def cancel_state_callback(self, handle, name, silent=False):
        executed = False
        async with self.AD.callbacks.callbacks_lock:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                del self.AD.callbacks.callbacks[name][handle]
                await self.AD.state.remove_entity("admin", "state_callback.{}".format(handle))
                executed = True

            if name in self.AD.callbacks.callbacks and self.AD.callbacks.callbacks[name] == {}:
                del self.AD.callbacks.callbacks[name]

        if not executed and not silent:
            self.logger.warning(
                "Invalid callback handle '{}' in cancel_state_callback() from app {}".format(handle, name)
            )

        return executed

    async def info_state_callback(self, handle, name):
        async with self.AD.callbacks.callbacks_lock:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                callback = self.AD.callbacks.callbacks[name][handle]
                return (
                    callback["namespace"],
                    callback["entity"],
                    callback["kwargs"].get("attribute", None),
                    self.sanitize_state_kwargs(self.AD.app_management.objects[name].object, callback["kwargs"]),
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
                        callback["namespace"] == namespace or callback["namespace"] == "global" or namespace == "global"
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
                            if remove is True:
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

    async def remove_entity(self, namespace: str, entity: str):
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
        plugin = await self.AD.plugins.get_plugin_object(namespace)

        if hasattr(plugin, "remove_entity"):
            # We assume that the event will come back to us via the plugin
            await plugin.remove_entity(namespace, entity)

        await self.remove_entity_simple(namespace, entity)

    async def remove_entity_simple(self, namespace: str, entity_id: str) -> None:
        """Used to remove an internal AD entity"""

        if entity_id in self.state[namespace]:
            self.state[namespace].pop(entity_id)
            data = {"event_type": "__AD_ENTITY_REMOVED", "data": {"entity_id": entity_id}}
            self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

    async def add_entity(self, namespace: str, entity: str, state: Dict, attributes: Optional[Dict] = None):
        if self.entity_exists(namespace, entity):
            return

        attrs = {}
        if isinstance(attributes, dict):
            attrs.update(attributes)

        state = {
            "entity_id": entity,
            "state": state,
            "last_changed": utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0)),
            "attributes": attrs,
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
        entity_id: Optional[str] = None,
        attribute: Optional[str] = None,
        default=None,
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

    def parse_state(self, namespace: str, entity: str, **kwargs):
        self.logger.debug(f"parse_state: {entity}, {kwargs}")

        if entity in self.state[namespace]:
            new_state = self.state[namespace][entity]
        else:
            # Its a new state entry
            new_state = {"attributes": {}}

        if "state" in kwargs:
            new_state["state"] = kwargs["state"]
            del kwargs["state"]

        if "attributes" in kwargs:
            if kwargs.get("replace", False):
                new_state["attributes"] = kwargs["attributes"]
            else:
                new_state["attributes"].update(kwargs["attributes"])
        else:
            new_state["attributes"].update(kwargs)

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

    async def set_state(self, name: str, namespace: str, entity: str, _silent: bool = False, **kwargs):
        self.logger.debug("set_state(): %s, %s", entity, kwargs)
        if entity in self.state[namespace]:
            old_state = deepcopy(self.state[namespace][entity])
        else:
            old_state = {"state": None, "attributes": {}}
        new_state = self.parse_state(namespace, entity, **kwargs)
        new_state["last_changed"] = utils.dt_to_str((await self.AD.sched.get_now()).replace(microsecond=0), self.AD.tz)
        self.logger.debug("Old state: %s", old_state)
        self.logger.debug("New state: %s", new_state)

        if not self.entity_exists(namespace, entity) and not _silent:
            self.logger.info("%s: Entity %s created in namespace: %s", name, entity, namespace)

        # Fire the plugin's state update if it has one

        plugin = await self.AD.plugins.get_plugin_object(namespace)

        if set_plugin_state := getattr(plugin, "set_plugin_state", False):
            # We assume that the state change will come back to us via the plugin
            self.logger.debug("sending event to plugin")

            result = await set_plugin_state(
                namespace, entity, state=new_state["state"], attributes=new_state["attributes"]
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
            self.add_persistent_namespace(namespace, "safe")
            self.state[namespace].update(state)
        else:
            # first in case it had been created before, it should be deleted
            await self.remove_persistent_namespace(namespace)
            self.state[namespace] = state

    def update_namespace_state(self, namespace, state):
        if isinstance(namespace, list):  # if its a list, meaning multiple namespaces to be updated
            for ns in namespace:
                if state.get(ns) is not None:
                    self.state[ns].update(state[ns])
        else:
            self.state[namespace].update(state)

    async def save_namespace(self, namespace):
        if isinstance(self.state[namespace], utils.PersistentDict):
            self.state[namespace].sync()
        else:
            self.logger.warning("Namespace: %s cannot be saved", namespace)
        return None

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
    def sanitize_state_kwargs(app, kwargs):
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
            + app.list_constraints(),
        )
