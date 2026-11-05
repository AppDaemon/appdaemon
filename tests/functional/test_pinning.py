import asyncio
import logging
from logging import LogRecord
from random import randint

import pytest
from appdaemon.utils.parse import parse_timedelta

from tests.conftest import ConfiguredAppDaemonFunc

logger = logging.getLogger("AppDaemon._test")


def find_app_line(caplog: pytest.LogCaptureFixture, app_name: str, msg: str):
    for record in caplog.records:
        match record:
            case LogRecord(
                appname=str(app_name_),
                msg=str(msg_),
            ) if app_name_ == app_name and msg_ == msg:
                return record
    return False


@pytest.mark.asyncio(loop_scope="session")
async def test_config_pin_thread(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    run_time = 0.5

    extra_ad_cfg = {
        "total_threads": 7,
        "pin_threads": 5
    }

    app_cfgs = {
        f'test-app-{n}': {
            'module': 'pin_thread_app',
            'class': 'PinThreadTester',
            'pin_thread': randint(0, extra_ad_cfg['pin_threads'])
        }
        for n in range(1, 10)
    }

    thread_map = {
        app_name: f'thread-{cfg["pin_thread"]}'
        for app_name, cfg in app_cfgs.items()
    }

    async with configured_appdaemon(app_cfgs=app_cfgs, extra_ad_cfg=extra_ad_cfg) as (ad, caplog):
        await asyncio.sleep(run_time)
        for app_name in app_cfgs:
            assert find_app_line(caplog, app_name, "%s initialized") is not False, (
                "Didn't match the app initialization"
            )

            match find_app_line(caplog, app_name, "Example callback: %s"):
                case LogRecord(args={"__thread_id": str(thread_name)}):
                    assert thread_map[app_name] == thread_name


@pytest.mark.asyncio(loop_scope="session")
async def test_callback_pin_thread(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    run_time = 1.0
    n_apps = 10

    app_cfgs = {
        f'test-pin-app-{n}': {
            'module': 'pin_thread_app',
            'class': 'PinThreadTester',
            "register_delay": parse_timedelta(0.1),
            "cb_pin_thread": randint(0, n_apps - 1),
        }
        for n in range(n_apps)
    }

    thread_map = {
        app_name: f'thread-{app_cfg["cb_pin_thread"]}'
        for app_name, app_cfg in app_cfgs.items()
    }

    extra_ad_cfg = {
        'total_threads': None,
        'pin_threads': None,
        'pin_apps': True
    }

    async with configured_appdaemon(app_cfgs=app_cfgs, extra_ad_cfg=extra_ad_cfg) as (ad, caplog):
        await asyncio.sleep(run_time)

    assert ad.threading.thread_count == n_apps, "Thread count doesn't match app count"
    for app_name in app_cfgs:
        assert find_app_line(caplog, app_name, "%s initialized") is not False, (
            "Didn't match the app initialization"
        )
        match find_app_line(caplog, app_name, 'Example callback: %s'):
            case LogRecord(args={"__thread_id": str(thread_name)}):
                assert thread_map[app_name] == thread_name
            case _:
                assert False


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("pin_app", [None, True, False])
async def test_pin_thread_raises_exception(pin_app: bool | None, configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    pin_thread = -1
    run_time = 1.0

    app_cfgs = {
        'test-pin-app': {
            'module': 'pin_thread_app',
            'class': 'PinThreadTester',
            "register_delay": parse_timedelta(0.1),
            "pin_thread": pin_thread,
            "pin_app": pin_app
        }
    }

    extra_ad_cfg = {}

    async with configured_appdaemon(app_cfgs=app_cfgs, extra_ad_cfg=extra_ad_cfg) as (ad, caplog):
        await asyncio.sleep(run_time)
        if pin_app is not False:
            err = [r for r in caplog.records if r.levelname == "ERROR"]
            assert err[2].msg.strip() == f"NegativePinThread: Pin threads can't be negative: {pin_thread}"


@pytest.mark.asyncio(loop_scope="session")
async def test_new_app_pins(configured_appdaemon: ConfiguredAppDaemonFunc):
    n_apps = 5

    app_cfgs = {
        f'test-pin-app-{n}': {
            'module': 'pin_thread_app',
            'class': 'PinThreadTester',
            "write_app_file": False,
            "register_delay": 0.1,
        }
        for n in range(n_apps)
    }

    async with configured_appdaemon(
        loggers=["_threading"],
        extra_ad_cfg={
            "total_threads": None,
            "pin_threads": None,
            "pin_apps": True,
        },
    ) as (ad, caplog):
        logger.info('=' * 150)
        for app_name, app_cfg in app_cfgs.items():
            await asyncio.sleep(0.25)
            await ad.services.call_service(
                namespace="admin",
                domain="app",
                service="create",
                data={"app": app_name, **app_cfg},
            )
            assert find_app_line(caplog, app_name, "%s initialized") is not False, (
                "Didn't match the app initialization"
            )
        await asyncio.sleep(0.5)
        assert ad.threading.thread_count == n_apps, "Thread count doesn't match app count"

    logger.info('=' * 150)

    for n, app_name in enumerate(app_cfgs):
        match find_app_line(caplog, app_name, 'Example callback: %s'):
            case LogRecord(args={"__thread_id": str(thread_name)}):
                assert thread_name == f'thread-{n}', (
                    f"Called from the wrong thread: {thread_name}"
                )
            case _:
                assert False
