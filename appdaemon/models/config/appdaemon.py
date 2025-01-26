import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Union

import pytz
from pydantic import BaseModel, ConfigDict, Discriminator, Field, RootModel, Tag, field_validator, model_validator
from typing_extensions import deprecated

from ...plugins.hass.config import HASSConfig
from ...plugins.mqtt.config import MQTTConfig
from ...version import __version__
from .misc import FilterConfig, NamespaceConfig


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
    time_zone: Union[pytz.StaticTzInfo, pytz.DstTzInfo]
    plugins: dict[
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

    filters: list[FilterConfig] = []

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
    import_paths: list[Path] = Field(default_factory=list)
    namespaces: dict[str, NamespaceConfig] = Field(default_factory=dict)
    exclude_dirs: list[str] = Field(default_factory=list)
    cert_verify: bool = True
    disable_apps: bool = False

    import_method: Literal["default", "legacy", "expert"] | None = None

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
        extra="allow",
        validate_assignment=True,
    )
    ad_version: str = __version__

    @field_validator("config_dir", mode="after")
    @classmethod
    def convert_to_absolute(cls, v: Path):
        return v.resolve()

    @field_validator("exclude_dirs", mode="after")
    @classmethod
    def add_default_exclusions(cls, v: list[Path]):
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
