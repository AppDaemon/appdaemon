import os
from pathlib import Path
from typing import Annotated, Any

import pytz
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretStr, field_validator, model_validator
from typing_extensions import deprecated

from ...models.config.plugin import PluginConfig


class HASSConfig(PluginConfig):
    ha_url: str = "http://supervisor/core"
    token: SecretStr
    ha_key: Annotated[SecretStr, deprecated("'ha_key' is deprecated. Please use long lived tokens instead")] | None = None
    appdaemon_startup_conditions: dict = Field(default_factory=dict)
    plugin_startup_conditions: dict = Field(default_factory=dict)
    cert_path: Path | None = None
    cert_verify: bool | None = None
    commtype: str = "WS"
    q_timeout: int = 30
    return_result: bool | None = None
    suppress_log_messages: bool = False
    retry_secs: int = 5
    services_sleep_time: int = 60
    """The sleep time in the background task that updates the internal list of available services every once in a while"""
    config_sleep_time: int = 60
    """The sleep time in the background task that updates the config metadata every once in a while"""

    @field_validator("ha_key", mode="after")
    @classmethod
    def validate_ha_key(cls, v: Any):
        if v is None:
            return os.environ.get("SUPERVISOR_TOKEN")
        else:
            return v

    @field_validator("ha_url", mode="after")
    @classmethod
    def validate_ha_url(cls, v: str):
        return v.rstrip("/")

    @model_validator(mode="after")
    def custom_validator(self):
        self = super().custom_validator()
        assert "token" in self.model_fields_set or "ha_key" in self.model_fields_set
        return self

    @property
    def websocket_url(self) -> str:
        return f"{self.ha_url}/api/websocket"

    @property
    def states_api(self) -> str:
        return f"{self.ha_url}/api/states"

    def get_entity_api(self, entity_id: str) -> str:
        return f"{self.states_api}/{entity_id}"

    @property
    def auth_json(self) -> dict:
        if self.token is not None:
            return {"type": "auth", "access_token": self.token.get_secret_value()}
        elif self.ha_key is not None:
            return {"type": "auth", "api_password": self.ha_key.get_secret_value()}

    @property
    def auth_headers(self) -> dict:
        if self.token is not None:
            return {"Authorization": f"Bearer {self.token.get_secret_value()}"}
        elif self.ha_key is not None:
            return {"x-ha-access": self.ha_key}


class HASSMetaData(BaseModel, extra="allow"):
    """Represents the fields required to be returned from the ``get_config``
    command from the websocket connection
    """

    latitude: float
    longitude: float
    elevation: float
    time_zone: Annotated[pytz.BaseTzInfo, BeforeValidator(pytz.timezone)]

    model_config = ConfigDict(arbitrary_types_allowed=True)
