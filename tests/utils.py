from collections.abc import Generator, Iterable
from datetime import datetime, timedelta
from itertools import pairwise
from logging import LogRecord

import pytest


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
    assert all((diff - expected) <= buffer for diff in time_diffs(records))
