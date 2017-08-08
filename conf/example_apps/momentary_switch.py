import appdaemon.appapi as appapi
import globals

#
# App to make a regular switch act as a momentary switch
# Args:
#
# switch: switch to make momentary e.g. switch.garage
# delay: amount of time to waut upon activation of the switch before turning it off
# 
#
# Release Notes
#
# Version 1.0:
#   Initial Version

class MomentarySwitch(appapi.AppDaemon):

  def initialize(self):
    self.listen_state(self.state_change, self.args["switch"], new="on")

  def state_change(self, entity, attribute, old, new, kwargs):
    self.log_notify("{} turned {}".format(entity, new))
    self.run_in(self.switch_off, self.args["delay"], switch = entity)
  
  def switch_off(self, kwargs):
    self.log_notify("Turning {} off".format(kwargs["switch"]))
    self.turn_off(self.args["switch"])
      
  def log_notify(self, message):
    if "log" in self.args:
      self.log(message)
    if "notify" in self.args:
      self.notify(message, name=globals.notify)
