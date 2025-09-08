import pytest

from .utils import AsyncTempTest


@pytest.mark.parametrize("dump_type", ["sun", "threads", "nows"])
@pytest.mark.asyncio
async def test_log_dump(run_app_for_time: AsyncTempTest, dump_type: str) -> None:
    async with run_app_for_time("diag_app", 0.5, dump_type=dump_type) as (ad, caplog):
        for record in caplog.records:
            assert "AssertionError" not in record.msg, "Assertion failed inside app"
