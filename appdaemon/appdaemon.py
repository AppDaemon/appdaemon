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
import os
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
import math
import random

__version__ = "1.3.6"

# Windows does not have Daemonize package so disallow

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

  #now = datetime.datetime.now(conf.tz)
  now = conf.tz.localize(ha.get_now())
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

def is_dst( ):
  return bool(time.localtime(ha.get_now_ts()).tm_isdst)

def do_every(period,f):
    def g_tick():
        t = math.floor(time.time())
        count = 0
        while True:
            count += 1
            yield max(t + count*period - time.time(),0)
    g = g_tick()
    t = math.floor(ha.get_now_ts())
    while True:
      time.sleep(next(g))
      t += conf.interval
      r = f(t)
      if r != None and r != t:
        t = math.floor(r)

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
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    ha.log(conf.logger, "INFO", "Sun")
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    ha.log(conf.logger, "INFO", conf.sun)
    ha.log(conf.logger, "INFO", "--------------------------------------------------")

def dump_schedule():
  if conf.schedule == {}:
      ha.log(conf.logger, "INFO", "Schedule is empty")
  else:
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    ha.log(conf.logger, "INFO", "Scheduler Table")
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    for name in conf.schedule.keys():
      ha.log(conf.logger, "INFO", "{}:".format(name))
      for entry in sorted(conf.schedule[name].keys(), key=lambda uuid: conf.schedule[name][uuid]["timestamp"]):
        ha.log(conf.logger, "INFO", "  Timestamp: {} - data: {}".format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(conf.schedule[name][entry]["timestamp"])), conf.schedule[name][entry]))
    ha.log(conf.logger, "INFO", "--------------------------------------------------")

def dump_callbacks():
  if conf.callbacks == {}:
    ha.log(conf.logger, "INFO", "No callbacks")
  else:
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    ha.log(conf.logger, "INFO", "Callbacks")
    ha.log(conf.logger, "INFO", "--------------------------------------------------")
    for name in conf.callbacks.keys():
      ha.log(conf.logger, "INFO", "{}:".format(name))
      for uuid in conf.callbacks[name]:
        ha.log(conf.logger, "INFO", "  {} = {}".format(uuid, conf.callbacks[name][uuid]))
    ha.log(conf.logger, "INFO", "--------------------------------------------------")

def dump_objects():
  ha.log(conf.logger, "INFO", "--------------------------------------------------")
  ha.log(conf.logger, "INFO", "Objects")
  ha.log(conf.logger, "INFO", "--------------------------------------------------")
  for object in conf.objects.keys():
    ha.log(conf.logger, "INFO", "{}: {}".format(object, conf.objects[object]))
  ha.log(conf.logger, "INFO", "--------------------------------------------------")

def dump_queue():
  ha.log(conf.logger, "INFO", "--------------------------------------------------")
  ha.log(conf.logger, "INFO", "Current Queue Size is {}".format(q.qsize()))
  ha.log(conf.logger, "INFO", "--------------------------------------------------")

def check_constraint(key, value):
  unconstrained = True
  with conf.ha_state_lock:
    if key == "constrain_input_boolean":
      values = value.split(",")
      if len(values) == 2:
        entity = values[0]
        state = values[1]
      else:
        entity = value
        state = "on"      
      if entity in conf.ha_state and conf.ha_state[entity]["state"] != state:
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
    with conf.threads_busy_lock:
      conf.threads_busy += 1
      q.put_nowait(args)

def today_is_constrained(days):
    day = ha.get_now().weekday()
    daylist = [ha.day_of_week(day) for day in days.split(",")]
    if day in daylist:
      return False
    return True

def process_sun(action):
  ha.log(conf.logger, "DEBUG", "Process sun: {}, next sunrise: {}, next sunset: {}".format(action, conf.sun["next_rising"], conf.sun["next_setting"]))
  with conf.schedule_lock:
    for name in conf.schedule.keys():
      for entry in sorted(conf.schedule[name].keys(), key=lambda uuid: conf.schedule[name][uuid]["timestamp"]):
        schedule = conf.schedule[name][entry]
        if schedule["type"] == action and "inactive" in schedule:
          del schedule["inactive"]
          c_offset = ha.get_offset(schedule)
          schedule["timestamp"] = ha.calc_sun(action) + c_offset
          schedule["offset"] = c_offset

