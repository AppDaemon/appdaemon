
import logging
from datetime import datetime, time, timedelta

import pytest

from tests.conftest import AsyncTempTest

logger = logging.getLogger("AppDaemon._test")

class TestRunDaily:
    app_name: str = "test_run_daily"

    @pytest.mark.asyncio
    async def test_run_daily(self, run_app_for_time: AsyncTempTest):
        """Test run_daily scheduling."""
        async with run_app_for_time(self.app_name, run_time=0.5, time="12:34:56.789") as (ad, caplog):
            match ad.sched.schedule.get(self.app_name):
                case None:
                    pytest.fail("No schedule found for the app")
                case dict(entries):
                    for entry in entries.values():
                        match entry:
                            case {"interval": interval, "repeat": True, "timestamp": timestamp}:
                                assert interval == timedelta(days=1).total_seconds()
                                assert timestamp.astimezone(ad.tz).time() == time(12, 34, 56, 789000)
                                break
                    else:
                        assert False, "No matching entry found"

    @pytest.mark.asyncio
    async def test_run_sunrise_offset(self, run_app_for_time: AsyncTempTest):
        """Test run_daily scheduling."""
        async with run_app_for_time(self.app_name, run_time=0.5, time="sunrise - 1hr") as (ad, caplog):
            match ad.sched.schedule.get(self.app_name):
                case None:
                    pytest.fail("No schedule found for the app")
                case dict(entries):
                    for entry in entries.values():
                        match entry:
                            case {"type": "next_rising", "repeat": True, "timestamp": timestamp, "offset": offset}:
                                assert offset == timedelta(hours=-1).total_seconds()
                                assert timestamp.astimezone(ad.tz).date() == (datetime.now(ad.tz) + timedelta(days=1)).date()
                                break
                    else:
                        assert False, "No matching entry found"
