import logging

import pytest

from appdaemon.appdaemon import AppDaemon

logger = logging.getLogger('AppDaemon._test')

@pytest.mark.asyncio(loop_scope="session")
async def test_startup(ad_obj: AppDaemon, caplog) -> None:

    ad_obj.app_dir = ad_obj.config_dir / 'apps/hello_world'
    assert ad_obj.app_dir.exists(), "App directory does not exist"

    logger.info("Test started")
    with caplog.at_level(logging.DEBUG, logger='AppDaemon'):
        await ad_obj.utility.app_update_event.wait()
    logger.info("Test completed")

    assert "All plugins ready" in caplog.text
    assert "New app config file: hello_world/apps.yaml" in caplog.text
    assert "New app config: hello_world" in caplog.text
    assert "App initialization complete" in caplog.text
