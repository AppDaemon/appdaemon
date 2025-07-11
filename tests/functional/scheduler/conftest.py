import asyncio
import logging
from collections.abc import AsyncGenerator

import pytest_asyncio
from appdaemon import AppDaemon
from appdaemon.logging import Logging
from appdaemon.models.config.appdaemon import AppDaemonConfig

logger = logging.getLogger("AppDaemon._test")


@pytest_asyncio.fixture(scope="package", loop_scope="session")
async def ad(running_loop: asyncio.BaseEventLoop, ad_cfg: AppDaemonConfig) -> AsyncGenerator[AppDaemon]:
    # logger.info(f"Passed loop: {hex(id(running_loop))}")
    assert running_loop == asyncio.get_running_loop(), "The running loop should match the one passed in"

    ad = AppDaemon(
        logging=Logging({"main_log": {"format": "{asctime} {levelname} {appname}: {message}"}}),
        loop=running_loop,
        ad_config_model=ad_cfg,
    )
    logger.info(f"Created AppDaemon object {hex(id(ad))}")

    for cfg in ad.logging.config.values():
        logger_ = logging.getLogger(cfg["name"])
        logger_.propagate = True
        logger_.setLevel("DEBUG")

    # This can't be done here because the test might set the app directory to a different location
    # await ad.app_management.check_app_updates(mode=UpdateMode.TESTING)

    ad.start()
    yield ad
    logger.info("Back to fixture scope, stopping AppDaemon")
    if stopping_tasks := ad.stop():
        logger.debug("Waiting for stopping tasks to complete")
        await stopping_tasks
