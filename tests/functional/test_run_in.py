import logging
import uuid

import pytest
from appdaemon.utils import format_timedelta, parse_timedelta

logger = logging.getLogger("AppDaemon._test")

ERROR_MARGIN = 0.005  # Allowable error margin for run_in timing


@pytest.mark.parametrize("delay", [None, 0, 0.5, "0.52", "00:0.3", "00:00:0.25", 1])
@pytest.mark.asyncio(loop_scope="session")
async def test_run_in_delay(run_app_for_time, delay):
    run_time = parse_timedelta(delay).total_seconds()
    run_time += ERROR_MARGIN * 10
    register_delay = 0.1
    run_time += register_delay
    test_id = str(uuid.uuid4())  # Generate a unique test ID for each run
    kwargs = dict(delay=delay, test_id=test_id, register_delay=register_delay)
    async with run_app_for_time("test_run_in", run_time=run_time, **kwargs) as (ad, caplog):
        assert "TestSchedulerRunIn initialized" in caplog.text
        for record in caplog.records:
            match record:
                case logging.LogRecord(msg=msg, created=created_ts) if msg.startswith("Registering run_in"):
                    # Nothing really needs to happen here. The created_ts variable is set if the record is matched.
                    # It's already been asserted that this text is somewhere in the caplog text, so this is guaranteed to
                    # match one of the records.
                    continue
                case logging.LogRecord(
                    msg="Run in callback executed with kwargs: %s",
                    args={"test_id": tid},
                    created=callback_ts,
                ) if tid == test_id:
                    elapsed_time = callback_ts - created_ts
                    error = elapsed_time - parse_timedelta(delay).total_seconds()
                    logger.info(f"Scheduler run_in succeeded with delay {format_timedelta(delay)}, " f"elapsed time {format_timedelta(elapsed_time)}, " f"error {format_timedelta(error)}")
                    assert error <= ERROR_MARGIN
                    break
        else:
            # If it reaches here, no matching record was found
            assert False, "Run in callback was not executed"
