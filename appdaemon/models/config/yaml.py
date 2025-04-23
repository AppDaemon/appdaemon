from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, model_validator
from typing_extensions import deprecated

from ... import utils
from .appdaemon import AppDaemonConfig
from .dashboard import DashboardConfig
from .http import HTTPConfig
from .log import AppDaemonFullLogConfig
from .misc import AppDaemonCLIKwargs


class MainConfig(BaseModel):
    appdaemon: AppDaemonConfig
    hadashboard: DashboardConfig | None = None
    admin: dict | None = None
    old_admin: dict | None = None
    api: dict | None = None
    http: HTTPConfig | None = None
    logs: AppDaemonFullLogConfig | None = None
    log: Annotated[dict | None, deprecated("'log' directive deprecated, please convert to new 'logs' syntax")] = None

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
