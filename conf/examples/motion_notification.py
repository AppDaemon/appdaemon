import appapi

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

class MotionNotification(appapi.AppDaemon):

  def initialize(self):
    if "sensor" in self.args:
      self.listen_state(self.motion, self.args["sensor"])
    else:
      self.listen_state(self.motion, "binary_sensor")
    
  def motion(self, entity, attribute, old, new):
    if ("state" in new and new["state"] == "on" and old["state"] == "off") or new == "on": 
      self.notify("Motion detected: {}".format(self.friendly_name(entity)))