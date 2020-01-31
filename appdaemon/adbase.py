import threading
from functools import wraps
from copy import deepcopy

import appdaemon.utils as utils
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon


class Entities:
    def __init__(self):
        pass

    def __get__(self, instance, owner):
        stateattrs = utils.StateAttrs(instance.get_state())
        return stateattrs


#
# Locking decorator
#


def app_lock(f):
    """Synchronization decorator."""

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
    """Synchronization decorator."""

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

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars):

        # Store args

        self.AD = ad
        self.name = name
        self._logging = logging
        self.config = config
        self.app_config = app_config
        self.args = deepcopy(args)
        self.global_vars = global_vars
        self.namespace = "default"
        self.app_dir = self.AD.app_dir
        self.config_dir = self.AD.config_dir
        self.dashboard_dir = None

        if self.AD.http is not None:
            self.dashboard_dir = self.AD.http.dashboard_dir

        self.logger = self._logging.get_child(name)
        self.err = self._logging.get_error().getChild(name)
        self.user_logs = {}
        if "log_level" in args:
            self.logger.setLevel(args["log_level"])
            self.err.setLevel(args["log_level"])

        # Some initial Setup

        self.lock = threading.RLock()

        self.constraints = []

    #
    # API/Plugin
    #

    def get_ad_api(self):
        api = adapi.ADAPI(self.AD, self.name, self._logging, self.args, self.config, self.app_config, self.global_vars,)

        return api

    @utils.sync_wrapper
    async def get_plugin_api(self, plugin_name):
        return await self.AD.plugins.get_plugin_api(
            plugin_name, self.name, self._logging, self.args, self.config, self.app_config, self.global_vars,
        )

    #
    # Constraints
    #

    def register_constraint(self, name):
        self.constraints.append(name)

    def deregister_constraint(self, name):
        self.constraints.remove(name)

    def list_constraints(self):
        return self.constraints
