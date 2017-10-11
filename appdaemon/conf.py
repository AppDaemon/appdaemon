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