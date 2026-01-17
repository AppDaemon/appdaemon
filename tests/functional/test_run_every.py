import logging
import re
import uuid
from datetime import datetime, timedelta
from functools import partial
from itertools import product
from typing import cast

import pytest
import pytz
from appdaemon.types import TimeDeltaLike
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
    interval: TimeDeltaLike,
    start: str,
    n: int = 2,
) -> None:
    interval = parse_timedelta(interval)

    # Calculate base runtime for 'n' occurrences plus a small buffer to account for the delay in registering the callback
    register_delay = timedelta(seconds=0.2)
    run_time = (interval * (n + 1)) + register_delay

    # If start time is future "now + offset", add offset to ensure coverage
    if (parts := re.split(r"\s+[\+]\s+", start)) and len(parts) == 2:
        _, offset = parts
        run_time += parse_timedelta(offset)

    app_name = "scheduler_test_app"
    test_id = str(uuid.uuid4())
    app_args = dict(start=start, interval=interval, msg=test_id, register_delay=register_delay)
    async with run_app_for_time(app_name, run_time=run_time.total_seconds(), **app_args) as (ad, caplog):
        check_interval_partial = partial(check_interval, caplog, f"kwargs: {{'msg': '{test_id}',")
        check_interval_partial(n, interval)

        cb_count = await ad.state.get_state('test', 'admin', f'app.{app_name}', 'instancecallbacks')
        assert cast(int, cb_count) >= n, "Callback didn't get called enough times."

        # diffs = utils.time_diffs(utils.filter_caplog(caplog, test_id))
        # logger.debug(diffs)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("start", ["now", "immediate"])
async def test_run_every_start_time(
    run_app_for_time: AsyncTempTest,
    start: str,
) -> None:
    interval = timedelta(seconds=0.5)
    run_time = timedelta(seconds=1)
    register_delay = timedelta(seconds=0.1)

    match start:
        case "now":
            n = 1
        case "immediate":
            n = 2

    app_name = "scheduler_test_app"
    test_id = str(uuid.uuid4())
    app_args = dict(start=start, interval=interval, msg=test_id, register_delay=register_delay)
    async with run_app_for_time(app_name, run_time=run_time.total_seconds(), **app_args) as (ad, caplog):
        check_interval(
            caplog,
            f"kwargs: {{'msg': '{test_id}',",
            n=n,
            interval=interval
        )

        cb_count = await ad.state.get_state('test', 'admin', f'app.{app_name}', 'instancecallbacks')
        assert cast(int, cb_count) >= (n + 1), "Callback didn't get called enough times."

now = datetime.now(pytz.utc)
START_TIMES = ["now", now, now.time(), now.isoformat()]

@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("start", START_TIMES)
async def test_run_every_start_time_types(
    run_app_for_time: AsyncTempTest,
    start: str,
) -> None:
    interval = timedelta(seconds=0.25)
    run_time = timedelta(seconds=1)
    register_delay = timedelta(seconds=0.1)
    n = 3

    app_name = "scheduler_test_app"
    test_id = str(uuid.uuid4())
    app_args = dict(start=start, interval=interval, msg=test_id, register_delay=register_delay)
    async with run_app_for_time(app_name, run_time=run_time.total_seconds(), **app_args) as (ad, caplog):
        cb_count = await ad.state.get_state('test', 'admin', f'app.{app_name}', 'instancecallbacks')
        assert cast(int, cb_count) >= (n + 1), "Callback didn't get called enough times."
