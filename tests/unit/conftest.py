"""This module contains the conftest.py file for unit tests."""

from collections.abc import Callable
from datetime import date, datetime, time
from functools import partial

import pytest
from appdaemon import utils
from astral.location import Location
from pytz import BaseTzInfo, timezone


@pytest.fixture
def tz(location: Location) -> BaseTzInfo:
    return timezone(location.timezone)


@pytest.fixture
def default_date() -> date:
    return date(2025, 6, 20)


@pytest.fixture
def tomorrow_date(default_date: date) -> date:
    return default_date.replace(day=default_date.day + 1)


@pytest.fixture
def now_creator(default_date: date, tz: BaseTzInfo):
    def create_time(hour: int):
        naive = datetime.combine(default_date, time(hour, 0, 0))
        return tz.localize(naive)

    return create_time


@pytest.fixture
def early_now(now_creator: Callable[..., datetime]) -> datetime:
    now = now_creator(4)
    assert now.isoformat() == "2025-06-20T04:00:00-04:00"
    return now


@pytest.fixture
def default_now(now_creator: Callable[..., datetime]) -> datetime:
    now = now_creator(12)
    assert now.isoformat() == "2025-06-20T12:00:00-04:00"
    return now


@pytest.fixture
def late_now(now_creator: Callable[..., datetime]) -> datetime:
    now = now_creator(23)
    assert now.isoformat() == "2025-06-20T23:00:00-04:00"
    return now


@pytest.fixture
def parser(tz: BaseTzInfo, default_now: datetime) -> partial[datetime]:
    return partial(utils.parse_datetime, now=default_now, timezone=tz)


@pytest.fixture
def parser_location(tz: BaseTzInfo, location: Location) -> partial[datetime]:
    return partial(utils.parse_datetime, location=location, timezone=tz)


@pytest.fixture
def time_at_elevation(location: Location, default_now: datetime) -> Callable[..., datetime]:
    return partial(location.time_at_elevation, date=default_now.date(), local=True)
