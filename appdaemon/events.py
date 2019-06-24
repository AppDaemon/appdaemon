"""
Module to handle all events within AppDameon.
"""

import uuid
from copy import deepcopy
import traceback

from appdaemon.appdaemon import AppDaemon

class Events:
    """
    Encapsulate event handling.
    """

    def __init__(self, ad: AppDaemon):

        """
        Constructor.

        :param ad: Reference to the AppDaemon object
        """

        self.AD = ad
        self.logger = ad.logging.get_child("_events")
        #
        # Events
        #

    async def add_event_callback(self, _name, namespace, cb, event, **kwargs):
        """
        Called by apps and internally to add a callback for an event.

        :param _name: name of the app
        :param namespace: namespace of the event
        :param cb: callback
        :param event: name of the event
        :param kwargs: list of values to filter on, and additional arguments to pass to the callback
        """

        if self.AD.threading.validate_pin(_name, kwargs) is True:
            if "pin" in kwargs:
                pin_app = kwargs["pin_app"]
            else:
                pin_app = self.AD.app_management.objects[_name]["pin_app"]

            if "pin_thread" in kwargs:
                pin_thread = kwargs["pin_thread"]
                pin_app = True
            else:
                pin_thread = self.AD.app_management.objects[_name]["pin_thread"]

            if _name not in self.AD.callbacks.callbacks:
                self.AD.callbacks.callbacks[_name] = {}
            handle = uuid.uuid4().hex
            self.AD.callbacks.callbacks[_name][handle] = {
                "name": _name,
                "id": self.AD.app_management.objects[_name]["id"],
                "type": "event",
                "function": cb,
                "namespace": namespace,
                "event": event,
                "pin_app": pin_app,
                "pin_thread": pin_thread,
                "kwargs": kwargs
            }

            await self.AD.state.add_entity("admin", "event_callback.{}".format(handle), "active", {"app": _name, "event_name": event, "function": cb.__name__, "pinned": pin_app, "pinned_thread": pin_thread, "fired": 0, "executed": 0, "kwargs": kwargs})
            return handle
        else:
            return None

    async def cancel_event_callback(self, name, handle):
        """
        Cancel an event callback.

        :param name: app or module name
        :param handle: previously supplied callback handle for the callback
        """
        if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
            del self.AD.callbacks.callbacks[name][handle]
            await self.AD.state.remove_entity("admin",
                                                "event_callback.{}".format(handle))
        if name in self.AD.callbacks.callbacks and self.AD.callbacks.callbacks[name] == {}:
            del self.AD.callbacks.callbacks[name]

    async def info_event_callback(self, name, handle):
        """
        Return information on an event callback.

        :param name: name of the app or subsystem
        :param handle: previously supplied handle for the calllback
        :return: dictionary of callback entries
        """
        if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
            callback = self.AD.callbacks.callbacks[name][handle]
            return callback["event"], callback["kwargs"].copy()
        else:
            raise ValueError("Invalid handle: {}".format(handle))

    async def fire_event(self, namespace, event, **kwargs):
        """
        Fire an event.

        If the namespace does not have a plugin associated with it, the event will be fired locally. If a plugin is associated, the firing of the event will be delegated to the plugin, under the understanding that when the event is fired, the plugin will notify appdaemon that it occured, usually via the system the plugin is communicating with.

        :param namespace: namespace for the event to be fired in
        :param event: name of the event
        :param kwargs: arguments to associate with the event.
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
        """
        Process an event that has been recieved either locally or from a plugin.

        :param namespace: namespace the event was fired in
        :param data: data associated with the event
        """

        try:

            #if data["event_type"] == "__AD_ENTITY_REMOVED":
            #    print("process event")

            self.logger.debug("Event type:%s:", data['event_type'])
            self.logger.debug(data["data"])

            # Kick the scheduler so it updates it's clock for time travel
            if self.AD.sched is not None and self.AD.sched.realtime is False and namespace != "admin":
                await self.AD.sched.kick()

            if data['event_type'] == "state_changed":
                if 'entity_id' in data['data'] and 'new_state' in data['data']:
                    entity_id = data['data']['entity_id']

                    self.AD.state.set_state_simple(namespace, entity_id, data['data']['new_state'])

                    if self.AD.apps is True and namespace != "admin":
                        # Process state changecallbacks
                        if data['event_type'] == "state_changed":
                            await self.AD.state.process_state_callbacks(namespace, data)
                else:
                    self.logger.warning("Malformed 'state_changed' event: %s", data['data'])
                    return


            if self.AD.apps is True and namespace != "admin":
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

        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error during process_event()")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)

    def has_log_callback(self, name):
        """
        Check if an app has a log callback.

        Used to prevent callback loops. In the calling logic, if this function returns true the resulting logging event will be suppressed.
        :param name: name of the app
        :return:
        """
        has_log_callback = False
        if name == "AppDaemon._stream":
            has_log_callback = True
        else:
            for callback in self.AD.callbacks.callbacks:
                for uuid in self.AD.callbacks.callbacks[callback]:
                    cb = self.AD.callbacks.callbacks[callback][uuid]
                    if cb["name"] == name and cb["type"] == "event" and cb["event"] == "__AD_LOG_EVENT":
                        has_log_callback = True

        return has_log_callback

    async def process_event_callbacks(self, namespace, data):
        """
        Process a pure event callback.

        Locate any callbacks that may be registered for this event, check for filters and if appropriate, dispatch the event for further checking and eventual action.

        :param namespace: namesoace of the event
        :param data: data associated with the event.
        """

        self.logger.debug("process_event_callbacks() %s %s", namespace, data)
        # Check for log callbacks and exit to prevent loops
        if data["event_type"] == "__AD_LOG_EVENT":
            if self.has_log_callback(data["data"]["app_name"]):
                self.logger.debug("Discarding event for loop avoidance")
                return

        for name in self.AD.callbacks.callbacks.keys():
            for uuid_ in self.AD.callbacks.callbacks[name]:
                callback = self.AD.callbacks.callbacks[name][uuid_]
                if callback["namespace"] == namespace or callback[
                    "namespace"] == "global" or namespace == "global":
                    #
                    # Check for either a blank event (for all events)
                    # Or the event is a match
                    # But don't allow a global listen for any system events (events that start with __)
                    #
                    if "event" in callback and (
                            (callback["event"] is None and data['event_type'][:2] != "__")
                            or data['event_type'] == callback["event"]):

                        # Check any filters

                        _run = True
                        for key in callback["kwargs"]:
                            if key in data["data"] and callback["kwargs"][key] != \
                                    data["data"][key]:
                                _run = False

                        if data["event_type"] == "__AD_LOG_EVENT":
                            if "log" in callback["kwargs"] and callback["kwargs"]["log"] != data["data"]["log_type"]:
                                _run = False

                        if _run:
                            if name in self.AD.app_management.objects:
                                await self.AD.threading.dispatch_worker(name, {
                                    "id": uuid_,
                                    "name": name,
                                    "objectid": self.AD.app_management.objects[name]["id"],
                                    "type": "event",
                                    "event": data['event_type'],
                                    "function": callback["function"],
                                    "data": data["data"],
                                    "pin_app": callback["pin_app"],
                                    "pin_thread": callback["pin_thread"],
                                    "kwargs": callback["kwargs"]
                                })
