import logging

import pytest
from appdaemon.appdaemon import AppDaemon

logger = logging.getLogger("AppDaemon._test")


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.parametrize("app_name", ["hello_world", "another_app"])
@pytest.mark.asyncio(loop_scope="session")
async def test_hello_world(ad: AppDaemon, caplog: pytest.LogCaptureFixture, app_name: str) -> None:
    """Run one of the hello world apps and ensure that the startup text is in the logs."""

    ad.app_dir = ad.config_dir / "apps/hello_world"
    assert ad.app_dir.exists(), "App directory does not exist"
    logger.info("Test started")
    with caplog.at_level(logging.DEBUG, logger="AppDaemon"):
        async with ad.app_management.app_run_context(app_name):
            await ad.utility.app_update_event.wait()
    logger.info("Test completed")

    assert "Hello from AppDaemon" in caplog.text
    assert "You are now ready to run Apps!" in caplog.text
