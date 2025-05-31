from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, RootModel

from .common import CoercedPath, LogLevel, TimeType

SYSTEM_LOG_NAME_MAP = {
    "main_log": 'AppDaemon',
    "error_log": 'Error',
    "access_log": 'Access',
    "diag_log": 'Diag',
}


class AppDaemonLogConfig(BaseModel):
    filename: CoercedPath = "STDOUT"
    name: str | None = None
    level: LogLevel = 'INFO'
    log_generations: int = 3
    log_size: int = 1000000
    format_: str = Field(default="{asctime} {levelname} {appname}: {message}", alias="format")
    date_format: str = "%Y-%m-%d %H:%M:%S.%f"
    filter_threshold: int = 1
    filter_timeout: TimeType = timedelta(seconds=0.9)
    filter_repeat_delay: TimeType = timedelta(seconds=5.0)


class AppDaemonFullLogConfig(RootModel):
    root: dict[str, AppDaemonLogConfig] = Field(default_factory=dict)

    def model_post_init(self, context: Any) -> None:
        for log_name, log_config in self.root.items():
            log_config.name = log_config.name or SYSTEM_LOG_NAME_MAP.get(log_name, None)
        if log_config.name is None:
            raise NameError(f"Log name must be specified for user logs: {log_name}")
