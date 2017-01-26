import logging
import threading

ha_url = ""
ha_key = ""
app_dir = ""
threads = 0
monitored_files = {}
modules = {}

# Will require object based locking if implemented
objects = {}

schedule = {}
schedule_lock = threading.RLock()

callbacks = {}
callbacks_lock = threading.RLock()

ha_state = {}
ha_state_lock = threading.RLock()

# No locking yet
global_vars = {}

sun = {}
config = None
location = None
tz = None
logger = logging.getLogger(__name__)
now = 0
tick = 1
realtime = True
timeout = 10
endtime = None
interval = 1
certpath = None

loglevel = "INFO"
ha_config = None
version = 0
commtype = None