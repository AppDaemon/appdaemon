import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import pytz
from pydantic import BaseModel, BeforeValidator, ConfigDict, Discriminator, Field, PlainSerializer, RootModel, SecretStr, Tag, field_validator, model_validator
from pytz.tzinfo import BaseTzInfo
from typing_extensions import deprecated

from appdaemon.version import __version__

from .common import CoercedPath, CoercedRelPath, ParsedTimedelta
from .misc import FilterConfig, NamespaceConfig
from .plugin import HASSConfig, MQTTConfig, PluginConfig


def plugin_discriminator(plugin: dict[str, Any] | PluginConfig) -> Literal["hass", "mqtt", "custom"]:
    """Determine which tag string to use for the plugin config.

    Only built-in plugins like HASS and MQTT use their own config models. Custom plugins will fall back to the generic
    PluginConfig model.
    """
    match plugin:
        case {"type": str(t)} | PluginConfig(type=str(t)):
            match t.lower():
                case ("hass" | "mqtt") as type_:
                    return type_
    return "custom"


DiscriminatedPluginConfig = Annotated[
    Annotated[HASSConfig, Tag("hass")] | Annotated[MQTTConfig, Tag("mqtt")] | Annotated[PluginConfig, Tag("custom")],
    Discriminator(plugin_discriminator),
]


class ModuleLoggingLevels(RootModel):
    root: dict[str, str] = {"_events": "WARNING"}


class AppDaemonConfig(BaseModel, extra="allow"):
    latitude: float
    longitude: float
    elevation: int
    time_zone: Annotated[BaseTzInfo, BeforeValidator(pytz.timezone), PlainSerializer(lambda tz: tz.zone)]
    plugins: dict[str, DiscriminatedPluginConfig] = Field(default_factory=dict)

    config_dir: CoercedPath
    config_file: CoercedPath
    # The CoercedRelPath validator doesn't resolve the relative paths because it will be done relative to wherever
    # AppDaemon is started from, which might not be the config directory.
    app_dir: CoercedRelPath = Path("./apps")
    """Directory to look for apps in, relative to config_dir if not absolute"""

    write_toml: bool = False
    ext: Literal[".yaml", ".toml"] = ".yaml"

    filters: list[FilterConfig] = Field(default_factory=list)

    starttime: datetime | None = None
    endtime: datetime | None = None
    timewarp: float = 1

    loglevel: str = "INFO"
    module_debug: ModuleLoggingLevels = Field(default_factory=ModuleLoggingLevels)

    api_port: int | None = None
    api_key: SecretStr | None = None
    api_ssl_certificate: CoercedPath | None = None
    api_ssl_key: CoercedPath | None = None
    stop_function: Callable | None = None

    utility_delay: ParsedTimedelta = timedelta(seconds=1)
    admin_delay: ParsedTimedelta = timedelta(seconds=1)
    plugin_performance_update: int = 10
    """How often in seconds to update the admin entities with the plugin performance data"""
    max_utility_skew: ParsedTimedelta = timedelta(seconds=2)
    check_app_updates_profile: bool = False
    production_mode: bool = False
    invalid_config_warnings: bool = True
    missing_app_warnings: bool = True
    log_thread_actions: bool = False
    qsize_warning_threshold: int = 50
    qsize_warning_step: int = 60
    qsize_warning_iterations: int = 10
    internal_function_timeout: ParsedTimedelta = timedelta(seconds=60)
    """Timeout for internal function calls. This determines how long apps can wait in their thread for an async function
    to complete in the main thread."""
    use_dictionary_unpacking: Annotated[bool, deprecated("This option is no longer necessary")] = False
    uvloop: bool = False
    use_stream: bool = False
    import_paths: list[Path] = Field(default_factory=list)
    namespaces: dict[str, NamespaceConfig] = Field(default_factory=dict)
    exclude_dirs: list[str] = Field(default_factory=list)
    """List of directory names to exclude when searching for apps. This will always include __pycache__, build, and
    .venv"""
    cert_verify: bool = True
    disable_apps: bool = False
    suppress_log_messages: bool = False
    """Suppresses the log messages based on the result field of the response"""
    discard_init_events: bool = False
    """If True, the thread workers will not do anything with events that arrive while the app is initializing. This can
    be used to prevent race conditions at startup."""
    import_method: Literal["default", "legacy", "expert"] | None = None

    ascii_encode: bool = True
    """Set to false to disable ascii encoding of log messages. This is useful for non-English languages."""

    load_distribution: str = "roundrobbin"
    threads: (
        Annotated[
            int | None,
            deprecated("Threads directive is deprecated apps - will be pinned. Use total_threads if you want to unpin your apps"),
        ]
    ) = None
    total_threads: int | None = None
    """The number of dedicated worker threads to create for running the apps.
    Normally, AppDaemon will create enough threads to provide one per app, or
    default to 10 if app pinning is turned off. Setting this to a specific
    value will turn off automatic thread management."""
    pin_apps: bool = True
    """If ``True``, AppDaemon apps will be each pinned to a particular thread. This avoids complications around
    re-entrant code and locking of instance variables."""
    pin_threads: int | None = None
    """Number of threads to use for pinned apps, allowing the user to section off a sub-pool just for pinned apps. By
    default all threads are used for pinned apps."""
    thread_duration_warning_threshold: float = 10
    threadpool_workers: int = 10
    """Number of threads in AppDaemon's internal thread pool, which can be used to execute functions asynchronously in
    worker threads.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
        validate_assignment=True,
        validate_default=True,
    )
    ad_version: str = __version__

    @model_validator(mode="after")
    def resolve_app_dir(self) -> "AppDaemonConfig":
        if not self.app_dir.is_absolute():
            self.app_dir = (self.config_dir / self.app_dir).resolve()
        return self

    @field_validator("exclude_dirs", mode="after")
    @classmethod
    def add_default_exclusions(cls, v: list[str]) -> list[str]:
        v.extend(["__pycache__", "build", ".venv"])
        return v

    @field_validator("loglevel", mode="before")
    @classmethod
    def convert_loglevel(cls, lvl: str | int) -> str:
        match lvl:
            case int():
                return logging._levelToName[lvl]
            case str():
                lvl = lvl.upper()
                assert lvl in logging._nameToLevel, f"Invalid log level: {lvl}"
                return lvl
            case _:
                raise ValueError(f"Invalid log level: {lvl}")

    @field_validator("plugins", mode="before")
    @classmethod
    def validate_plugins(cls, v: Any):
        # This is needed to set the name field in each plugin config to the name of the key used to define it.
        for n in set(v.keys()):
            v[n]["name"] = n
        return v

    @model_validator(mode="before")
    @classmethod
    def validate_ad_cfg(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if (file := data.get("config_file")) and not data.get("config_dir"):
                data["config_dir"] = Path(file).parent
        return data

    def model_post_init(self, __context: Any):
        # Convert app_dir to Path object
        self.app_dir = Path(self.app_dir) if not isinstance(self.app_dir, Path) else self.app_dir

        # Resolve app_dir relative to config_dir if it's a relative path
        if not self.app_dir.is_absolute():
            self.app_dir = self.config_dir / self.app_dir

        self.ext = ".toml" if self.write_toml else ".yaml"

        if self.total_threads is not None:
            self.pin_apps = False

        if self.pin_threads is not None and self.total_threads is not None:
            # assert self.total_threads is not None, "Using pin_threads requires total_threads to be set."
            assert self.pin_threads <= self.total_threads, (
                "Number of pin threads has to be less than or equal to total threads."
            )
