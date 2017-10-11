import logging
import threading


__version__ = "2.1.10"


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
config_file = None
config_file_modified = 0
location = None
tz = None
ad_time_zone = None
logger = logging.getLogger(__name__)
now = 0
tick = 1
realtime = True
endtime = None
interval = 1
loglevel = "INFO"
version = 0
config_dir = None
api_port = None
was_dst = False
config = None
app_config_file = None
app_config_file_modified = 0
app_config = None

# HomeAssistant plugin

certpath = None
ha_config = None
timeout = 10
commtype = None
last_state = None
ha_url = ""
ha_key = ""
api_key = None

# Other

secrets = None


#
# Dashboard
#
dash = None
dash_url = None
dash_ssl_key = None
dash_ssl_certificate = None
dash_port = 0
dash_password = ""
dash_compile_on_start = False
dash_force_compile = False
profile_dashboard = False
dashboard_dir = None
dashboard = None