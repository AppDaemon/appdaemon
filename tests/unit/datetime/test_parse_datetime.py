import itertools
from datetime import date, datetime, timedelta
from functools import partial
from typing import Literal

import appdaemon.parse
import pytest
import pytz
from appdaemon.exceptions import OffsetExceedsIntervalError
from appdaemon.parse import resolve_time_str
from appdaemon.utils import SUN_EVENT_INTERVAL, validate_offset_within_interval
from astral import SunDirection
from astral.location import Location
from pytz import BaseTzInfo

from .utils import ParameterBuilder

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


class TestParseDatetime:
    @pytest.mark.parametrize(*ParameterBuilder.hour_params())
    def test_parse_hour(
        self,
        input_: str,
        aware: bool,
        today: bool,
        default_now: datetime,
        parser: partial[datetime],
    ) -> None:
        result = parser(input_, aware=aware, today=today)
        if default_now.time() > result.time():
            if not today:
                assert result.date() == (default_now + timedelta(days=1)).date()
                return

        assert result.date() == default_now.date()

    @pytest.mark.parametrize(
        ("input_", "aware", "today"),
        itertools.product(
            ["2025-10-25 13:51:42"],
            (True, False),
            (True, False),
        ),
    )
    def test_parse_datetime(
        self,
        input_: str,
        aware: bool,
        today: bool,
        parser: partial[datetime],
    ) -> None:
        try:
            result = parser(input_, aware=aware, today=today)
        except Exception as e:
            assert False, f"Parsing failed: {e}"
        else:
            correct = datetime(2025, 10, 25, 13, 51, 42)
            if aware:
                correct = pytz.timezone("America/New_York").localize(correct)
            assert result == correct

    @pytest.mark.parametrize(*ParameterBuilder.sun_params())
    def test_parse_sun_offsets(
        self,
        now_str: str,
        input_: str,
        when: Literal["today", "next"],
        default_now: datetime,
        location: Location,
        parser: partial[datetime],
    ) -> None:
        today_sunrise = location.sunrise(date=default_now.date(), local=True)
        assert today_sunrise.isoformat() == "2025-06-20T05:25:07.925165-04:00"

        tomorrow_sunrise = location.sunrise(date=(default_now + timedelta(days=1)).date(), local=True)
        assert tomorrow_sunrise.isoformat() == "2025-06-21T05:25:20.585440-04:00"

        today_sunset = location.sunset(date=default_now.date(), local=True)
        assert today_sunset.isoformat() == "2025-06-20T20:30:19.662056-04:00"

        tomorrow_sunset = location.sunset(date=(default_now + timedelta(days=1)).date(), local=True)
        assert tomorrow_sunset.isoformat() == "2025-06-21T20:30:31.933561-04:00"

        match now_str:
            case "early":
                now = default_now.replace(hour=3)
            case "midday":
                now = default_now.replace(hour=12)
            case "late":
                now = default_now.replace(hour=23)

        parser.keywords["now"] = now

        if when == "today":
            parser.keywords["today"] = True

        result = parser(input_, location=location, aware=True)
        assert result.tzinfo is not None

        type_ = input_.split()[0]
        _, offset = resolve_time_str(input_, now=now, location=location)

        match now_str, when, type_:
            case (_, "today", "sunrise"):
                assert result == (today_sunrise + offset)
            case (_, "today", "sunset"):
                assert result == (today_sunset + offset)

            case ("early", _, "sunrise"):
                assert result == (today_sunrise + offset)
            case ("midday" | "late", _, "sunrise"):
                assert result == (tomorrow_sunrise + offset)

            case ("early" | "midday", _, "sunset"):
                assert result == (today_sunset + offset)
            case ("late", "next", "sunset"):
                assert result == (tomorrow_sunset + offset)

            case _:
                # This makes sure all the cases get handled.
                assert False

        match when:
            case "today":
                assert result.date() == now.date()
            case "next":
                assert result > now


def test_time_parse(default_now: datetime, parser: partial[datetime]) -> None:
    test_time = default_now.replace(hour=20)
    assert parser("20:00:00") == test_time
    assert parser("20:00") == test_time
    assert parser("20") == test_time

    # assert parser("20:00 + 01") == (test_time + timedelta(seconds=1))
    # assert parser("20:00 + 2.5") == (test_time + timedelta(seconds=2.5))
    # assert parser("20:00 + 01:00") == (test_time + timedelta(minutes=1))
    # assert parser("20:00 + 01:00:00") == (test_time + timedelta(hours=1))
    # assert parser("20:00 + 01:00:00", offset=timedelta(hours=1)) == (test_time + timedelta(hours=2))

    # assert parser("20:00 - 01") == (test_time - timedelta(seconds=1))
    # assert parser("20:00 - 2.5") == (test_time - timedelta(seconds=2.5))
    # assert parser("20:00 - 01:00") == (test_time - timedelta(minutes=1))
    # assert parser("20:00 - 01:00:00") == (test_time - timedelta(hours=1))
    # assert parser("20:00 - 01:00:00", offset=-12) == (test_time - timedelta(hours=1, seconds=12))

    assert parser("2025-06-20T20:00:00-04:00") == test_time


