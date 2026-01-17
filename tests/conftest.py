import asyncio
import logging
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime

import pytest
import pytest_asyncio
from appdaemon import AppDaemon
from appdaemon.dependency_manager import DependencyManager
from appdaemon.logging import Logging
from appdaemon.models.config.app import AppConfig
from appdaemon.models.config.appdaemon import AppDaemonConfig
from appdaemon.utils import format_timedelta, recursive_get_files

logger = logging.getLogger("AppDaemon._test")


@pytest_asyncio.fixture(scope="function")
async def ad_obj(running_loop: asyncio.BaseEventLoop, ad_cfg: AppDaemonConfig, logging_obj: Logging) -> AsyncGenerator[AppDaemon]:
    ad = AppDaemon(
        logging=logging_obj,
        loop=running_loop,
        ad_config_model=ad_cfg,
    )
    logger.info(f"Created AppDaemon object {hex(id(ad))}")

    for cfg in ad.logging.config.values():
        logger_ = logging.getLogger(cfg["name"])
        logger_.propagate = True
    #     logger_.setLevel("DEBUG")

    await ad.app_management._process_import_paths()
    ad.app_management.dependency_manager = DependencyManager(python_files=list(), config_files=list())
    yield ad


@pytest_asyncio.fixture(scope="function")
async def ad(ad_obj: AppDaemon, running_loop: asyncio.BaseEventLoop) -> AsyncGenerator[AppDaemon]:
    """Pytest fixture that provides a full AppDaemon instance for tests.

    General steps:
      - Create the top-level AppDaemon object.
      - Set the log levels of the main logs to DEBUG.
      - Process the import paths.
      - Set up the dependency manager with the app directory.
        - Reads all the config files in the app directory.
      - Disables apps for the duration of the fixture.
      - Starts/stops the AppDaemon instance.
    """
    # logger.info(f"Passed loop: {hex(id(running_loop))}")
    assert running_loop == asyncio.get_running_loop(), "The running loop should match the one passed in"
    ad = ad_obj
    config_files = list(recursive_get_files(base=ad.app_dir, suffix={'.yaml', '.toml'}))
    ad.app_management.dependency_manager = DependencyManager(python_files=list(), config_files=config_files)

    for cfg in ad.app_management.app_config.root.values():
        match cfg:
            case AppConfig() as app_config:
                app_config.disable = True

    ad.start()
    logger.info(f"AppDaemon[{hex(id(ad))}] started")
    yield ad
    logger.info(f"AppDaemon[{hex(id(ad))}] stopping")
    await ad.stop()

    for cfg in ad.app_management.app_config.root.values():
        match cfg:
            case AppConfig() as app_config:
                app_config.disable = True


@pytest.fixture(scope="function")
def ad_cfg() -> AppDaemonConfig:
    logger.debug("Creating AppDaemonConfig object")
    return AppDaemonConfig.model_validate(
        dict(
            latitude=40.7128,
            longitude=-74.0060,
            elevation=0,
            time_zone="America/New_York",
            config_file="tests/conf/appdaemon.yaml",
            write_toml=False,
            ext=".yaml",
            filters=[],
            starttime=None,
            endtime=None,
            timewarp=1.0,
            max_clock_skew=1,
            # loglevel="INFO",
            module_debug={
                "_app_management": "DEBUG",
                "_state": "DEBUG",
                # "_events": "DEBUG",
                # "_scheduler": "DEBUG",
                "_utility": "DEBUG",
            },
            # namespaces={"test_namespace": {"writeback": "hybrid", "persist": False}},
        )
    )


@pytest_asyncio.fixture(scope="module")
async def ad_obj_fast(logging_obj: Logging, running_loop, ad_cfg: AppDaemonConfig):
    logger = logging.getLogger("AppDaemon._test")
    logger.info(f"Passed loop: {hex(id(running_loop))}")

    ad_cfg.timewarp = 2000
    ad_cfg.starttime = ad_cfg.time_zone.localize(datetime(2025, 6, 25, 0, 0, 0))

    ad = AppDaemon(
        logging=logging_obj,
        loop=running_loop,
        ad_config_model=ad_cfg,
    )

    for cfg in ad.logging.config.values():
        logger = logging.getLogger(cfg["name"])
        logger.propagate = True
        logger.setLevel("DEBUG")

    # ad.start()
    yield ad
    # raise_signal(Signals.SIGTERM)
    # ad.stop()
    pass


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create a single event loop for the session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def logging_obj() -> Logging:
    logger.debug("Creating Logging object")
    return Logging(
        {
            "main_log": {"format": "{asctime} {levelname} {appname}: {message}"},
            "diag_log": {"level": "WARNING", "filename": "tests/diag.log"},
        }
    )


AsyncTempTest = Callable[..., AbstractAsyncContextManager[tuple[AppDaemon, pytest.LogCaptureFixture]]]


@pytest_asyncio.fixture(scope="function")
async def run_app_for_time(ad: AppDaemon, caplog: pytest.LogCaptureFixture) -> AsyncTempTest:
    @asynccontextmanager
    async def _run(app_name: str, run_time: float | None = None, **kwargs):
        with caplog.at_level(logging.DEBUG, logger=f"AppDaemon.{app_name}"):
            async with ad.app_management.app_run_context(app_name, **kwargs):
                logger.info(f"===== Running app {app_name} for {format_timedelta(run_time)}")
                if run_time is not None:
                    await asyncio.sleep(run_time)
                logger.info("=== Done, yielding caplog for inspection")
                yield ad, caplog

    return _run


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def running_loop():
    return asyncio.get_running_loop()
