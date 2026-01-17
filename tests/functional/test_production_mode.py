import os
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from appdaemon.appdaemon import AppDaemon


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
async def test_production_mode_loads_apps(ad_production: AppDaemon) -> None:
    """Test that apps load correctly when production_mode is enabled."""
    # Wait for initialization to complete
    await ad_production.utility.app_update_event.wait()
    # Check that the app loaded
    assert "hello_world" in ad_production.app_management.objects


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_production_mode_no_reloading(ad_production: AppDaemon) -> None:
    """Test that production mode doesn't reload apps when files change."""
    # Wait for initialization to complete
    await ad_production.utility.app_update_event.wait()

    # Mock check_app_updates to track calls from now on
    mock = AsyncMock(wraps=ad_production.app_management.check_app_updates)
    ad_production.app_management.check_app_updates = mock

    # Touch file and wait for utility loop
    ad_production.utility.app_update_event.clear()
    os.utime(ad_production.app_dir / "hello.py", None)
    await ad_production.utility.app_update_event.wait()

    assert not mock.called, "Should not reload in production mode"
