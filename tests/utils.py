import logging
from collections.abc import Generator, Iterable
from datetime import datetime, timedelta
from itertools import pairwise
from logging import LogRecord

import pytest

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
