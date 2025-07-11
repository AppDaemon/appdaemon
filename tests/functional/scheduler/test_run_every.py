import logging
from datetime import timedelta
from functools import partial
from itertools import product

import pytest
from appdaemon.app_management import UpdateMode
from appdaemon.appdaemon import AppDaemon
from appdaemon.utils import parse_timedelta

from tests import utils

from .utils import check_interval

logger = logging.getLogger("AppDaemon._test")


INTERVALS = ["00:00:0.53", 0.75, 2, timedelta(seconds=0.87)]
STARTS = ["now", "now + 00:00:0.5", "now - 00:00:10"]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(("start", "interval"), product(STARTS, INTERVALS))
async def test_run_every(
    ad: AppDaemon,
    caplog: pytest.LogCaptureFixture,
    interval: str | int | float | timedelta,
    start: str,
    n: int = 3,
) -> None:
    logging.info("Starting test_run_every with parameters: %s, %s", interval, start)
    ad_id = hex(id(ad))
    logger.info(f"Running test_run_every with AppDaemon ID: {ad_id}")

    ad.app_dir = ad.config_dir / "apps/scheduler"
    assert ad.app_dir.exists(), "App directory does not exist"

    interval = parse_timedelta(interval)
    run_time = (interval * n) + timedelta(seconds=0.01)

    with caplog.at_level(logging.DEBUG, logger="AppDaemon.run_every_now"):
        # Initialize the app management system to ensure the dependency manager is initialized
        await ad.app_management.check_app_updates(mode=UpdateMode.TESTING)

        msg = "asdfasdf"
        ad.app_management.update_app("run_every_now", start=start, interval=interval, msg=msg)
        async with ad.run_for_time(run_time.total_seconds()):
            check_interval_partial = partial(check_interval, caplog, msg)

            match (start, interval):
                case ("now", _):
                    check_interval_partial(n + 1, interval)
                case _:
                    check_interval_partial(n, interval)

            diffs = utils.time_diffs(utils.filter_caplog(caplog, msg))
            logger.debug(diffs)
            pass
