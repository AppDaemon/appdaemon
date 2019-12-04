import hassapi as hass
import os
import json

"""

Enable caching of appdaemon events.

You would probably NOT want to use this for HomeAssistant events.

The reason you would use this is probably because you're using custom events in
some other appdaemon app, and want this event to be available (typically for
hadashboard) before the app has been able to publish a fresh event.

Simply put, you list up events you want to monitor, and every time this event
is published, it is persisted to disk. When this app is restarted (probably
because of a restart of appdaemon), it will publish all monitored events at
startup.

Arguments:
 - cache: Location, on disk, where the events are stored
 - events: List of events to monitor, and later publish

"""


class Cache(hass.Hass):
    def initialize(self):
        self.cache = self.args["cache"]
        self.events = self.args["events"]

        self.state = self.loadCache()
        self.deprecateOldEvents()

        self.publishCache()

        for event in self.events:
            self.log('watching event "{}" for state changes'.format(event))
            self.listen_state(self.changed, event)

    def loadCache(self):
        if not os.path.exists(self.cache):
            with open(self.cache, mode="w") as f:
                json.dump({}, f)

        with open(self.cache) as f:
            try:
                return json.load(f)
            except Exception:
                return {}

    def saveCache(self):
        try:
            with open(self.cache, mode="w") as f:
                json.dump(self.state, f)
        except Exception:
            self.log("oops during save of cache")

    def deprecateOldEvents(self):
        deprecatedEvents = [e for e in self.state if e not in self.events]
        for deprecated in deprecatedEvents:
            del self.state[deprecated]

    def publishCache(self):
        for event in self.events:
            if event in self.state:
                self.set_app_state(event, self.state[event])
                self.log("published event: " + event)
            else:
                self.log("event not in cache: " + event)

    def changed(self, entity, attribute, old, new, kwargs):
        value = self.get_state(entity, "all")
        self.state[entity] = value
        self.saveCache()
