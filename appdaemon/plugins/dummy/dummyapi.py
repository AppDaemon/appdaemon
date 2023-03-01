import appdaemon.adbase as adbase
import appdaemon.adapi as adapi

from appdaemon.appdaemon import AppDaemon


class Dummy(adbase.ADBase, adapi.ADAPI):
    def __init__(
        self,
        ad: AppDaemon,
        name,
        logger,
        error,
        args,
        config,
        app_config,
        global_vars,
    ):
        # Call Super Classes
        adbase.ADBase.__init__(self, ad, name, logger, error, args, config, app_config, global_vars)
        adapi.ADAPI.__init__(self, ad, name, logger, error, args, config, app_config, global_vars)

        self.AD = ad
        self.name = name
        self._logger = logger
        self._error = error
        self.args = args
        self.config = config
        self.app_config = app_config
        self.global_vars = global_vars
