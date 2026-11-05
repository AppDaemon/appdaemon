import logging

import pytest

from tests.conftest import ConfiguredAppDaemonFunc

logger = logging.getLogger("AppDaemon._test")


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.parametrize("app_name", ["hello_world", "another_app"])
@pytest.mark.asyncio(loop_scope="session")
async def test_hello_world(configured_appdaemon: ConfiguredAppDaemonFunc, app_name: str) -> None:
    """Run one of the hello world apps and ensure that the startup text is in the logs."""

    app_cfgs = {
        app_name: {
            "module": "hello",
            "class": "HelloWorld",
        }
    }

    logger.info("Test started")
    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        # await asyncio.sleep(1.0)
    logger.info("Test completed")

    assert "Hello from AppDaemon" in caplog.text
    assert "You are now ready to run Apps!" in caplog.text


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_no_plugins(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """Ensure that apps start correctly when there are no plugins configured."""
    app_name = "hello-world"

    app_cfgs = {
        app_name: {
            "module": "hello",
            "class": "HelloWorld",
        }
    }

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        await ad.utility.app_update_event.wait()

    assert not any(r.levelname == "ERROR" for r in caplog.records)
