#!/usr/bin/python3

import json
import sys
import importlib
from importlib.machinery import SourceFileLoader
import traceback
import configparser
import datetime
from time import mktime
import argparse
import time
import logging
import os.path
import glob
from sseclient import SSEClient
from logging.handlers import RotatingFileHandler
from queue import Queue
import threading
import appdaemon.conf as conf
import time
import datetime
import signal
import re
import uuid
import astral
import pytz
import appdaemon.homeassistant as ha
import appdaemon.appapi as api
import platform

# Windows does not have Daemonize package so disalow

if platform.system() != "Windows":
  from daemonize import Daemonize


q = Queue(maxsize=0)

config = None
config_file_modified = 0
config_file = ""
was_dst = None
last_state = None
reading_messages = False

def init_sun():
  latitude = conf.latitude
  longitude = conf.longitude

  if -90 > latitude < 90:
    raise ValueError("Latitude needs to be -90 .. 90")

  if -180 > longitude < 180:
    raise ValueError("Longitude needs to be -180 .. 180")

  elevation = conf.elevation

  conf.tz = pytz.timezone(conf.time_zone)

  conf.location = astral.Location(('', '', latitude, longitude,
                       conf.tz.zone, elevation))

def update_sun():

  now = datetime.datetime.now(conf.tz)
  mod = -1
  while True:
    try:
        next_rising_dt = conf.location.sunrise(
            now + datetime.timedelta(days=mod), local=False)
        if next_rising_dt > now:
            break
    except astral.AstralError:
        pass
    mod += 1

  mod = -1
  while True:
      try:
          next_setting_dt = (conf.location.sunset(
              now + datetime.timedelta(days=mod), local=False))
          if next_setting_dt > now:
              break
      except astral.AstralError:
          pass
      mod += 1

  old_next_rising_dt =  conf.sun.get("next_rising")
  old_next_setting_dt = conf.sun.get("next_setting")
  conf.sun["next_rising"] = next_rising_dt
  conf.sun["next_setting"] = next_setting_dt

  if old_next_rising_dt != None and old_next_rising_dt != conf.sun["next_rising"]:
    #dump_schedule()
    process_sun("next_rising")
    #dump_schedule()
  if old_next_setting_dt != None and old_next_setting_dt != conf.sun["next_setting"]:
    #dump_schedule()
    process_sun("next_setting")
    #dump_schedule()

def process_sun(action):
  conf.logger.debug("Process sun: {}, next sunrise: {}, next sunset: {}".format(action, conf.sun["next_rising"], conf.sun["next_setting"]))
  for name in conf.schedule.keys():
    for entry in sorted(conf.schedule[name].keys(), key=lambda uuid: conf.schedule[name][uuid]["timestamp"]):
      schedule = conf.schedule[name][entry]
      if schedule["type"] == action and "inactive" in schedule:
        del schedule["inactive"]
        schedule["timestamp"] = ha.calc_sun(action, schedule["time"])

def is_dst( ):
  return bool(time.localtime( ).tm_isdst)

def do_every(period,f):
    def g_tick():
        t = int(time.time())
        count = 0
        while True:
            count += 1
            yield max(t + count*period - time.time(),0)
    g = g_tick()
    while True:
        time.sleep(next(g))
        f()

def handle_sig(signum, frame):
  if signum == signal.SIGUSR1:
    dump_schedule()
    dump_callbacks()
    dump_objects()
    dump_queue()
    dump_sun()
  if signum == signal.SIGUSR2:
    readApps(True)

def dump_sun():
    conf.logger.info("--------------------------------------------------")
    conf.logger.info("Sun")
    conf.logger.info("--------------------------------------------------")
    conf.logger.info(conf.sun)
    conf.logger.info("--------------------------------------------------")

def dump_schedule():
  if conf.schedule == {}:
      conf.logger.info("Schedule is empty")
  else:
    conf.logger.info("--------------------------------------------------")
    conf.logger.info("Scheduler Table")
    conf.logger.info("--------------------------------------------------")
    for name in conf.schedule.keys():
      conf.logger.info("{}:".format(name))
      for entry in sorted(conf.schedule[name].keys(), key=lambda uuid: conf.schedule[name][uuid]["timestamp"]):
        conf.logger.info("  Timestamp: {} - data: {}".format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(conf.schedule[name][entry]["timestamp"])), conf.schedule[name][entry]))
    conf.logger.info("--------------------------------------------------")

