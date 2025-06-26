import asyncio
import logging
from datetime import date, datetime, time
from functools import partial
from typing import Callable

import pytest
import pytest_asyncio
from astral import LocationInfo
from astral.location import Location
from pytz import BaseTzInfo, timezone

from appdaemon import AppDaemon, utils
from appdaemon.logging import Logging
from appdaemon.models.config.appdaemon import AppDaemonConfig

logger = logging.getLogger('AppDaemon._test')


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()



@pytest.fixture(scope="session")
def logging_obj():
    return Logging(
        {
            "main_log": {"format": "{asctime} {levelname} {appname}: {message}"},
            "diag_log": {"level": "WARNING", "filename": "tests/diag.log"},
        }
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def running_loop():
    return asyncio.get_running_loop()


@pytest.fixture(scope="session")
def ad_cfg() -> AppDaemonConfig:
    return AppDaemonConfig.model_validate(
        dict(
            latitude=40.7128,
            longitude=-74.0060,
            elevation=0,
            time_zone="America/New_York",
            config_file="tests/conf/appdaemon.yaml",
            write_toml=False,
            ext=".yaml",
            filters=[],
            starttime=None,
            endtime=None,
            timewarp=1.0,
            max_clock_skew=1,
            # loglevel="INFO",
            # module_debug={"_events": "DEBUG"},
            module_debug={
                "_app_management": "DEBUG",
                # "_events": "DEBUG",
                # "_utility": "DEBUG",
            }
        )
    )


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def ad_obj(logging_obj: Logging, running_loop, ad_cfg: AppDaemonConfig):
    logger = logging.getLogger('AppDaemon._test')
    logger.info(f"Passed loop: {hex(id(running_loop))}")
    assert running_loop == asyncio.get_running_loop(), "The running loop should match the one passed in"

    ad = AppDaemon(
        logging=logging_obj,
        loop=running_loop,
        ad_config_model=ad_cfg,
    )

    for cfg in ad.logging.config.values():
        logger = logging.getLogger(cfg["name"])
        logger.propagate = True
        logger.setLevel("DEBUG")

    ad.start()
    yield ad
    ad.stop()


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
