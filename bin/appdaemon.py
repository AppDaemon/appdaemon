#!/usr/bin/python3

import json
import sys
import importlib
from importlib.machinery import SourceFileLoader
import traceback
import configparser
import datetime
import argparse
import time
from daemonize import Daemonize
import logging
import os.path
import glob
from sseclient import SSEClient
from logging.handlers import RotatingFileHandler
from queue import Queue
import threading
import conf
import time
import datetime
import signal
import homeassistant as ha

q = Queue(maxsize=0)

timer = 0
config = None
config_file_modified = 0
config_file = ""
was_dst = None

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
  if conf.state_callbacks == {}:
    conf.logger.info("No callbacks")
  else:
    conf.logger.info("--------------------------------------------------")
    conf.logger.info("Callbacks")
    conf.logger.info("--------------------------------------------------")
    for name in conf.state_callbacks.keys():
      conf.logger.info("{}:".format(name))
      for uuid in conf.state_callbacks[name]:
        conf.logger.info("  {} = {}".format(uuid, conf.state_callbacks[name][uuid]))
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
  
    
def process_sun(state):
  action = ""
  if state["state"] == "above_horizon":
    # Sun has just risen, meaning next_rising time is valid for tomorrow
    action = "next_rising"
  else:
    # Sun has just set, meaning next_setting time is valid for tomorrow
    action = "next_setting"

  for name in conf.schedule.keys():
    for entry in sorted(conf.schedule[name].keys(), key=lambda uuid: conf.schedule[name][uuid]["timestamp"]):
      schedule = conf.schedule[name][entry]
      if schedule["type"] == action and "inactive" in schedule:
        del schedule["inactive"]
        schedule["timestamp"] = ha._calc_sun(action, schedule["time"])
      
def exec_schedule(name, entry, args):
  if "inactive" in args:
    return
  # Call function
  q.put_nowait({"type": "timer", "function": args["callback"], "args": args["args"], "kwargs": args["kwargs"], })
  # If it is a repeating entry, rewrite with new timestamp
  if args["repeat"]:
    if args["type"] == "next_rising" or args["type"] == "next_setting":
      # Its sunrise or sunset, and due to the offset we may not know the next rise or set yet
      # Mark the entry as inactive, and set the new time after the transition
      args["inactive"] = 1
    else:
      # Not sunrise or sunset so just increment the timestamp with the repeat interval
      args["timestamp"] += args["time"]
  else: # Otherwise just delete
    del conf.schedule[name][entry]
        
def do_every_second():

  global was_dst
  
  # Check if we have entered or exited DST - if so, reload apps to ensure all time callbacks are recalculated
  
  now_dst = is_dst()
  if now_dst != was_dst:
    conf.logger.info("Detected change in DST from {} to {} - reloading all modules".format(was_dst, now_dst))
    readApps(True)
    was_dst = is_dst()

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
    

  #dump_schedule()
  
  # Check to see if any apps have changed
  
  readApps()
  
  # Check to see if config has changed
  
  check_config()

  # Call me suspicious, but lets update state form HA periodically in case we miss events for whatever reason
  # Every 10 minutes seems like a good place to start

  global timer
  timer += 1
  if timer == 600:
    get_ha_state()
    timer = 0
   
  # Check on Queue size
  
  if q.qsize() > 0 and q.qsize() % 10 == 0:
    conf.logger.warning("Queue size is {}, suspect thread starvation".format(q.qsize()))
  
def timer_thread():
  do_every(1, do_every_second)
        
def worker():
  while True:
    args = q.get()
    type = args["type"]
    function = args["function"]
    try:
      if type == "initialize":
        function()
      if type == "timer":
        function(args["args"], args["kwargs"])
      elif type == "attr":
        entity = args["entity"]
        attr = args["attr"]
        old_state = args["old_state"]
        new_state = args["new_state"]
        function(entity, attr, old_state, new_state)
    except:
      conf.error.warn('-'*60)
      conf.error.warn("Unexpected error:")
      conf.error.warn('-'*60)
      conf.error.warn(traceback.format_exc())
      conf.error.warn('-'*60)
      conf.logger.warn("Logged an error to {}".format(conf.errorfile))

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
  if object in conf.state_callbacks:
    del conf.state_callbacks[object]
  if object in conf.schedule:
    del conf.schedule[object]

