import functools
from datetime import datetime, time, timedelta

from astral.location import Location
from pytz.tzinfo import BaseTzInfo

from .parse import parse_datetime

# Maximum allowed offset for sun events (sunrise/sunset repeat daily)
SUN_EVENT_INTERVAL = timedelta(days=1)



def now_is_between(
    now: datetime,
    start_time: str | time | datetime,
    end_time: str | time | datetime,
    location: Location | None = None,
) -> bool:
    assert now.tzinfo is not None, "Now must be a timezone-aware datetime"
    parse = functools.partial(
        parse_datetime,
        now=now,
        location=location,
        today=True,
    )

    aware_start = parse(start_time)
    aware_end = parse(end_time)

    if aware_start > aware_end and (now < aware_start or now < aware_end):
        aware_start = parse(start_time, days_offset=-1)
        if aware_start > aware_end:
            aware_start -= timedelta(days=1)

    if aware_start > aware_end and now > aware_start and now > aware_end:
        aware_end = parse(end_time, days_offset=1)
        if aware_start > aware_end:
            aware_end += timedelta(days=1)

    return aware_start <= now <= aware_end


def ensure_timezone(input_: datetime, timezone: BaseTzInfo | None) -> datetime:
    if timezone is not None:
        if input_.tzinfo is None:
            result = timezone.localize(input_)
        else:
            result = input_.astimezone(timezone)
    else:
        result = input_

    assert result.tzinfo is not None, "Resulting datetime must be timezone-aware"
    return result


def day_of_week(day):
    nums = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    days = {day: idx for idx, day in enumerate(nums)}

    if isinstance(day, str):
        return days[day]
    if isinstance(day, int):
        return nums[day]
    raise ValueError("Incorrect type for 'day' in day_of_week()'")