def dump_callbacks():
  if conf.callbacks == {}:
    conf.logger.info("No callbacks")
  else:
    conf.logger.info("--------------------------------------------------")
    conf.logger.info("Callbacks")
    conf.logger.info("--------------------------------------------------")
    for name in conf.callbacks.keys():
      conf.logger.info("{}:".format(name))
      for uuid in conf.callbacks[name]:
        conf.logger.info("  {} = {}".format(uuid, conf.callbacks[name][uuid]))
    conf.logger.info("--------------------------------------------------")

def dump_objects():
  conf.logger.info("--------------------------------------------------")
  conf.logger.info("Objects")
  conf.logger.info("--------------------------------------------------")
  for object in conf.objects.keys():
    conf.logger.info("{}: {}".format(object, conf.objects[object]))
  conf.logger.info("--------------------------------------------------")

def dump_queue():
  conf.logger.info("--------------------------------------------------")
  conf.logger.info("Current Queue Size is {}".format(q.qsize()))
  conf.logger.info("--------------------------------------------------")

def check_constraint(key, value):
  unconstrained = True
  if key == "constrain_input_boolean":
      if value in conf.ha_state and conf.ha_state[value]["state"] == "off":
        unconstrained = False
  if key == "constrain_input_select":
    values = value.split(",")
    entity = values.pop(0)
    if entity in conf.ha_state and conf.ha_state[entity]["state"] not in values:
      unconstrained = False
  if key == "constrain_presence":
    if value == "everyone" and not ha.everyone_home():
      unconstrained = False
    elif value == "anyone" and not ha.anyone_home():
      unconstrained = False
    elif value == "noone" and not ha.noone_home():
      unconstrained = False
  if key == "constrain_days":
    if today_is_constrained(value):
      unconstrained = False

  return unconstrained

def check_time_constraint(args, name):
  unconstrained = True
  if "constrain_start_time" in args or "constrain_end_time" in args:
    if "constrain_start_time" not in args:
      start_time = "00:00:00"
    else:
      start_time = args["constrain_start_time"]
    if "constrain_end_time" not in args:
      end_time = "23:59:59"
    else:
      end_time = args["constrain_end_time"]
    if not ha.now_is_between(start_time, end_time, name):
      unconstrained = False

  return unconstrained

def dispatch_worker(name, args):
  unconstrained = True
  #
  # Argument Constraints
  #
  for arg in config[name].keys():
    if not check_constraint(arg, config[name][arg]):
      unconstrained = False
  if not check_time_constraint(config[name], name):
    unconstrained = False
  #
  # Callback level constraints
  #
  if "kwargs" in args:
    for arg in args["kwargs"].keys():
      if not check_constraint(arg, args["kwargs"][arg]):
        unconstrained = False
    if not check_time_constraint(args["kwargs"], name):
      unconstrained = False

  if unconstrained:
    q.put_nowait(args)

def today_is_constrained(days):
    day = datetime.datetime.today().weekday()
    daylist = [ha.day_of_week(day) for day in days.split(",")]
    if day in daylist:
      return False
    return True

def exec_schedule(name, entry, args):
  if "inactive" in args:
    return
  # Call function
  dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "timer", "function": args["callback"], "kwargs": args["kwargs"], })
  # If it is a repeating entry, rewrite with new timestamp
  if args["repeat"]:
    if args["type"] == "next_rising" or args["type"] == "next_setting":
      # Its sunrise or sunset - if the offset is negative we won't know the next rise or set time yet so mark as inactive
      # So we can adjust with a scan at sun rise/set
      if args["time"] < 0:
        args["inactive"] = 1
      else:
        # We have a valid time for the next sunrise/set so use it
        args["timestamp"] = ha.calc_sun(args["type"], args["time"])
    else:
      # Not sunrise or sunset so just increment the timestamp with the repeat interval
      args["timestamp"] += args["time"]
  else: # Otherwise just delete
    del conf.schedule[name][entry]

