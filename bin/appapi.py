import conf
import datetime
from datetime import timezone
import time
import uuid
import re
import requests

import homeassistant as ha

class APPDaemon():

  def __init__(self, name, logger, error, args):
    self.name = name
    self._logger = logger
    self._error = error
    self.args = args
    
  def log(self, msg):
    self._logger.info("{}: {}".format(self.name, msg))

  def error(self, msg):
    self._error.warning("{}: {}".format(self.name, msg))

  def get_trackers(self):
    return (key for key, value in self.get_state("device_tracker").items())
    
  def get_tracker_state(self, entity_id):
    return(self.get_state(entity_id))
    
  def anyone_home(self):
    for entity_id in conf.ha_state.keys():
      thisdevice, thisentity = entity_id.split(".")
      if thisdevice == "device_tracker":
        if conf.ha_state[entity_id]["state"] == "home":
          return True
    return False

  def everyone_home(self):
    for entity_id in conf.ha_state.keys():
      thisdevice, thisentity = entity_id.split(".")
      if thisdevice == "device_tracker":
        if conf.ha_state[entity_id]["state"] != "home":
          return False
    return True
      
    
  def noone_home(self):
    for entity_id in conf.ha_state.keys():
      thisdevice, thisentity = entity_id.split(".")
      if thisdevice == "device_tracker":
        if conf.ha_state[entity_id]["state"] == "home":
          return False
    return True

      
  def convert_utc(self, utc):
    return datetime.datetime(*map(int, re.split('[^\d]', utc)[:-1])) + datetime.timedelta(minutes=ha.get_tz_offset())

  def friendly_name(self, entity_id):
    if entity_id in conf.ha_state:
      if "friendly_name" in conf.ha_state[entity_id]["attributes"]:
        return conf.ha_state[entity_id]["attributes"]["friendly_name"]
      else:
        return None
    return None
    
  def get_state(self, entity_id = None, attribute = None):
    conf.logger.debug("get_state: {}.{}".format(entity_id, attribute))
    device = None
    entity = None
    if entity_id != None:
      if entity_id.find(".") == -1:
        if attribute != None:
          raise ValueError
        device = entity_id
        entity = None
      else:
        device, entity = entity_id.split(".")
    if device == None:
      return conf.ha_state
    elif entity == None:
      devices = {}
      for entity_id in conf.ha_state.keys():
        thisdevice, thisentity = entity_id.split(".")
        if device == thisdevice:
          devices[entity_id] = conf.ha_state[entity_id]
      return devices
    elif attribute == None:
      entity_id = "{}.{}".format(device, entity)
      if entity_id in conf.ha_state:
        return conf.ha_state[entity_id]["state"]
      else:
        return None
    else:
      entity_id = "{}.{}".format(device, entity)
      if attribute == "all":
        if entity_id in conf.ha_state:
          return conf.ha_state[entity_id]
        else:
          return None
      else:
        if attribute in conf.ha_state[entity_id]:
          return conf.ha_state[entity_id][attribute]
        elif attribute in conf.ha_state[entity_id]["attributes"]:
            return conf.ha_state[entity_id]["attributes"][attribute]
        else:
          return None

  def set_state(self, entity_id, **kwargs):
    conf.logger.debug("set_state: {}, {}".format(entity_id, kwargs))
    if conf.ha_key != "":
      headers = {'x-ha-access': conf.ha_key}
    else:
      headers = {}
    apiurl = "{}/api/states/{}".format(conf.ha_url, entity_id)
    r = requests.post(apiurl, headers=headers, json = kwargs)
    r.raise_for_status()
    return r.json()
    
  def call_service(self, domain, service, **kwargs):
    conf.logger.debug("call_service: {}/{}, {}".format(domain, service, kwargs))
    if conf.ha_key != "":
      headers = {'x-ha-access': conf.ha_key}
    else:
      headers = {}
    apiurl = "{}/api/services/{}/{}".format(conf.ha_url, domain, service)
    r = requests.post(apiurl, headers=headers, json = kwargs)
    r.raise_for_status()
    return r.json()
    
  def turn_on(self, entity_id, **kwargs):
    if kwargs == {}:
      rargs = {"entity_id": entity_id}
    else:
      rargs = kwargs
      rargs["entity_id"] = entity_id
    self.call_service("homeassistant", "turn_on", **rargs)
    
  def turn_off(self, entity_id):
    self.call_service("homeassistant", "turn_off", entity_id = entity_id)

  def toggle(self, entity_id):
    self.call_service("homeassistant", "toggle", entity_id = entity_id)
    
  def notify(self, title, message):
    self.call_service("notify", "notify", title = title, message = message)

  def listen_state(self, function, entity = None, attribute = None):
    name = self.name
    if name not in conf.state_callbacks:
        conf.state_callbacks[name] = {}
    handle = uuid.uuid4()
    conf.state_callbacks[name][handle] = {"function": function, "entity": entity, "attribute": attribute}
    return handle
    
  def cancel_listen_state(self, handle):
    name = self.name
    conf.logger.debug("Canceling listen_state for {}".format(name))
    if name in conf.state_callbacks and handle in conf.state_callbacks[name]:
      del conf.state_callbacks[name][handle]
    if conf.state_callbacks[name] == {}:
      del conf.state_callbacks[name]
  
  def sun_up(self):
    return conf.ha_state["sun.sun"]["state"] == "above_horizon"

  def sun_down(self):
    return conf.ha_state["sun.sun"]["state"] == "below_horizon"
    
  def sunrise(self):
    return(datetime.datetime.fromtimestamp(ha.calc_sun("next_rising", 0)))

  def sunset(self):
    return(datetime.datetime.fromtimestamp(ha.calc_sun("next_setting", 0)))
        
  def cancel_timer(self, handle):
    name = self.name
    conf.logger.debug("Canceling timer for {}".format(name))
    if name in conf.schedule and handle in conf.schedule[name]:
      del conf.schedule[name][handle]
    if conf.schedule[name] == {}:
      del conf.schedule[name]
        
  def run_in(self, callback, seconds, *args, **kwargs):
    name = self.name
    conf.logger.debug("Registering run_in in {} seconds for {}".format(seconds, name))  
    exec_time = datetime.datetime.now().timestamp() + seconds
    handle = self._insert_schedule(name, exec_time, callback, False, None, None, *args, **kwargs)
    return handle

  def run_once(self, callback, start, *args, **kwargs):
    name = self.name
    now = datetime.datetime.now()
    today = datetime.date.today()
    event = datetime.datetime.combine(today, start)
    if event < now:
      one_day = datetime.timedelta(days=1)
      event = event + one_day
    exec_time = event.timestamp()
    handle = self._insert_schedule(name, exec_time, callback, False, None, None, *args, **kwargs)
    return handle

  def run_daily(self, callback, start, *args, **kwargs):
    name = self.name
    now = datetime.datetime.now()
    today = datetime.date.today()
    event = datetime.datetime.combine(today, start)
    if event < now:
      one_day = datetime.timedelta(days=1)
      event = event + one_day
    handle = self.run_every(callback, event, 24 * 60 * 60, *args, **kwargs)
    return handle
    
  def run_hourly(self, callback, start, *args, **kwargs):
    name = self.name
    now = datetime.datetime.now()
    if start == None:
      event = now + datetime.timedelta(hours=1)
    else:
      event = now
      event = event.replace(minute = start.minute, second = start.second)
      if event < now:
        event = event.replace(hour = event.hour + 1)
      
    handle = self.run_every(callback, event, 60 * 60, *args, **kwargs)
    return handle  

  def run_minutely(self, callback, start, *args, **kwargs):
    name = self.name
    now = datetime.datetime.now()
    if start == None:
      event = now + datetime.timedelta(minutes=1)
    else:
      event = now
      event = event.replace(second = start.second)
      if event < now:
        event = event.replace(minute = event.minute + 1)

    handle = self.run_every(callback, event, 60, *args, **kwargs)
    return handle  

  def run_every(self, callback, start, interval, *args, **kwargs):
    name = self.name
    conf.logger.debug("Registering run_every starting {} in {}s intervals for {}".format(start, interval, name))  
    exec_time = start.timestamp()
    handle = self._insert_schedule(name, exec_time, callback, True, interval, None, *args, **kwargs)
    return handle

  # For Sunrise and Sunset we add add 1 second to the offset because we want the next sunrise function to be accurate for an offset of 0
  # There is a race condition in which the scheduler will execute the callback as close to the full second as possible
  # but we may not get the sun event from Home Assistant for some 10s of milliseconds.
  # Adding 1 to the timestamp delays the callback (hopefully) enough that the sunrise/sunset data can be received and stored
  # This is however a hack and if it doesn't work out a more thorough workaround would be to mark sunrise/sunset scheduler entries
  # with an offset of >=0 as "pending" and perform a sweep when the event occurs. This would also need a failsafe in case the event was somehow missed altogether.
    
  def run_at_sunset(self, callback, offset, *args, **kwargs):
    name = self.name
    conf.logger.debug("Registering run_at_sunset with {} second offset for {}".format(offset, name))    
    handle = self._schedule_sun(name, "next_setting", offset + 1, callback, *args, **kwargs)
    return handle

  def run_at_sunrise(self, callback, offset, *args, **kwargs):
    name = self.name
    conf.logger.debug("Registering run_at_sunrise with {} second offset for {}".format(offset, name))    
    handle = self._schedule_sun(name, "next_rising", offset + 1, callback, *args, **kwargs)
    return handle
    
  def _insert_schedule(self, name, utc, callback, repeat, time, type, *args, **kwargs):
    if name not in conf.schedule:
      conf.schedule[name] = {}
    handle = uuid.uuid4()
    conf.schedule[name][handle] = {"callback": callback, "timestamp": utc, "repeat": repeat, "time": time, "type": type, "args": args, "kwargs": kwargs}
    return handle
    
  def _schedule_sun(self, name, type, offset, callback, *args, **kwargs):
    event = ha.calc_sun(type, offset)
    handle = self._insert_schedule(name, event, callback, True, offset, type, *args, **kwargs)