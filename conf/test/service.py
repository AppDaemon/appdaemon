import appapi

class Service(appapi.APPDaemon):

  def initialize(self):
    return
    self.notify("", "Service initialized")
    #
    # turn_on and turn_off work with switches, lights, input_booleans, scenes and scripts
    #
    self.turn_on("light.office_1")
    self.run_in(self.toggle_light, 5)
    self.count = 0
   
  def toggle_light(self, args, kwargs):
    self.log("Toggling Light")
    self.toggle("light.office_1")
    self.count += 1
    if self.count < 6:
      self.run_in(self.toggle_light, 5)
    else:
      self.turn_off("light.office_1")
