"""This module has the sections"""

import os
from datetime import timedelta
from ssl import _SSLMethod
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, SecretBytes, SecretStr, ValidationInfo, field_validator, model_validator
from typing_extensions import deprecated

from .common import CoercedPath

from appdaemon import utils


class PluginConfig(BaseModel, extra="allow"):
    type: str
    name: str
    """Gets set by a field_validator in the AppDaemonConfig"""
    disable: bool = False
    persist_entities: bool = False
    refresh_delay: Annotated[timedelta, BeforeValidator(lambda v: timedelta(minutes=v))] = timedelta(minutes=10)
    """Delay between refreshes of the complete plugin state in the utility loop"""
    refresh_timeout: int = 30
    use_dictionary_unpacking: bool = True

    # Used by the AppDaemon internals to import the plugins.
    plugin_module: str = None
    plugin_class: str = None
    api_module: str = None
    api_class: str = None

    connect_timeout: int | float = 1.0
    reconnect_delay: int | float = 5.0

    namespace: str = "default"
    namespaces: list[str] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def lower(cls, v: str, info: ValidationInfo):
        return v.lower()

    @model_validator(mode="after")
    def custom_validator(self):
        if "plugin_module" not in self.model_fields_set:
            self.plugin_module = f"appdaemon.plugins.{self.type}.{self.type}plugin"

        if "plugin_class" not in self.model_fields_set:
            self.plugin_class = f"{self.type.capitalize()}Plugin"

        if "api_module" not in self.model_fields_set:
            self.api_module = f"appdaemon.plugins.{self.type}.{self.type}api"

        if "api_classname" not in self.model_fields_set:
            self.api_class = f"{self.type.capitalize()}"

        return self

    @property
    def disabled(self) -> bool:
        return self.disable


class StartupState(BaseModel):
    state: Any
    attributes: dict[str, Any] | None = None


class StateStartupCondition(BaseModel):
    entity: str
    value: StartupState | None = None


class EventStartupCondition(BaseModel):
    event_type: str
    data: dict | None = None


class StartupConditions(BaseModel):
    delay: int | float | None = None
    state: StateStartupCondition | None = None
    event: EventStartupCondition | None = None


class HASSConfig(PluginConfig):
    ha_url: str = "http://supervisor/core"
    token: SecretStr
    ha_key: Annotated[SecretStr, deprecated("'ha_key' is deprecated. Please use long lived tokens instead")] | None = None
    appdaemon_startup_conditions: StartupConditions | None = None
    plugin_startup_conditions: StartupConditions | None = None
    enable_started_event: bool = True
    """If true, the plugin will wait for the 'homeassistant_started' event before starting the plugin."""
    cert_path: CoercedPath | None = None
    cert_verify: bool = True
    commtype: str = "WS"
    q_timeout: int = 30
    ws_timeout: Annotated[
        timedelta,
        BeforeValidator(utils.parse_timedelta)
    ] = Field(default_factory=lambda: timedelta(seconds=10))
    """Default timeout for waiting for responses from the websocket connection"""
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


class MQTTConfig(PluginConfig):
    name: str
    client_host: str = "127.0.0.1"
    client_port: int = 1883
    transport: Literal["tcp", "websockets", "unix"] = "tcp"
    clean_session: bool = True
    client_user: str | None = None
    client_password: SecretBytes | None = None
    client_id: str | None = None
    client_qos: int = 0
    client_topics: list[str] = Field(default=["#"])
    client_timeout: int = 60
    event_name: str = "MQTT_MESSAGE"
    force_start: bool = False

    status_topic: str = None

    birth_topic: str | None = None
    birth_payload: str = "online"
    birth_retain: bool = True

    will_topic: str | None = None
    will_payload: str = "offline"
    will_retain: bool = True

    shutdown_payload: str = None

    ca_cert: str | None = None
    client_cert: str | None = None
    client_key: str | None = None
    verify_cert: bool = True
    tls_version: _SSLMethod | Literal["auto", "1.0", "1.1", "1.2"] = "auto"

    @field_validator("client_topics", mode="before")
    @classmethod
    def validate_client_topics(cls, v: Any) -> list[str]:
        match v:
            case None:
                return []
            case str():
                match v.upper():
                    case "NONE":
                        return []
                    case "ALL":
                        return ["#"]
                    case _:
                        return [v]
            case list():
                return v
            case _:
                raise ValueError("client_topics must be a string or a list")

    @model_validator(mode="after")
    def custom_validator(self):
        self = super().custom_validator()
        if "client_id" not in self.model_fields_set:
            self.client_id = f"appdaemon_{self.name}_client".lower()

        if "status_topic" not in self.model_fields_set:
            self.status_topic = f"{self.client_id}/status"

        if "birth_topic" not in self.model_fields_set:
            self.birth_topic = self.status_topic

        if "will_topic" not in self.model_fields_set:
            self.will_topic = self.status_topic

        if "shutdown_payload" not in self.model_fields_set:
            self.shutdown_payload = self.will_payload

        return self
