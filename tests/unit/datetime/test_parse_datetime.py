from datetime import date, datetime, timedelta
from functools import partial

from appdaemon import utils
from astral import SunDirection
from astral.location import Location
from pytz import BaseTzInfo


def test_time_parse(default_now: datetime, parser: partial[datetime]) -> None:
    test_time = default_now.replace(hour=20)
    assert parser("20:00:00") == test_time
    assert parser("20:00") == test_time
    assert parser("20") == test_time

    assert parser("20:00 + 01") == (test_time + timedelta(seconds=1))
    assert parser("20:00 + 2.5") == (test_time + timedelta(seconds=2.5))
    assert parser("20:00 + 01:00") == (test_time + timedelta(minutes=1))
    assert parser("20:00 + 01:00:00") == (test_time + timedelta(hours=1))
    assert parser("20:00 + 01:00:00", offset=timedelta(hours=1)) == (test_time + timedelta(hours=2))

    assert parser("20:00 - 01") == (test_time - timedelta(seconds=1))
    assert parser("20:00 - 2.5") == (test_time - timedelta(seconds=2.5))
    assert parser("20:00 - 01:00") == (test_time - timedelta(minutes=1))
    assert parser("20:00 - 01:00:00") == (test_time - timedelta(hours=1))
    assert parser("20:00 - 01:00:00", offset=-12) == (test_time - timedelta(hours=1, seconds=12))

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
    for i in [10, 1, -1, -10]:
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
    assert parser("23.5 deg rising + 01:00:00") == (rising_func(elevation=23.5) + timedelta(hours=1))
    assert parser("17.34234 deg rising - 01:05:23.5") == (rising_func(elevation=17.34234) - timedelta(hours=1, minutes=5, seconds=23.5))


def test_elevation_setting(parser: partial[datetime], time_at_elevation: partial[datetime], location: Location) -> None:
    parser = partial(parser, location=location)
    setting_func = partial(time_at_elevation, direction=SunDirection.SETTING)

    assert parser("15 deg setting") == setting_func(elevation=15)
    assert parser("15 deg setting") == setting_func(elevation=15)
    assert parser("8.7 deg setting") == setting_func(elevation=8.7)
    assert parser("23.5 deg setting + 01:00:00") == (setting_func(elevation=23.5) + timedelta(hours=1))
    assert parser("17.34234 deg setting - 01:05:23.5") == (setting_func(elevation=17.34234) - timedelta(hours=1, minutes=5, seconds=23.5))


def test_exact_sun_event(default_date: date, location: Location, tz: BaseTzInfo) -> None:
    """Test the exact sunrise/sunset event parsing."""
    parser = partial(utils.parse_datetime, location=location, timezone=tz, today=False)
    today_sunrise = location.sunrise(date=default_date, local=True)
    next_sunrise = parser("sunrise", now=today_sunrise)
    assert next_sunrise.date() != default_date, "Next sunrise should be tomorrow"

    today_sunset = location.sunset(date=default_date, local=True)
    next_sunset = parser("sunset", now=today_sunset)
    assert next_sunset.date() != default_date, "Next sunset should be tomorrow"