def init_object(name, class_name, module_name, args):
  conf.logger.info("Loading Object {} using class {} from module {}".format(name, class_name, module_name))
  module = __import__(module_name)  
  APPclass = getattr(module, class_name)
  conf.objects[name] = APPclass(name, conf.logger, conf.error, args)

  # Call it's initialize function
  
  q.put_nowait({"type": "initialize", "function": conf.objects[name].initialize})

def process_message(msg):
  try:
    if msg.data == "ping":
      return
    
    data = json.loads(msg.data)
    conf.logger.debug("Event type:{}:".format(data['event_type']))
    # Process state changed message
    if data['event_type'] == "state_changed":
      entity_id = data['data']['entity_id']
      conf.logger.debug("Entity ID:{}:".format(entity_id))
      device, entity = entity_id.split(".")
      
      # First update our global state

      conf.ha_state[entity_id] = data['data']['new_state']
      
      # Check sunrise/sunset
      
      if entity_id == "sun.sun" and data["data"]["old_state"]["state"] != data["data"]["new_state"]["state"]:
        
        #dump_schedule()
        
        #conf.logger.info("Detected Sunrise/Sunset")
        #conf.logger.info(data['data'])
        
        process_sun(data["data"]["new_state"])
        
        #dump_schedule()
      
      # Process any callbacks
      
      for name in conf.state_callbacks.keys():
        for uuid in conf.state_callbacks[name]:
          callback = conf.state_callbacks[name][uuid]
          cdevice = None
          centity = None
          cattribute = callback["attribute"]
          if callback["entity"] != None:
            if callback["entity"].find(".") == -1:
              cdevice = callback["entity"]
              centity = None
            else:
              cdevice, centity = callback["entity"].split(".")
          if cdevice == None:
            q.put_nowait({"type": "attr", "function": callback["function"], "entity": entity_id, "attr": None, "new_state": data['data']['new_state'], "old_state": data['data']['old_state']})
          elif centity == None:
            if device == cdevice:
              q.put_nowait({"type": "attr", "function": callback["function"], "entity": entity_id, "attr": None, "new_state": data['data']['new_state'], "old_state": data['data']['old_state']})
          elif cattribute == None:
            if device == cdevice and entity == centity:
             q.put_nowait({"type": "attr", "function": callback["function"], "entity": entity_id, "attr": "state", "new_state": data['data']['new_state']['state'], "old_state": data['data']['old_state']['state']})
          else:
            if device == cdevice and entity == centity:
              if cattribute == "all":
                q.put_nowait({"type": "attr", "function": callback["function"], "attr": cattribute, "entity": entity_id, "new_state": data['data']['new_state'], "old_state": data['data']['old_state']})
              else:
                if cattribute in data['data']['old_state']:
                  old = data['data']['old_state'][cattribute]
                elif cattribute in data['data']['old_state']['attributes']:
                  old = data['data']['old_state']['attributes'][cattribute]
                else:
                  old = None
                if cattribute in data['data']['new_state']:
                  new = data['data']['new_state'][cattribute]
                elif cattribute in data['data']['new_state']['attributes']:
                  new = data['data']['new_state']['attributes'][cattribute]
                else:
                  new = None

                if old != new:
                  q.put_nowait({"type": "attr", "function": callback["function"], "attr": cattribute, "entity": entity_id, "new_state": new, "old_state": old})

    elif data['event_type'] == "call_service":
      pass
    elif data['event_type'] == "homeassistant_start":
      pass
    elif data['event_type'] == "homeassistant_stop":
      pass
    elif data['event_type'] == "mqtt_message_reveived":
      pass
    elif data['event_type'] == "platform_discovered":
      pass
    elif data['event_type'] == "time_changed":
      pass

  except:
    conf.error.warn('-'*60)
    conf.error.warn("Unexpected error during process_message()")
    conf.error.warn('-'*60)
    conf.error.warn(traceback.format_exc())
    conf.error.warn('-'*60)
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
      importlib.reload(conf.modules[module_name])
    else:
      conf.logger.info("Loading Module: %s", file)
      conf.modules[module_name] = importlib.import_module(module_name)
    
    
    # Instantiate class and Run initialize() function
    
    for name in config:
      if name == "DEFAULT" or name == "appdaemon":
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
        if name == "DEFAULT" or name == "appdaemon":
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
        if name == "DEFAULT" or name == "appdaemon":
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
    conf.logger.warn("Logged an error to {}".format(conf.errorfile))

