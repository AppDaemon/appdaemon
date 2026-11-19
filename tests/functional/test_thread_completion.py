import asyncio
import logging
from datetime import timedelta

import pytest
from appdaemon.utils.str import dt_to_str

from tests.conftest import ConfiguredAppDaemonFunc


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("thread_id", ["thread-0", "async"])
@pytest.mark.parametrize("duration", [1, 12], ids=["fast", "slow"])
async def test_completed_callback_returns_to_idle(
    configured_appdaemon: ConfiguredAppDaemonFunc,
    thread_id: str,
    duration: int,
) -> None:
    """A slow-callback warning must not leave a completed callback busy."""
    app_name = "hello_world"
    callback = "HelloWorld.callback for hello_world"
    handle = "test_completion"
    app_cfgs = {app_name: {"module": "hello", "class": "HelloWorld"}}

    async with configured_appdaemon(app_cfgs=app_cfgs, loggers=["_threading"]) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        # Avoid duplicate DEBUG messages replacing the warning in DuplicateFilter.
        with caplog.at_level(logging.WARNING, logger=ad.threading.logger.name):
            await ad.state.add_entity("admin", f"scheduler_callback.{handle}", "active")
            await ad.threading.update_thread_info(thread_id, callback, app_name, "scheduler", handle, False)
            now = await ad.sched.get_now()
            await ad.state.set_state(
                "test",
                "admin",
                f"thread.{thread_id}",
                time_called=dt_to_str(now - timedelta(seconds=duration), ad.tz),
            )
            await asyncio.sleep(0)
            caplog.clear()

            await ad.threading.update_thread_info(thread_id, "idle", app_name, "scheduler", handle, False)

            assert await ad.state.get_state("test", "admin", f"thread.{thread_id}") == "idle"
            assert await ad.state.get_state("test", "admin", f"app.{app_name}") == "idle"
            warnings = [
                record.getMessage()
                for record in caplog.records
                if record.levelno == logging.WARNING and "Excessive time spent in callback" in record.getMessage()
            ]
            if duration == 12:
                assert len(warnings) == 1
                assert callback in warnings[0]
            else:
                assert not warnings
