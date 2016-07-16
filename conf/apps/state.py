import homeassistant as ha
import appapi

class State(appapi.APPDaemon):

  def initialize(self):
    ha.listen_attr(self.name, self.attr, "input_select.house_mode", "state")
    state = ha.get_state("input_select.house_mode", "state")
    self.logger.info("State: Current State is {}".format(state))
    return
    ha.listen_attr(self.name, self.attr, "light.office_1", "state")
    ha.listen_attr(self.name, self.attr, "light.office_1", "attributes.brightness")
    #self.logger.info(self.args["param1"])
    ha.listen_state(self.name, self.all_state)
    ha.listen_state(self.name, self.lights, "light")
    ha.listen_state(self.name, self.lights, "light.office_1")


  def all_state(self, entity, old, new):
    self.logger.info("Entity {} changed state".format(entity))
    
  def lights(self, entity, old, new):
    self.logger.info("Light {} went from {} to {}".format(entity, old["state"], new["state"]))
    
  def attr(self, entity, attribute, old, new):
    self.logger.info("ATTR {} {} {} {}".format(entity, attribute, old, new))
   
