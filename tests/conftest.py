import asyncio
import logging
from collections.abc import AsyncGenerator, Callable, Iterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, Protocol

import pytest
import pytest_asyncio
from appdaemon import AppDaemon
from appdaemon.dependency_manager import DependencyManager
from appdaemon.logging import Logging
from appdaemon.models.config.app import AllAppConfig, AppConfig
from appdaemon.models.config.appdaemon import AppDaemonConfig
from appdaemon.utils.file import recursive_get_files
from appdaemon.utils.str import format_timedelta

logger = logging.getLogger("AppDaemon._test")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def running_loop():
    return asyncio.get_running_loop()


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
            ext=".yaml",
        )
    )


@pytest.fixture(scope="session")
def logging_obj() -> Logging:
    logger.debug("Creating Logging object")
    return Logging(
        {
            "main_log": {"format": "{asctime} {levelname} {appname}: {message}"},
            "diag_log": {"level": "WARNING", "filename": "tests/diag.log"},
        }
    )


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


class ConfiguredAppDaemonFunc(Protocol):
    def __call__(
        self,
        app_cfgs: dict[str, dict[str, Any]] | None = None,
        extra_ad_cfg: dict[str, Any] | None = None,
        loggers: Iterable[str] | None = None,
    ) -> AbstractAsyncContextManager[tuple[AppDaemon, pytest.LogCaptureFixture]]: ...

@pytest_asyncio.fixture(scope="function")
async def configured_appdaemon(
    running_loop: asyncio.BaseEventLoop,
    ad_cfg: AppDaemonConfig,
    logging_obj: Logging,
    caplog: pytest.LogCaptureFixture,
) -> ConfiguredAppDaemonFunc:
    """Fixture factory for creating AppDaemon instances with custom configuration.

    Returns a callable that accepts additional AppDaemon config parameters and returns
    an async context manager yielding a configured, started AppDaemon instance.
    """
    @asynccontextmanager
    async def _run(
        app_cfgs: dict[str, dict[str, Any]] | None = None,
        extra_ad_cfg: dict[str, Any] | None = None,
        loggers: Iterable[str] | None = None,
    ) -> AsyncGenerator[tuple[AppDaemon, pytest.LogCaptureFixture]]:
        assert running_loop == asyncio.get_running_loop(), "The running loop should match the one passed in"

        # Merge kwargs into the base config
        config_dict = config_dict = ad_cfg.model_dump(by_alias=True)
        extra_ad_cfg = {} if extra_ad_cfg is None else extra_ad_cfg
        config_dict.update(extra_ad_cfg)
        custom_cfg = AppDaemonConfig.model_validate(config_dict)

        ad = AppDaemon(
            logging=logging_obj,
            loop=running_loop,
            ad_config_model=custom_cfg,
        )
        logger.info(f"Created AppDaemon object {hex(id(ad))} with custom config")

        # Enable propagation for all AppDaemon loggers so caplog can capture them
        for cfg in ad.logging.config.values():
            match cfg:
                case {"name": str(name)}:
                    logger_ = logging.getLogger(name)
                    logger_.propagate = True

        loggers = [] if loggers is None else loggers
        for logger_name in loggers:
            logger.info(f"Setting up logger AppDaemon.{logger_name} for testing")
            logger_ = logging.getLogger(f"AppDaemon.{logger_name}")
            logger_.propagate = True
            logger_.setLevel("DEBUG")

        await ad.app_management._process_import_paths()
        config_files = list(recursive_get_files(base=ad.app_dir, suffix={'.yaml', '.toml'}))
        ad.app_management.dependency_manager = DependencyManager(python_files=list(), config_files=config_files)

        app_cfgs = app_cfgs if app_cfgs is not None else {}
        app_cfgs = {
            name: {
                "config_path": Path.cwd(),
                "name": name,
                **cfg
            }
            for name, cfg in app_cfgs.items()
        }
        ad.app_management.dependency_manager.app_deps.app_config = AllAppConfig.model_validate(app_cfgs)
        ad.app_management.dependency_manager.app_deps.refresh_dep_graph()

        try:
            ad.start()
            logger.info(f"AppDaemon[{hex(id(ad))}] started")
            with caplog.at_level(logging.DEBUG, "AppDaemon"):
                yield ad, caplog
        finally:
            logger.info(f"AppDaemon[{hex(id(ad))}] stopping")
            await ad.stop()

    return _run
