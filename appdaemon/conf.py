import logging
import threading


__version__ = "2.1.8"


ha_url = ""
ha_key = ""
api_key = None
threads = 0
monitored_files = {}
modules = {}
app_dir = None
apps = False
start_time = None
logfile = None
error = None
latitude = None
longitude = None
elevation = None
time_zone = None
errorfile = None
rss_feeds = None
rss_update = None
rss_last_update = None
rss = None
appq = None

executor = None
loop = None
srv = None
appd = None

stopping = False

# Will require object based locking if implemented
objects = {}

schedule = {}
schedule_lock = threading.RLock()

callbacks = {}
callbacks_lock = threading.RLock()

ha_state = {}
ha_state_lock = threading.RLock()

endpoints = {}
endpoints_lock = threading.RLock()

# No locking yet
global_vars = {}

sun = {}
config = None
config_file = None
config_file_modified = 0
location = None
tz = None
ad_time_zone = None
logger = logging.getLogger(__name__)
now = 0
tick = 1
realtime = True
timeout = 10
endtime = None
interval = 1
certpath = None
secrets = None

loglevel = "INFO"
ha_config = None
version = 0
commtype = None

config_dir = None

api_port = None

dashboard = None

last_state = None
was_dst = False

#
# Dashboard
#
dash = None
dash_ssl_key = None
dash_ssl_certificate = None
dash_port = 0
dash_password = ""
dash_compile_on_start = False
dash_force_compile = False
profile_dashboard = False
dashboard_dir = None