import logging
import threading

rss_feeds = None

rss_update = None

rss = None
rss_last_update = None

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

