import itertools
from datetime import datetime, timedelta
from typing import Any

import pytest
from appdaemon import parse
from astral.location import Location

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


TIMEDELTA_CASES = {
    1: timedelta(seconds=1),
    10: timedelta(seconds=10),
    "1.234567": timedelta(seconds=1, microseconds=234567),
    "05:00": timedelta(minutes=5),
    "   1.2   :   3.7    ": timedelta(minutes=1.2, seconds=3.7),
    "1.5:00:00": timedelta(hours=1, minutes=30),
    "1.2:3.4:5.6": timedelta(hours=1.2, minutes=3.4, seconds=5.6),
    "3s": timedelta(seconds=3),
    "2m 3s": timedelta(minutes=2, seconds=3),
    "1h 2 min 3seconds": timedelta(hours=1, minutes=2, seconds=3),
    "15": timedelta(seconds=15),
    "01:30:00": timedelta(hours=1, minutes=30),
    "02:90:00": timedelta(hours=2, minutes=90),
    "2.5:00": timedelta(minutes=2.5),
    "10.5seconds, 90 min": timedelta(hours=1, minutes=30, seconds=10.5),
    "2.5hr": timedelta(hours=2, minutes=30),
    "asdf": timedelta(),
    None: timedelta(),
}


@pytest.mark.parametrize("val", TIMEDELTA_CASES.keys())
def test_parse_timedelta(val: Any) -> None:
    assert parse.parse_timedelta(val) == TIMEDELTA_CASES[val]


# SUN_EVENT_CASES = {
#     "sunrise + 30    mins": parse.SunEvent("sunrise", timedelta(minutes=30)),
#     "sunset - 45:00  ": parse.SunEvent("sunset", timedelta(minutes=-45)),
#     "   sunset-2hr": parse.SunEvent("sunset", timedelta(hours=-2))
# }

# @pytest.mark.parametrize("input_string", SUN_EVENT_CASES.keys())
# def test_parse_sun_event(input_string: str) -> None:
#     assert parse._parse(input_string) == SUN_EVENT_CASES[input_string]


DATETIME_PARAMS = {
    "val": ["now", "now + 05:00", "sunrise-1hr", "sunset + 30mins", "16:20:00", "3:30 am"],
    "now": ["2025-06-20T04:00:00-04:00", "2025-06-20T12:00:00-04:00", "2025-06-20T23:00:00-04:00"],
}

DATETIME_CASES = {
    ("now", "2025-06-20T04:00:00-04:00"): ("2025-06-20T04:00:00-04:00", timedelta()),
    ("sunrise-1hr", "2025-06-20T04:00:00-04:00"): ("2025-06-20T05:25:07.925165-04:00", timedelta(hours=-1)),
    ("sunrise-1hr", "2025-06-20T12:00:00-04:00"): ("2025-06-20T05:25:07.925165-04:00", timedelta(hours=-1)),
    ("sunrise-1hr", "2025-06-20T23:00:00-04:00"): ("2025-06-20T05:25:07.925165-04:00", timedelta(hours=-1)),
    ("sunset + 30mins", "2025-06-20T23:00:00-04:00"): ("2025-06-20T20:30:19.662056-04:00", timedelta(minutes=30)),
    ("16:20:00", "2025-06-20T04:00:00-04:00"): ("2025-06-20T16:20:00-04:00", timedelta()),
    ("16:20:00", "2025-06-20T12:00:00-04:00"): ("2025-06-20T16:20:00-04:00", timedelta()),
    ("16:20:00", "2025-06-20T23:00:00-04:00"): ("2025-06-20T16:20:00-04:00", timedelta()),
}


OFFSETS = ["", "-1hr", " + 30 mins"]
NOW_PARAMS = {"val": [f"now{offset}" for offset in OFFSETS], "now_str": ["2025-06-20T12:00:00-04:00"]}

