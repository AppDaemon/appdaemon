import appapi

class Trackers(appapi.APPDaemon):

  def initialize(self):
    #return
    self.log("Tracker: Anyone home is {}".format(self.anyone_home()))
    trackers = self.get_trackers()
    #
    # Two ways to track individual state changes 
    
    # Individual callbacks
    for tracker in trackers:
      self.log("{}  ({}) is {}".format(tracker, self.friendly_name(tracker), self.get_tracker_state(tracker)))
      self.listen_state(self.presence_change, tracker)
    # Tracker state callbacks
    self.listen_state(self.state_presence_change, "device_tracker")
    
    # Track Global state
    self.listen_state(self.global_presence_change, "group.all_devices")
    
  def presence_change(self, entity, attribute, old, new):
    self.log("{} went from {} to {}".format(self.friendly_name(entity), old, new))
    self.log("Tracker: Anyone home is {}".format(self.anyone_home()))
    self.log("Tracker: Everyone home is {}".format(self.everyone_home()))
    self.log("Tracker: Noone home is {}".format(self.noone_home()))
  
  def state_presence_change(self, entity, attribute, old, new):
    self.log("{} went from {} to {}".format(self.friendly_name(entity), old["state"], new["state"]))
    self.log("Tracker: Anyone home is {}".format(self.anyone_home()))
    self.log("Tracker: Everyone home is {}".format(self.everyone_home()))
    self.log("Tracker: Noone home is {}".format(self.noone_home()))
    
  def global_presence_change(self, entity, attribute, old, new):
    self.log("{} went from {} to {}".format(entity, old, new))
    self.log("Tracker: Anyone home is {}".format(self.anyone_home()))
    self.log("Tracker: Everyone home is {}".format(self.everyone_home()))
    self.log("Tracker: Noone home is {}".format(self.noone_home()))
