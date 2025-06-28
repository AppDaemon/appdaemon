import asyncio
import logging
from datetime import datetime, timedelta

import pytest

from appdaemon import ADAPI
from appdaemon.appdaemon import AppDaemon

from .utils import assert_timedelta, filter_caplog

logger = logging.getLogger("AppDaemon._test")


def check_interval(
    caplog: pytest.LogCaptureFixture,
    search_str: str,
    n: int,
    interval: timedelta,
    buffer: timedelta = timedelta(microseconds=10000),
) -> None:
    logs = list(filter_caplog(caplog, search_str))
    assert len(logs) == n, f"Expected {n} log entries with '{search_str}', found {len(logs)}"
    assert_timedelta(logs, interval)


@pytest.mark.asyncio(loop_scope="session")
async def test_run_every(ad_obj: AppDaemon, caplog: pytest.LogCaptureFixture, default_now: datetime) -> None:
    ad_obj.app_dir = ad_obj.config_dir / "apps/scheduler"
    assert ad_obj.app_dir.exists(), "App directory does not exist"

    logger.info("Test started")
    with caplog.at_level(logging.DEBUG, logger="AppDaemon"):
        await ad_obj.utility.app_update_event.wait()
        # await asyncio.sleep(5)

        adapi: ADAPI = ad_obj.app_management.objects["run_every"].object
        adapi.start_realtime() # pyright: ignore[reportAttributeAccessIssue]

        await asyncio.sleep(5)

    check_interval(caplog, "start now", 5, timedelta(seconds=1))


@pytest.mark.asyncio(loop_scope="session")
async def test_run_every_fast(ad_obj_fast: AppDaemon, caplog: pytest.LogCaptureFixture, default_now: datetime) -> None:
    ad_obj_fast.app_dir = ad_obj_fast.config_dir / "apps/scheduler"
    assert ad_obj_fast.app_dir.exists(), "App directory does not exist"

    logger.info("Test started")
    with caplog.at_level(logging.DEBUG, logger="AppDaemon"):
        await ad_obj_fast.utility.app_update_event.wait()
        ad_obj_fast.app_management.objects["run_every"].object.start_timewarp()
        await asyncio.sleep(5)
    logger.info("Test completed")

    assert "All plugins ready" in caplog.text
    assert "App initialization complete" in caplog.text

    check_interval(caplog, "start now", 9, timedelta(minutes=45))
    check_interval(caplog, "start now", 9, timedelta(hours=1.37))
