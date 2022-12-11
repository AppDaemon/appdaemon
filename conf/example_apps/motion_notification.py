import hassapi as hass
import globals

#
# App to send notification when motion detected
#
# Args:
#
# sensor: sensor to monitor e.g. input_binary.hall
#
# Release Notes
#
# Version 1.0:
#   Initial Version


class MotionNotification(hass.Hass):
    def initialize(self):
        if "sensor" in self.args:
            for sensor in self.split_device_list(self.args["sensor"]):
                self.listen_state(self.motion, sensor)
        else:
            self.listen_state(self.motion, "binary_sensor")

    def motion(self, entity, attribute, old, new, kwargs):
        if ("state" in new and new["state"] == "on" and old["state"] == "off") or new == "on":
            self.log("Motion detected: {}".format(self.friendly_name(entity)))
            self.notify(
                "Motion detected: {}".format(self.friendly_name(entity)),
                name=globals.notify,
            )
