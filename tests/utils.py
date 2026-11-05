import asyncio
import logging
from collections.abc import Generator, Iterable
from datetime import datetime, timedelta
from itertools import pairwise
from logging import LogRecord
from typing import cast

import pytest
from appdaemon.appdaemon import AppDaemon
from appdaemon.models.internal.app_management import ManagedObject

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
            logger.error(f"Wrong amount of time between log entries: {diff}")
            logger.error(f"  {lines[0].asctime} {lines[0].msg} at ")
            logger.error(f"  {lines[1].asctime} {lines[1].msg} at ")
            raise

    # assert all((diff - expected) <= buffer for diff in time_diffs(records))


async def wait_for_event(ad: AppDaemon, app_name: str, event_attr: str, timeout: float = 0.5):
    """Wait for an app event to be set.

    Encapsulates a chunk of logic for the pattern of waiting for an app to set an async event during a test.
    """
    match ad.app_management.objects.get(app_name):
        case ManagedObject(object=app_obj):
            event = cast(asyncio.Event, getattr(app_obj, event_attr))
            return await asyncio.wait_for(event.wait(), timeout=timeout)
        case None:
            pytest.fail(f"App {app_name} not found")


def get_app_log_records(caplog: pytest.LogCaptureFixture, app_name: str) -> Generator[LogRecord]:
    """Get log records for a specific app containing a search string."""
    for record in caplog.records:
        match record:
            case LogRecord(appname=str(appname)) if appname == app_name:
                yield record
