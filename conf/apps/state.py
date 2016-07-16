import appapi

class State(appapi.APPDaemon):

  def initialize(self):
    return
    # Set some callbacks
    #self.handle = self.listen_state(self.all_state)
    
    # set timer to cancel above callback in 10 seconds
    
    #self.run_in(self.cancel, 10)

    #self.listen_state(self.device, "light")
    #self.listen_state(self.entity, "light.office_1")
    #self.listen_state(self.attr, "light.office_1", "all")
    #self.listen_state(self.attr, "light.office_1", "state")
    #self.listen_state(self.attr, "light.office_1", "brightness")
    
    
    # Check some state values
    #state = self.get_state()
    #self.log(state)
    #state = self.get_state("media_player")
    #self.log(state)
    #state = self.get_state("light.office_1")
    #self.log(state)
    #state = self.get_state("light.office_1", "brightness")
    #self.log(state)
    #state = self.get_state("light.office_1", "all")
    #self.log(state)
    
    # Invalid combination
    
    #state = self.get_state("media_player", "state")
    #self.log(state)
    
    # Set a state
    
    #status = self.set_state("light.office_1", state = "on", attributes = {"color_name": "red"})
    #self.log(status)
    
    
    
  def all_state(self, entity, attribute, old, new):
    self.log("Device {} went from {} to {}".format(entity, old, new))
    
  def device(self, entity, attribute, old, new):
    self.log("Device {} went from {} to {}".format(entity, old, new))
    
  def entity(self, entity, attribute, old, new):
    self.log("Entity {} went from {} to {}".format(entity, old, new))
    
  def attr(self, entity, attribute, old, new):
    self.log("Attr {} {} {} {}".format(entity, attribute, old, new))
   
  def cancel(self, args, kwargs):
    self.log("Cancelling callback: {}".format(self.handle))
    self.cancel_listen_state(self.handle)