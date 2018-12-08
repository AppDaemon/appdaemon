import uuid
from copy import deepcopy
import traceback
import threading
import os
import iso8601

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon

class State:

    def __init__(self, ad: AppDaemon):

        self.AD = ad

        self.state = {}
        self.state["default"] = {}
        self.state["admin"] = {}
        self.state_lock = threading.RLock()
        self.logger = ad.logging.get_child("_state")

        # Initialize User Defined Namespaces

        nspath = os.path.join(self.AD.config_dir, "namespaces")
        try:
            if not os.path.isdir(nspath):
                os.makedirs(nspath)
            for ns in self.AD.namespaces:
                self.logger.info("User Defined Namespace '%s' initialized", ns)
                writeback = "safe"
                if "writeback" in self.AD.namespaces[ns]:
                    writeback = self.AD.namespaces[ns]["writeback"]

                safe = False
                if writeback == "safe":
                    safe = True

                self.state[ns] = utils.PersistentDict(os.path.join(nspath, ns), safe)
        except:
                self.logger.warning('-' * 60)
                self.logger.warning("Unexpected error in namespace setup")
                self.logger.warning('-' * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning('-' * 60)

    def list_namespaces(self):
        ns = []
        with self.state_lock:
            for namespace in self.state:
                ns.append(namespace)
        return ns

    def terminate(self):
        self.logger.debug("terminate() called for state")
        self.logger.info("Saving all namespaces")
        self.save_all_namespaces()

    def add_state_callback(self, name, namespace, entity, cb, kwargs):
        if self.AD.threading.validate_pin(name, kwargs) is True:
            with self.AD.app_management.objects_lock:
                if "pin" in kwargs:
                    pin_app = kwargs["pin"]
                else:
                    pin_app = self.AD.app_management.objects[name]["pin_app"]

                if "pin_thread" in kwargs:
                    pin_thread = kwargs["pin_thread"]
                    pin_app = True
                else:
                    pin_thread = self.AD.app_management.objects[name]["pin_thread"]

            with self.AD.callbacks.callbacks_lock:
                if name not in self.AD.callbacks.callbacks:
                    self.AD.callbacks.callbacks[name] = {}

                handle = uuid.uuid4()
                with self.AD.app_management.objects_lock:
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
            # In the case of a quick_start parameter,
            # start the clock immediately if the device is already in the new state
            #
            if "immediate" in kwargs and kwargs["immediate"] is True:
                if entity is not None and "new" in kwargs and "duration" in kwargs:
                    with self.state_lock:
                        if self.state[namespace][entity]["state"] == kwargs["new"]:
                            exec_time = self.AD.sched.get_now_ts() + int(kwargs["duration"])
                            kwargs["__duration"] = self.AD.sched.insert_schedule(
                                name, exec_time, cb, False, None,
                                __entity=entity,
                                __attribute=None,
                                __old_state=None,
                                __new_state=kwargs["new"], **kwargs
                            )

            return handle
        else:
            return None

    def cancel_state_callback(self, handle, name):
        with self.AD.callbacks.callbacks_lock:
            if name not in self.AD.callbacks.callbacks or handle not in self.AD.callbacks.callbacks[name]:
                self.logger.warning("Invalid callback in cancel_state_callback() from app {}".format(name))

            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                del self.AD.callbacks.callbacks[name][handle]
            if name in self.AD.callbacks.callbacks and self.AD.callbacks.callbacks[name] == {}:
                del self.AD.callbacks.callbacks[name]

    def info_state_callback(self, handle, name):
        with self.AD.callbacks.callbacks_lock:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                callback = self.AD.callbacks.callbacks[name][handle]
                with self.AD.app_management.objects_lock:
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
        with self.AD.callbacks.callbacks_lock:
            for name in self.AD.callbacks.callbacks.keys():
                for uuid_ in self.AD.callbacks.callbacks[name]:
                    callback = self.AD.callbacks.callbacks[name][uuid_]
                    if callback["type"] == "state" and (callback["namespace"] == namespace or callback[
                        "namespace"] == "global" or namespace == "global"):
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
                self.cancel_state_callback(remove["uuid"], remove["name"])

    def entity_exists(self, namespace, entity):
        with self.state_lock:
            if namespace in self.state and entity in self.state[namespace]:
                return True
            else:
                return False

    def get_entity(self, namespace = None, entity_id = None):
        with self.state_lock:
            if namespace is None:
                return self.state
            elif entity_id is None:
                if namespace in self.state:
                    return self.state[namespace]
                else:
                    self.logger.warning("Unknown namespace: %s", namespace)
            elif namespace in self.state:
                if entity_id in self.state[namespace]:
                    return self.state[namespace][entity_id]
                else:
                    self.logger.warning("Unknown namespace: %s", namespace)

            return None

    def get_namespaces(self):
        namespaces = []
        with self.state_lock:
            for ns in self.state:
                namespaces.append(ns)

        return namespaces

    async def add_entity(self, namespace, entity, state, attributes = None):
        if attributes is None:
            attrs = {}
        else:
            attrs = attributes

        with self.state_lock:
            self.state[namespace][entity] = {"state": state, "attributes": attrs}

    def get_state(self, name, namespace, entity_id=None, attribute=None):
        self.logger.debug("get_state: %s.%s", entity_id, attribute)
        device = None
        entity = None
        if entity_id is not None and "." in entity_id:
            if not self.AD.state.entity_exists(namespace, entity_id):
                return None
        if entity_id is not None:
            if "." not in entity_id:
                if attribute is not None:
                    raise ValueError(
                        "{}: Invalid entity ID: {}".format(name, entity))
                device = entity_id
                entity = None
            else:
                device, entity = entity_id.split(".")

        with self.state_lock:
            if device is None:
                return deepcopy(dict(self.state[namespace]))
            elif entity is None:
                devices = {}
                for entity_id in self.state[namespace].keys():
                    thisdevice, thisentity = entity_id.split(".")
                    if device == thisdevice:
                        devices[entity_id] = self.state[namespace][entity_id]
                return deepcopy(devices)
            elif attribute is None:
                entity_id = "{}.{}".format(device, entity)
                if entity_id in self.state[namespace]:
                    return deepcopy(self.state[namespace][entity_id]["state"])
                else:
                    return None
            else:
                entity_id = "{}.{}".format(device, entity)
                if attribute == "all":
                    if entity_id in self.state[namespace]:
                        return deepcopy(self.state[namespace][entity_id])
                    else:
                        return None
                else:
                    if namespace in self.state and entity_id in self.state[namespace]:
                        if attribute in self.state[namespace][entity_id]["attributes"]:
                            return deepcopy(self.state[namespace][entity_id]["attributes"][
                                                attribute])
                        elif attribute in self.state[namespace][entity_id]:
                            return deepcopy(self.state[namespace][entity_id][attribute])
                        else:
                            return None
                    else:
                        return None

    def parse_state(self, entity_id, namespace, **kwargs):
        self.logger.debug("parse_state: %s, %s", entity_id, kwargs)

        if entity_id in self.state[namespace]:
            new_state = self.state[namespace][entity_id]
        else:
            # Its a new state entry
            new_state = {}
            new_state["attributes"] = {}

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
        value = self.get_state(name, namespace, entity_id)
        value += i
        await self.set_state(name, namespace, entity_id, state=value)

    def set_state_simple(self, namespace, entity_id, state):
        with self.state_lock:
            self.state[namespace][entity_id] = state

    async def set_state(self, name, namespace, entity_id, **kwargs):

        with self.state_lock:
            old_state = self.state[namespace][entity_id]
            new_state = self.parse_state(entity_id, namespace, **kwargs)

            if not self.AD.state.entity_exists(namespace, entity_id):
                self.logger.info("%s: Entity %s created in namespace: %s", name, entity_id, namespace)
                data = ret = \
                        {
                            "event_type": "state_changed",
                            "data":
                                {
                                    "entity_id": entity_id,
                                    "new_state": new_state,
                                    "old_state": old_state
                                }
                        }
                await self.AD.thread_async.call_async_no_wait(self.AD.events.process_event, namespace, {"event_type": "state_changed", "data": data})

        return new_state

    def set_namespace_state(self, namespace, state):
        with self.state_lock:
            self.state[namespace] = state

    def update_namespace_state(self, namespace, state):
        with self.state_lock:
            self.state[namespace].update(state)

    def save_namespace(self, namespace):
        with self.state_lock:
            self.state[namespace].save()

    def save_all_namespaces(self):
        with self.state_lock:
            for ns in self.AD.namespaces:
                self.state[ns].save()

    def save_hybrid_namespaces(self):
        with self.state_lock:
            for ns in self.AD.namespaces:
                if self.AD.namespaces[ns]["writeback"] == "hybrid":
                    self.state[ns].save()

    #
    # Utilities
    #

    def sanitize_state_kwargs(self, app, kwargs):
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(kwargs_copy, [
            "old", "new", "__attribute", "duration", "state",
            "__entity", "__duration", "__old_state", "__new_state",
            "oneshot", "pin_app", "pin_thread"
        ] + app.list_constraints())