NOW_CASES = {
    ("now", "2025-06-20T12:00:00-04:00"): ("2025-06-20T12:00:00-04:00", timedelta()),
    ("now-1hr", "2025-06-20T12:00:00-04:00"): ("2025-06-20T12:00:00-04:00", timedelta(hours=-1)),
    ("now + 30 mins", "2025-06-20T12:00:00-04:00"): ("2025-06-20T12:00:00-04:00", timedelta(minutes=30)),
}

SUN_OFFSET_PARAMS = {"val": [f"{b}{offset}" for b, offset in itertools.product(["sunrise", "sunset"], OFFSETS)], "now_str": ["2025-06-20T12:00:00-04:00"]}

SUN_OFFSET_CASES = {
    ("sunrise", "2025-06-20T12:00:00-04:00"): ("2025-06-20T05:25:07.925165-04:00", timedelta()),
    ("sunrise-1hr", "2025-06-20T12:00:00-04:00"): ("2025-06-20T05:25:07.925165-04:00", timedelta(hours=-1)),
    ("sunrise + 30 mins", "2025-06-20T12:00:00-04:00"): ("2025-06-20T05:25:07.925165-04:00", timedelta(minutes=30)),
    ("sunset", "2025-06-20T12:00:00-04:00"): ("2025-06-20T20:30:19.662056-04:00", timedelta()),
    ("sunset-1hr", "2025-06-20T12:00:00-04:00"): ("2025-06-20T20:30:19.662056-04:00", timedelta(hours=-1)),
    ("sunset + 30 mins", "2025-06-20T12:00:00-04:00"): ("2025-06-20T20:30:19.662056-04:00", timedelta(minutes=30)),
}


SUNRISE_PARAMS = {
    "val": ["sunrise"],
    "now_str": ["2025-06-20T04:00:00-04:00", "2025-06-20T12:00:00-04:00"],
    "today": [None, True, False],
}

SUNSET_PARAMS = {
    "val": ["sunset"],
    "now_str": ["2025-06-20T12:00:00-04:00", "2025-06-20T23:00:00-04:00"],
    "today": [None, True, False],
}

SUN_NEXT_CASES = {
    # Calling before sunrise with various today settings
    ("sunrise", "2025-06-20T04:00:00-04:00", None): "2025-06-20T05:25:07.925165-04:00",
    ("sunrise", "2025-06-20T04:00:00-04:00", True): "2025-06-20T05:25:07.925165-04:00",
    ("sunrise", "2025-06-20T04:00:00-04:00", False): "2025-06-20T05:25:07.925165-04:00",
    # Calling after sunrise with various today settings
    ("sunrise", "2025-06-20T12:00:00-04:00", None): "2025-06-21T05:25:20.585440-04:00",
    ("sunrise", "2025-06-20T12:00:00-04:00", True): "2025-06-20T05:25:07.925165-04:00",
    ("sunrise", "2025-06-20T12:00:00-04:00", False): "2025-06-21T05:25:20.585440-04:00",
    # Calling before sunset with various today settings
    ("sunset", "2025-06-20T12:00:00-04:00", None): "2025-06-20T20:30:19.662056-04:00",
    ("sunset", "2025-06-20T12:00:00-04:00", True): "2025-06-20T20:30:19.662056-04:00",
    ("sunset", "2025-06-20T12:00:00-04:00", False): "2025-06-20T20:30:19.662056-04:00",
    # Calling after sunset with various today settings
    ("sunset", "2025-06-20T23:00:00-04:00", None): "2025-06-21T20:30:31.933561-04:00",
    ("sunset", "2025-06-20T23:00:00-04:00", True): "2025-06-20T20:30:19.662056-04:00",
    ("sunset", "2025-06-20T23:00:00-04:00", False): "2025-06-21T20:30:31.933561-04:00",
}

