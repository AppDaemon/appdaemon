import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, tzinfo
from functools import partial
from typing import ClassVar, Literal
from zoneinfo import ZoneInfo

import astral
import pytz
from astral.location import Location

from .types import TimeDeltaLike


def normalize_tz(tz: tzinfo) -> tzinfo:
    """Convert pytz timezone to ZoneInfo for clean stdlib-compatible handling.

    pytz timezones don't behave like normal tzinfo implementations and require
    special localize()/normalize() calls. By converting to ZoneInfo at the boundary,
    we can use standard replace(tzinfo=...) and astimezone() everywhere else.

    Args:
        tz: Any tzinfo object (pytz, ZoneInfo, or fixed-offset)

    Returns:
        ZoneInfo if input was pytz with an IANA zone name, otherwise unchanged
    """
    if isinstance(tz, pytz.tzinfo.BaseTzInfo) and tz.zone is not None:
        return ZoneInfo(tz.zone)
    return tz


def localize_naive(naive_dt: datetime, tz: tzinfo) -> datetime:
    """Interpret a naive datetime as wall-clock time in the given timezone.

    This normalizes pytz timezones to ZoneInfo first, so we can use standard
    replace(tzinfo=...) semantics instead of pytz's localize().

    Args:
        naive_dt: A naive datetime (no tzinfo)
        tz: The timezone to interpret the datetime in

    Returns:
        A timezone-aware datetime

    Raises:
        ValueError: If naive_dt already has tzinfo
    """
    if naive_dt.tzinfo is not None:
        raise ValueError("expected naive datetime")
    tz = normalize_tz(tz)
    return naive_dt.replace(tzinfo=tz)


CONVERTERS = {
    "hour": lambda v: timedelta(hours=v),
    "hr": lambda v: timedelta(hours=v),
    "h": lambda v: timedelta(hours=v),
    "minute": lambda v: timedelta(minutes=v),
    "min": lambda v: timedelta(minutes=v),
    "m": lambda v: timedelta(minutes=v),
    "second": lambda v: timedelta(seconds=v),
    "sec": lambda v: timedelta(seconds=v),
    "s": lambda v: timedelta(seconds=v),
}

NUM_BASE = r"\d+(?:\.\d+)?"

WHITESPACE = r"\s*?"
TIMEDELTA_GROUPS = {
    p: rf"{WHITESPACE}(?P<{p}>{NUM_BASE}){WHITESPACE}"
    for p in ("hours", "minutes", "seconds")
}  # fmt: skip
TD_REGEX = re.compile(
    rf'(?:{TIMEDELTA_GROUPS["hours"]}:)?'
    rf'{TIMEDELTA_GROUPS["minutes"]}:'
    rf'{TIMEDELTA_GROUPS["seconds"]}'
)  # fmt: skip

NUM_REGEX_STR = rf"(?P<num>{NUM_BASE})"
UNITS = "|".join(CONVERTERS.keys())
UNIT_REGEX = rf"(?:\s*?(?P<unit>{UNITS}))"
FULL_REGEX = re.compile(f"{NUM_REGEX_STR}{UNIT_REGEX}?", re.IGNORECASE)

NOW_REGEX = re.compile(
    r"^now(\s*(?P<sign>[-+])\s*(?P<offset>.*?))?$",
    re.IGNORECASE,
)

ELEVATION_REGEX = re.compile(
    rf'(?P<val>-?{NUM_BASE})\s*?(deg\s*?)?(?P<direction>rising|setting)',
    re.IGNORECASE
)

SUN_REGEX = re.compile(
    r"^(?P<sun>(sunrise|sunset))(\s*(?P<sign>[-+])\s*(?P<offset>.*?))?$",
    re.IGNORECASE,
)


@dataclass
class ParsedTimeString(ABC):
    REGEX: ClassVar[re.Pattern]

    @classmethod
    @abstractmethod
    def from_match(cls, m: re.Match) -> "ParsedTimeString": ...

    @classmethod
    def from_str(cls, s: str) -> "ParsedTimeString":
        if m := cls.REGEX.match(s.lower().strip()):
            return cls.from_match(m)
        raise ValueError(f"Invalid sun event string: {s}")

    @abstractmethod
    def resolve_time(self, location: Location, now: datetime, days_offset: int = 0) -> datetime: ...


@dataclass
class ParsedWithOffset(ParsedTimeString):
    event_type: str
    offset: timedelta = field(default_factory=timedelta)

    @property
    def offset_str(self) -> str:
        res = f'{self.event_type}'
        secs = self.offset.total_seconds()
        abs_td = timedelta(seconds=abs(secs))

        if secs == 0:
            pass
        elif secs < 0:
            res += f" - {abs_td}"
        else:
            res += f" + {abs_td}"
        return res

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.offset_str}>"