def do_every_second():

  global was_dst
  global last_state

  # Lets check if we are connected, if not give up.
  if not reading_messages:
    return
  try:

    now = datetime.datetime.now()

    # Update sunrise/sunset etc.

    update_sun()

    # Check if we have entered or exited DST - if so, reload apps to ensure all time callbacks are recalculated

    now_dst = is_dst()
    if now_dst != was_dst:
      conf.logger.info("Detected change in DST from {} to {} - reloading all modules".format(was_dst, now_dst))
      readApps(True)
    was_dst = now_dst

    #dump_schedule()

    # Check to see if any apps have changed but only if we have valid state

    if last_state != None:
      readApps()

    # Check to see if config has changed

    check_config()

    # Call me suspicious, but lets update state form HA periodically in case we miss events for whatever reason
    # Every 10 minutes seems like a good place to start

    if  last_state != None and now - last_state > datetime.timedelta(minutes = 10):
      try:
        get_ha_state()
        last_state = now
      except:
        conf.log.warn("Unexpected error refreshing HA state - retrying in 10 minutes")

    # Check on Queue size

    if q.qsize() > 0 and q.qsize() % 10 == 0:
      conf.logger.warning("Queue size is {}, suspect thread starvation".format(q.qsize()))

    # Process callbacks

    now = datetime.datetime.now().timestamp()
    #conf.logger.debug("Scheduler invoked at {}".format(now))
    for name in conf.schedule.keys():
      for entry in sorted(conf.schedule[name].keys(), key=lambda uuid: conf.schedule[name][uuid]["timestamp"]):
        #conf.logger.debug("{} : {}".format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(conf.schedule[name][entry]["timestamp"])), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))))
        if conf.schedule[name][entry]["timestamp"] < now:
          exec_schedule(name, entry, conf.schedule[name][entry])
        else:
          break
    for k, v in list(conf.schedule.items()):
      if v == {}:
        del conf.schedule[k]

  except:
    conf.error.warn('-'*60)
    conf.error.warn("Unexpected error during do_every_second()")
    conf.error.warn('-'*60)
    conf.error.warn(traceback.format_exc())
    conf.error.warn('-'*60)
    if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
      # When explicitly logging to stdout and stderr, suppress
      # log messages abour writing an error (since they show up anyway)
      conf.logger.warn("Logged an error to {}".format(conf.errorfile))

def timer_thread():
  do_every(1, do_every_second)

def worker():
  while True:
    args = q.get()
    type = args["type"]
    function = args["function"]
    id = args["id"]
    name = args["name"]
    if name in conf.objects and conf.objects[name]["id"] == id:
      try:
        if type == "initialize":
          function()
        if type == "timer":
          function(args["kwargs"])
        elif type == "attr":
          entity = args["entity"]
          attr = args["attr"]
          old_state = args["old_state"]
          new_state = args["new_state"]
          function(entity, attr, old_state, new_state, args["kwargs"])
        elif type == "event":
          data = args["data"]
          function(args["event"], data, args["kwargs"])

      except:
        conf.error.warn('-'*60)
        conf.error.warn("Unexpected error:")
        conf.error.warn('-'*60)
        conf.error.warn(traceback.format_exc())
        conf.error.warn('-'*60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
          conf.logger.warn("Logged an error to {}".format(conf.errorfile))

    else:
      conf.logger.warning("Found stale callback for {} - discarding".format(name))
    q.task_done()

def clear_file(name):
  global config
  for key in config:
    if "module" in config[key] and config[key]["module"] == name:
      clear_object(key)
      if key in conf.objects:
        del conf.objects[key]


def clear_object(object):
  conf.logger.debug("Clearing callbacks for %s", object)
  if object in conf.callbacks:
    del conf.callbacks[object]
  if object in conf.schedule:
    del conf.schedule[object]

def init_object(name, class_name, module_name, args):
  conf.logger.info("Loading Object {} using class {} from module {}".format(name, class_name, module_name))
  module = __import__(module_name)
  APPclass = getattr(module, class_name)
  conf.objects[name] = {"object": APPclass(name, conf.logger, conf.error, args, conf.global_vars), "id": uuid.uuid4()}

  # Call it's initialize function

  q.put_nowait({"type": "initialize", "name": name, "id": conf.objects[name]["id"], "function": conf.objects[name]["object"].initialize})

def check_and_disapatch(name, function, entity, attribute, new_state, old_state, cold, cnew, kwargs):
  if attribute == "all":
    dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "attr", "function": function, "attr": attribute, "entity": entity, "new_state": new_state, "old_state": old_state, "kwargs": kwargs})
  else:
    if attribute in old_state:
      old = old_state[attribute]
    elif attribute in old_state['attributes']:
      old = old_state['attributes'][attribute]
    else:
      old = None
    if attribute in 'new_state':
      new = new_state[attribute]
    elif attribute in new_state['attributes']:
      new = new_state['attributes'][attribute]
    else:
      new = None

    if (cold == None or cold == old) and (cnew == None or cnew == new):
      dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "attr", "function": function, "attr": attribute, "entity": entity, "new_state": new, "old_state": old, "kwargs": kwargs})

