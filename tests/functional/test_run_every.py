import logging
import re
import uuid
from datetime import timedelta
from functools import partial
from itertools import product

import pytest
from appdaemon.utils import parse_timedelta

from tests.conftest import AsyncTempTest

from .utils import check_interval

logger = logging.getLogger("AppDaemon._test")


INTERVALS = ["00:0.35", 1, timedelta(seconds=0.87)]
STARTS = ["now - 00:00.5", "now", "now + 00:0.5"]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(("start", "interval"), product(STARTS, INTERVALS))
async def test_run_every(
    run_app_for_time: AsyncTempTest,
    interval: str | int | float | timedelta,
    start: str,
    n: int = 2,
) -> None:
    interval = parse_timedelta(interval)
    run_time = (interval * n) + timedelta(seconds=0.01)
    register_delay = 0.1
    run_time += timedelta(seconds=register_delay)  # Accounts for the delay in registering the callback
    if (parts := re.split(r"\s+[\+]\s+", start)) and len(parts) == 2:
        _, offset = parts
        run_time += parse_timedelta(offset)

    app_name = "scheduler_test_app"
    test_id = str(uuid.uuid4())
    app_args = dict(start=start, interval=interval, msg=test_id, register_delay=register_delay)
    async with run_app_for_time(app_name, run_time=run_time.total_seconds(), **app_args) as (ad, caplog):
        check_interval_partial = partial(check_interval, caplog, f"kwargs: {{'msg': '{test_id}',")

        if start.startswith("now -"):
            check_interval_partial(n, interval)
        else:
            check_interval_partial(n + 1, interval)

        # diffs = utils.time_diffs(utils.filter_caplog(caplog, test_id))
        # logger.debug(diffs)
