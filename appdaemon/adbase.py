import threading
import appdaemon.utils as utils
import appdaemon.adapi as adapi

class Entities:

    def __get__(self, instance, owner):
        stateattrs = utils.StateAttrs(instance.get_state())
        return stateattrs

#
# Locking decorator
#

def app_lock(myFunc):
    """ Synchronization decorator. """

    def wrap(*args, **kw):
        self = args[0]

        self.lock.acquire()
        try:
            return myFunc(*args, **kw)
        finally:
            self.lock.release()
    return wrap

def global_lock(myFunc):
    """ Synchronization decorator. """

    def wrap(*args, **kw):
        self = args[0]

        self.AD.global_lock.acquire()
        try:
            return myFunc(*args, **kw)
        finally:
            self.AD.global_lock.release()
    return wrap

class ADBase:
    #
    # Internal
    #

    entities = Entities()

    def __init__(self, ad, name, logger, error, args, config, app_config, global_vars):

        # Store args

        self.AD = ad
        self.name = name
        self._logger = logger
        self._error = error
        self.config = config
        self.app_config = app_config
        self.args = args
        self.global_vars = global_vars
        self.namespace = "default"

        # Some initial Setup

        self.lock = threading.RLock()

        self.constraints = []


    #
    # API/Plugin
    #

    def get_ad_api(self):
        api = adapi.ADAPI(self.AD, self.name, self._logger, self._error, self.args, self.config, self.app_config, self.global_vars)
        return api

    def get_plugin_api(self, name):
        if name in self.AD.plugin.plugins:
            plugin = self.AD.plugin.plugins[name]
            module_name = "{}api".format(plugin["type"])
            mod = __import__(module_name, globals(), locals(), [module_name], 0)
            app_class = getattr(mod, plugin["type"].title())
            api = app_class(self.AD, self.name, self._logger, self._error, self.args, self.config, self.app_config, self.global_vars)
            if "namespace" in plugin:
                api.set_namespace(plugin["namespace"])
            else:
                api.set_namespace("default")
            return api

        else:
            self.AD.log("WARNING", "Unknown Plugin Configuration in get_plugin_api()")
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


