import asyncio
from collections.abc import AsyncGenerator, Generator, Iterable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from itertools import pairwise
from logging import LogRecord
import logging

import pytest

from appdaemon.appdaemon import AppDaemon
from appdaemon.app_management import UpdateActions, UpdateMode
from appdaemon import utils

logger = logging.getLogger("AppDaemon._test")


def filter_caplog(caplog: pytest.LogCaptureFixture, search_str: str) -> Generator[LogRecord]:
    """Count the number of log records at a specific level."""
    for record in caplog.records:
        if search_str in record.msg:
            yield record


def time_diffs(records: Iterable[LogRecord]) -> Generator[timedelta]:
    """Calculate time differences between consecutive log records."""
    times = (datetime.strptime(r.asctime, "%Y-%m-%d %H:%M:%S.%f") for r in records)
    yield from (t2 - t1 for t1, t2 in pairwise(times))


def assert_timedelta(
    records: Iterable[LogRecord],
    expected: timedelta,
    buffer: timedelta = timedelta(microseconds=10000),
) -> None:
    """Assert that all time differences between consecutive log records match the expected timedelta."""

    # lines = ((r.msg, r.asctime) for r in records)
    # times = list(zip(pairwise(lines), map(str, time_diffs(records))))
    assert all((diff - expected) <= buffer for diff in time_diffs(records))


@asynccontextmanager
async def run_app_temporarily(ad_obj: AppDaemon, app_name: str, duration: float) -> AsyncGenerator[AppDaemon]:
    """Run a specific app temporarily for a given duration."""
    try:
        await ad_obj.app_management.check_app_updates(mode=UpdateMode.TESTING)

        # Must set before the app is started
        await ad_obj.sched.set_start_time()

        actions = UpdateActions()
        actions.apps.init.add(app_name)
        await ad_obj.app_management._start_apps(actions)
        ad_obj.start()

        duration_str = utils.format_timedelta(timedelta(seconds=duration))
        logger.debug(f"Sleeping for {duration_str} to allow {app_name} to run")
        await asyncio.sleep(duration)
        logger.debug(f"Finished sleeping for {duration_str} for {app_name} complete")
        yield ad_obj
    finally:
        logger.debug("Stopping AppDaemon")
        if stopping_tasks := ad_obj.stop():
            logger.debug("Waiting for stopping tasks to complete")
            await stopping_tasks