@dataclass
class ElevationEvent(ParsedTimeString):
    val: float
    direction: astral.SunDirection
    REGEX: ClassVar[re.Pattern] = ELEVATION_REGEX

    def __repr__(self) -> str:
        return f"<ElevationEvent {self.val:.1f}° {self.direction.name.lower()}>"

    @classmethod
    def from_match(cls, m: re.Match) -> "ElevationEvent":
        match m.groupdict():
            case {"direction": ("rising" | "setting") as dir_, "val": val}:
                direction = {
                    "rising": astral.SunDirection.RISING,
                    "setting": astral.SunDirection.SETTING
                }[dir_]
                return cls(direction=direction, val=float(val))
            case _:
                raise ValueError(f"Invalid elevation event match: {m.group()}")

    def resolve_time(self, location: Location, now: datetime, days_offset: int = 0) -> datetime:
        return location.time_at_elevation(
            elevation=self.val,
            date=now.date() + timedelta(days=days_offset),
            direction=self.direction,
            local=True,
        )


@dataclass(repr=False)
class SunEvent(ParsedWithOffset):
    event_type: Literal["sunrise", "sunset"]
    REGEX: ClassVar[re.Pattern] = SUN_REGEX

    @classmethod
    def from_match(cls, m: re.Match) -> "SunEvent":
        match m.groupdict():
            case {"sun": ("sunrise" | "sunset") as event_type, "sign": ("+" | "-") as sign, "offset": str() as offset_str}:
                offset = parse_timedelta(offset_str)
                if sign == "-":
                    offset *= -1
                return cls(event_type=event_type, offset=offset)
            case {"sun": ("sunrise" | "sunset") as event_type}:
                return cls(event_type=event_type)
        raise ValueError(f"Invalid sun event match: {m}")

    def resolve_time(self, location: Location, now: datetime, days_offset: int = 0) -> datetime:
        match self.event_type:
            case "sunrise":
                func = location.sunrise
            case "sunset":
                func = location.sunset
            case _:
                raise TypeError(f'Invalid sun event type: {self.event_type}')
        return func(date=(now + timedelta(days=days_offset)).date(), local=True)


@dataclass(repr=False)
class Now(ParsedWithOffset):
    event_type: Literal["now"] = "now"
    REGEX: ClassVar[re.Pattern] = NOW_REGEX

    @classmethod
    def from_match(cls, m: re.Match) -> "Now":
        match m.groupdict():
            case {"sign": ("+" | "-") as sign, "offset": str() as offset_str}:
                offset = parse_timedelta(offset_str)
                if sign == "-":
                    offset *= -1
                return cls(offset=offset)
            case _:
                return cls()

    def resolve_time(self, now: datetime) -> datetime:
        return now + self.offset


# Defining the time formats up here allows them to be monkey-patched later by users.
TIME_FORMATS = [
    "%I %p",
    "%I:%M %p",
    "%I:%M:%S %p",
    "%H",
    "%H:%M",
    "%H:%M:%S",
    "%H:%M:%S.%f",
]

DATACLASSES: list[type[ParsedTimeString]] = [Now, SunEvent, ElevationEvent]


def parse_timedelta(input_: TimeDeltaLike | None, total: timedelta | None = None) -> timedelta:
    """Convert a variety of inputs, including strings in various formats, to a timedelta object."""
    total = timedelta() if total is None else total

    match input_:
        case timedelta() as td:
            return td + total
        case int() | float():
            return timedelta(seconds=float(input_)) + total
        case None:
            return timedelta() + total
        case str():
            if m := TD_REGEX.match(str(input_)):
                kwargs = {k: float(v.strip()) for k, v in m.groupdict().items() if v is not None}
                return timedelta(**kwargs)
            else:
                total = timedelta() if total is None else total
                for m in FULL_REGEX.finditer(str(input_).lower()):
                    match m.groupdict():
                        case {"num": num, "unit": unit}:
                            val = float(num)
                            if unit is not None and (converter := CONVERTERS.get(unit)):
                                total += converter(val)
                            else:
                                total += timedelta(seconds=val)
            return total