SUNRISE_DAY_OFFSET_PARAMS = {
    "val": ["sunrise"],
    "now_str": ["2025-06-20T12:00:00-04:00"],
    "days_offset": [-10, -1, 1, 10],
}


def parametrize(params: dict[str, list[Any]]) -> Any:
    return pytest.mark.parametrize(list(params.keys()), itertools.product(*params.values()))


class TestParseDatetime:
    @parametrize(NOW_PARAMS)
    def test_parse_now_offset(self, val: str, now_str: str) -> None:
        parsed_dt, parsed_td = parse.resolve_time_str(val, now_str)

        correct_dt_str, correct_td = NOW_CASES.get((val, now_str), (None, None))
        assert parsed_dt.isoformat() == correct_dt_str, f"Parsed datetime {parsed_dt} does not match expected {correct_dt_str}"
        assert parsed_td == correct_td, f"Parsed timedelta {parsed_td} does not match expected {correct_td}"


class TestParseSunTimes:
    @parametrize(SUN_OFFSET_PARAMS)
    def test_parse_sun_offset(self, val: str, now_str: str, location: Location) -> None:
        parsed_dt, parsed_td = parse.resolve_time_str(val, now_str, location=location)

        correct_dt_str, correct_td = SUN_OFFSET_CASES.get((val, now_str), (None, None))
        assert parsed_dt.isoformat() == correct_dt_str, f"Parsed datetime {parsed_dt} does not match expected {correct_dt_str}"
        assert parsed_td == correct_td, f"Parsed timedelta {parsed_td} does not match expected {correct_td}"

    @parametrize(SUNRISE_PARAMS)
    def test_next_sunrise(self, val: str, now_str: str, today: bool | None, location: Location) -> None:
        """Tests whether the today argument works correctly around sunrises."""
        result = parse.parse_datetime(val, now_str, location=location, today=today)
        correct = SUN_NEXT_CASES.get((val, now_str, today), None)
        assert result.isoformat() == correct, f"Incorrect result: {result}"

    @parametrize(SUNSET_PARAMS)
    def test_next_sunset(self, val: str, now_str: str, today: bool | None, location: Location) -> None:
        """Tests whether the today argument works correctly around sunsets."""
        result = parse.parse_datetime(val, now_str, location=location, today=today)
        correct = SUN_NEXT_CASES.get((val, now_str, today), None)
        assert result.isoformat() == correct, f"Incorrect result: {result}"

    @parametrize(SUNRISE_DAY_OFFSET_PARAMS)
    def test_sunrise_days_offset(self, val: str, now_str: str, days_offset: int, location: Location) -> None:
        parse.parse_datetime(val, now_str, location=location, days_offset=days_offset)
        return


# @parametrize(DATETIME_PARAMS)
@pytest.mark.parametrize(list(DATETIME_PARAMS.keys()), DATETIME_CASES.keys())
def test_parse_datetime(val: str, now: str, location: Location) -> None:
    now_dt = datetime.fromisoformat(now)
    correct = DATETIME_CASES.get((val, now), None)
    # if correct is None:
    #     return

    assert correct is not None, f"No test case for {val} with {now}"
    correct_dt, correct_td = correct
    match correct_dt:
        case str() as correct_dt_str:
            correct_dt = datetime.fromisoformat(correct_dt_str)
        case datetime():
            correct_dt = correct_dt
        case _:
            assert False, f"Unexpected type for correct_dt: {type(correct_dt)}"

    parsed_dt, parsed_td = parse.resolve_time_str(val, now_dt, location)

    assert isinstance(parsed_dt, datetime), f"Parsed datetime is not a datetime object for {val} with {now}"
    assert isinstance(parsed_td, timedelta), f"Parsed timedelta is not a timedelta object for {val} with {now}"

    assert parsed_dt == correct_dt, f"Incorrect datetime for {val} with {now}"
    assert correct_td == parsed_td, f"Incorrect offset timedelta for {val} with {now}"
