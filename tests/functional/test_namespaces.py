
import asyncio
import logging
import uuid

import pytest
from appdaemon.utils.state import PersistentDict

from tests.conftest import ConfiguredAppDaemonFunc
from tests.utils import wait_for_event

logger = logging.getLogger("AppDaemon._test")


pytestmark = [
    pytest.mark.ci,
    pytest.mark.functional,
]


@pytest.mark.asyncio(loop_scope="session")
async def test_simple_namespaces(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """Test simple namespace functionality."""
    test_val = str(uuid.uuid4())
    test_ns = "test_namespace"
    app_name = "basic_namespace_app"
    app_cfgs = {
        app_name: {
            "module": "namespace_app",
            "class": "BasicNamespaceTester",
            'start_delay': 0.1,
            "custom_namespace": test_ns,
            "test_val": test_val,
        }
    }

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        for p in ad.state.namespace_path.iterdir():
            p.unlink()

        await ad.utility.app_update_event.wait()
        await wait_for_event(ad, app_name, "changed_event", timeout=1.0)

        init_ts = None
        changed_delta = None
        non_existence_warning = False
        for record in caplog.records:
            match record:
                case logging.LogRecord(
                    levelno=logging.INFO,
                    msg='Initial namespaces: %s',
                    args=[list() as init_namespaces, *_],
                ):
                    assert test_ns in init_namespaces, f'Expected {test_ns} in initial namespaces'
                case logging.LogRecord(
                    levelno=logging.INFO,
                    msg="Initialized %s",
                    created=float(init_ts),
                    args=[str(app_name_), *_],
                ):
                    assert app_name_ == app_name, f"Expected app name to be {app_name}"
                case logging.LogRecord(levelno=logging.WARNING, msg="Entity %s not found in namespace %s"):
                    non_existence_warning = True
                case logging.LogRecord(
                    levelno=logging.INFO,
                    msg="Change called from thread %s",
                    created=float(changed_ts)
                ):
                    assert init_ts is not None, "Initialization timestamp should be set before change timestamp"
                    changed_delta = changed_ts - init_ts

        assert non_existence_warning, "Expected non-existence warning was not logged"
        assert changed_delta is not None, "Changed delta should have been calculated"
        logger.info("Changed delta: %s", changed_delta)


@pytest.mark.asyncio(loop_scope="session")
async def test_hybrid_writeback(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """Test hybrid namespace functionality.

    The general idea is to create a namespace with hybrid writeback and ensure that it saves correctly.
    """
    test_val = str(uuid.uuid4())
    test_ns = "hybrid_test_ns"
    app_name = "hybrid_namespace_app"
    app_cfgs = {
        app_name: {
            "module": "namespace_app",
            "class": "HybridWritebackTester",
            "start_delay": 0.1,
            "custom_namespace": test_ns,
            "test_val": test_val,
            "test_n": 10,
        }
    }

    async with configured_appdaemon(app_cfgs=app_cfgs, loggers=["_state"]) as (ad, caplog):
        for p in ad.state.namespace_path.iterdir():
            p.unlink()

        await ad.utility.app_update_event.wait()
        await asyncio.sleep(2.5)

        state = None
        app_initialized = False
        namespace_initialized = False
        save_count = 0
        dbm_error = False

        for record in caplog.records:
            match record:
                case logging.LogRecord(
                    levelno=logging.INFO,
                    msg="Initialized %s",
                    args=[str(app_name_), *_],
                ):
                    assert app_name_ == app_name, f"Expected app name to be {app_name}"
                    app_initialized = True
                case logging.LogRecord(
                    levelno=logging.INFO,
                    msg="Persistent namespace '%s' initialized from %s",
                    args=[str(ns), str(thread)],
                ):
                    assert ns == test_ns, f"Expected namespace to be {test_ns}, got {ns}"
                    assert thread == "MainThread", f"Expected namespace to be initialized from MainThread, got {thread}"
                    namespace_initialized = True
                case logging.LogRecord(
                    levelno=logging.DEBUG,
                    msg="Saving hybrid persistent namespace: %s",
                    args=[str(ns), *_],
                ):
                    if ns == test_ns:
                        save_count += 1
                case logging.LogRecord(msg=str(msg)) if "dbm.sqlite3.error" in msg:
                    dbm_error = True

        assert app_initialized, f"App {app_name} should have been initialized"
        assert namespace_initialized, f"Persistent namespace '{test_ns}' should have been initialized"
        assert save_count >= 2, f"Expected exactly two saves of hybrid persistent namespace, got {save_count}"

        match ad.state.state.get(test_ns):
            case PersistentDict() as state:
                files = list(state.filepath.parent.glob(f"{test_ns}*"))
                assert len(files) > 0, f'Namespace files for {test_ns} should exist, but they do not.'
            case _:
                assert False, f"Expected a PersistentDict for namespace '{test_ns}'"

    namespace_files = [f.name for f in state.filepath.parent.iterdir() if f.is_file()]
    assert not namespace_files, f"Namespace files for {test_ns} should not exist after test, but they do: {namespace_files}"
    assert not dbm_error, "dbm.sqlite3.error should not appear in logs"
