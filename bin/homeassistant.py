import conf
import requests
import datetime
import re

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def parse_time(time_str):
  time = None
  parts = re.search('^(\d+):(\d+):(\d+)', time_str)
  if parts:
    time = datetime.time(int(parts.group(1)), int(parts.group(2)), int(parts.group(3)))
  else:
    if time_str == "sunrise":
      time = sunrise().time()
    elif time_str == "sunset":
      time = sunset().time()
    else:
      parts = re.search('^sunrise\s*([+-])\s*(\d+):(\d+):(\d+)', time_str)
      if parts:
        if parts.group(1) == "+":
          time = (sunrise() + datetime.timedelta(hours=int(parts.group(2)), minutes=int(parts.group(3)), seconds=int(parts.group(4)))).time()
        else:
          time = (sunrise() - datetime.timedelta(hours=int(parts.group(2)), minutes=int(parts.group(3)), seconds=int(parts.group(4)))).time()
      else:
        parts = re.search('^sunset\s*([+-])\s*(\d+):(\d+):(\d+)', time_str)
        if parts:
          if parts.group(1) == "+":
            time = (sunset() + datetime.timedelta(hours=int(parts.group(2)), minutes=int(parts.group(3)), seconds=int(parts.group(4)))).time()
          else:
            time = (sunset() - datetime.timedelta(hours=int(parts.group(2)), minutes=int(parts.group(3)), seconds=int(parts.group(4)))).time()
  return time
  
def now_is_between(start_time_str, end_time_str):
  start_time = parse_time(start_time_str)
  end_time = parse_time(end_time_str)
  now = datetime.datetime.now()
  start_date = now.replace(hour=start_time.hour, minute=start_time.minute, second=start_time.second)
  end_date = now.replace(hour=end_time.hour, minute=end_time.minute, second=end_time.second)
  if end_date < start_date:
    # Spans midnight
    if now < start_date and now < end_date:
      now = now + datetime.timedelta(days=1)
    end_date = end_date + datetime.timedelta(days=1)    
  return start_date <= now <= end_date
 
def sunrise():
  return(datetime.datetime.fromtimestamp(calc_sun("next_rising", 0)))

def sunset():
  return(datetime.datetime.fromtimestamp(calc_sun("next_setting", 0)))

def anyone_home():
  for entity_id in conf.ha_state.keys():
    thisdevice, thisentity = entity_id.split(".")
    if thisdevice == "device_tracker":
      if conf.ha_state[entity_id]["state"] == "home":
        return True
  return False

def everyone_home():
  for entity_id in conf.ha_state.keys():
    thisdevice, thisentity = entity_id.split(".")
    if thisdevice == "device_tracker":
      if conf.ha_state[entity_id]["state"] != "home":
        return False
  return True
    
  
def noone_home():
  for entity_id in conf.ha_state.keys():
    thisdevice, thisentity = entity_id.split(".")
    if thisdevice == "device_tracker":
      if conf.ha_state[entity_id]["state"] == "home":
        return False
  return True

def calc_sun(type, offset):
  # convert to a localized timestamp
  return conf.sun[type].timestamp() + offset
  
def parse_utc_string(s):
  return datetime.datetime(*map(int, re.split('[^\d]', s)[:-1])).timestamp() + get_tz_offset() * 60
 
def get_tz_offset():
  utcOffset_min = int(round((datetime.datetime.now() - datetime.datetime.utcnow()).total_seconds())) / 60   # round for taking time twice
  utcOffset_h = utcOffset_min / 60
  assert(utcOffset_min == utcOffset_h * 60)   # we do not handle 1/2 h timezone offsets
  return(utcOffset_min)
  
def get_ha_state(entity_id = None):
  conf.logger.debug("get_ha_state: enitiy is {}".format(entity_id))  
  if conf.ha_key != "":
    headers = {'x-ha-access': conf.ha_key}
  else:
    headers = {}
  if entity_id == None:
    apiurl = "{}/api/states".format(conf.ha_url)
  else:
    apiurl = "{}/api/states/{}".format(conf.ha_url, entity_id)
  r = requests.get(apiurl, headers=headers)
  r.raise_for_status()
  return r.json()