def test_sunrise(default_now: datetime, parser: partial[datetime], location: Location) -> None:
    parser = partial(parser, location=location)
    correct_sunrise = location.sunrise(date=(default_now + timedelta(days=1)).date(), local=True)
    assert correct_sunrise.isoformat() == "2025-06-21T05:25:20.585440-04:00"
    assert parser("sunrise") == correct_sunrise

    # Negative offsets
    assert parser("sunrise - 01:00:00") == (correct_sunrise - timedelta(hours=1))
    assert parser("sunrise - 01:00") == (correct_sunrise - timedelta(minutes=1))
    assert parser("sunrise - 01") == (correct_sunrise - timedelta(seconds=1))
    assert parser("sunrise - 2.5") == (correct_sunrise - timedelta(seconds=2.5))

    # Positive offsets
    assert parser("sunrise + 01:00:00") == (correct_sunrise + timedelta(hours=1))
    assert parser("sunrise + 01:00") == (correct_sunrise + timedelta(minutes=1))
    assert parser("sunrise + 01") == (correct_sunrise + timedelta(seconds=1))
    assert parser("sunrise + 2.5") == (correct_sunrise + timedelta(seconds=2.5))

    # Today
    parse_func_today = partial(parser, today=True)
    correct_sunrise = location.sunrise(date=default_now.date(), local=True)
    assert parse_func_today("sunrise") == correct_sunrise
    assert parse_func_today("sunrise - 01:00:00") == (correct_sunrise - timedelta(hours=1))
    assert parse_func_today("sunrise + 01:00:00") == (correct_sunrise + timedelta(hours=1))

    # Aware vs naive datetime
    assert parser("sunrise", aware=False).tzinfo is None
    assert parser("sunrise", aware=True).tzinfo is not None
    assert parser("sunrise").tzinfo is not None

    def check_days_offset(days: int) -> None:
        def offset_sunrise(days: int) -> datetime:
            return location.sunrise(date=(default_now + timedelta(days=days)).date(), local=True)

        assert parser("sunrise", days_offset=days) == offset_sunrise(days)

    # Check small/big and positive/negative days offset
    for i in [10, 1, -1, -10]:
        check_days_offset(i)


def test_sunset(default_now: datetime, parser: partial[datetime], location: Location) -> None:
    parser = partial(parser, location=location)
    correct_sunset = location.sunset(date=default_now.date(), local=True)
    assert parser("sunset") == correct_sunset

    # Negative offsets
    assert parser("sunset - 01:00:00") == (correct_sunset - timedelta(hours=1))
    assert parser("sunset - 01:00") == (correct_sunset - timedelta(minutes=1))
    assert parser("sunset - 01") == (correct_sunset - timedelta(seconds=1))
    assert parser("sunset - 2.5") == (correct_sunset - timedelta(seconds=2.5))

    # Positive offsets
    assert parser("sunset + 01:00:00") == (correct_sunset + timedelta(hours=1))
    assert parser("sunset + 01:00") == (correct_sunset + timedelta(minutes=1))
    assert parser("sunset + 01") == (correct_sunset + timedelta(seconds=1))
    assert parser("sunset + 2.5") == (correct_sunset + timedelta(seconds=2.5))

    # Running the same functions with the today option should have the same result
    parse_func_today = partial(parser, today=True)
    assert parse_func_today("sunset") == correct_sunset
    assert parse_func_today("sunset + 01:00:00") == (correct_sunset + timedelta(hours=1))
    assert parse_func_today("sunset - 01:00:00") == (correct_sunset - timedelta(hours=1))

    # Aware vs naive datetime
    assert parser("sunset", aware=False).tzinfo is None
    assert parser("sunset", aware=True).tzinfo is not None
    assert parser("sunset").tzinfo is not None

    def check_days_offset(days: int) -> None:
        def offset_sunset(days: int) -> datetime:
            return location.sunset(date=(default_now + timedelta(days=days)).date(), local=True)

        assert parser("sunset", days_offset=days) == offset_sunset(days)

    # Check small/big and positive/negative days offset
    for i in [-10, -1, 1, 10]:
        check_days_offset(i)


