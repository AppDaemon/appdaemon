import appapi

#
# App to send notification when door opened or closed
#
# Args:
#
# sensor: sensor to monitor e.g. input_binary.hall
#
# Release Notes
#
# Version 1.0:
#   Initial Version

class DoorNotification(appapi.AppDaemon):

  def initialize(self):
    if "sensor" in self.args:
      for sensor in self.split_device_list(self.args["sensor"]):
        self.listen_state(self.state_change, sensor)
    else:
      self.listen_state(self.motion, "binary_sensor")   
    
  def state_change(self, entity, attribute, old, new, kwargs):
    self.log("{} is {}".format(self.friendly_name(entity), new))
    self.notify("{} is {}".format(self.friendly_name(entity), new))