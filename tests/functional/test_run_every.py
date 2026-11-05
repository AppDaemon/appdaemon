import asyncio
import itertools
import logging
import re
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from itertools import product

import pytest
from appdaemon.types import TimeDeltaLike
from appdaemon.utils.parse import parse_timedelta

from tests.conftest import ConfiguredAppDaemonFunc

logger = logging.getLogger("AppDaemon._test")


@dataclass
class RunEveryTestResults:
    """Container class for the test results.

    This provides some convenience methods for making different calculations.
    """
    app_init: datetime | None = None
    callback_start: datetime | None = None
    call_times: list[datetime] = field(default_factory=list)

    @classmethod
    def from_caplog(cls, caplog: pytest.LogCaptureFixture, app_name: str, test_id: str):
        results = cls()
        for record in caplog.records:
            match record:
                case logging.LogRecord(
                    appname=str(app_name),
                    msg=str(msg),
                    created=float(created),
                ) if "initialized" in msg:
                    results.app_init = datetime.fromtimestamp(created)
                case logging.LogRecord(msg="Registering callbacks every %s", created=float(created)):
                    results.callback_start = datetime.fromtimestamp(created)
                case logging.LogRecord(
                    appname=str(_app_name),
                    msg="Run every callback executed with kwargs: %s",
                    args={"msg": str(msg_id)},
                    created=float(created)
                ) if _app_name == app_name and msg_id == test_id and results.callback_start is not None:
                    results.call_times.append(datetime.fromtimestamp(created))
        return results

    @property
    def num_calls(self) -> int:
        return len(self.call_times)

    @property
    def register_delay(self) -> float:
        assert self.app_init is not None
        assert self.callback_start is not None
        return (self.callback_start - self.app_init).total_seconds()

    @property
    def start_delay(self) -> timedelta:
        assert self.callback_start is not None
        assert len(self.call_times) > 0
        return (self.call_times[0] - self.callback_start)

    def rel_times(self) -> Generator[timedelta]:
        assert self.callback_start is not None, "Callbacks not started yet"
        for ct in self.call_times:
            yield ct - self.callback_start

    def diffs(self) -> Generator[timedelta]:
        for t1, t2 in itertools.pairwise(self.rel_times()):
            yield t2 - t1

    def errors(self, interval: timedelta) -> Generator[timedelta]:
        for diff in self.diffs():
            yield abs(interval - diff)


INTERVALS = ["00:0.35", 1, 0.87]
STARTS = ["now - 00:00.5", "now", "now + 00:0.5"]

@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(("start", "interval"), product(STARTS, INTERVALS))
async def test_run_every(
    configured_appdaemon: ConfiguredAppDaemonFunc,
    interval: TimeDeltaLike,
    start: str,
    n: int = 3,
) -> None:
    interval = parse_timedelta(interval)

    # Calculate base runtime for 'n' occurrences plus a small buffer to account for the delay in registering the callback
    register_delay = timedelta(seconds=0.5)
    run_time = (interval * (n + 1)) + register_delay

    # If start time is future "now + offset", add offset to ensure coverage
    if (parts := re.split(r"\s+[\+]\s+", start)) and len(parts) == 2:
        _, offset = parts
        run_time += parse_timedelta(offset)

    app_name = "scheduler_test_app"
    test_id = str(uuid.uuid4())
    app_cfgs = {
        app_name: {
            "module": "scheduler_test_app",
            "class": "RunEveryTestApp",
            "start": start,
            "interval": interval,
            "msg": test_id,
            "register_delay": register_delay,
        }
    }
    async with configured_appdaemon(app_cfgs=app_cfgs, loggers=[app_name, "_scheduler"]) as (ad, caplog):
        await asyncio.sleep(run_time.total_seconds())

    results = RunEveryTestResults.from_caplog(caplog, app_name, test_id)
    assert results.app_init, "App never initialized"
    assert results.num_calls >= n, "Callback wasn't executed enough"
    for err in results.errors(interval):
        assert err < timedelta(seconds=0.01), "Buffer exceeded"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("start", ["now", "immediate"])
async def test_now_immediate(
    configured_appdaemon: ConfiguredAppDaemonFunc,
    start: str,
) -> None:
    interval = timedelta(seconds=0.5)
    run_time = timedelta(seconds=1)
    register_delay = timedelta(seconds=0.1)

    app_name = "scheduler_test_app"
    test_id = str(uuid.uuid4())
    app_cfgs = {
        app_name: {
            "module": "scheduler_test_app",
            "class": "RunEveryTestApp",
            "start": start,
            "interval": interval,
            "msg": test_id,
            "register_delay": register_delay,
        }
    }
    async with configured_appdaemon(app_cfgs=app_cfgs, loggers=[app_name]) as (ad, caplog):
        await asyncio.sleep(run_time.total_seconds())
    results = RunEveryTestResults.from_caplog(caplog, app_name, test_id)
    assert results.app_init, "App never initialized"
    assert results.num_calls > 0
    match start:
        case "now":
            assert (results.start_delay - interval) <= timedelta(seconds=0.01)
        case "immediate":
            assert results.start_delay <= timedelta(seconds=0.01)


@pytest.fixture
def start_time(request):
    """Fixture to generate start time values at test runtime, not collection time."""
    match request.param:
        case "string-now":
            return "now"
        case "datetime-object":
            return datetime.now()
        case "time-object":
            return datetime.now().time()
        case "isoformat-string":
            return datetime.now().isoformat()
        case _:
            return request.param

START_TIME_IDS = ["string-now", "datetime-object", "time-object", "isoformat-string"]

@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("start_time", START_TIME_IDS, indirect=True, ids=START_TIME_IDS)
async def test_start_time_types(
    configured_appdaemon: ConfiguredAppDaemonFunc,
    start_time: str | datetime | time,
) -> None:
    interval = timedelta(seconds=0.25)
    run_time = timedelta(seconds=1)
    register_delay = timedelta(seconds=0.1)

    app_name = "scheduler_test_app"
    test_id = str(uuid.uuid4())
    app_cfgs = {
        app_name: {
            "module": "scheduler_test_app",
            "class": "RunEveryTestApp",
            "start": start_time,
            "interval": interval,
            "msg": test_id,
            "register_delay": register_delay,
        }
    }
    async with configured_appdaemon(app_cfgs=app_cfgs, loggers=[app_name]) as (ad, caplog):
        await asyncio.sleep(run_time.total_seconds())
    results = RunEveryTestResults.from_caplog(caplog, app_name, test_id)
    assert results.app_init, "App never initialized"
    assert results.num_calls > 0