def process_state_change(data):

  entity_id = data['data']['entity_id']
  conf.logger.debug("Entity ID:{}:".format(entity_id))
  device, entity = entity_id.split(".")

  # First update our global state
  conf.ha_state[entity_id] = data['data']['new_state']

  # Process state callbacks

  for name in conf.callbacks.keys():
    for uuid in conf.callbacks[name]:
      callback = conf.callbacks[name][uuid]
      if callback["type"] == "state":
        cdevice = None
        centity = None
        if callback["entity"] != None:
          if "." not in callback["entity"]:
            cdevice = callback["entity"]
            centity = None
          else:
            cdevice, centity = callback["entity"].split(".")
        if callback["kwargs"].get("attribute") == None:
          cattribute = "state"
        else:
          cattribute = callback["kwargs"].get("attribute")

        cold = callback["kwargs"].get("old")
        cnew = callback["kwargs"].get("new")

        if cdevice == None:
          check_and_disapatch(name, callback["function"], entity_id, cattribute, data['data']['new_state'], data['data']['old_state'], cold, cnew. callback["kwargs"])
        elif centity == None:
          if device == cdevice:
            check_and_disapatch(name, callback["function"], entity_id, cattribute, data['data']['new_state'], data['data']['old_state'], cold, cnew, callback["kwargs"])
        elif device == cdevice and entity == centity:
          check_and_disapatch(name, callback["function"], entity_id, cattribute, data['data']['new_state'], data['data']['old_state'], cold, cnew, callback["kwargs"])

def process_event(data):
  for name in conf.callbacks.keys():
    for uuid in conf.callbacks[name]:
      callback = conf.callbacks[name][uuid]
      if "event" in callback and data['event_type'] == callback["event"]:
        dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "event", "event": callback["event"], "function": callback["function"], "data": data["data"], "kwargs": callback["kwargs"]})


def process_message(msg):
  try:
    if msg.data == "ping":
      return

    data = json.loads(msg.data)
    conf.logger.debug("Event type:{}:".format(data['event_type']))
    conf.logger.debug(data["data"])

    # Process state changed message
    if data['event_type'] == "state_changed":
      process_state_change(data)

    # Process non-state callbacks
    process_event(data)

  except:
    conf.error.warn('-'*60)
    conf.error.warn("Unexpected error during process_message()")
    conf.error.warn('-'*60)
    conf.error.warn(traceback.format_exc())
    conf.error.warn('-'*60)
    if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
      conf.logger.warn("Logged an error to {}".format(conf.errorfile))

def check_config():
  global config_file_modified
  global config

  try:
    modified = os.path.getmtime(config_file)
    if modified > config_file_modified:
      conf.logger.info("{} modified".format(config_file))
      config_file_modified = modified
      new_config = configparser.ConfigParser()
      new_config.read_file(open(config_file))

      # Check for changes

      for name in config:
        if name == "DEFAULT" or name == "AppDaemon":
          continue
        if name in new_config:
          if config[name] != new_config[name]:

            # Something changed, clear and reload

            conf.logger.info("App '{}' changed - reloading".format(name))
            clear_object(name)
            init_object(name, new_config[name]["class"], new_config[name]["module"], new_config[name])
        else:

          # Section has been deleted, clear it out

          conf.logger.info("App '{}' deleted - removing".format(name))
          clear_object(name)

      for name in new_config:
        if name == "DEFAULT" or name == "AppDaemon":
          continue
        if not name in config:
          #
          # New section added!
          #
          conf.logger.info("App '{}' added - running".format(name))
          init_object(name, new_config[name]["class"], new_config[name]["module"], new_config[name])

      config = new_config
  except:
    conf.error.warn('-'*60)
    conf.error.warn("Unexpected error:")
    conf.error.warn('-'*60)
    conf.error.warn(traceback.format_exc())
    conf.error.warn('-'*60)
    if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
      conf.logger.warn("Logged an error to {}".format(conf.errorfile))

