import appapi

class Battery(appapi.APPDaemon):

  def initialize(self):
    self.handle = self.listen_state(self.all_state)
    
  def all_state(self, entity, attribute, old, new):
    if "battery_level" in new["attributes"]:
      self.log("{} battery: {}%".format(entity, new["attributes"]["battery_level"]))
    if "battery" in new["attributes"]:
      self.log("{} battery: {}%".format(entity, new["attributes"]["battery"]))
    