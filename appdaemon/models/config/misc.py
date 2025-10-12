import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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
    writeback: Literal["safe", "hybrid"] | None = None
    persist: bool = Field(default=False, alias="persistent")

    @model_validator(mode="before")
    @classmethod
    def validate_persistence(cls, values: Any):
        """Sets persistence to True if writeback is set to safe or hybrid."""
        match values:
            case {"writeback": wb} if wb is not None:
                values["persistent"] = True
            case _ if getattr(values, "writeback", None) is not None:
                values.persistent = True
        return values

    @model_validator(mode="after")
    def validate_writeback(self):
        """Makes the writeback safe by default if persist is set to True."""
        if self.persist and self.writeback is None:
            self.writeback = "safe"
        return self
