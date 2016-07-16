import logging

ha_url = ""
ha_key = ""
app_dir = ""
monitored_files = {}
modules = {}
objects = {}
schedule = {}
state_callbacks = {}
threads = 0
ha_state = {}

logger = logging.getLogger(__name__)
