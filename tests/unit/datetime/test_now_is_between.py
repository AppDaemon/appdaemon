from datetime import datetime, time
from functools import partial

from astral.location import Location

from appdaemon import utils


def test_between_overnight(location: Location, early_now: datetime, default_now: datetime, late_now: datetime) -> None:
    sun_check = partial(utils.now_is_between, start_time="sunset", end_time="sunrise", location=location)
    assert sun_check(now=early_now), "The early time is not between sunset and sunrise, but should be"
    assert not sun_check(now=default_now), "The default time is between sunset and sunrise, but should not be"
    assert sun_check(now=late_now), "The late time is not between sunset and sunrise, but should be"

    # Test again with some offsets
    offset = "03:00:00"
    sun_check = partial(
        utils.now_is_between,
        start_time="sunset",
        end_time=f"sunrise - {offset}",
        location=location
    )  # fmt: skip
    assert not sun_check(now=early_now), "The early time is between sunset and the offset sunrise, but should not be"
    assert not sun_check(now=default_now), "The default time is between sunset and the offset sunrise, but should not be"
    assert sun_check(now=late_now), "The late time is not between sunset and the offset sunrise, but should be"

    sun_check = partial(
        utils.now_is_between,
        start_time=f"sunset + {offset}",
        end_time="sunrise",
        location=location
    )  # fmt: skip
    assert sun_check(now=early_now), "The early time is not between the offset sunset and sunrise, but should be"
    assert not sun_check(now=default_now), "The default time is between the offset sunset and sunrise, but should not be"
    assert not sun_check(now=late_now), "The late time is not between the offset sunset and sunrise, but should be"


def test_between_times(location: Location, early_now: datetime, default_now: datetime, late_now: datetime) -> None:
    between_check = partial(utils.now_is_between, start_time="22:00:00", end_time="02:00:00", location=location)
    assert not between_check(now=early_now)
    assert not between_check(now=default_now)
    assert between_check(now=late_now)

    between_check = partial(utils.now_is_between, start_time="22:00:00", end_time="08:00:00", location=location)
    assert between_check(now=early_now)
    assert not between_check(now=default_now)
    assert between_check(now=late_now)

    # Should work with time objects
    between_check = partial(utils.now_is_between, start_time=time(22, 0, 0), end_time=time(8, 0, 0), location=location)
    assert between_check(now=early_now)
    assert not between_check(now=default_now)
    assert between_check(now=late_now)

    # Should work with datetime time objects
    between_check = partial(utils.now_is_between, start_time=default_now.replace(hour=22), end_time=default_now.replace(hour=8), location=location)
    assert between_check(now=early_now)
    assert not between_check(now=default_now)
    assert between_check(now=late_now)


def test_between_simple(default_now: datetime, location: Location) -> None:
    check = partial(utils.now_is_between, now=default_now, location=location)
    assert not check(start_time="10:00:00", end_time="11:00:00"), "Both times before 'now'"
    assert check(start_time="11:00:00", end_time="13:00:00"), "'Now' is between the two times"
    assert not check(start_time="13:00:00", end_time="14:00:00"), "Both times are after 'now'"
