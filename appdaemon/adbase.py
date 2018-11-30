import threading
from functools import wraps

import appdaemon.utils as utils
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon


class Entities:

    def __get__(self, instance, owner):
        stateattrs = utils.StateAttrs(instance.get_state())
        return stateattrs


#
# Locking decorator
#

def app_lock(f):
    """ Synchronization decorator. """

    @wraps(f)
    def f_app_lock(*args, **kw):
        self = args[0]

        self.lock.acquire()
        try:
            return f(*args, **kw)
        finally:
            self.lock.release()
    return f_app_lock

def global_lock(f):
    """ Synchronization decorator. """

    @wraps(f)
    def f_global_lock(*args, **kw):
        self = args[0]

        self.AD.global_lock.acquire()
        try:
            return f(*args, **kw)
        finally:
            self.AD.global_lock.release()
    return f_global_lock

class ADBase:
    #
    # Internal
    #

    entities = Entities()

    def __init__(self, ad: AppDaemon, name, logging,  args, config, app_config, global_vars):

        # Store args

        self.AD = ad
        self.name = name
        self.logging = logging
        self.config = config
        self.app_config = app_config
        self.args = args
        self.global_vars = global_vars
        self.namespace = "default"
        self._error = None
        self._logger = None

        # Some initial Setup

        self.lock = threading.RLock()

        self.constraints = []


    #
    # API/Plugin
    #

    def get_ad_api(self):
        api = adapi.ADAPI(self.AD, self.name, self.logging, self.args, self.config, self.app_config, self.global_vars)

        return api

    def get_plugin_api(self, name):
        if name in self.AD.plugins.plugins:
            plugin = self.AD.plugins.plugins[name]
            module_name = "{}api".format(plugin["type"])
            mod = __import__(module_name, globals(), locals(), [module_name], 0)
            app_class = getattr(mod, plugin["type"].title())
            api = app_class(self.AD, self.name, self.logging, self.args, self.config, self.app_config, self.global_vars)
            if "namespace" in plugin:
                api.set_namespace(plugin["namespace"])
            else:
                api.set_namespace("default")
            return api

        else:
            self.AD.logging.log("WARNING", "Unknown Plugin Configuration in get_plugin_api()")
            return None
    #
    # Constraints
    #

    def register_constraint(self, name):
        self.constraints.append(name)

    def deregister_constraint(self, name):
        self.constraints.remove(name)

    def list_constraints(self):
        return self.constraints
