import appdaemon.adapi as adapi
import appdaemon.adbase as adbase
from appdaemon.appdaemon import AppDaemon
from appdaemon.logging import Logging
from appdaemon.models.config.app import AppConfig


class Dummy(adbase.ADBase, adapi.ADAPI):
    def __init__(self, ad: AppDaemon, config_model: AppConfig):
        # Call Super Classes
        adbase.ADBase.__init__(self, ad, config_model)
        adapi.ADAPI.__init__(self, ad, config_model)

        self.AD = ad
        self.config_model = config_model

        self.config = self.AD.config.model_dump(by_alias=True, exclude_unset=True)
        self.args = self.config_model.model_dump(by_alias=True, exclude_unset=True)

        self.logger = self._logging.get_child(self.name)
        self.err = self._logging.get_error().getChild(self.name)

    @property
    def app_config(self):
        return self.AD.app_management.app_config

    @property
    def global_vars(self):
        return self.AD.global_vars

    @property
    def _logging(self) -> Logging:
        return self.AD.logging

    @property
    def name(self) -> str:
        return self.config_model.name
