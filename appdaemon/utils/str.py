
from datetime import datetime, timedelta, tzinfo
from time import perf_counter
from typing import Literal

import dateutil

from appdaemon.types import TimeDeltaLike

from .parse import parse_timedelta


def time_str(start: float, now: float | None = None) -> str:
    return format_timedelta((now or perf_counter()) - start)


def format_seconds(secs: TimeDeltaLike) -> str:
    return str(parse_timedelta(secs))


def format_timedelta(td: TimeDeltaLike | None) -> str:
    """Format a timedelta object into a human-readable string.

    There are different brackets for lengths of time that will format the strings differently.

    Uses ``parse_timedelta`` to convert the input into a timedelta object before formatting the string.

    Examples:
        >>> format_timedelta(0.025374)
        '25.374ms'

        >>> format_timedelta(0.687)
        '687ms'

        >>> format_timedelta(2.5)
        '2.5s'

        >>> format_timedelta(25)
        '25s'

        >>> format_timedelta(None)
        'never'

        >>> format_timedelta(0)
        'No time'

    """
    match td:
        case None:
            return "never"
        case _:
            td = parse_timedelta(td)
            seconds = td.total_seconds()
            if seconds == 0:
                return "No time"
            elif seconds < 0.1:
                return f"{seconds * 10**3:.3f}ms"
            elif seconds < 1:
                return f"{seconds * 10**3:.0f}ms"
            elif seconds < 25:
                return f"{seconds:.1f}s"
            else:
                td = timedelta(seconds=round(seconds, 0))  # Round off the seconds for longer durations
                res = str(td)
                hours = int(seconds / 3600)
                if hours == 0:  # Remove the hours portion if it's 0
                    res = res.split(":", 1)[1]
                return res


def str_to_dt(time):
    if time == "never":
        return time
    return dateutil.parser.parse(time)


def dt_to_str(dt: datetime, tz: tzinfo | None = None, *, round: bool = False) -> str | Literal["never"]:
    """Convert a datetime object to a string.

    This function provides a single place for standardizing the conversion of datetimes to strings.

    Args:
        dt (datetime): The datetime object to convert.
        tz (tzinfo, optional): Optional timezone to apply. Defaults to None.
        round (bool, optional): Whether to round the datetime to the nearest second. Defaults to False.
    """
    if round:
        dt = dt.replace(microsecond=0)

    if dt == datetime(1970, 1, 1, 0, 0, 0, 0):
        return "never"
    else:
        if tz is not None:
            return dt.astimezone(tz).isoformat()
        else:
            return dt.isoformat()
