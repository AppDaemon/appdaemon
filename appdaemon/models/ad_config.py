import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Callable, Dict, List, Literal, Optional, Union

import pytz
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    RootModel,
    SecretBytes,
    SecretStr,
    Tag,
    field_validator,
    model_serializer,
    model_validator,
)
from pytz.tzinfo import DstTzInfo, StaticTzInfo
from typing_extensions import deprecated

from .. import utils
from ..version import __version__
from .config.namespace import NamespaceConfig
from .config.plugin import PluginConfig
from .internal.cli import AppDaemonCLIKwargs

if TYPE_CHECKING:
    pass


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
    tls_version: Literal["auto", "1.0", "1.1", "1.2"] = "auto"

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

    @model_serializer
    def serial(self, vals: dict):
        return vals


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


class FilterConfig(BaseModel):
    command_line: str
    input_ext: str
    output_ext: str


def plugin_discriminator(plugin):
    if isinstance(plugin, dict):
        return plugin["type"].lower()
    else:
        plugin.type


class ModuleLoggingLevels(RootModel):
    root: dict[str, str] = {"_events": "WARNING"}


class AppDaemonConfig(BaseModel):
    latitude: float
    longitude: float
    elevation: int
    time_zone: Union[StaticTzInfo, DstTzInfo]
    plugins: Dict[
        str,
        Annotated[
            Union[Annotated[HASSConfig, Tag("hass")], Annotated[MQTTConfig, Tag("mqtt")]],
            Discriminator(plugin_discriminator),
        ],
    ] = Field(default_factory=dict)

    config_dir: Path
    config_file: Path
    app_dir: Path = "./apps"

    write_toml: bool = False
    ext: Literal[".yaml", ".toml"] = ".yaml"

    filters: List[FilterConfig] = []

    starttime: datetime | None = None
    endtime: datetime | None = None
    timewarp: float = 1
    max_clock_skew: int = 1

    loglevel: str = "INFO"
    module_debug: ModuleLoggingLevels = Field(default_factory=dict)

    api_port: int | None = None
    stop_function: Callable | None = None

    utility_delay: int = 1
    admin_delay: int = 1
    plugin_performance_update: int = 10
    """How often in seconds to update the admin entities with the plugin performance data"""
    max_utility_skew: float = 2
    check_app_updates_profile: bool = False
    production_mode: bool = False
    invalid_config_warnings: bool = True
    missing_app_warnings: bool = True
    log_thread_actions: bool = False
    qsize_warning_threshold: int = 50
    qsize_warning_step: int = 60
    qsize_warning_iterations: int = 10
    internal_function_timeout: int = 10
    use_dictionary_unpacking: Annotated[bool, deprecated("This option is no longer necessary")] = False
    uvloop: bool = False
    use_stream: bool = False
    import_paths: List[Path] = Field(default_factory=list)
    namespaces: Dict[str, NamespaceConfig] = Field(default_factory=dict)
    exclude_dirs: List[str] = Field(default_factory=list)
    cert_verify: bool = True
    disable_apps: bool = False

    import_method: Annotated[
        Literal["normal", "expert"] | None,
        deprecated("Import method is no longer relevant with the new AppManagement system."),
    ] = None

    load_distribution: str = "roundrobbin"
    threads: (
        Annotated[
            int,
            deprecated("Threads directive is deprecated apps - will be pinned. Use total_threads if you want to unpin your apps"),
        ]
        | None
    ) = None
    total_threads: int | None = None
    """The number of dedicated worker threads to create for running the apps. 
    Normally, AppDaemon will create enough threads to provide one per app, or 
    default to 10 if app pinning is turned off. Setting this to a specific 
    value will turn off automatic thread management."""
    pin_apps: bool = True
    """If true, AppDaemon apps will be pinned to a particular thread. This 
    should avoids complications around re-entrant code and locking of instance 
    variables."""
    pin_threads: int | None = None
    """Number of threads to use for pinned apps, allowing the user to section 
    off a sub-pool just for pinned apps. By default all threads are used for 
    pinned apps."""
    thread_duration_warning_threshold: float = 10
    threadpool_workers: int = 10
    """Number of threads in AppDaemon's internal thread pool, which can be used 
    to execute functions asynchronously in worker threads. 
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='allow'
    )
    ad_version: str = __version__

    @field_validator("config_dir", mode="after")
    @classmethod
    def convert_to_absolute(cls, v: Path):
        return v.resolve()

    @field_validator("exclude_dirs", mode="after")
    @classmethod
    def add_default_exclusions(cls, v: List[Path]):
        v.extend(["__pycache__", "build"])
        return v

    @field_validator("loglevel", mode="before")
    @classmethod
    def convert_loglevel(cls, v: Union[str, int]):
        if isinstance(v, int):
            return logging._levelToName[int]
        elif isinstance(v, str):
            v = v.upper()
            assert v in logging._nameToLevel, f"Invalid log level: {v}"
            return v

    @field_validator("time_zone", mode="before")
    @classmethod
    def convert_timezone(cls, v: str):
        return pytz.timezone(v)

    @field_validator("plugins", mode="before")
    @classmethod
    def validate_plugins(cls, v: Any):
        for n in set(v.keys()):
            v[n]["name"] = n
        return v

    def model_post_init(self, __context: Any):
        # Convert app_dir to Path object
        self.app_dir = Path(self.app_dir) if not isinstance(self.app_dir, Path) else self.app_dir

        # Resolve app_dir relative to config_dir if it's a relative path
        if not self.app_dir.is_absolute():
            self.app_dir = self.config_dir / self.app_dir

        self.ext = ".toml" if self.write_toml else ".yaml"

    @model_validator(mode="before")
    @classmethod
    def validate_ad_cfg(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if (file := data.get("config_file")) and not data.get("config_dir"):
                data["config_dir"] = Path(file).parent
        return data

    @model_validator(mode="after")
    def warn_deprecated(self):
        for field in self.model_fields_set:
            if field in self.__pydantic_extra__:
                print(f'WARNING {field}: Extra config field. This will be ignored')
            elif (info := self.model_fields.get(field)) and info.deprecated:
                print(f"WARNING {field}: {info.deprecation_message}")

        return self


class MainConfig(BaseModel):
    appdaemon: AppDaemonConfig
    hadashboard: Optional[dict] = None
    admin: Optional[dict] = None
    api: Optional[dict] = None
    http: Optional[dict] = None
    log: Optional[dict] = None
    logs: Optional[dict] = None

    @classmethod
    def from_config_file(cls, file: str | Path):
        config = utils.read_config_file(file)
        config["appdaemon"]["config_file"] = file
        return cls.model_validate(config)

    @classmethod
    def from_cli_kwargs(cls, cli_kwargs: AppDaemonCLIKwargs):
        cfg = cls.from_config_file(cli_kwargs.configfile)
        cfg.appdaemon.config_dir = cli_kwargs.config

        if cli_kwargs.debug:
            cfg.appdaemon.loglevel = cli_kwargs.debug

        if cli_kwargs.moduledebug:
            cfg.appdaemon.module_debug = cli_kwargs.moduledebug

        return cfg

    @model_validator(mode="before")
    @classmethod
    def validate_ad_cfg(cls, data: Any) -> Any:
        # replace None values with empty dictionaries
        if isinstance(data, dict):
            data = {key: val if val is not None else {} for key, val in data.items()}
        return data