def readApp(file, reload = False):
  global config
  name = os.path.basename(file)
  module_name = os.path.splitext(name)[0]
  # Import the App
  try:
    if reload:
      conf.logger.info("Reloading Module: %s", file)

      file, ext = os.path.splitext(name)

      #
      # Clear out callbacks and remove objects
      #
      clear_file(file)
      #
      # Reload
      #
      try:
        importlib.reload(conf.modules[module_name])
      except KeyError:
        if name not in sys.modules:
          # Probably failed to compile on initial load so we need to re-import
          readApp(file)
        else:
         # A real KeyError!
         raise
    else:
      conf.logger.info("Loading Module: %s", file)
      conf.modules[module_name] = importlib.import_module(module_name)

    # Instantiate class and Run initialize() function

    for name in config:
      if name == "DEFAULT" or name == "AppDaemon":
        continue
      if module_name == config[name]["module"]:
        class_name = config[name]["class"]

        init_object(name, class_name, module_name, config[name])

  except:
    conf.error.warn('-'*60)
    conf.error.warn("Unexpected error during loading of {}:".format(name))
    conf.error.warn('-'*60)
    conf.error.warn(traceback.format_exc())
    conf.error.warn('-'*60)
    if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
      conf.logger.warn("Logged an error to {}".format(conf.errorfile))

def readApps(all = False):
  found_files = []
  for root, subdirs, files in os.walk(conf.app_dir):
    if root[-11:] != "__pycache__":
      for file in files:
        if file[-3:] == ".py":
          found_files.append(os.path.join(root, file))    
  for file in found_files:
    if file == os.path.join(conf.app_dir, "__init__.py"):
     continue
    if file == os.path.join(conf.app_dir, "__pycache__"):
     continue
    modified = os.path.getmtime(file)
    try:
      if file in conf.monitored_files:
        if conf.monitored_files[file] < modified or all:
          readApp(file, True)
          conf.monitored_files[file] = modified
      else:
        readApp(file)
        conf.monitored_files[file] = modified
    except:
      conf.logger.warn('-'*60)
      conf.logger.warn("Unexpected error loading file")
      conf.logger.warn('-'*60)
      conf.logger.warn(traceback.format_exc())
      conf.logger.warn('-'*60)

def get_ha_state():
  conf.logger.debug("Refreshing HA state")
  states = ha.get_ha_state()
  for state in states:
    conf.ha_state[state["entity_id"]] = state

def run():

  global was_dst
  global last_state
  global reading_messages

  # Take a note of DST

  was_dst = is_dst()

  # Setup sun

  update_sun()

  # Create Worker Threads
  for i in range(conf.threads):
     t = threading.Thread(target=worker)
     t.daemon = True
     t.start()

  # Create timer thread

  t = threading.Thread(target=timer_thread)
  t.daemon = True
  t.start()

  # Enter main loop

  first_time = True

  while True:
    try:
      # Get initial state
      get_ha_state()
      conf.logger.info("Got initial state")
      # Load apps
      readApps(True)
      last_state = datetime.datetime.now()

      #
      # Fire HA_STARTED and APPD_STARTED Events
      #
      if first_time == True:
        process_event({"event_type": "appd_started", "data": {}})
        first_time = False
      else:
        process_event({"event_type": "ha_started", "data": {}})

      headers = {'x-ha-access': conf.ha_key}
      reading_messages = True
      messages = SSEClient("{}/api/stream".format(conf.ha_url), verify = False, headers = headers, retry = 3000)
      for msg in messages:
        process_message(msg)
    except:
      reading_messages = False
      conf.logger.warning("Not connected to Home Assistant, retrying in 5 seconds")
      if last_state == None:
        conf.logger.warn('-'*60)
        conf.logger.warn("Unexpected error:")
        conf.logger.warn('-'*60)
        conf.logger.warn(traceback.format_exc())
        conf.logger.warn('-'*60)
    time.sleep(5)

def find_path(name):
  for path in [os.path.join(os.path.expanduser("~"), ".homeassistant"), os.path.join(os.path.sep, "etc", "appdaemon")]:
    file = os.path.join(path, name)
    if os.path.isfile(file) or os.path.isdir(file):
      return(file)
  raise ValueError("{} not specified and not found in default locations".format(name))
    
