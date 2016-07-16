import homeassistant as ha
import appapi

class Service(appapi.APPDaemon):

  def initialize(self):
    return
    ha.notify("", "Service initialized")
    #
    # turn_on and turn_off work with switches, lights, input_booleans, scenes and scripts
    #
    ha.turn_on("light.office_1")
    ha.run_in(self.name, self.toggle_light, 5)
    self.count = 0
   
  def toggle_light(self, args, kwargs):
    ha.toggle("light.office_1")
    self.count += 1
    if self.count < 6:
      ha.run_in(self.name, self.toggle_light, 5)
    else:
      ha.turn_off("light.office_1")
