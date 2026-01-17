import os
from datetime import timedelta
from ssl import _SSLMethod
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, SecretBytes, SecretStr, field_validator, model_validator
from typing_extensions import deprecated
from yarl import URL

from .common import CoercedPath, ParsedTimedelta


class PluginConfig(BaseModel, extra="allow"):
    type: Annotated[str, BeforeValidator(lambda s: s.lower())]
    name: str
    """Name of the plugin, which is used by the plugin manager to track it.

    This is set by a field_validator in the AppDaemonConfig.
    """
    disable: bool = False
    persist_entities: bool = False
    refresh_delay: ParsedTimedelta = timedelta(minutes=10)
    """Delay between refreshes of the complete plugin state in the utility loop."""
    refresh_timeout: ParsedTimedelta = timedelta(seconds=30)
    """Timeout for refreshes of the complete plugin state in the utility loop."""

    connect_timeout: ParsedTimedelta = timedelta(seconds=1)
    retry_secs: ParsedTimedelta = timedelta(seconds=5)

    namespace: str = "default"
    namespaces: list[str] = Field(default_factory=list)
    """Additional namespaces to associate with this plugin."""

    # Used by the AppDaemon internals to import the plugins.
    plugin_module: str = None  # pyright: ignore[reportAssignmentType]
    plugin_class: str = None  # pyright: ignore[reportAssignmentType]
    api_module: str = None  # pyright: ignore[reportAssignmentType]
    api_class: str = None  # pyright: ignore[reportAssignmentType]

    @model_validator(mode="after")
    def set_internal_fields(self):
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

    def __getitem__(self, item: str) -> Any:
        """Allows accessing plugin config attributes as if it were a dict."""
        if item in self.model_fields_set:
            return getattr(self, item)
        raise KeyError(f"'{item}' not found in plugin config '{self.type}'")


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


class HASSConfig(PluginConfig, extra="forbid"):
    ha_url: Annotated[
        URL,
        BeforeValidator(URL),
        PlainSerializer(str),
    ] = Field(default="http://supervisor/core", validate_default=True) # pyright: ignore[reportAssignmentType]
    token: SecretStr = Field(default_factory=lambda: SecretStr(os.environ.get("SUPERVISOR_TOKEN"))) # pyright: ignore[reportArgumentType]
    ha_key: Annotated[SecretStr, deprecated("'ha_key' is deprecated. Please use long lived tokens instead")] | None = None
    appdaemon_startup_conditions: StartupConditions | None = None
    """Startup conditions that apply only when AppDaemon first starts."""
    plugin_startup_conditions: StartupConditions | None = None
    """Startup conditions that apply if the plugin is restarted."""
    enable_started_event: bool = True
    """If `True`, the plugin will wait for the 'homeassistant_started' event before starting the plugin. Defaults to
    `True`."""
    cert_path: CoercedPath | None = None
    cert_verify: bool = True
    commtype: Annotated[str, deprecated("'commtype' is deprecated")] | None = None
    ws_timeout: ParsedTimedelta = timedelta(seconds=10)
    """Default timeout for waiting for responses from the websocket connection"""
    ws_max_msg_size: int = 4 * 1024 * 1024
    suppress_log_messages: bool = False
    services_sleep_time: ParsedTimedelta = timedelta(seconds=60)
    """The sleep time in the background task that updates the internal list of available services every once in a while"""
    config_sleep_time: ParsedTimedelta = timedelta(seconds=60)
    """The sleep time in the background task that updates the config metadata every once in a while"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def custom_validator(self):
        if self.token.get_secret_value() is None:
            raise ValueError(
                "Home Assistant token must be set either via 'token' field or 'SUPERVISOR_TOKEN' env variable"
            )
        return self

    @property
    def websocket_url(self) -> URL:
        return self.ha_url / "api/websocket"

    @property
    def auth_json(self) -> dict:
        if self.token is not None:
            return {"type": "auth", "access_token": self.token.get_secret_value()}
        elif self.ha_key is not None:
            return {"type": "auth", "api_password": self.ha_key.get_secret_value()}
        raise ValueError("Home Assistant token not set")

    @property
    def auth_headers(self) -> dict:
        if self.token is not None:
            return {"Authorization": f"Bearer {self.token.get_secret_value()}"}
        elif self.ha_key is not None:
            return {"x-ha-access": self.ha_key.get_secret_value()}
        raise ValueError("Home Assistant token not set")


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

    status_topic: str | None = None

    birth_topic: str | None = None
    birth_payload: str = "online"
    birth_retain: bool = True

    will_topic: str | None = None
    will_payload: str = "offline"
    will_retain: bool = True

    shutdown_payload: str | None = None

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
    def set_topics(self):
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
