"""This module contains the conftest.py file for unit tests."""

import logging
import uuid
from collections.abc import Callable, Iterator
from datetime import date, datetime, time
from functools import partial

import pytest
from appdaemon.logging import Logging
from appdaemon.utils import parse
from astral import LocationInfo
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
def parser(default_now: datetime) -> partial[datetime]:
    return partial(parse.parse_datetime, now=default_now)


@pytest.fixture
def parser_location(location: Location) -> partial[datetime]:
    return partial(parse.parse_datetime, location=location)


@pytest.fixture
def time_at_elevation(location: Location, default_now: datetime) -> Callable[..., datetime]:
    return partial(location.time_at_elevation, date=default_now.date(), local=True)


@pytest.fixture
def location() -> Location:
    return Location(
        LocationInfo(
            name="Test Location",
            region="Test Region",
            timezone="America/New_York",
            latitude=40.7128,
            longitude=-74.0060,
        )
    )


@pytest.fixture
def make_logging() -> Iterator[Callable[[dict], Logging]]:
    """Builds fresh, non-singleton Logging objects whose loggers have unique names, and detaches their handlers afterwards.

    Call it from the test body when using capsys: stream handlers bind sys.stdout/sys.stderr when they are created, and capsys
    only swaps in the streams it reads during the call phase.
    """
    created: list[Logging] = []

    def _make(config: dict) -> Logging:
        suffix = uuid.uuid4().hex
        config = {log: {**cfg, "name": f"{cfg.get('name', log)}_{suffix}"} for log, cfg in config.items()}
        for log in ("main_log", "error_log"):
            config.setdefault(log, {"name": f"{log}_{suffix}"})
        obj = object.__new__(Logging)
        created.append(obj)
        obj.__init__(config)
        return obj

    yield _make

    for obj in created:
        for cfg in obj.config.values():
            if handler := cfg.get("handler"):
                logging.getLogger(cfg["name"]).removeHandler(handler)
                handler.close()