def readApps(all = False): 
  found_files = glob.glob(os.path.join(conf.app_dir, '*.py'))
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
  
  # Take a note of DST

  was_dst = is_dst()
  
  # grab system state
  
  get_ha_state()
  
  # Load apps
  
  readApps()
  
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
  
  while True:
    try:
      headers = {'x-ha-access': conf.ha_key}
      messages = SSEClient("{}/api/stream".format(conf.ha_url), verify = False, headers = headers, retry = 3000)
      for msg in messages:
        process_message(msg)
    except requests.exceptions.ConnectionError:
      conf.logger.warning("Unable to connect to Home Assistant, retrying in 5 seconds")
    except:
      conf.logger.warn('-'*60)
      conf.logger.warn("Unexpected error:")
      conf.logger.warn('-'*60)
      conf.logger.warn(traceback.format_exc())
      conf.logger.warn('-'*60)
    time.sleep(5)

def main():
  
  global config
  global config_file
  global config_file_modified
  
  # Get command line args
  
  signal.signal(signal.SIGUSR1, handle_sig)
  
  parser = argparse.ArgumentParser()

  parser.add_argument("config", help="full path to config file", type=str)
  parser.add_argument("-d", "--daemon", help="run as a background process", action="store_true")
  parser.add_argument("-p", "--pidfile", help="full path to PID File", default = "/tmp/hapush.pid")
  parser.add_argument("-D", "--debug", help="debug level", default = "INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
  args = parser.parse_args()
  config_file = args.config
  
  isdaemon = args.daemon

  # Read Config File

  config = configparser.ConfigParser()
  config.read_file(open(args.config))
  
  assert "appdaemon" in config, "[appdaemon] section required in {}".format(args.config)

  conf.ha_url = config['appdaemon']['ha_url']
  conf.ha_key = config['appdaemon']['ha_key']
  conf.logfile = config['appdaemon']['logfile']
  conf.errorfile = config['appdaemon']['errorfile']
  conf.app_dir = config['appdaemon']['app_dir']
  conf.threads = int(config['appdaemon']['threads'])
  
  config_file_modified = os.path.getmtime(args.config)
    
  # Add appdir to path
  
  sys.path.insert(0, conf.app_dir)
  
  # Setup Logging
  
  conf.logger = logging.getLogger("log1")
  numeric_level = getattr(logging, args.debug, None)
  conf.logger.setLevel(numeric_level)
  conf.logger.propagate = False
  formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

  # Send to file if we are daemonizing, else send to console
  
  if isdaemon:
    fh = RotatingFileHandler(conf.logfile, maxBytes=1000000, backupCount=3)
    fh.setLevel(numeric_level)
    fh.setFormatter(formatter)
    conf.logger.addHandler(fh)
  else:
    ch = logging.StreamHandler()
    ch.setLevel(numeric_level)
    ch.setFormatter(formatter)
    conf.logger.addHandler(ch)

  # Setup compile output
  
  conf.error = logging.getLogger("log2")
  numeric_level = getattr(logging, args.debug, None)
  conf.error.setLevel(numeric_level)
  conf.error.propagate = False
  formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

  efh = RotatingFileHandler(conf.errorfile, maxBytes=1000000, backupCount=3)
  efh.setLevel(numeric_level)
  efh.setFormatter(formatter)
  conf.error.addHandler(efh)
  
  # Start main loop

  if isdaemon:
    keep_fds = [fh.stream.fileno(), efh.stream.fileno()]
    pid = args.pidfile
    daemon = Daemonize(app="hapush", pid=pid, action=run, keep_fds=keep_fds) 
    daemon.start()
    while True:
      time.sleep(1)
  else:
    run()

if __name__ == "__main__":
    main()