def exec_schedule(name, entry, args):
  # Locking performed in calling function
  if "inactive" in args:
    return
  # Call function
  if "entity" in args["kwargs"]:
    dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "attr", "function": args["callback"], "attribute": args["kwargs"]["attribute"], "entity": args["kwargs"]["entity"], "new_state": args["kwargs"]["new_state"], "old_state": args["kwargs"]["old_state"], "kwargs": args["kwargs"]})
  else:
    dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "timer", "function": args["callback"], "kwargs": args["kwargs"], })
  # If it is a repeating entry, rewrite with new timestamp
  if args["repeat"]:    
    if args["type"] == "next_rising" or args["type"] == "next_setting":
      # Its sunrise or sunset - if the offset is negative we won't know the next rise or set time yet so mark as inactive
      # So we can adjust with a scan at sun rise/set
      if args["offset"] < 0:
        args["inactive"] = 1
      else:
        # We have a valid time for the next sunrise/set so use it
        c_offset = ha.get_offset(args)
        args["timestamp"] = ha.calc_sun(args["type"]) + c_offset
        args["offset"] = c_offset
    else:
      # Not sunrise or sunset so just increment the timestamp with the repeat interval
      args["basetime"] += args["interval"]
      args["timestamp"] = args["basetime"] + ha.get_offset(args)
  else: # Otherwise just delete
    del conf.schedule[name][entry]

def do_every_second(utc):

  global was_dst
  global last_state
    
  # Lets check if we are connected, if not give up.
  if not reading_messages:
    return
  try:

    #now = datetime.datetime.now()
    #now = now.replace(microsecond=0)
    now = datetime.datetime.fromtimestamp(utc)
    conf.now = utc

    # If we have reached endtime bail out
    
    if conf.endtime != None and ha.get_now() >= conf.endtime:
      ha.log(conf.logger, "INFO", "End time reached, exiting")
      os._exit(0)
      
    if conf.realtime:
      real_now = datetime.datetime.now().timestamp()
      delta = abs(utc - real_now)
      if delta > 1:
        ha.log(conf.logger, "WARNING", "Scheduler clock skew detected - delta = {} - resetting".format(delta))
        return real_now
        
    # Update sunrise/sunset etc.

    update_sun()

    # Check if we have entered or exited DST - if so, reload apps to ensure all time callbacks are recalculated

    now_dst = is_dst()
    if now_dst != was_dst:
      ha.log(conf.logger, "INFO", "Detected change in DST from {} to {} - reloading all modules".format(was_dst, now_dst))
      #dump_schedule()
      ha.log(conf.logger, "INFO", "-" * 40)
      readApps(True)
      #dump_schedule()
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

    qsize = q.qsize()
    if qsize > 0 and qsize % 10 == 0:
      conf.logger.warning("Queue size is {}, suspect thread starvation".format(q.qsize()))

    # Process callbacks

    #ha.log(conf.logger, "DEBUG", "Scheduler invoked at {}".format(now))
    with conf.schedule_lock:
      for name in conf.schedule.keys():
        for entry in sorted(conf.schedule[name].keys(), key=lambda uuid: conf.schedule[name][uuid]["timestamp"]):
          #ha.log(conf.logger, "DEBUG", "{} : {}".format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(conf.schedule[name][entry]["timestamp"])), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))))
          if conf.schedule[name][entry]["timestamp"] <= utc:
            exec_schedule(name, entry, conf.schedule[name][entry])
          else:
            break
      for k, v in list(conf.schedule.items()):
        if v == {}:
          del conf.schedule[k]
        
    return utc

  except:
    ha.log(conf.error, "WARNING", '-'*60)
    ha.log(conf.error, "WARNING", "Unexpected error during do_every_second()")
    ha.log(conf.error, "WARNING", '-'*60)
    ha.log(conf.error, "WARNING", traceback.format_exc())
    ha.log(conf.error, "WARNING", '-'*60)
    if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
      # When explicitly logging to stdout and stderr, suppress
      # log messages abour writing an error (since they show up anyway)
      ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))