def test_next_sunrise(
    parser_location: partial[datetime],
    default_date: date,
    tomorrow_date: date,
    early_now: datetime,  # Before sunrise
    default_now: datetime,  # After sunrise
    late_now: datetime,  # After sunrise
) -> None:
    """This test demonstrates the behavior of the ``today`` parameter of parse_datetime.

    The default is None, which means that the function will return the next sunrise
    """
    default_sunrise = partial(parser_location, "sunrise")
    todays_sunrise = partial(default_sunrise, today=True)
    next_sunrise = partial(default_sunrise, today=False)

    # The early time is before sunrise, so both today and next are on today's date
    assert todays_sunrise(early_now).date() == default_date
    assert next_sunrise(early_now).date() == default_date
    assert default_sunrise(early_now).date() == default_date

    # The default time is after sunrise, so the next one is tomorrow
    assert todays_sunrise(default_now).date() == default_date
    assert next_sunrise(default_now).date() == tomorrow_date
    assert default_sunrise(default_now).date() == tomorrow_date

    # The late time is after sunrise, so the next one is tomorrow
    assert todays_sunrise(late_now).date() == default_date
    assert next_sunrise(late_now).date() == tomorrow_date
    assert default_sunrise(late_now).date() == tomorrow_date


def test_next_sunset(
    parser_location: partial[datetime],
    default_date: date,
    tomorrow_date: date,
    early_now: datetime,  # Before sunset
    default_now: datetime,  # Before sunset
    late_now: datetime,  # After sunset
) -> None:
    """This test demonstrates the behavior of the ``today`` parameter of parse_datetime.

    The default is None, which means that the function will return the next sunrise
    """
    default_sunset = partial(parser_location, "sunset")
    todays_sunset = partial(default_sunset, today=True)
    next_sunset = partial(default_sunset, today=False)

    # The early time is before sunset, so both today and next are on today's date
    assert todays_sunset(early_now).date() == default_date
    assert next_sunset(early_now).date() == default_date
    assert default_sunset(early_now).date() == default_date

    # The default time is before sunset, so both today and next are on today's date
    assert todays_sunset(default_now).date() == default_date
    assert next_sunset(default_now).date() == default_date
    assert default_sunset(default_now).date() == default_date

    # The late time is after sunset, so the next one is tomorrow
    assert todays_sunset(late_now).date() == default_date
    assert next_sunset(late_now).date() == tomorrow_date
    assert default_sunset(late_now).date() == tomorrow_date


def test_elevation_rising(parser: partial[datetime], time_at_elevation: partial[datetime], location: Location) -> None:
    parser = partial(parser, location=location)
    rising_func = partial(time_at_elevation, direction=SunDirection.RISING)

    assert parser("   37    deg     rising   ") == rising_func(elevation=37)
    assert parser("15 deg rising") == rising_func(elevation=15)
    assert parser("8.7 deg rising") == rising_func(elevation=8.7)
    # assert parser("23.5 deg rising + 01:00:00") == (rising_func(elevation=23.5) + timedelta(hours=1))
    # assert parser("17.34234 deg rising - 01:05:23.5") == (rising_func(elevation=17.34234) - timedelta(hours=1, minutes=5, seconds=23.5))


def test_elevation_setting(parser: partial[datetime], time_at_elevation: partial[datetime], location: Location) -> None:
    parser = partial(parser, location=location)
    setting_func = partial(time_at_elevation, direction=SunDirection.SETTING)

    assert parser("15 deg setting") == setting_func(elevation=15)
    assert parser("15 deg setting") == setting_func(elevation=15)
    assert parser("8.7 deg setting") == setting_func(elevation=8.7)
    # assert parser("23.5 deg setting + 01:00:00") == (setting_func(elevation=23.5) + timedelta(hours=1))
    # assert parser("17.34234 deg setting - 01:05:23.5") == (setting_func(elevation=17.34234) - timedelta(hours=1, minutes=5, seconds=23.5))


def test_exact_sun_event(default_date: date, location: Location, tz: BaseTzInfo) -> None:
    """Test the exact sunrise/sunset event parsing."""
    parser = partial(appdaemon.parse.parse_datetime, location=location, today=False)
    today_sunrise = location.sunrise(date=default_date, local=True)
    next_sunrise = parser("sunrise", now=today_sunrise)
    assert next_sunrise.date() != default_date, "Next sunrise should be tomorrow"

    today_sunset = location.sunset(date=default_date, local=True)
    next_sunset = parser("sunset", now=today_sunset)
    assert next_sunset.date() != default_date, "Next sunset should be tomorrow"
    assert next_sunset.date() != default_date, "Next sunset should be tomorrow"
    assert next_sunset.date() != default_date, "Next sunset should be tomorrow"


