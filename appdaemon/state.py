import uuid
import traceback
import os
from copy import copy, deepcopy
import datetime

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon


class State:

    def __init__(self, ad: AppDaemon):

        self.AD = ad

        self.state = {"default": {}, "admin": {}, "rules": {}}
        self.logger = ad.logging.get_child("_state")

        # Initialize User Defined Namespaces

        nspath = os.path.join(self.AD.config_dir, "namespaces")
        try:
            if not os.path.isdir(nspath):
                os.makedirs(nspath)
            for ns in self.AD.namespaces:
                self.logger.info("User Defined Namespace '%s' initialized", ns)
                writeback = self.AD.namespaces[ns].get("writeback", "safe")
                safe = bool(writeback == "safe")
                self.state[ns] = utils.PersistentDict(os.path.join(nspath, ns), safe)
        except:
                self.logger.warning('-' * 60)
                self.logger.warning("Unexpected error in namespace setup")
                self.logger.warning('-' * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning('-' * 60)

    async def list_namespaces(self):
        ns = []
        for namespace in self.state:
            ns.append(namespace)
        return ns

    def list_namespace_entities(self, namespace):
        et = []
        if namespace in self.state:
            for entity in self.state[namespace]:
                et.append(entity)
            return et
        else:
            return None

    def terminate(self):
        self.logger.debug("terminate() called for state")
        self.logger.info("Saving all namespaces")
        self.save_all_namespaces()

    async def add_state_callback(self, name, namespace, entity, cb, kwargs):
        if self.AD.threading.validate_pin(name, kwargs) is True:
            if "pin" in kwargs:
                pin_app = kwargs["pin"]
            else:
                pin_app = self.AD.app_management.objects[name]["pin_app"]

            if "pin_thread" in kwargs:
                pin_thread = kwargs["pin_thread"]
                pin_app = True
            else:
                pin_thread = self.AD.app_management.objects[name]["pin_thread"]

            #
            # Add the callback
            #

            if name not in self.AD.callbacks.callbacks:
                self.AD.callbacks.callbacks[name] = {}

            handle = uuid.uuid4().hex
            self.AD.callbacks.callbacks[name][handle] = {
                "name": name,
                "id": self.AD.app_management.objects[name]["id"],
                "type": "state",
                "function": cb,
                "entity": entity,
                "namespace": namespace,
                "pin_app": pin_app,
                "pin_thread": pin_thread,
                "kwargs": kwargs
            }

            #
            # If we have a timeout parameter, add a scheduler entry to delete the callback later
            #
            if "timeout" in kwargs:
                exec_time = await self.AD.sched.get_now() + datetime.timedelta(seconds=int(kwargs["timeout"]))

                kwargs["__timeout"] = await self.AD.sched.insert_schedule(
                    name, exec_time, None, False, None, __state_handle=handle,
                )
            #
            # In the case of a quick_start parameter,
            # start the clock immediately if the device is already in the new state
            #
            if "immediate" in kwargs and kwargs["immediate"] is True:
                __duration = 0 # run it immediately
                __new_state = None
                __attribute = None
                run = False
                
                if entity is not None and entity in self.state[namespace]:
                    run = True
                    
                    if "attribute" in kwargs:
                        __attribute = kwargs["attribute"]
                    if "new" in kwargs:
                        if __attribute is None and self.state[namespace][entity]["state"] == kwargs["new"]:
                            __new_state = kwargs["new"]
                        elif __attribute is not None and __attribute in self.state[namespace][entity]["attributes"] and self.state[namespace][entity]["attributes"][__attribute] == kwargs["new"]:
                            __new_state = kwargs["new"]
                        else:
                            run = False
                    else: #use the present state of the entity
                        if __attribute is None and "state" in self.state[namespace][entity]:
                            __new_state = self.state[namespace][entity]["state"]
                        elif __attribute is not None:
                            if __attribute in self.state[namespace][entity]["attributes"]:
                                __new_state = self.state[namespace][entity]["attributes"][__attribute]
                            elif __attribute == "all":
                                __new_state = self.state[namespace][entity]

                    if "duration" in kwargs:
                        __duration = kwargs["duration"]
                if run:
                    exec_time = await self.AD.sched.get_now() + datetime.timedelta(seconds=int(__duration))

                    if kwargs.get("oneshot", False):
                        kwargs["__handle"] = handle

                    kwargs["__duration"] = await self.AD.sched.insert_schedule(
                        name, exec_time, cb, False, None,
                        __entity=entity,
                        __attribute=__attribute,
                        __old_state=None,
                        __new_state=__new_state, **kwargs
                    )
                    
            await self.AD.state.add_entity("admin", "state_callback.{}".format(handle), "active",
                                                    {"app": name, "listened_entity": entity, "function": cb.__name__,
                                                     "pinned": pin_app, "pinned_thread": pin_thread, "fired": 0, "executed":0, "kwargs": kwargs})

            return handle
        else:
            return None

    async def cancel_state_callback(self, handle, name):
        if name not in self.AD.callbacks.callbacks or handle not in self.AD.callbacks.callbacks[name]:
            self.logger.warning("Invalid callback in cancel_state_callback() from app {}".format(name))

        if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
            del self.AD.callbacks.callbacks[name][handle]
            await self.AD.state.remove_entity("admin", "state_callback.{}".format(handle))
        if name in self.AD.callbacks.callbacks and self.AD.callbacks.callbacks[name] == {}:
            del self.AD.callbacks.callbacks[name]

    async def info_state_callback(self, handle, name):
        if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
            callback = self.AD.callbacks.callbacks[name][handle]
            return (
                callback["namespace"],
                callback["entity"],
                callback["kwargs"].get("attribute", None),
                self.sanitize_state_kwargs(self.AD.app_management.objects[name]["object"],
                                           callback["kwargs"])
            )
        else:
            raise ValueError("Invalid handle: {}".format(handle))

    async def process_state_callbacks(self, namespace, state):
        data = state["data"]
        entity_id = data['entity_id']
        self.logger.debug(data)
        device, entity = entity_id.split(".")

        # Process state callbacks

        removes = []
        for name in self.AD.callbacks.callbacks.keys():
            for uuid_ in self.AD.callbacks.callbacks[name]:
                callback = self.AD.callbacks.callbacks[name][uuid_]
                if callback["type"] == "state" and (callback["namespace"] == namespace or
                   callback["namespace"] == "global" or namespace == "global"):
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
                            name, callback["function"], entity_id,
                            cattribute,
                            data['new_state'],
                            data['old_state'],
                            cold, cnew,
                            callback["kwargs"],
                            uuid_,
                            callback["pin_app"],
                            callback["pin_thread"]
                        )
                    elif centity is None:
                        if device == cdevice:
                            executed = await self.AD.threading.check_and_dispatch_state(
                                name, callback["function"], entity_id,
                                cattribute,
                                data['new_state'],
                                data['old_state'],
                                cold, cnew,
                                callback["kwargs"],
                                uuid_,
                                callback["pin_app"],
                                callback["pin_thread"]
                            )

                    elif device == cdevice and entity == centity:
                        executed = await self.AD.threading.check_and_dispatch_state(
                            name, callback["function"], entity_id,
                            cattribute,
                            data['new_state'],
                            data['old_state'], cold,
                            cnew,
                            callback["kwargs"],
                            uuid_,
                            callback["pin_app"],
                            callback["pin_thread"]
                        )

                    # Remove the callback if appropriate
                    if executed is True:
                        remove = callback["kwargs"].get("oneshot", False)
                        if remove is True:
                            removes.append({"name": callback["name"], "uuid": uuid_})

        for remove in removes:
            await self.cancel_state_callback(remove["uuid"], remove["name"])

    async def entity_exists(self, namespace, entity):
        if namespace in self.state and entity in self.state[namespace]:
            return True
        else:
            return False

    def get_entity(self, namespace=None, entity_id=None, name=None):
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

    async def remove_entity(self, namespace, entity):
        if entity in self.state[namespace]:
            self.state[namespace].pop(entity)
            data = \
                {
                    "event_type": "__AD_ENTITY_REMOVED",
                    "data":
                        {
                            "entity_id": entity,
                        }
                }
            await self.AD.events.process_event(namespace, data)

    async def add_entity(self, namespace, entity, state, attributes=None):
        if attributes is None:
            attrs = {}
        else:
            attrs = attributes

        state = {"state": state, "last_changed": utils.dt_to_str(datetime.datetime(1970, 1, 1, 0, 0, 0, 0)), "attributes": attrs}

        self.state[namespace][entity] = state

        data = \
            {
                "event_type": "__AD_ENTITY_ADDED",
                "data":
                    {
                        "entity_id": entity,
                        "state": state,
                    }
            }

        await self.AD.events.process_event(namespace, data)

    async def get_state(
            self, name, namespace, entity_id=None, attribute=None,
            default=None, copy=True
    ):
        self.logger.debug("get_state: %s.%s %s %s",
                          entity_id, attribute, default, copy)

        maybe_copy = lambda data: deepcopy(data) if copy else data

        if entity_id is not None and "." in entity_id:
            if not await self.entity_exists(namespace, entity_id):
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
            raise ValueError(
                "{}: Querying a specific attribute is only possible for a single entity"
                .format(name)
            )

        if entity_id is None:
            return maybe_copy(self.state[namespace])

        domain = entity_id.split(".", 1)[0]
        return {
            entity_id: maybe_copy(state)
            for entity_id, state in self.state[namespace].items()
            if entity_id.split(".", 1)[0] == domain
        }

    def parse_state(self, entity_id, namespace, **kwargs):
        self.logger.debug("parse_state: %s, %s", entity_id, kwargs)

        if entity_id in self.state[namespace]:
            new_state = self.state[namespace][entity_id]
        else:
            # Its a new state entry
            new_state = {"attributes": {}}

        if "state" in kwargs:
            new_state["state"] = kwargs["state"]
            del kwargs["state"]

        if "attributes" in kwargs and kwargs.get('replace', False):
            new_state["attributes"] = kwargs["attributes"]
        else:
            if "attributes" in kwargs:
                new_state["attributes"].update(kwargs["attributes"])
            else:
                if "replace" in kwargs:
                    del kwargs["replace"]

                new_state["attributes"].update(kwargs)

        return new_state

    async def add_to_state(self, name, namespace, entity_id, i):
        value = await self.get_state(name, namespace, entity_id)
        if value is not None:
            value += i
            await self.set_state(name, namespace, entity_id, state=value)

    async def add_to_attr(self, name, namespace, entity_id, attr, i):
        state = await self.get_state(name, namespace, entity_id, attribute="all")
        if state is not None:
            state["attributes"][attr] = copy(state["attributes"][attr]) + i
            await self.set_state(name, namespace, entity_id, attributes=state["attributes"])

    def set_state_simple(self, namespace, entity_id, state):
        self.state[namespace][entity_id] = state

    async def state_services(self, namespace, domain, service, kwargs):
        self.logger.debug("state_services: %s, %s, %s, %s", namespace, domain, service, kwargs)
        if "entity_id" not in kwargs:
            self.logger.warning("Entity not specified in set_state service call: %s", kwargs)
            return
        else:
            entity_id = kwargs["entity_id"]
            del kwargs["entity_id"]

        if service == "set":
            await self.set_state(domain, namespace, entity_id, **kwargs)
        else:
            self.logger.warning("Unknown service in set_state service call: %s", kwargs)

    async def set_state(self, name, namespace, entity_id, **kwargs):
        self.logger.debug("set_state(): %s, %s", entity_id, kwargs)
        if entity_id in self.state[namespace]:
            old_state = deepcopy(self.state[namespace][entity_id])
        else:
            old_state = {"state": None, "attributes": {}}
        new_state = self.parse_state(entity_id, namespace, **kwargs)
        new_state["last_changed"] = utils.dt_to_str((await self.AD.sched.get_now()).replace(microsecond=0), self.AD.tz)
        self.logger.debug("Old state: %s", old_state)
        self.logger.debug("New state: %s", new_state)
        if not await self.AD.state.entity_exists(namespace, entity_id):
            if not ("_silent" in kwargs and kwargs["_silent"] is True):
                self.logger.info("%s: Entity %s created in namespace: %s", name, entity_id, namespace)

        # Fire the plugin's state update if it has one

        plugin = await self.AD.plugins.get_plugin_object(namespace)

        if hasattr(plugin, "set_plugin_state"):
                # We assume that the state change will come back to us via the plugin
                self.logger.debug("sending event to plugin")
                result = await plugin.set_plugin_state(namespace, entity_id, **kwargs)
                if result is not None:
                    if "entity_id" in result:
                        result.pop("entity_id")
                    self.state[namespace][entity_id] = self.parse_state(entity_id, namespace, **result)
        else:
            # Set the state locally
            self.state[namespace][entity_id] = new_state
            # Fire the event locally
            self.logger.debug("sending event locally")
            data = \
                        {
                            "event_type": "state_changed",
                            "data":
                                {
                                    "entity_id": entity_id,
                                    "new_state": new_state,
                                    "old_state": old_state
                                }
                        }

            await self.AD.events.process_event(namespace, data)

        return new_state

    def set_namespace_state(self, namespace, state):
        self.state[namespace] = state

    def update_namespace_state(self, namespace, state):
        self.state[namespace].update(state)

    async def save_namespace(self, namespace):
        if namespace in self.AD.namespaces:
            self.state[namespace].sync()
        else:
            self.logger.warning("Namespace: %s cannot be saved", namespace)
        return None

    def save_all_namespaces(self):
        for ns in self.AD.namespaces:
            self.state[ns].sync()

    def save_hybrid_namespaces(self):
        for ns in self.AD.namespaces:
            if self.AD.namespaces[ns].get("writeback") == "hybrid":
                self.state[ns].sync()

    #
    # Utilities
    #
    @staticmethod
    def sanitize_state_kwargs(app, kwargs):
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(kwargs_copy, [
            "old", "new", "__attribute", "duration", "state",
            "__entity", "__duration", "__old_state", "__new_state",
            "oneshot", "pin_app", "pin_thread", "__delay"
        ] + app.list_constraints())
