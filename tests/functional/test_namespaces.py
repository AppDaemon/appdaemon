
import logging
import uuid

import pytest
from appdaemon.utils import PersistentDict

from .utils import AsyncTempTest

logger = logging.getLogger("AppDaemon._test")


pytestmark = [
    pytest.mark.ci,
    pytest.mark.functional,
]


def assert_current_namespace(caplog: pytest.LogCaptureFixture, expected_namespace: str) -> None:
    """Assert that the expected namespace is in the current namespaces log."""
    for record in caplog.records:
        match record:
            case logging.LogRecord(levelno=logging.INFO, msg=str(msg), args=[list(namespaces), *_]):
                if msg == 'Current namespaces: %s':
                    assert expected_namespace in namespaces, f'Expected {expected_namespace} in current namespaces'
                    return
    assert False, f"Did not find log record for current namespaces including {expected_namespace}"


def assert_non_existence_warning(caplog: pytest.LogCaptureFixture, correct: int = 1) -> None:
    """Assert that a warning about non-existence of an entity in a namespace was logged."""
    non_existence_warnings = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and
        r.msg == "Entity %s not found in namespace %s"
    ]
    assert len(non_existence_warnings) == correct, f"Expected {correct} warning(s) about non-existence should be logged"


@pytest.mark.asyncio(loop_scope="session")
async def test_simple_namespaces(run_app_for_time: AsyncTempTest) -> None:
    """Test simple namespace functionality."""
    test_val = str(uuid.uuid4())
    test_ns = "test_namespace"
    app_kwargs = {
        "custom_namespace": test_ns,
        'start_delay': 0.1,
        "test_val": test_val,
    }
    async with run_app_for_time("basic_namespace_app", 0.5, **app_kwargs) as (ad, caplog):
        assert "Persistent namespace 'test_namespace' initialized from MainThread" in caplog.text

        # In order for this to be in the log, the state change callback must have fired, which means that the entity
        # was created in the correct namespace and the state change was detected.
        assert test_val in caplog.text

        # The current namespaces should include the custom test namespace
        assert_current_namespace(caplog, test_ns)

        # There should only be one warning about non-existence of the entity in the custom namespace
        assert_non_existence_warning(caplog)


@pytest.mark.asyncio(loop_scope="session")
async def test_hybrid_writeback(run_app_for_time: AsyncTempTest) -> None:
    """Test hybrid namespace functionality.

    The general idea is to create a namespace with hybrid writeback and ensure that it saves correctly.
    """
    test_val = str(uuid.uuid4())
    test_ns = "hybrid_test_ns"
    app_kwargs = {
        "custom_namespace": test_ns,
        "test_val": test_val,
        "start_delay": 0.5,
        "test_n": 10**3,
    }
    async with run_app_for_time("hybrid_namespace_app", 2.2, **app_kwargs) as (ad, caplog):
        match ad.state.state.get(test_ns):
            case PersistentDict() as state:
                def get_files():
                    return list(state.filepath.parent.glob(f"{test_ns}*"))
                files = get_files()
                assert len(files) > 0, f'Namespace files for {test_ns} should exist, but it does not.'
            case _:
                assert False, f"Expected a PersistentDict for namespace '{test_ns}'"
        assert f"Persistent namespace '{test_ns}' initialized from MainThread" in caplog.text

        saves = [
            record
            for record in caplog.records
            if record.levelno == logging.DEBUG and
            record.msg == "Saving hybrid persistent namespace: %s"
        ]
        assert len(saves) == 2, "Expected exactly two saves of hybrid persistent namespace"

    files = get_files()
    namespace_files = [f.name for f in state.filepath.parent.iterdir() if f.is_file()]
    assert not namespace_files, f"Namespace files for {test_ns} should not exist after test, but they do: {namespace_files}"

    assert "dbm.sqlite3.error" not in caplog.text
