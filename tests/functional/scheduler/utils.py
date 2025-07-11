from datetime import timedelta

import pytest

from tests.utils import assert_timedelta, filter_caplog


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
