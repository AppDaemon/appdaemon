import logging

import pytest
from appdaemon.appdaemon import AppDaemon

logger = logging.getLogger("AppDaemon._test")


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.parametrize(
    ("app_name", "app_config_class_name"),
    [
        ("hello_world_1", "AppConfig"),
        ("hello_world_2", "AppConfig"),
        ("typed_hello_world_1", "TypedAppConfig"),
        ("typed_hello_world_2", "TypedAppConfig"),
    ],
)
@pytest.mark.asyncio(loop_scope="session")
async def test_typed_hello_world(ad: AppDaemon, app_name: str, app_config_class_name: str) -> None:
    """Run one of the hello world apps and ensure that the startup text is in the logs."""

    ad.app_dir = ad.config_dir / "apps/typed_hello_world"
    assert ad.app_dir.exists(), "App directory does not exist"
    logger.info("Test started")
    async with ad.app_management.app_run_context(app_name):
        assert (app := ad.app_management.get_app(app_name)) is not None, f"App {app_name} not found."
        assert (
            app.config_model.__class__.__name__ == app_config_class_name
        ), f"App {app_name} config type name {app.__class__.__name__} differs from {app_config_class_name}"
    logger.info("Test completed")


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.parametrize(
    "app_name",
    [
        "hello_world_3",
        "typed_hello_world_3",
        "typed_hello_world_4",
        "typed_hello_world_5",
    ],
)
@pytest.mark.asyncio(loop_scope="session")
async def test_incorrect_typed_hello_world(ad: AppDaemon, app_name: str) -> None:
    """Run one of the hello world apps and ensure that the startup text is in the logs."""

    ad.app_dir = ad.config_dir / "apps/typed_hello_world"
    assert ad.app_dir.exists(), "App directory does not exist"
    logger.info("Test started")
    assert ad.app_management.get_app(app_name) is None, f"App {app_name} was suppose to be not found."
    logger.info("Test completed")
