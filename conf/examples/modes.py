import appapi
import datetime

class Modes(appapi.APPDaemon):

  def initialize(self):
    
    self.mode = self.get_state("input_select.house_mode")
    self.listen_event(self.mode_event, "MODE_CHANGE")
    self.listen_state(self.light_event, "sensor.side_multisensor_luminance_25")
    self.listen_state(self.motion_event, "binary_sensor.downstairs_sensor_26")
    runtime = datetime.time(22, 0, 0)
    self.run_daily(self.night_mode_check, runtime)

  def night_mode_check(self, args, kwargs):
    if self.get_state("input_boolean.vacation") == "on":
      self.night(True)
  
  def light_event(self, entity, attribute, old, new):
    lux = float(new)
    if self.mode == "Morning" or self.mode == "Night" and self.now_is_between("sunrise", "12:00:00"):
      if lux > 200:
        self.day()
        
    if self.mode == "Day" and self.now_is_between("sunset - 02:00:00", "sunset"):
      if lux < 200:
        self.evening()
  
  def motion_event(self, entity, attribute, old, new):
    if new == "on" and self.mode == "Night" and self.now_is_between("04:30:00", "10:00:00"):
      self.morning()

  def mode_event(self, event_name, data):
    mode = data["mode"]
    
    if mode == "Morning":
      self.morning()
    elif mode == "Day":
      self.day()
    elif mode == "Evening":
      self.evening()
    elif mode == "Night":
      self.night()
    elif mode == "Night Quiet":
      self.night(True)
  
  # Main mode functions
  
  def morning(self):
    #Set the house up for morning
    self.mode = "Morning"
    self.log("Switching mode to Morning")
    self.call_service("input_select/select_option", entity_id="input_select.house_mode", option="Morning")
    self.turn_on("scene.wendys_lamp")
    self.notify("Switching mode to Morning")
    
  def day(self):
    # Set the house up for daytime
    self.mode = "Day"
    self.log("Switching mode to Day")
    self.call_service("input_select/select_option", entity_id="input_select.house_mode", option="Day")
    self.turn_on("scene.downstairs_off")
    self.turn_on("scene.upstairs_off")
    self.notify("Switching mode to Day")

  def evening(self):
    #Set the house up for evening
    self.mode = "Evening"
    self.log("Switching mode to Evening")
    self.call_service("input_select/select_option", entity_id="input_select.house_mode", option="Evening")
    if self.anyone_home():
      self.turn_on("scene.downstairs_on")
    else:
      self.turn_on("scene.downstairs_front")
      
    self.notify("Switching mode to Evening")

  def night(self, quiet = False):
    #Set the house up for evening
    self.mode = "Night"
    self.log("Switching mode to Night")
    self.call_service("input_select/select_option", entity_id="input_select.house_mode", option="Night")
    
    if self.anyone_home() and not quiet:
      self.turn_on("scene.upstairs_hall_on")
    else:
      self.turn_on("scene.upstairs_hall_off")

    wendy = self.get_state("device_tracker.dedb5e711a24415baaae5cf8e880d852")
    andrew = self.get_state("device_tracker.5722a8985b4043e9b59305b5e4f71502")
    
    if not quiet:
      if self.everyone_home():
        self.turn_on("scene.bedroom_on")
      elif wendy == "home":
        self.turn_on("scene.bedroom_on_wendy")
      elif andrew == "home":
        self.turn_on("scene.bedroom_on_andrew")
              
    self.notify("Switching mode to Night")
    self.run_in(self.downstairs_off, 5)
      
  def downstairs_off(self, args, kwargs):
    self.turn_on("scene.downstairs_off")
      
    
