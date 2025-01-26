from ssl import _SSLMethod
from typing import Literal

from pydantic import Field, SecretBytes, model_validator

from ...models.config.plugin import PluginConfig


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

        if isinstance(self.client_topics, str) and self.client_topics.upper() == "NONE":
            self.client_topics = list()

        return self
