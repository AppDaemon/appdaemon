import asyncio
import logging
from datetime import datetime

import pytest
import pytest_asyncio
from appdaemon import AppDaemon
from appdaemon.logging import Logging
from appdaemon.models.config.appdaemon import AppDaemonConfig
from astral import LocationInfo
from astral.location import Location

logger = logging.getLogger("AppDaemon._test")


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def logging_obj():
    logger.debug("Creating Logging object")
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
    logger.debug("Creating AppDaemonConfig object")
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
                "_utility": "DEBUG",
            },
        )
    )


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def ad_obj(logging_obj: Logging, running_loop, ad_cfg: AppDaemonConfig):
    logger = logging.getLogger("AppDaemon._test")
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

    # This can't be done here because the test might set the app directory to a different location
    # await ad.app_management.check_app_updates(mode=UpdateMode.TESTING)

    ad.start()
    yield ad
    logger.info("Back to fixture scope, stopping AppDaemon")
    if stopping_tasks := ad.stop():
        logger.debug("Waiting for stopping tasks to complete")
        await stopping_tasks


@pytest_asyncio.fixture(scope="module")
async def ad_obj_fast(logging_obj: Logging, running_loop, ad_cfg: AppDaemonConfig):
    logger = logging.getLogger("AppDaemon._test")
    logger.info(f"Passed loop: {hex(id(running_loop))}")

    ad_cfg.timewarp = 2000
    ad_cfg.starttime = ad_cfg.time_zone.localize(datetime(2025, 6, 25, 0, 0, 0))

    ad = AppDaemon(
        logging=logging_obj,
        loop=running_loop,
        ad_config_model=ad_cfg,
    )

    for cfg in ad.logging.config.values():
        logger = logging.getLogger(cfg["name"])
        logger.propagate = True
        logger.setLevel("DEBUG")

    # ad.start()
    yield ad
    # raise_signal(Signals.SIGTERM)
    # ad.stop()
    pass


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
