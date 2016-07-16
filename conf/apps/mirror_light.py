import appapi

class MirrorLight(appapi.APPDaemon):

  def initialize(self):
    #return
    self.listen_state(self.light_changed, "light.andrew_bedside")
    
    state = self.get_state("light.andrew_bedside")
    brightness = self.get_state("light.andrew_bedside", "brightness")
    
    self.log("MirrorLight: Current State is {}, current brightness is {}".format(state, brightness))
    
    if state == "on":
      self.call_service("light", "office_lamp", color_name = "red")
    else:
      self.turn_off("light.office_lamp")

  def light_changed(self, entity, attribute, old, new):
    self.log("MirrorLight: entity {}.{} state changed, old: {}, new: {}".format(entity, attribute, old, new))
    
    if new == 'on':
      #self.turn_on("light.office_lamp")
      print(self.call_service("light", "turn_on", entity_id = "light.office_lamp", color_name = "red"))
    else:
      print(self.turn_off("light.office_lamp"))
