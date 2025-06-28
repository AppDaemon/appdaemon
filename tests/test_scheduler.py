import logging
from datetime import timedelta

import pytest

from appdaemon.appdaemon import AppDaemon

from .utils import assert_timedelta, filter_caplog
from .utils import run_app_temporarily

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
async def test_run_every(ad_obj: AppDaemon, caplog: pytest.LogCaptureFixture) -> None:
    ad_obj.app_dir = ad_obj.config_dir / "apps/scheduler"
    assert ad_obj.app_dir.exists(), "App directory does not exist"

    with caplog.at_level(logging.DEBUG, logger="AppDaemon.run_every"):
        async with run_app_temporarily(ad_obj, "run_every", 5) as ad_obj:
            logger.info("Starting test for run_every")

    check_interval(caplog, "start now", 4, timedelta(seconds=1))


# @pytest.mark.asyncio(loop_scope="session")
# async def test_run_every_fast(ad_obj_fast: AppDaemon, caplog: pytest.LogCaptureFixture, default_now: datetime) -> None:
#     ad_obj_fast.app_dir = ad_obj_fast.config_dir / "apps/scheduler"
#     assert ad_obj_fast.app_dir.exists(), "App directory does not exist"

#     with caplog.at_level(logging.DEBUG, logger="AppDaemon.run_every"):
#         async with run_app_temporarily(ad_obj_fast, "run_every", 5) as ad_obj_fast:
#             logger.info("Starting test for run_every")

#     check_interval(caplog, "start now", 4, timedelta(minutes=45))
#     check_interval(caplog, "start later", 4, timedelta(hours=1.37))
