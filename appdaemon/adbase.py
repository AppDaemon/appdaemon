import threading
from functools import wraps
from copy import deepcopy

import appdaemon.utils as utils
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon
import appdaemon.conditions as conditions


class Entities:

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

    def __init__(self, ad: AppDaemon, name, logging,  args, config, app_config, global_vars):

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
        api = adapi.ADAPI(self.AD, self.name, self._logging, self.args, self.config, self.app_config, self.global_vars)

        return api

    def get_plugin_api(self, plugin_name):
        return utils.run_coroutine_threadsafe(self, self.AD.plugins.get_plugin_api(plugin_name, self.name, self._logging, self.args, self.config, self.app_config, self.global_vars))

    #
    # Constraints
    #

    def register_constraint(self, name):
        self.constraints.append(name)

    def deregister_constraint(self, name):
        self.constraints.remove(name)

    def list_constraints(self):
        return self.constraints

    # def constrain(self, v_dict):
    #     """Universal Constraint

    #     Uses a dict like the following:
        
    #     >>> dict:
    #     >>>   any:
    #     >>>     - constraint
    #     >>>     - constraint

    #     or

    #     >>> dict:
    #     >>>   all:
    #     >>>     - constraint
    #     >>>     - constraint

    #     Each constraint above take a form like the following:

    #     >>> dict:
    #     >>>   all:
    #     >>>     - constraint_or_condition_name: string_based_config
    #     >>>     - constraint_or_condition_name:
    #     >>>         dict_based: config
    #     >>>         items_go: right_here

    #     constraint_or_condition name can be any registered condition name as
    #     well as any registered_constraint. In addition, if the constraint name
    #     starts with "constrain_" you can omit that in the dict key.
    #     """
        
    #     if not isinstance(v_dict, dict):
    #         return None

    #     if len(v_dict) != 1:
    #         return None

    #     if "any" in v_dict:
    #         return self.constrain_any(self, v_dict['any'])

    #     if "all" in v_dict:
    #         return self.constrain_all(self, v_dict['all'])

    #     return None

    # def constrain_all(self, v_list):
    #     """Universal All Constraint

    #     Performs a Universal Constraint (as seen in constrain()) with the
    #     initial dict_level "all".
    #     """

    #     cond = self.get_condition('all', v_list)
    #     return cond.check()

    # def constrain_any(self, v_list):
    #     """Universal Any Constraint

    #     Performs a Universal Constraint (as seen in constrain()) with the
    #     initial dict_level "any".
    #     """

    #     cond = self.get_condition('any', v_list)
    #     return cond.check()