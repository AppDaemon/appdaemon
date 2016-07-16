import appapi

class MotionLights(appapi.APPDaemon):

  def initialize(self):
    return
    self.listen_state(self.motion, "binary_sensor.upstairs_sensor_28")
  
  def motion(self, entity, attribute, old, new):
    if new == "on":
    #if new == "on" and self.sun_state() == "below_horizon":
      self.turn_on("light.office_1")
      self.run_in(self.light_off, 60)
      self.flashcount = 0
      self.run_in(self.flash_warning, 1)
  
  def light_off(self, args, kwargs):
    self.turn_off("light.office_1")
    
  def flash_warning(self, args, kwargs):
    self.toggle("light.office_2")
    self.flashcount += 1
    if self.flashcount < 10:
      self.run_in(self.flash_warning, 1)
  
