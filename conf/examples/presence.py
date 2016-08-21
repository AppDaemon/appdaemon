import appdaemon.appapi as appapi

#
# App to track presence changes

# Args:
#
#
# notify = set to anything and presence changes will be notified
# day_scene_off = scene to use to turn lights off during the day
# night_scene_absent = scene to use to turn lights off at night (e.g. keep just one on)
# night_scene_present = scene to use to turn lights on at night
# input_select = input_select.house_mode,Day
#
# Release Notes
#
# Version 1.0:
#   Initial Version

class Presence(appapi.AppDaemon):

  def initialize(self):
    
    # Subscribe to presence changes
    
    self.listen_state(self.presence_change, "device_tracker")
    self.listen_state(self.everyone_left, "group.all_devices", old = "home", new = "not_home")
    self.listen_state(self.someone_home, "group.all_devices", old = "not_home", new = "home")

  def presence_change(self, entity, attribute, old, new, kwargs):
    person = self.friendly_name(entity)
    if new == "not_home":
      place = "is away"
    elif new == "home":
      place = "arrived home"
    else:
      place = "is at ".format(new)
    message = "{} {}".format(person, place)
    self.log(message)
    if "notify" in self.args:
      self.notify(message)
    
  def everyone_left(self, entity, attribute, old, new, kwargs):
    self.log("Everyone left")
    valid_modes = self.split_device_list(self.args["input_select"])
    input_select = valid_modes.pop(0)
    if self.get_state(input_select) in valid_modes:
      self.turn_on(self.args["day_scene_off"])
    else:
      self.turn_on(self.args["night_scene_absent"])
    
  def someone_home(self, entity, attribute, old, new, kwargs):
    self.log("Someone came home")
    valid_modes = self.split_device_list(self.args["input_select"])
    input_select = valid_modes.pop(0)
    if self.get_state(input_select) in valid_modes:
      self.turn_on(self.args["day_scene_off"])
    else:
      self.turn_on(self.args["night_scene_present"])
      
    
    