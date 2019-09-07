import asyncio
import appdaemon.adbase as adbase
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon

    
class Ad(adbase.ADBase, adapi.ADAPI):

    #entities = Entities()

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars,):

        # Call Super Classes
        adbase.ADBase.__init__(self, ad, name, logging, args, config, app_config, global_vars)
        adapi.ADAPI.__init__(self, ad, name, logging, args, config, app_config, global_vars)