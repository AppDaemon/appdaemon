import appdaemon.adbase as appapi

class Dummy(appapi.ADBase):

    def __init__(self, ad, name, logger, error, args, config, app_config, global_vars,):

        super(Dummy, self).__init__(ad, name, logger, error, args, config, app_config, global_vars)

        self.AD = ad
        self.name = name
        self._logger = logger
        self._error = error
        self.args = args
        self.config = config
        self.app_config = app_config
        self.global_vars = global_vars