def test_run_at_time_in_past(default_now: datetime, default_date: date, tomorrow_date: date, parser: partial[datetime]) -> None:
    """Test that run_at schedules for next day when time is in the past.

    This test reproduces the bug reported in issue #2491 where run_at() with a time
    in the past runs immediately instead of scheduling for the next day.

    The fix is to have run_at() explicitly pass today=False to parse_datetime,
    which forces times in the past to be scheduled for tomorrow.
    """
    from datetime import time

    # Current time is 12:00 (default_now is 12:00:00)
    # Test with a time object that's 1 hour in the past (11:00)
    past_time = time(11, 0, 0)
    # run_at should call parse_datetime with today=False
    result = parser(past_time, today=False)

    # Since the time is in the past and today=False (behavior for run_at),
    # it should be scheduled for tomorrow
    assert result.date() == tomorrow_date, f"Expected {tomorrow_date}, got {result.date()}"
    assert result.time() == past_time

    # Test with a time string that's in the past
    result_str = parser("11:00:00", today=False)
    assert result_str.date() == tomorrow_date, f"Expected {tomorrow_date}, got {result_str.date()}"

    # Test with a time that's in the future (should be today)
    future_time = time(13, 0, 0)
    result_future = parser(future_time, today=False)
    assert result_future.date() == default_date, f"Expected {default_date}, got {result_future.date()}"
    assert result_future.time() == future_time

    # Test with today=True explicitly (should be today even if in the past)
    result_today = parser(past_time, today=True)
    assert result_today.date() == default_date
    assert result_today.time() == past_time

    # Test with today=None (default for elevation events - should be today even if past)
    result_none = parser(past_time, today=None)
    assert result_none.date() == default_date
    assert result_none.time() == past_time


class TestOffsetValidation:
    """Tests for validate_offset_within_interval"""

    def test_valid_offset_within_interval(self) -> None:
        """Offset smaller than interval should pass"""
        # 1 hour offset with 24 hour interval - should not raise
        offset = timedelta(hours=1)
        validate_offset_within_interval(offset, timedelta(days=1), "daily")

    def test_valid_offset_with_random_within_interval(self) -> None:
        """Offset + random range smaller than interval should pass"""
        # 1 hour offset with random range of -30min to +30min
        # Max possible offset = 1h + 30m = 1.5h, which is < 1 day
        offset = timedelta(hours=1)
        validate_offset_within_interval(
            offset, SUN_EVENT_INTERVAL, "sunset",
            random_start=timedelta(minutes=-30), random_end=timedelta(minutes=30)
        )

    def test_offset_exceeds_interval_raises(self) -> None:
        """Offset larger than interval should raise"""
        # 25 hour offset with 1 day sun event interval - should raise
        offset = timedelta(hours=25)
        with pytest.raises(OffsetExceedsIntervalError) as exc_info:
            validate_offset_within_interval(offset, SUN_EVENT_INTERVAL, "sunrise")

        assert exc_info.value.offset == timedelta(hours=25)
        assert exc_info.value.interval == SUN_EVENT_INTERVAL
        assert exc_info.value.event_type == "sunrise"

    def test_random_end_exceeds_interval_raises(self) -> None:
        """Random end that would push total offset past interval should raise"""
        # 23 hour offset + random range up to 2 hours = 25 hours max, exceeds 1 day
        offset = timedelta(hours=23)
        with pytest.raises(OffsetExceedsIntervalError):
            validate_offset_within_interval(
                offset, SUN_EVENT_INTERVAL, "sunset",
                random_start=timedelta(), random_end=timedelta(hours=2)
            )

    def test_negative_offset_exceeds_interval_raises(self) -> None:
        """Negative offset larger than interval should raise"""
        # -25 hour offset with 24 hour daily interval - should raise
        offset = timedelta(hours=-25)
        with pytest.raises(OffsetExceedsIntervalError):
            validate_offset_within_interval(offset, timedelta(days=1), "daily")

    def test_zero_interval_skips_validation(self) -> None:
        """Zero interval (non-repeating) should skip validation"""
        # Even a huge offset should pass with zero interval
        offset = timedelta(days=365)
        validate_offset_within_interval(offset, timedelta(), "one-time")
