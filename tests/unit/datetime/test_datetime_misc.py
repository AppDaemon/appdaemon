from datetime import datetime, timedelta

import pytest
from appdaemon import utils
from pytz import BaseTzInfo

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


def test_resolve_offset() -> None:
    offsets = sorted(
        utils.resolve_offset(
            timedelta(seconds=10),
            random_start=timedelta(seconds=-5),
            random_end=timedelta(seconds=5)
        )
        for _ in range(100)
    )
    assert len(set(offsets)) >= 90, "Offsets should be sufficiently random"
    assert offsets[0] > timedelta(seconds=5)
    assert offsets[-1] < timedelta(seconds=15)


def test_ensure_timezone(tz: BaseTzInfo) -> None:
    naive = datetime(2025, 6, 25, 12, 0, 0)
    aware = utils.ensure_timezone(naive, tz)
    assert aware.tzinfo is not None, "Datetime should be timezone-aware"
    assert naive.time() == aware.time(), "Time should remain the same after ensuring timezone"
    assert aware != datetime(2025, 6, 25, 12, 0, 0, tzinfo=tz)
