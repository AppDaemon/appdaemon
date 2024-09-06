import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Union

import pytz
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pytz.tzinfo import DstTzInfo, StaticTzInfo
from typing_extensions import deprecated

from appdaemon.version import __version__


class PluginConfig(BaseModel, extra="allow"):
    type: str
    persist_entities: bool = False
    namespace: str = "default"


class FilterConfig(BaseModel):
    command_line: str
    input_ext: str
    output_ext: str


class NamespaceConfig(BaseModel):
    writeback: Literal["safe", "hybrid"] = "safe"
    persist: bool = False


class AppDaemonConfig(BaseModel, extra="forbid"):
    latitude: float
    longitude: float
    elevation: int
    time_zone: Union[StaticTzInfo, DstTzInfo]
    plugins: Dict[str, PluginConfig] = Field(default_factory=dict)

    config_dir: Path
    config_file: Path
    app_dir: Path = "./apps"

    use_toml: bool = False
    ext: Literal[".yaml", ".toml"] = ".yaml"

    module_debug: Dict = {}
    filters: List[FilterConfig] = []

    starttime: Optional[datetime] = None
    endtime: Optional[datetime] = None
    timewarp: float = 1
    max_clock_skew: int = 1

    loglevel: str = "INFO"
    module_debug: Dict[str, str] = {}

    api_port: Optional[int] = None
    stop_function: Optional[Callable] = None

    utility_delay: int = 1
    admin_delay: int = 1
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
    use_dictionary_unpacking: bool = False
    uvloop: bool = False
    use_stream: bool = False
    import_paths: List[Path] = []
    namespaces: Dict[str, NamespaceConfig] = {}
    exclude_dirs: List[str] = []
    cert_verify: bool = True
    disable_apps: bool = False

    module_debug: Dict[str, str] = {}
    pin_apps: Optional[bool] = None

    load_distribution: str = "roundrobbin"
    threads: Optional[
        Annotated[
            int,
            deprecated(
                "Threads directive is deprecated apps - will be pinned. Use total_threads if you want to unpin your apps"
            ),
        ]
    ] = None
    total_threads: Optional[int] = None
    pin_threads: Optional[int] = None
    thread_duration_warning_threshold: float = 10
    threadpool_workers: int = 10

    model_config = ConfigDict(arbitrary_types_allowed=True)
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

    def model_post_init(self, __context: Any):
        # Convert app_dir to Path object
        self.app_dir = Path(self.app_dir) if not isinstance(self.app_dir, Path) else self.app_dir

        # Resolve app_dir relative to config_dir if it's a relative path
        if not self.app_dir.is_absolute():
            self.app_dir = self.config_dir / self.app_dir

        self.ext = ".toml" if self.use_toml else ".yaml"
