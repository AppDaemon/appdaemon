import hassapi as hass

#
# App to send notification when sensor values in specific ranges
# Args:
#
# sensor: sensor to monitor e.g. sensor.washer
# range_min: minimum value to regard as 'on'
# range_max: maximum value to regard as 'on'
# verbose_log: if set to anything will verbose_log on and off messages
# verbose_log: if set to anything will notify on and off messages
#
#
# Release Notes
#
# Version 1.0:
#   Initial Version


class SensorNotification(hass.Hass):
    def initialize(self):
        self.listen_state(self.state, self.args["sensor"])

    def in_range(self, value):
        if int(self.args["range_min"]) <= int(value) <= int(self.args["range_max"]):
            return True
        else:
            return False

    def state(self, entity, attribute, old, new, kwargs):
        if (not self.in_range(old)) and self.in_range(new):
            notify = "{} turned on".format(self.friendly_name(entity))
            self.log_notify(notify)

        if self.in_range(old) and (not self.in_range(new)):
            notify = "{} turned off".format(self.friendly_name(entity))
            self.log_notify(notify)

    def log_notify(self, message):
        if "verbose_log" in self.args:
            self.log(message)
        if "notify" in self.args:
            self.notify(message)
