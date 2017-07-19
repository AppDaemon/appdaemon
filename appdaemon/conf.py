import logging
import threading


__version__ = "2.0.7"


ha_url = ""
ha_key = ""
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

config_dir = None

# Dashboard

dash_host = None
dash_dir = None
dash_port = None
dashboard = False
compile_dir = None
dash_url = None
profile_dashboard = False
dashboard_dir = None
javascript_dir = None
template_dir = None
css_dir = None
fonts_dir = None
images_dir = None
base_url = None
stream_url = None
state_url = None
max_include_depth = 10
dash_force_compile = False
custom_css_dir = None
dash = None
dash_compile_on_start = None
compiled_javascript_dir = None
compiled_html_dir = None
compiled_css_dir = None