def resolve_time_str(
    time_str: str,
    now: datetime | str,
    location: Location | None = None,
    days_offset: int = 0,
) -> tuple[datetime, timedelta]:
    """Parse a time string into a timezone-aware datetime object along with any time offset it may have.

    Note:
        This function is intended to break out the logic of parsing time strings from the rest of the codebase to make
        it easier to test and maintain.

    Args:
        time_str (str): The time string to parse. Can be in various formats
        now (datetime, str): The current datetime to use as a reference for parsing. This is intended to represent the
            datetime that the call is being made, which affects how times are resolved. Strings will be interpreted as
            ISO 8601 datetime strings, which helps with testing.
        location (Location | None): Location used for sunrise/sunset parsing. Comes from the astral package
        days_offset (int): Number of days to offset from the current date for sunrise/sunset parsing. Defaults to 0.

    Returns:
        tuple[datetime, timedelta]: A tuple containing the parsed time as a datetime object and a timedelta representing
            any offset applied to the time.
    """
    match now:
        case str() as now_str:
            now = datetime.fromisoformat(now_str)

    assert isinstance(now, datetime) and now.tzinfo is not None, "Now must be a timezone-aware datetime"
    assert isinstance(time_str, str), "Input must be a string"

    def _parse(input_string: str) -> ParsedTimeString | time | datetime:
        """Internal function to figure out what kind of time string we're dealing with."""
        if not isinstance(input_string, str):
            raise TypeError("Input must be a string")

        input_string = input_string.strip().lower()
        for cls in DATACLASSES:
            if m := cls.REGEX.match(input_string):
                return cls.from_match(m)

        try:
            return datetime.fromisoformat(input_string)
        except ValueError:
            for fmt in TIME_FORMATS:
                try:
                    return datetime.strptime(input_string, fmt).time()
                except ValueError:
                    continue
            else:
                raise ValueError(f"Invalid time string: {input_string}")

    tz = normalize_tz(now.tzinfo)

    offset = timedelta()
    match _parse(time_str):
        case time() as parsed_time:
            naive_dt = datetime.combine(
                (now + timedelta(days=days_offset)).date(),
                parsed_time,
            )
            result = localize_naive(naive_dt, tz)
        case datetime() as result:
            pass
        case Now(offset=offset):
            result = now
        case SunEvent(offset=offset) as sun_event:
            assert location is not None, "Location must be provided for sun event parsing"
            resolve = partial(sun_event.resolve_time, location, now)
            result = resolve(days_offset=days_offset)
            if result == now:
                # This only happens if it's a sun event being calculated exactly at the current time, which happens during
                # time-travel tests. In this case, we want to force the result to be for the next day.
                result = resolve(days_offset=days_offset + 1)
        case ElevationEvent() as elevation_event:
            assert location is not None, "Location must be provided for elevation parsing"
            result = elevation_event.resolve_time(location, now, days_offset=days_offset)
        case _:
            raise ValueError(f"Invalid time string: {time_str}")

    return result, offset


def parse_datetime(
    input_: str | time | datetime,
    now: datetime | str,
    location: Location | None = None,
    today: bool | None = None,
    offset: TimeDeltaLike | None = None,
    days_offset: int = 0,
    aware: bool = True,
) -> datetime:
    """Parse a variety of inputs into a datetime object.

    Args:
        input_ (str | time | datetime): The input to parse. Can be a string, time, or datetime object.
        now (datetime | str): The current datetime to use as a reference for parsing. This is intended to represent the
            datetime that the call is being made, which affects how times are resolved. Strings will be interpreted as
            ISO 8601 datetime strings, which helps with testing.
        location (Location, optional): Location used for sunrise/sunset parsing. This is needed in order to parse
            sunset/sunrise times from the input.
        today (bool, optional): If `True`, forces the result to have the same date as the `now` datetime. `False` is
            effectively equivalent to `next`. The default value is `None`, which doesn't try to coerce the output at
            all. This results in slightly different date results for different input types. For example, a time string
            will be given the same date as the one in the `now` datetime, but a sun event string will be the datetime
            of the next one.
        offset (timedelta, optional): An optional offset to apply to the resulting datetime. This is separate from the
            offset that may be included in an input string, and the `days_offset` parameter.
        days_offset (int, optional): Number of days to offset from the current date for sunrise/sunset parsing. If this
            is negative, this will unset the `today` argument, which allows the result to be in the past.
        aware (bool, optional): If `False`, the resulting datetime will be naive (without timezone). Defaults to
            `True`.

    Returns:
        datetime: A datetime object representing the parsed time.

    """


    match now:
        case str() as now_str:
            now = datetime.fromisoformat(now_str)

    assert isinstance(now, datetime) and now.tzinfo is not None, "Now must be a timezone-aware datetime"

    tz = normalize_tz(now.tzinfo)

    offset = timedelta()
    match input_:
        case time() as input_time:
            naive_dt = datetime.combine(
                (now + timedelta(days=days_offset)).date(),
                input_time,
            )
            result = localize_naive(naive_dt, tz)
        case datetime() as result:
            result += timedelta(days=days_offset)
        case str() as time_str:
            time_str = time_str.strip().lower()
            # For the sunrise/sunset cases, default to getting the next occurrence if today is not specified
            if time_str.startswith("sun") and today is None:
                today = False  # This forces the result to be in the future
            result, offset = resolve_time_str(
                time_str=time_str,
                now=now,
                location=location,
                days_offset=days_offset,
            )
        case _:
            raise NotImplementedError(f"Unsupported input type: {type(input_)}")

    # Make the timezones match for the comparison below
    if result.tzinfo is None:
        result = localize_naive(result, tz)
    else:
        result = result.astimezone(tz)

    # The the days offset is negative, the result can't be forced to today, so set today to False
    if days_offset < 0:
        today = None  # This allows the result to be in the past

    # Intentionally don't include the false-y case of None here
    if result < (now - offset) and today is False:
        result = parse_datetime(
            input_,
            now=now,
            location=location,
            today=today,
            days_offset=days_offset + 1,
        )
    else:
        result += offset

    if not aware:
        result = result.replace(tzinfo=None)
    return result
