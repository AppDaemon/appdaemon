import appapi
import datetime

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


class DarkDay(appapi.APPDaemon):

  def initialize(self):
    
    self.active = False
    self.listen_state(self.light_event, self.args["sensor"])

  def light_event(self, entity, attribute, old, new):
    lux = float(new)
    if lux < 200:
      self.active = True
      if "entity_on" in self.args:
        self.log("Low light detected: turning {} on".format(self.args["entity_on"]))
        self.turn_on(self.args["entity_on"])
    
    if lux > 400 and self.active:
      self.active = False
      if "entity_off" in self.args:
        # If it's a scene we need to turn it on not off
        device, entity = self.split_entity(self.args["entity_off"])
        if device == "scene":
          self.log("Brighter light detected: activating {}".format(self.args["entity_off"]))
          self.turn_on(self.args["entity_off"])
        else:
          self.log("It's brighter now: turning {} off".format(self.args["entity_off"]))
          self.turn_off(self.args["entity_off"])