def timer_thread():
  do_every(conf.tick, do_every_second)

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
          ha.log(conf.logger, "DEBUG", "Calling initialize() for {}".format(name))
          function()
          ha.log(conf.logger, "DEBUG", "{} initialize() done".format(name))
        if type == "timer":
          function(ha.sanitize_timer_kwargs(args["kwargs"]))
        if type == "attr":
          entity = args["entity"]
          attr = args["attribute"]
          old_state = args["old_state"]
          new_state = args["new_state"]
          function(entity, attr, old_state, new_state, ha.sanitize_state_kwargs(args["kwargs"]))
        if type == "event":
          data = args["data"]
          function(args["event"], data, args["kwargs"])

      except:
        ha.log(conf.error, "WARNING", '-'*60)
        ha.log(conf.error, "WARNING", "Unexpected error:")
        ha.log(conf.error, "WARNING", '-'*60)
        ha.log(conf.error, "WARNING", traceback.format_exc())
        ha.log(conf.error, "WARNING", '-'*60)
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
          ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))

    else:
      conf.logger.warning("Found stale callback for {} - discarding".format(name))

    with conf.threads_busy_lock:
      conf.threads_busy -= 1
    q.task_done()
    

def clear_file(name):
  global config
  for key in config:
    if "module" in config[key] and config[key]["module"] == name:
      clear_object(key)
      if key in conf.objects:
        del conf.objects[key]


def clear_object(object):
  ha.log(conf.logger, "DEBUG", "Clearing callbacks for {}".format(object))
  with conf.callbacks_lock:
    if object in conf.callbacks:
      del conf.callbacks[object]
  with conf.schedule_lock:
    if object in conf.schedule:
      del conf.schedule[object]

def init_object(name, class_name, module_name, args):
  ha.log(conf.logger, "INFO", "Loading Object {} using class {} from module {}".format(name, class_name, module_name))
  module = __import__(module_name)
  APPclass = getattr(module, class_name)
  conf.objects[name] = {"object": APPclass(name, conf.logger, conf.error, args, conf.global_vars), "id": uuid.uuid4()}

  # Call it's initialize function

  with conf.threads_busy_lock:
    conf.threads_busy += 1
    q.put_nowait({"type": "initialize", "name": name, "id": conf.objects[name]["id"], "function": conf.objects[name]["object"].initialize})

def check_and_disapatch(name, function, entity, attribute, new_state, old_state, cold, cnew, kwargs):
  if attribute == "all":
    dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "attr", "function": function, "attribute": attribute, "entity": entity, "new_state": new_state, "old_state": old_state, "kwargs": kwargs})
  else:
    if old_state == None:
      old = None
    else:
      if attribute in old_state:
        old = old_state[attribute]
      elif attribute in old_state['attributes']:
        old = old_state['attributes'][attribute]
      else:
        old = None
    if new_state == None:
      new = None
    else:
      if attribute in 'new_state':
        new = new_state[attribute]
      elif attribute in new_state['attributes']:
        new = new_state['attributes'][attribute]
      else:
        new = None

    if (cold == None or cold == old) and (cnew == None or cnew == new):     
      if "duration" in kwargs:
        # Set a timer
        exec_time = ha.get_now_ts() + int(kwargs["duration"])
        kwargs["handle"] = ha.insert_schedule(name, exec_time, function, False, None, entity = entity, attribute = attribute, old_state = old, new_state = new, **kwargs)
      else:
        # Do it now
        dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "attr", "function": function, "attribute": attribute, "entity": entity, "new_state": new, "old_state": old, "kwargs": kwargs})
    else:
      if "handle" in kwargs:
        #cancel timer
        ha.cancel_timer(name, kwargs["handle"])
        

def process_state_change(data):

  entity_id = data['data']['entity_id']
  ha.log(conf.logger, "DEBUG", "Entity ID:{}:".format(entity_id))
  device, entity = entity_id.split(".")

  # First update our global state
  with conf.ha_state_lock:
    conf.ha_state[entity_id] = data['data']['new_state']

  # Process state callbacks

  with conf.callbacks_lock:
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
            check_and_disapatch(name, callback["function"], entity_id, cattribute, data['data']['new_state'], data['data']['old_state'], cold, cnew, callback["kwargs"])
          elif centity == None:
            if device == cdevice:
              check_and_disapatch(name, callback["function"], entity_id, cattribute, data['data']['new_state'], data['data']['old_state'], cold, cnew, callback["kwargs"])
          elif device == cdevice and entity == centity:
            check_and_disapatch(name, callback["function"], entity_id, cattribute, data['data']['new_state'], data['data']['old_state'], cold, cnew, callback["kwargs"])

