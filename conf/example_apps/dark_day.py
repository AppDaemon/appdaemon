import hassapi as hass

#
# App to turn lights on when it gets dark during the day
#
# Use with input_select or time constraints to have it run during daytime when someone is home only
#
# Args:
#
# sensor: binary sensor to use as trigger
# entity_on : entity to turn on when detecting motion, can be a light, script, scene or anything else that can be turned on
# entity_off : entity to turn off when detecting motion, can be a light, script or anything else that can be turned off. Can also be a scene which will be turned on
#
# Release Notes
#
# Version 1.0:
#   Initial Version


class DarkDay(hass.Hass):
    def initialize(self):

        self.active = False
        self.set_state("sensor.dark_day", state=0)
        self.listen_state(self.light_event, self.args["sensor"])

    def light_event(self, entity, attribute, old, new, kwargs):
        lux = float(new)
        # Can't use a constraint for this because if self.active = true when the constraint kicks in it will never get cleared
        # and the program will ignore future changes
        if self.now_is_between(self.args["start_time"], self.args["end_time"]):
            if lux < 200 and not self.active:
                self.active = True
                self.set_state("sensor.dark_day", state=1)
                if "entity_on" in self.args:
                    self.log("Low light detected: turning {} on".format(self.args["entity_on"]))
                    self.turn_on(self.args["entity_on"])

            if lux > 400 and self.active:
                self.active = False
                self.set_state("sensor.dark_day", state=0)
                if "entity_off" in self.args:
                    self.log("Brighter light detected: turning {} off".format(self.args["entity_off"]))
                    self.turn_off(self.args["entity_off"])
        else:
            # We are now dormant so set self.active false
            self.active = False
            self.set_state("sensor.dark_day", state=0)
