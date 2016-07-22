import appapi
import datetime

#
# App to manage heating:
# - Turn on at different times in morning for weekdays and weekend, only if someone present
# - Stay on all day as long someone present
# - Turn off if everyone leaves
# - Turn off at night when input_select changes state
#
# Smart Heat doesn;t actually turn the heat on and off, it merely sets it to a lower temperature for off so the house does not get too cold
#
# Args:
#
# morning_on_week = Weekday on time
# morning_on_weekend = Weekend on time
# evening_on = Evening on time of noone around
# switch = Input boolean to activate and deactivate smart heat
# thermostats = comma separated list of thermostats to use
# off_temp = Temperature to set thermostats for "off"
# on_temp = Temperature to set thermostats for "on"
# input_select = Name of input_select to monitor followed by comma separated list of values for which heating should be ON
# Release Notes
#
# Version 1.0:
#   Initial Version

class SmartHeat(appapi.AppDaemon):

  def initialize(self):
    
    # Schedule our morning check

    self.schedule_morning()
    
    
    # Test
    
    #self.run_in(self.morning, 1)
    #self.run_in(self.evening, 2)
    
    # Run every day at a specific time
    
    evening = self.parse_time(self.args["evening_on"])
    self.run_daily(self.evening, evening)
    
    # Subscribe to presence changes
    
    self.listen_state(self.presence_change, "device_tracker")
    
    # Subscribe to switch
    
    self.listen_state(self.switch, self.args["switch"])
    
    #
    
    # Subscribe to input_select
    #
    # Could also use a timer to turn off at a specified time
    
    input_select = self.split_device_list(self.args["input_select"]).pop(0)
    self.listen_state(self.mode, input_select)
    
  def schedule_morning(self):
    day = datetime.datetime.today().weekday()
    if day == 4 or day == 5:
      # day = 4 (Friday) or 5 (Saturday) then it is a weekend day TOMORROW, so schedule weekend time heat check for tomorrow
      runtime = self.parse_time(self.args["morning_on_weekend"])
    else:
      # else use week time
      runtime = self.parse_time(self.args["morning_on_week"])
    self.run_once(self.morning, runtime)

  def mode(self, entity, attribute, old, new):
    valid_modes = self.split_device_list(self.args["input_select"])
    if new not in valid_modes and self.get_state(self.args["switch"]) == "on":
      self.heat_off()
  
  def switch(self, entity, attribute, old, new):
    # Toggling switch turns heat on and off as well as enabling smart behavior
    if new == "on":
      self.heat_on()
    else:
      self.heat_off()
  
  def evening(self, args, kwargs):
    # If noone home in the evening turn heat on in preparation (if someone is home heat is already on)
    self.log("Evening heat check")
    if self.noone_home() and self.get_state(self.args["switch"]) == "on":
      self.heat_on()
    
  def morning(self, args, kwargs):
    # Setup tomorrows callback
    self.log("Morning heat check")
    self.schedule_morning()
    if self.anyone_home() and self.get_state(self.args["switch"]) == "on":
      self.heat_on()

  def presence_change(self, entity, attribute, old, new):
    if self.get_state(self.args["switch"]) == "on":
      if self.anyone_home():
        self.heat_on()
      else:
        self.heat_off()
      
  def heat_on(self):
    self.log("Turning heat on")
    for tstat in self.split_device_list(self.args["thermostats"]):
      self.call_service("thermostat/set_temperature", entity_id = tstat, temperature = self.args["on_temp"])
      
  def heat_off(self):
    self.log("Turning heat off")
    for tstat in self.split_device_list(self.args["thermostats"]):
      self.call_service("thermostat/set_temperature", entity_id = tstat, temperature = self.args["off_temp"])
      