def process_event(data):
  with conf.callbacks_lock:
    for name in conf.callbacks.keys():
      for uuid in conf.callbacks[name]:
        callback = conf.callbacks[name][uuid]
        if "event" in callback and (callback["event"] == None or data['event_type'] == callback["event"]):
          # Check any filters
          run = True
          for key in callback["kwargs"]:
            if key in data["data"] and callback["kwargs"][key] != data["data"][key]:
              run = False
          if run:
            dispatch_worker(name, {"name": name, "id": conf.objects[name]["id"], "type": "event", "event": data['event_type'], "function": callback["function"], "data": data["data"], "kwargs": callback["kwargs"]})


def process_message(msg):
  try:
    if msg.data == "ping":
      return

    data = json.loads(msg.data)
    ha.log(conf.logger, "DEBUG", "Event type:{}:".format(data['event_type']))
    ha.log(conf.logger, "DEBUG", data["data"])

    # Process state changed message
    if data['event_type'] == "state_changed":
      process_state_change(data)

    # Process non-state callbacks
    process_event(data)

  except:
    ha.log(conf.error, "WARNING", '-'*60)
    ha.log(conf.error, "WARNING", "Unexpected error during process_message()")
    ha.log(conf.error, "WARNING", '-'*60)
    ha.log(conf.error, "WARNING", traceback.format_exc())
    ha.log(conf.error, "WARNING", '-'*60)
    if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
      ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))

def check_config():
  global config_file_modified
  global config

  try:
    modified = os.path.getmtime(config_file)
    if modified > config_file_modified:
      ha.log(conf.logger, "INFO", "{} modified".format(config_file))
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

            ha.log(conf.logger, "INFO", "App '{}' changed - reloading".format(name))
            clear_object(name)
            init_object(name, new_config[name]["class"], new_config[name]["module"], new_config[name])
        else:

          # Section has been deleted, clear it out

          ha.log(conf.logger, "INFO", "App '{}' deleted - removing".format(name))
          clear_object(name)

      for name in new_config:
        if name == "DEFAULT" or name == "AppDaemon":
          continue
        if not name in config:
          #
          # New section added!
          #
          ha.log(conf.logger, "INFO", "App '{}' added - running".format(name))
          init_object(name, new_config[name]["class"], new_config[name]["module"], new_config[name])

      config = new_config
  except:
    ha.log(conf.error, "WARNING", '-'*60)
    ha.log(conf.error, "WARNING", "Unexpected error:")
    ha.log(conf.error, "WARNING", '-'*60)
    ha.log(conf.error, "WARNING", traceback.format_exc())
    ha.log(conf.error, "WARNING", '-'*60)
    if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
      ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))

def readApp(file, reload = False):
  global config
  name = os.path.basename(file)
  module_name = os.path.splitext(name)[0]
  # Import the App
  try:
    if reload:
      ha.log(conf.logger, "INFO", "Reloading Module: {}".format(file))

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
      ha.log(conf.logger, "INFO", "Loading Module: {}".format(file))
      conf.modules[module_name] = importlib.import_module(module_name)

    # Instantiate class and Run initialize() function

    for name in config:
      if name == "DEFAULT" or name == "AppDaemon":
        continue
      if module_name == config[name]["module"]:
        class_name = config[name]["class"]

        init_object(name, class_name, module_name, config[name])

  except:
    ha.log(conf.error, "WARNING", '-'*60)
    ha.log(conf.error, "WARNING", "Unexpected error during loading of {}:".format(name))
    ha.log(conf.error, "WARNING", '-'*60)
    ha.log(conf.error, "WARNING", traceback.format_exc())
    ha.log(conf.error, "WARNING", '-'*60)
    if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
      ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))

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
      ha.log(conf.logger, "WARNING", '-'*60)
      ha.log(conf.logger, "WARNING", "Unexpected error loading file")
      ha.log(conf.logger, "WARNING", '-'*60)
      ha.log(conf.logger, "WARNING", traceback.format_exc())
      ha.log(conf.logger, "WARNING", '-'*60)

