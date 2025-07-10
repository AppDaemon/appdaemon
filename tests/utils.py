import asyncio
from collections.abc import AsyncGenerator, Generator, Iterable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from itertools import pairwise
from logging import LogRecord
import logging

import pytest

from appdaemon.appdaemon import AppDaemon
from appdaemon.models.config import AppConfig
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

    lines = ((r.msg, r.asctime) for r in records)
    zipped = zip(pairwise(records), time_diffs(records))
    for lines, diff in zipped:
        try:
            assert (diff - expected) <= buffer, "Too much discrepancy in time difference"
        except AssertionError:
            logger.error(f'Wrong amount of time between log entries: {diff}')
            logger.error(f"  {lines[0].msg} at {lines[0].asctime}")
            logger.error(f"  {lines[1].msg} at {lines[1].asctime}")
            raise

    # assert all((diff - expected) <= buffer for diff in time_diffs(records))


@asynccontextmanager
async def run_app_temporarily(ad_obj: AppDaemon, app_name: str, duration: float) -> AsyncGenerator[AppDaemon]:
    """Run a specific app temporarily for a given duration."""
    try:
        await ad_obj.app_management.check_app_updates(mode=UpdateMode.TESTING)

        # Must set before the app is started
        await ad_obj.sched.set_start_time()

        match ad_obj.app_management.app_config.root[app_name]:
            case AppConfig() as app_cfg:
                app_cfg.disable = False
                ad_obj.app_management.dependency_manager.app_deps.refresh_dep_graph()

        actions = UpdateActions()
        actions.apps.init.add(app_name)
        await ad_obj.app_management._start_apps(actions)
        # ad_obj.start()

        duration_str = utils.format_timedelta(timedelta(seconds=duration))
        logger.debug(f"Sleeping for {duration_str} to allow {app_name} to run")
        await asyncio.sleep(duration)
        logger.debug(f"Finished sleeping for {duration_str} for {app_name} complete")
        yield ad_obj
    finally:
        logger.debug('Finally block reached in run_app_temporarily')
        await ad_obj.app_management.check_app_updates(mode=UpdateMode.TERMINATE)
        match ad_obj.app_management.app_config.root[app_name]:
            case AppConfig() as app_cfg:
                app_cfg.disable = True
                ad_obj.app_management.dependency_manager.app_deps.refresh_dep_graph()
