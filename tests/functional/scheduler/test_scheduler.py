import logging
from datetime import timedelta

import pytest

from appdaemon.app_management import UpdateMode
from appdaemon.models.config import AppConfig
from appdaemon.appdaemon import AppDaemon

from tests.utils import assert_timedelta, filter_caplog, run_app_temporarily

logger = logging.getLogger("AppDaemon._test")


def check_interval(
    caplog: pytest.LogCaptureFixture,
    search_str: str,
    n: int,
    interval: timedelta,
    buffer: timedelta = timedelta(microseconds=10000),
) -> None:
    logs = list(filter_caplog(caplog, search_str))
    assert_timedelta(logs, interval, buffer)
    assert len(logs) == n, f"Expected {n} log entries with '{search_str}', found {len(logs)}"


@pytest.mark.asyncio(loop_scope="session")
async def test_run_every(ad_obj: AppDaemon, caplog: pytest.LogCaptureFixture) -> None:
    ad_id = hex(id(ad_obj))
    logger.info(f"Running test_run_every_fast with AppDaemon ID: {ad_id}")

    ad_obj.app_dir = ad_obj.config_dir / "apps/scheduler"
    assert ad_obj.app_dir.exists(), "App directory does not exist"

    # with caplog.at_level(logging.DEBUG, logger="AppDaemon.run_every"):
    #     async with run_app_temporarily(ad_obj, "run_every", 4.8) as ad_obj:
    #         check_interval(caplog, "start now", 4, timedelta(seconds=1))
    #         # TODO: check_interval(caplog, "start now", 5, timedelta(seconds=1))
    #         check_interval(caplog, "start default", 9, timedelta(seconds=0.5))
    #     caplog.clear()


    msg = 'asdfasdf'
    with caplog.at_level(logging.DEBUG, logger="AppDaemon.run_every_now"):
        await ad_obj.app_management.check_app_updates(mode=UpdateMode.TESTING)
        match ad_obj.app_management.app_config.root["run_every_now"]:
            case AppConfig() as app_cfg:
                app_cfg.args["interval"] = 1.0
                app_cfg.args["msg"] = msg
        async with run_app_temporarily(ad_obj, "run_every_now", 3.5) as ad_obj:
            check_interval(caplog, msg, 3, timedelta(seconds=0.75))
        caplog.clear()

# @pytest.mark.asyncio(loop_scope="session")
# async def test_run_every_fast(ad_obj_fast: AppDaemon, caplog: pytest.LogCaptureFixture) -> None:
#     ad_id = hex(id(ad_obj_fast))
#     logger.info(f"Running test_run_every_fast with AppDaemon ID: {ad_id}")

#     ad_obj_fast.app_dir = ad_obj_fast.config_dir / "apps/scheduler"
#     assert ad_obj_fast.app_dir.exists(), "App directory does not exist"

#     with caplog.at_level(logging.DEBUG, logger="AppDaemon.run_every"):
#         async with run_app_temporarily(ad_obj_fast, "run_every", 15) as ad_obj_fast:
#             logger.info("Starting test for run_every")

#     # logs = list(filter_caplog(caplog, "start now"))
#     # assert_timedelta(logs, utils.parse_timedelta("02:37:45.7"), buffer=timedelta(minutes=1))

#     logs = list(filter_caplog(caplog, "start later"))
#     assert_timedelta(logs, timedelta(hours=2), buffer=timedelta(minutes=1))

    # check_interval(caplog, "start now", 4, timedelta(minutes=45))
    # check_interval(caplog, "start later", 4, timedelta(hours=1.37))