def get_ha_state():
  ha.log(conf.logger, "DEBUG", "Refreshing HA state")
  states = ha.get_ha_state()
  with conf.ha_state_lock:
    for state in states:
      conf.ha_state[state["entity_id"]] = state

def run():

  global was_dst
  global last_state
  global reading_messages

  ha.log(conf.logger, "DEBUG", "Entering run()")

  
  # Take a note of DST

  was_dst = is_dst()

  # Setup sun

  update_sun()

  ha.log(conf.logger, "DEBUG", "Creating worker threads ...")

  # Create Worker Threads
  for i in range(conf.threads):
     t = threading.Thread(target=worker)
     t.daemon = True
     t.start()

  ha.log(conf.logger, "DEBUG", "Done")

  # Read apps and get HA State before we start the timer thread
  ha.log(conf.logger, "DEBUG", "Calling HA for initial state")

  while last_state == None:
    try:
      get_ha_state()
      last_state = ha.get_now()
    except:
      ha.log(conf.logger, "WARNING", '-'*60)
      ha.log(conf.logger, "WARNING", "Unexpected error:")
      ha.log(conf.logger, "WARNING", '-'*60)
      ha.log(conf.logger, "WARNING", traceback.format_exc())
      ha.log(conf.logger, "WARNING", '-'*60)
      ha.log(conf.logger, "WARNING", "Not connected to Home Assistant, retrying in 5 seconds")
    time.sleep(5)
      

  ha.log(conf.logger, "INFO", "Got initial state")
  # Load apps

  ha.log(conf.logger, "DEBUG", "Reading Apps")

  readApps(True)

  # wait until all threads have finished initializing
  
  while True:
    with conf.threads_busy_lock:
      if conf.threads_busy == 0:
        break
      ha.log(conf.logger, "INFO", "Waiting for App initialization: {} remaining".format(conf.threads_busy))
    time.sleep(1)

  ha.log(conf.logger, "INFO", "App initialization complete")
  
  # Create timer thread

  # First, update "now" for less chance of clock skew error 
  if conf.realtime:
    conf.now = datetime.datetime.now().timestamp()
  
  ha.log(conf.logger, "DEBUG", "Starting timer thread")
  
  t = threading.Thread(target=timer_thread)
  t.daemon = True
  t.start()

  # Enter main loop

  first_time = True
  reading_messages = True

  while True:
    try:
      if first_time == False:
        # Get initial state
        get_ha_state()
        last_state = ha.get_now()
        ha.log(conf.logger, "INFO", "Got initial state")

        # Let the timer thread know we are in business, and give it time to tick at least once
        reading_messages = True
        time.sleep(2)  

        # Load apps
        readApps(True)

        while True:
          with conf.threads_busy_lock:
            if conf.threads_busy == 0:
              break
            ha.log(conf.logger, "INFO", "Waiting for App initialization: {} remaining".format(conf.threads_busy))
          time.sleep(1)

        ha.log(conf.logger, "INFO", "App initialization complete")

      #
      # Fire HA_STARTED and APPD_STARTED Events
      #
      if first_time == True:
        process_event({"event_type": "appd_started", "data": {}})
        first_time = False
      else:
        process_event({"event_type": "ha_started", "data": {}})

      headers = {'x-ha-access': conf.ha_key}
      messages = SSEClient("{}/api/stream".format(conf.ha_url), verify = False, headers = headers, retry = 3000)
      for msg in messages:
        process_message(msg)
    except:
      reading_messages = False
      ha.log(conf.logger, "WARNING", "Not connected to Home Assistant, retrying in 5 seconds")
      if last_state == None:
        ha.log(conf.logger, "WARNING", '-'*60)
        ha.log(conf.logger, "WARNING", "Unexpected error:")
        ha.log(conf.logger, "WARNING", '-'*60)
        ha.log(conf.logger, "WARNING", traceback.format_exc())
        ha.log(conf.logger, "WARNING", '-'*60)
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

  #import appdaemon.stacktracer
  #appdaemon.stacktracer.trace_start("/tmp/trace.html")
  
  # Windows does not support SIGUSR1 or SIGUSR2
  if platform.system() != "Windows":
    signal.signal(signal.SIGUSR1, handle_sig)
    signal.signal(signal.SIGUSR2, handle_sig)

  
  # Get command line args

  parser = argparse.ArgumentParser()

  parser.add_argument("-c", "--config", help="full path to config file", type=str, default = None)
  parser.add_argument("-p", "--pidfile", help="full path to PID File", default = "/tmp/hapush.pid")
  parser.add_argument("-t", "--tick", help = "time in seconds that a tick in the schedular lasts", default = 1, type = float)
  parser.add_argument("-s", "--starttime", help = "start time for scheduler <YYYY-MM-DD HH:MM:SS>", type = str)
  parser.add_argument("-e", "--endtime", help = "end time for scheduler <YYYY-MM-DD HH:MM:SS>",type = str, default = None)
  parser.add_argument("-i", "--interval", help = "multiplier for scheduler tick", type = float, default = 1)
  parser.add_argument("-D", "--debug", help="debug level", default = "INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
  parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + __version__)
  
  # Windows does not have Daemonize package so disallow
  if platform.system() != "Windows":
    parser.add_argument("-d", "--daemon", help="run as a background process", action="store_true")


  args = parser.parse_args()
  
  conf.tick = args.tick
  conf.interval = args.interval
  
  if args.starttime != None:
    conf.now = datetime.datetime.strptime(args.starttime, "%Y-%m-%d %H:%M:%S").timestamp()
  else:
    conf.now = datetime.datetime.now().timestamp()
    
  if args.endtime != None:
    conf.endtime = datetime.datetime.strptime(args.endtime, "%Y-%m-%d %H:%M:%S")
  
  if conf.tick != 1 or conf.interval != 1 or args.starttime != None:
    conf.realtime = False
  
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

  conf.config = config
  conf.ha_url = config['AppDaemon']['ha_url']
  conf.ha_key = config['AppDaemon'].get('ha_key', "")
  conf.logfile = config['AppDaemon'].get("logfile")
  conf.errorfile = config['AppDaemon'].get("errorfile")
  conf.app_dir = config['AppDaemon'].get("app_dir")
  conf.threads = int(config['AppDaemon']['threads'])
  conf.latitude = float(config['AppDaemon']['latitude'])
  conf.longitude = float(config['AppDaemon']['longitude'])
  conf.elevation = float(config['AppDaemon']['elevation'])
  conf.timezone = config['AppDaemon'].get("timezone")
  conf.time_zone = config['AppDaemon'].get("time_zone")
  conf.certpath = config['AppDaemon'].get("cert_path")
  
  if conf.timezone == None and conf.time_zone == None:
    raise KeyError("time_zone")

  if conf.time_zone == None:
    conf.time_zone = conf.timezone

  # Use the supplied timezone
  os.environ['TZ'] = conf.time_zone
  
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
  #formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

  # Send to file if we are daemonizing, else send to console
  
  if conf.logfile != "STDOUT":
    fh = RotatingFileHandler(conf.logfile, maxBytes=1000000, backupCount=3)
    fh.setLevel(numeric_level)
    #fh.setFormatter(formatter)
    conf.logger.addHandler(fh)
  else:
    # Default for StreamHandler() is sys.stderr
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(numeric_level)
    #ch.setFormatter(formatter)
    conf.logger.addHandler(ch)

  # Setup compile output

  conf.error = logging.getLogger("log2")
  numeric_level = getattr(logging, args.debug, None)
  conf.error.setLevel(numeric_level)
  conf.error.propagate = False
  #formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

  if conf.errorfile != "STDERR":
    efh = RotatingFileHandler(conf.errorfile, maxBytes=1000000, backupCount=3)
  else:
    efh = logging.StreamHandler()

  efh.setLevel(numeric_level)
  #efh.setFormatter(formatter)
  conf.error.addHandler(efh)

  # Now we have logging, warn about timezone
  if conf.timezone != None:
    ha.log(conf.logger, "WARNING", "'timezone' directive is deprecated, please use time_zone instead")

  
  init_sun()

  config_file_modified = os.path.getmtime(config_file)

  # Add appdir  and subdirs to path
  if conf.app_dir == None:
    conf.app_dir = find_path("apps")
  
  for root, subdirs, files in os.walk(conf.app_dir):
    if root[-11:] != "__pycache__":
      sys.path.insert(0, root)
  

  # Start main loop

  ha.log(conf.logger, "INFO", "AppDaemon Version {} starting".format(__version__))
  
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
