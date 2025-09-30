from collections.abc import Iterable
import os
import ssl
from datetime import timedelta
from ssl import _SSLMethod
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretBytes, SecretStr, ValidationError, field_validator, model_validator
from typing_extensions import deprecated


from .common import CoercedPath, ParsedTimedelta


class PluginConfig(BaseModel):
    type: Annotated[str, BeforeValidator(lambda s: s.lower())]
    name: str
    """Name of the plugin, which is used by the plugin manager to track it.

    This is set by a field_validator in the AppDaemonConfig.
    """
    # Used by the AppDaemon internals to import the plugins.
    plugin_module: str
    plugin_class: str
    api_module: str
    api_class: str

    disable: bool = False
    persist_entities: bool = False
    refresh_delay: ParsedTimedelta = timedelta(minutes=10)
    """Delay between refreshes of the complete plugin state in the utility loop."""
    refresh_timeout: ParsedTimedelta = timedelta(seconds=30)
    """Timeout for refreshes of the complete plugin state in the utility loop."""

    connect_timeout: ParsedTimedelta = timedelta(seconds=3)
    retry_secs: ParsedTimedelta = timedelta(seconds=5)

    namespace: str = "default"
    namespaces: list[str] = Field(default_factory=list)
    """Additional namespaces to associate with this plugin."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
        validate_assignment=True,
        validate_default=True,
    )

    @model_validator(mode="before")
    @classmethod
    def set_internals(cls, values: dict[str, Any]) -> dict[str, Any]:
        match values.get("type"):
            case str(type_):
                values["plugin_module"] = values.get("plugin_module", f"appdaemon.plugins.{type_}.{type_}plugin")
                values["plugin_class"] = values.get("plugin_class", f"{type_.capitalize()}Plugin")
                values["api_module"] = values.get("api_module", f"appdaemon.plugins.{type_}.{type_}api")
                values["api_class"] = values.get("api_class", f"{type_.capitalize()}")
        return values

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


class HASSConfig(PluginConfig):
    ha_url: str = "http://supervisor/core"
    token: SecretStr
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
    suppress_log_messages: bool = False
    services_sleep_time: ParsedTimedelta = timedelta(seconds=60)
    """The sleep time in the background task that updates the internal list of available services every once in a while"""
    config_sleep_time: ParsedTimedelta = timedelta(seconds=60)
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
        assert "token" in self.model_fields_set or "ha_key" in self.model_fields_set, (
            "Either 'token' or 'ha_key' must be set for the Home Assistant plugin"
        )
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
        raise ValueError("Home Assistant token not set")

    @property
    def auth_headers(self) -> dict:
        if self.token is not None:
            return {"Authorization": f"Bearer {self.token.get_secret_value()}"}
        elif self.ha_key is not None:
            return {"x-ha-access": self.ha_key}
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
    client_qos: Literal[0, 1, 2] = 0
    client_topics: set[str] = Field(default={"#"})
    client_timeout: int = 60
    event_name: str = "MQTT_MESSAGE"
    force_start: bool = False

    status_topic: str

    birth_topic: str
    birth_payload: str = "online"
    birth_retain: bool = True

    will_topic: str
    will_payload: str = "offline"
    will_retain: bool = True

    shutdown_payload: str | None = None

    ca_cert: str | None = None
    client_cert: str | None = None
    client_key: str | None = None
    verify_cert: bool = True
    tls_version: _SSLMethod = "auto" # pyright: ignore[reportAssignmentType]

    @field_validator("tls_version", mode="before")
    @classmethod
    def validate_tls_version(cls, v: Any) -> _SSLMethod:
        match v:
            case "1.0":
                return ssl.PROTOCOL_TLSv1
            case "1.1":
                return ssl.PROTOCOL_TLSv1_1
            case "1.2":
                return ssl.PROTOCOL_TLSv1_2
            case "auto":
                import sys
                return ssl.PROTOCOL_TLS if sys.hexversion >= 0x03060000 else ssl.PROTOCOL_TLSv1
            case _:
                raise ValidationError("tls_version must be one of '1.0', '1.1', '1.2', or 'auto'")

    @field_validator("client_topics", mode="before")
    @classmethod
    def validate_client_topics(cls, v: Any) -> set[str]:
        match v:
            case None:
                return set()
            case str():
                match v.upper():
                    case "NONE":
                        return set()
                    case "ALL":
                        return {"#"}
                    case _:
                        return {v}
            case Iterable():
                return set(v)
            case _:
                raise ValueError("client_topics must be a string or an iterable of them")

    @model_validator(mode="before")
    def set_defaults(cls, values: dict[str, Any]) -> dict[str, Any]:
        values["client_id"] = values.get("client_id", f"appdaemon_{values.get('name', 'unknown')}_client").lower()
        values["status_topic"] = values.get(
            "status_topic",
            f"appdaemon/{values.get('client_id', 'unknown')}/status".lower(),
        )
        values["birth_topic"] = values.get("birth_topic", values.get("status_topic"))
        values["will_topic"] = values.get("will_topic", values.get("status_topic"))
        values["shutdown_payload"] = values.get("shutdown_payload", values.get("will_topic"))
        return values
