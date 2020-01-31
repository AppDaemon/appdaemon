import hassapi as hass

"""

Monitor events and output changes to the verbose_log. Nice for debugging purposes.

Arguments:
 - events: List of events to monitor

"""


class Monitor(hass.Hass):
    def initialize(self):
        events = self.args["events"]

        for event in events:
            self.changed(event, None, None, None, None)

            self.log('watching event "{}" for state changes'.format(event))
            self.listen_state(self.changed, event)

    def changed(self, entity, attribute, old, new, kwargs):
        value = self.get_state(entity, "all")
        self.log(entity + ": " + str(value))
