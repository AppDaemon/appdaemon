from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, PlainSerializer, ValidationError

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


CoercedPath = Annotated[Path, BeforeValidator(lambda v: Path(v).resolve())]


def validate_timedelta(v: Any):
    match v:
        case str():
            parts = tuple(map(float, v.split(":")))
            match len(parts):
                case 1:
                    return timedelta(seconds=parts[0])
                case 2:
                    return timedelta(minutes=parts[0], seconds=parts[1])
                case 3:
                    return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
                case _:
                    raise ValidationError(f"Invalid timedelta format: {v}")
        case int() | float():
            return timedelta(seconds=v)
        case _:
            raise ValidationError(f"Invalid type for timedelta: {v}")


TimeType = Annotated[timedelta, BeforeValidator(validate_timedelta), PlainSerializer(lambda td: td.total_seconds())]


BoolNum = Annotated[bool, BeforeValidator(lambda v: False if int(v) == 0 else True)]
