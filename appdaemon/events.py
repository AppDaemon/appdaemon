"""Module to handle all events within AppDaemon."""

import uuid
from copy import deepcopy
import traceback
import datetime

from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils


class Events:
    """Encapsulate event handling."""

    def __init__(self, ad: AppDaemon):
        """Constructor.

        Args:
            ad: Reference to the AppDaemon object
        """

        self.AD = ad
        self.logger = ad.logging.get_child("_events")
        #
        # Events
        #

    async def add_event_callback(self, name, namespace, cb, event, **kwargs):
        """Adds a callback for an event which is called internally by apps.

        Args:
            name (str): Name of the app.
            namespace  (str): Namespace of the event.
            cb: Callback function.
            event (str): Name of the event.
            **kwargs: List of values to filter on, and additional arguments to pass to the callback.

        Returns:
            ``None`` or the reference to the callback handle.

        """

        if self.AD.threading.validate_pin(name, kwargs) is True:
            if "pin" in kwargs:
                pin_app = kwargs["pin_app"]
            else:
                pin_app = self.AD.app_management.objects[name]["pin_app"]

            if "pin_thread" in kwargs:
                pin_thread = kwargs["pin_thread"]
                pin_app = True
            else:
                pin_thread = self.AD.app_management.objects[name]["pin_thread"]

            async with self.AD.callbacks.callbacks_lock:
                if name not in self.AD.callbacks.callbacks:
                    self.AD.callbacks.callbacks[name] = {}
                handle = uuid.uuid4().hex
                self.AD.callbacks.callbacks[name][handle] = {
                    "name": name,
                    "id": self.AD.app_management.objects[name]["id"],
                    "type": "event",
                    "function": cb,
                    "namespace": namespace,
                    "event": event,
                    "pin_app": pin_app,
                    "pin_thread": pin_thread,
                    "kwargs": kwargs,
                }

            if "timeout" in kwargs:
                exec_time = await self.AD.sched.get_now() + datetime.timedelta(seconds=int(kwargs["timeout"]))

                kwargs["__timeout"] = await self.AD.sched.insert_schedule(
                    name, exec_time, None, False, None, __event_handle=handle,
                )

            await self.AD.state.add_entity(
                "admin",
                "event_callback.{}".format(handle),
                "active",
                {
                    "app": name,
                    "event_name": event,
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

    async def cancel_event_callback(self, name, handle):
        """Cancels an event callback.

        Args:
            name (str): Name of the app or module.
            handle: Previously supplied callback handle for the callback.

        Returns:
            None.

        """

        executed = False

        async with self.AD.callbacks.callbacks_lock:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                del self.AD.callbacks.callbacks[name][handle]
                await self.AD.state.remove_entity("admin", "event_callback.{}".format(handle))
                executed = True

            if name in self.AD.callbacks.callbacks and self.AD.callbacks.callbacks[name] == {}:
                del self.AD.callbacks.callbacks[name]

        if not executed:
            self.logger.warning("Invalid callback handle '{}' in cancel_event_callback() from app {}".format(handle, name))

        return executed

    async def info_event_callback(self, name, handle):
        """Gets the information of an event callback.

        Args:
            name (str): Name of the app or subsystem.
            handle: Previously supplied handle for the callback.

        Returns:
            A dictionary of callback entries or rise a ``ValueError`` if an invalid handle is provided.

        """

        async with self.AD.callbacks.callbacks_lock:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                callback = self.AD.callbacks.callbacks[name][handle]
                return callback["event"], callback["kwargs"].copy()
            else:
                raise ValueError("Invalid handle: {}".format(handle))

    async def fire_event(self, namespace, event, **kwargs):
        """Fires an event.

        If the namespace does not have a plugin associated with it, the event will be fired locally.
        If a plugin is associated, the firing of the event will be delegated to the plugin, under the
        understanding that when the event is fired, the plugin will notify appdaemon that it occurred,
        usually via the system the plugin is communicating with.

        Args:
            namespace (str): Namespace for the event to be fired in.
            event (str): Name of the event.
            **kwargs: Arguments to associate with the event.

        Returns:
            None.

        """

        self.logger.debug("fire_plugin_event() %s %s %s", namespace, event, kwargs)
        plugin = await self.AD.plugins.get_plugin_object(namespace)

        if hasattr(plugin, "fire_plugin_event"):
            # We assume that the event will come back to us via the plugin
            await plugin.fire_plugin_event(event, namespace, **kwargs)
        else:
            # Just fire the event locally
            await self.AD.events.process_event(namespace, {"event_type": event, "data": kwargs})

    async def process_event(self, namespace, data):
        """Processes an event that has been received either locally or from a plugin.

        Args:
            namespace (str): Namespace the event was fired in.
            data: Data associated with the event.

        Returns:
            None.

        """

        try:

            # if data["event_type"] == "__AD_ENTITY_REMOVED":
            #    print("process event")

            self.logger.debug("Event type:%s:", data["event_type"])
            self.logger.debug(data["data"])

            # Kick the scheduler so it updates it's clock
            if self.AD.sched is not None and self.AD.sched.realtime is False and namespace != "admin":
                await self.AD.sched.kick()

            if data["event_type"] == "state_changed":
                if "entity_id" in data["data"] and "new_state" in data["data"]:
                    if data["data"]["new_state"] is None:
                        # most likely it is a deleted entity
                        return

                    entity_id = data["data"]["entity_id"]

                    self.AD.state.set_state_simple(namespace, entity_id, data["data"]["new_state"])

                    if self.AD.apps is True and namespace != "admin":
                        await self.AD.state.process_state_callbacks(namespace, data)
                else:
                    self.logger.warning("Malformed 'state_changed' event: %s", data["data"])
                    return

            # Check for log callbacks and exit to prevent loops
            if data["event_type"] == "__AD_LOG_EVENT":
                if await self.has_log_callback(data["data"]["app_name"]):
                    self.logger.debug("Discarding event for loop avoidance")
                    return

                await self.AD.logging.process_log_callbacks(namespace, data)

            if self.AD.apps is True:  # and namespace != "admin":

                # Process callbacks
                await self.process_event_callbacks(namespace, data)

            #
            # Send to the stream
            #

            if self.AD.http is not None:

                if data["event_type"] == "state_changed":
                    if data["data"]["new_state"] == data["data"]["old_state"]:
                        # Nothing changed so don't send
                        return

                # take a copy without TS if present as it breaks deepcopy and jason
                if "ts" in data["data"]:
                    ts = data["data"].pop("ts")
                    mydata = deepcopy(data)
                    data["data"]["ts"] = ts
                else:
                    mydata = deepcopy(data)

                await self.AD.http.stream_update(namespace, mydata)

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during process_event()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

    async def has_log_callback(self, name):
        """Returns ``True`` if the app has a log callback, ``False`` otherwise.

        Used to prevent callback loops. In the calling logic, if this function returns
        ``True`` the resulting logging event will be suppressed.

        Args:
            name (str): Name of the app.

        """

        has_log_callback = False
        if name == "AppDaemon._stream":
            has_log_callback = True
        else:
            async with self.AD.callbacks.callbacks_lock:
                for callback in self.AD.callbacks.callbacks:
                    for _uuid in self.AD.callbacks.callbacks[callback]:
                        cb = self.AD.callbacks.callbacks[callback][_uuid]
                        if cb["name"] == name and cb["type"] == "event" and cb["event"] == "__AD_LOG_EVENT":
                            has_log_callback = True
                        elif cb["name"] == name and cb["type"] == "log":
                            has_log_callback = True

        return has_log_callback

    async def process_event_callbacks(self, namespace, data):
        """Processes a pure event callback.

        Locate any callbacks that may be registered for this event, check for filters and if appropriate,
        dispatch the event for further checking and eventual action.

        Args:
            namespace (str): Namespace of the event.
            data: Data associated with the event.

        Returns:
            None.

        """

        self.logger.debug("process_event_callbacks() %s %s", namespace, data)

        removes = []
        async with self.AD.callbacks.callbacks_lock:
            for name in self.AD.callbacks.callbacks.keys():
                for uuid_ in self.AD.callbacks.callbacks[name]:
                    callback = self.AD.callbacks.callbacks[name][uuid_]
                    if callback["namespace"] == namespace or callback["namespace"] == "global" or namespace == "global":
                        #
                        # Check for either a blank event (for all events)
                        # Or the event is a match
                        # But don't allow a global listen for any system events (events that start with __)
                        #
                        if "event" in callback and (
                            (callback["event"] is None and data["event_type"][:2] != "__")
                            or data["event_type"] == callback["event"]
                        ):

                            # Check any filters

                            _run = True
                            for key in callback["kwargs"]:
                                if key in data["data"] and callback["kwargs"][key] != data["data"][key]:
                                    _run = False

                            if data["event_type"] == "__AD_LOG_EVENT":
                                if (
                                    "log" in callback["kwargs"]
                                    and callback["kwargs"]["log"] != data["data"]["log_type"]
                                ):
                                    _run = False

                            if _run:
                                if name in self.AD.app_management.objects:
                                    executed = await self.AD.threading.dispatch_worker(
                                        name,
                                        {
                                            "id": uuid_,
                                            "name": name,
                                            "objectid": self.AD.app_management.objects[name]["id"],
                                            "type": "event",
                                            "event": data["event_type"],
                                            "function": callback["function"],
                                            "data": data["data"],
                                            "pin_app": callback["pin_app"],
                                            "pin_thread": callback["pin_thread"],
                                            "kwargs": callback["kwargs"],
                                        },
                                    )

                                    # Remove the callback if appropriate
                                    if executed is True:
                                        remove = callback["kwargs"].get("oneshot", False)
                                        if remove is True:
                                            removes.append({"name": name, "uuid": uuid_})

        for remove in removes:
            await self.cancel_event_callback(remove["name"], remove["uuid"])

    async def event_services(self, namespace, domain, service, kwargs):
        if "event" in kwargs:
            event = kwargs["event"]
            del kwargs["event"]
            await self.fire_event(namespace, event, **kwargs)
        else:
            self.logger.warning("Malformed 'fire_event' service call, as no event given")

    @staticmethod
    def sanitize_event_kwargs(app, kwargs):
        kwargs_copy = kwargs.copy()
        return utils._sanitize_kwargs(kwargs_copy, ["__silent"])
