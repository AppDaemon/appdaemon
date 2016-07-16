import homeassistant as ha
import appapi

class MirrorLight(appapi.APPDaemon):

  def initialize(self):
    ha.listen_state(self.name, self.light_changed, "light.andrew_bedside")
    
    state = ha.get_state("light.andrew_bedside", "state")
    brightness = ha.get_state("light.andrew_bedside", "attributes.brightness")
    
    self.logger.info("MirrorLight: Current State is {}, current brightness is {}".format(state, brightness))
    
    if ha.get_state("light.andrew_bedside", "state") == "on":
      ha.turn_on("light.office_lamp")

  def light_changed(self, entity, old_state, new_state):
    self.logger.info("entity state changed, old: {}, new: {}".format(old_state["state"], new_state["state"]))
    
    if new_state["state"] == 'on':
      #ha.turn_on("light.office_lamp")
      ha.turn_on("light.office_lamp", color_name = "blue")
    else:
      ha.turn_off("light.office_lamp")
