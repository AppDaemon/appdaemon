import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

LEVELS = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class AppDaemonCLIKwargs(BaseModel):
    config: Path
    configfile: Path
    moduledebug: dict[str, LEVELS] = Field(default_factory=dict)
    debug: LEVELS | None = None
    timewarp: float | None = None
    starttime: datetime | None = None
    endtime: datetime | None = None
    profiledash: bool = False
    write_toml: bool = False
    pidfile: Path | None = None

    def print(self):
        print(json.dumps(self.model_dump(mode="json", exclude_defaults=True), indent=4))


class FilterConfig(BaseModel):
    command_line: str
    input_ext: str
    output_ext: str


class NamespaceConfig(BaseModel):
    writeback: Literal["safe", "hybrid"] = "safe"
    persist: bool = Field(default=False, alias="persistent")
