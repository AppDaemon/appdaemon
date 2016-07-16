import conf
import requests
import datetime
import re

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def calc_sun(type, offset):
  # Parse the iso 8601 datestring and convert to a localized timestamp
  return parse_utc_string(conf.ha_state["sun.sun"]["attributes"][type]) + offset
  
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