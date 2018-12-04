import uuid

from appdaemon.appdaemon import AppDaemon


class Events:

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.logger = ad.logging.get_child("_events")
        #
        # Events
        #

    def add_event_callback(self, _name, namespace, cb, event, **kwargs):
        if self.AD.threading.validate_pin(_name, kwargs) is True:
            with self.AD.app_management.objects_lock:
                if "pin" in kwargs:
                    pin_app = kwargs["pin_app"]
                else:
                    pin_app = self.AD.app_management.objects[_name]["pin_app"]

                if "pin_thread" in kwargs:
                    pin_thread = kwargs["pin_thread"]
                    pin_app = True
                else:
                    pin_thread = self.AD.app_management.objects[_name]["pin_thread"]

            with self.AD.callbacks.callbacks_lock:
                if _name not in self.AD.callbacks.callbacks:
                    self.AD.callbacks.callbacks[_name] = {}
                handle = uuid.uuid4()
                with self.AD.app_management.objects_lock:
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
            return handle
        else:
            return None

    def cancel_event_callback(self, name, handle):
        with self.AD.callbacks.callbacks_lock:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                del self.AD.callbacks.callbacks[name][handle]
            if name in self.AD.callbacks.callbacks and self.AD.callbacks.callbacks[name] == {}:
                del self.AD.callbacks.callbacks[name]

    def info_event_callback(self, name, handle):
        with self.AD.callbacks.callbacks_lock:
            if name in self.AD.callbacks.callbacks and handle in self.AD.callbacks.callbacks[name]:
                callback = self.AD.callbacks.callbacks[name][handle]
                return callback["event"], callback["kwargs"].copy()
            else:
                raise ValueError("Invalid handle: {}".format(handle))

    def process_event(self, namespace, data):
        with self.AD.callbacks.callbacks_lock:
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
                                with self.AD.app_management.objects_lock:
                                    if name in self.AD.app_management.objects:
                                        self.AD.threading.dispatch_worker(name, {
                                            "name": name,
                                            "id": self.AD.app_management.objects[name]["id"],
                                            "type": "event",
                                            "event": data['event_type'],
                                            "function": callback["function"],
                                            "data": data["data"],
                                            "pin_app": callback["pin_app"],
                                            "pin_thread": callback["pin_thread"],
                                            "kwargs": callback["kwargs"]
                                        })
