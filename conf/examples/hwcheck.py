import appdaemon.appapi as appapi

#
# App to check if zwavbe and hue hardware is correctly configured after a restart
#
# Args:
#
#delay - amount of time after restart to perform the check
#zwave - representative ZWave device to check the existence of
#hue = representative Hue device to check the existence of
# 
#
# Release Notes
#
# Version 1.0:
#   Initial Version

class HWCheck(appapi.AppDaemon):

  def initialize(self):
    
    self.listen_event(self.ha_event, "ha_started")
    self.listen_event(self.appd_event, "appd_started")
    
  def ha_event(self, event_name, data, kwargs):
    self.log_notify("Home Assistant is up", "INFO")
    self.run_in(self.hw_check, self.args["delay"])
    
  def appd_event(self, event_name, data, kwargs):
    self.log_notify("AppDaemon is up", "INFO")
    self.run_in(self.hw_check, self.args["delay"])
    
  def hw_check(self, kwargs):
    state = self.get_state()
    
    if "zwave" in self.args and self.args["zwave"] not in state:
      self.log_notify("ZWAVE not started after delay period", "WARNING")
    if "hue" in self.args and self.args["hue"] not in state:
      self.log_notify("HUE not started after delay period", "WARNING")
      
  def log_notify(self, message, level = "INFO"):
    if "log" in self.args:
      self.log(message)
    if "notify" in self.args:
      self.notify(message, level)