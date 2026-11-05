import logging
from datetime import datetime, time, timedelta

import pytest

from tests.conftest import ConfiguredAppDaemonFunc

logger = logging.getLogger("AppDaemon._test")

@pytest.mark.ci
@pytest.mark.functional
class TestRunDaily:
    app_name: str = "test_run_daily"
    register_delay: float = 0.1

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("time_input", ["12:34:56.789", time(12, 34, 56, 789000)])
    async def test_run_daily(self, time_input: str | time, configured_appdaemon: ConfiguredAppDaemonFunc):
        """Test run_daily scheduling."""
        app_cfgs = {
            self.app_name: {
                "module": "scheduler_test_app",
                "class": "TestSchedulerRunDaily",
                "time": time_input,
            }
        }
        async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
            await ad.utility.app_update_event.wait()
            match ad.sched.schedule.get(self.app_name):
                case None:
                    pytest.fail("No schedule found for the app")
                case dict(entries):
                    # Don't really care about the keys (callback handles) here
                    for entry in entries.values():
                        match entry:
                            case {"timestamp": timestamp, "repeat": True, "interval": interval}:
                                assert interval == timedelta(days=1)
                                assert timestamp.astimezone(ad.tz).time() == time(12, 34, 56, 789000)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_run_sunrise_offset(self, configured_appdaemon: ConfiguredAppDaemonFunc):
        """Test run_daily scheduling."""
        app_cfgs = {
            self.app_name: {
                "module": "scheduler_test_app",
                "class": "TestSchedulerRunDaily",
                "time": "sunrise - 1 hour",
            }
        }
        async with configured_appdaemon(app_cfgs=app_cfgs, loggers=[self.app_name]) as (ad, caplog):
            await ad.utility.app_update_event.wait()
            match ad.sched.schedule.get(self.app_name):
                case None:
                    pytest.fail("No schedule found for the app")
                case dict(entries):
                    for entry in entries.values():
                        match entry:
                            case {"type": "next_rising", "repeat": True, "timestamp": timestamp, "offset": offset}:
                                assert offset == timedelta(hours=-1)
                                assert timestamp.astimezone(ad.tz).date() == (datetime.now(ad.tz) + timedelta(days=1)).date()
                                break
                    else:
                        assert False, "No matching entry found"
