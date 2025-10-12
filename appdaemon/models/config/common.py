from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BeforeValidator, PlainSerializer

from appdaemon.utils import parse_timedelta

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

BoolNum = Annotated[bool, BeforeValidator(lambda v: False if int(v) == 0 else True)]
ParsedTimedelta = Annotated[timedelta, BeforeValidator(parse_timedelta), PlainSerializer(lambda td: td.total_seconds())]


CoercedPath = Annotated[Path, BeforeValidator(lambda p: Path(p).resolve())]
CoercedRelPath = Annotated[Path, BeforeValidator(lambda p: Path(p))]
LogPath = Annotated[Literal["STDOUT", "STDERR"], BeforeValidator(lambda s: s.upper())] | CoercedPath
