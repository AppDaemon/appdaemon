import hassapi as hass
import globals

#
# App to send notification when a sensor changes state
#
# Args:
#
# sensor: sensor to monitor e.g. sensor.upstairs_smoke
# idle_state - normal state of sensor e.g. Idle
# turn_on - scene or device to activate when sensor changes e.g. scene.house_bright
# Release Notes
#
# Version 1.0:
#   Initial Version


class SensorNotification(hass.Hass):
    def initialize(self):
        if "sensor" in self.args:
            for sensor in self.split_device_list(self.args["sensor"]):
                self.listen_state(self.state_change, sensor)

    def state_change(self, entity, attribute, old, new, kwargs):
        if new != "":
            if "input_select" in self.args:
                valid_modes = self.split_device_list(self.args["input_select"])
                select = valid_modes.pop(0)
                is_state = self.get_state(select)
            else:
                is_state = None
                valid_modes = ()

            self.log("{} changed to {}".format(self.friendly_name(entity), new))
            self.notify(
                "{} changed to {}".format(self.friendly_name(entity), new), name=globals.notify,
            )
            if "idle_state" in self.args:
                if new != self.args["idle_state"] and "turn_on" in self.args and is_state in valid_modes:
                    self.turn_on(self.args["turn_on"])
