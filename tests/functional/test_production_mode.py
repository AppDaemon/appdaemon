import os
from logging import LogRecord
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from appdaemon.appdaemon import AppDaemon
from appdaemon.models.internal.app_management import ManagedObject

from tests.conftest import ConfiguredAppDaemonFunc


@pytest_asyncio.fixture(scope="function")
async def ad_production(ad_obj: AppDaemon):
    """AppDaemon fixture with production_mode enabled."""
    ad_obj.config.production_mode = True
    ad_obj.app_dir = ad_obj.config_dir / "apps/hello_world"

    ad_obj.start()
    yield ad_obj
    await ad_obj.stop()


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_production_mode_loads_apps(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """Test that apps load correctly when production_mode is enabled."""
    app_name = "hello_world"
    async with configured_appdaemon(
        app_cfgs={
            app_name: {
                "module": "hello",
                "class": "HelloWorld",
            }
        },
        extra_ad_cfg={"production_mode": True},
        loggers=[app_name],
    ) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        match ad.app_management.objects.get(app_name):
            case ManagedObject(type="app", running=True):
                return
            case _:
                pytest.fail("HelloWorld app not found in the app management objects")

    initialized = False
    for record in caplog.records:
        match record:
            case LogRecord(appname=str(app_name), msg=str(msg)) if "initialized" in msg:
                initialized = True
                break
    if not initialized:
        pytest.fail("HelloWorld app did not log initialization message")



@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_production_mode_no_reloading(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """Test that production mode doesn't reload apps when files change."""
    app_name = "hello_world"
    async with configured_appdaemon(
        app_cfgs={
            app_name: {
                "module": "hello",
                "class": "HelloWorld",
            }
        },
        extra_ad_cfg={"production_mode": True},
        loggers=[app_name],
    ) as (ad, caplog):
        await ad.utility.app_update_event.wait()

        # Mock check_app_updates to track calls from now on
        mock = AsyncMock(wraps=ad.app_management.check_app_updates)
        ad.app_management.check_app_updates = mock

        # Touch file and wait for utility loop
        ad.utility.app_update_event.clear()
        os.utime(ad.app_dir / "hello.py", None)
        await ad.utility.app_update_event.wait()

        assert not mock.called, "Should not reload in production mode"