def main():

  global config
  global config_file
  global config_file_modified

  # Windows does not support SIGUSR1 or SIGUSR2
  if platform.system() != "Windows":
    signal.signal(signal.SIGUSR1, handle_sig)
    signal.signal(signal.SIGUSR2, handle_sig)

  
  # Get command line args

  parser = argparse.ArgumentParser()

  parser.add_argument("-c", "--config", help="full path to config file", type=str, default = None)
  parser.add_argument("-p", "--pidfile", help="full path to PID File", default = "/tmp/hapush.pid")
  parser.add_argument("-D", "--debug", help="debug level", default = "INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

  # Windows does not have Daemonize package so disalow
  if platform.system() != "Windows":
    parser.add_argument("-d", "--daemon", help="run as a background process", action="store_true")


  args = parser.parse_args()
  config_file = args.config

  
  if config_file == None:
    config_file = find_path("appdaemon.cfg")
  
  if platform.system() != "Windows":
    isdaemon = args.daemon
  else:
    isdaemon = False

  # Read Config File

  config = configparser.ConfigParser()
  config.read_file(open(config_file))

  assert "AppDaemon" in config, "[AppDaemon] section required in {}".format(config_file)

  conf.ha_url = config['AppDaemon']['ha_url']
  conf.ha_key = config['AppDaemon']['ha_key']
  conf.logfile = config['AppDaemon'].get("logfile")
  conf.errorfile = config['AppDaemon'].get("errorfile")
  conf.app_dir = config['AppDaemon'].get("app_dir")
  conf.threads = int(config['AppDaemon']['threads'])
  conf.latitude = float(config['AppDaemon']['latitude'])
  conf.longitude = float(config['AppDaemon']['longitude'])
  conf.elevation = float(config['AppDaemon']['elevation'])
  conf.timezone = config['AppDaemon'].get("timezone")
  conf.time_zone = config['AppDaemon'].get("time_zone")

  if conf.logfile == None:
    conf.logfile = "STDOUT"

  if conf.errorfile == None:
    conf.errorfile = "STDERR"
   
  if isdaemon and (conf.logfile == "STDOUT" or conf.errorfile == "STDERR" or conf.logfile == "STDERR" or conf.errorfile == "STDOUT"):
    raise ValueError("STDOUT and STDERR not allowed with -d")
    
  # Setup Logging

  conf.logger = logging.getLogger("log1")
  numeric_level = getattr(logging, args.debug, None)
  conf.logger.setLevel(numeric_level)
  conf.logger.propagate = False
  formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

  # Send to file if we are daemonizing, else send to console
  
  if conf.logfile != "STDOUT":
    fh = RotatingFileHandler(conf.logfile, maxBytes=1000000, backupCount=3)
    fh.setLevel(numeric_level)
    fh.setFormatter(formatter)
    conf.logger.addHandler(fh)
  else:
    # Default for StreamHandler() is sys.stderr
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(numeric_level)
    ch.setFormatter(formatter)
    conf.logger.addHandler(ch)

  # Setup compile output

  conf.error = logging.getLogger("log2")
  numeric_level = getattr(logging, args.debug, None)
  conf.error.setLevel(numeric_level)
  conf.error.propagate = False
  formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

  if conf.errorfile != "STDERR":
    efh = RotatingFileHandler(conf.errorfile, maxBytes=1000000, backupCount=3)
  else:
    efh = logging.StreamHandler()

  efh.setLevel(numeric_level)
  efh.setFormatter(formatter)
  conf.error.addHandler(efh)

  if conf.timezone == None and conf.time_zone == None:
    raise KeyError("time_zone")

  if conf.timezone != None:
    conf.logger.warn("'timezone' directive is deprecated, please use time_zone instead")

  if conf.time_zone == None:
    conf.time_zone = conf.timezone

  init_sun()

  config_file_modified = os.path.getmtime(config_file)

  # Add appdir  and subdirs to path
  if conf.app_dir == None:
    conf.app_dir = find_path("apps")
  
  for root, subdirs, files in os.walk(conf.app_dir):
    if root[-11:] != "__pycache__":
      sys.path.insert(0, root)
  

  # Start main loop

  if isdaemon:
    keep_fds = [fh.stream.fileno(), efh.stream.fileno()]
    pid = args.pidfile
    daemon = Daemonize(app="appdaemon", pid=pid, action=run, keep_fds=keep_fds)
    daemon.start()
    while True:
      time.sleep(1)
  else:
    run()

if __name__ == "__main__":
    main()
