import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

import pytest
from appdaemon.app_management import ManagedObject
from appdaemon.utils.str import format_timedelta

from tests.conftest import ConfiguredAppDaemonFunc

logger = logging.getLogger("AppDaemon._test")


@dataclass
class StateTestResult:
    init_time: datetime
    state_change_time: datetime | None
    callback_time: datetime

    @classmethod
    def from_caplog(cls, caplog: pytest.LogCaptureFixture) -> "StateTestResult":
        init_time, state_change_time, callback_time = None, None, None
        for record in caplog.records:
            match record:
                case logging.LogRecord(created=float(created), msg="%s initialized"):
                    init_time = datetime.fromtimestamp(created)
                case logging.LogRecord(created=float(created), msg="Changing state of %s with kwargs: %s"):
                    state_change_time = datetime.fromtimestamp(created)
                case logging.LogRecord(created=float(created), msg="State callback executed successfully"):
                    callback_time = datetime.fromtimestamp(created)

        assert init_time is not None, "Initialization log time not found"
        assert callback_time is not None, "Callback execution log time not found"

        return cls(
            init_time=init_time,
            state_change_time=state_change_time,
            callback_time=callback_time,
        )

    @property
    def state_change_delay(self) -> timedelta | None:
        match self.state_change_time:
            case timedelta() as sct:
                return sct - self.init_time

    @property
    def change_callback_delay(self) -> timedelta | None:
        """Time between changing the state and the callback execution."""
        match self.state_change_time:
            case datetime() as sct:
                return self.callback_time - sct

    @property
    def init_callback_delay(self) -> timedelta | None:
        """Time between initializing the app and the callback execution."""
        return self.callback_time - self.init_time


@pytest.mark.ci
@pytest.mark.functional
class TestStateCallback:
    """Class to group the various tests for state callbacks.

    - Tests use state_test_app.StateTestApp as the app under test
        App Args:
            listen_kwargs: Keyword arguments for the state listener (e.g., filters)
            state_kwargs: Keyword arguments for setting the state (e.g., new state value)
            delay: Delay before changing the state (default: 0.1 seconds)
    - Tests use `self._run_callback_test` for common logic
        - Registers a callback for a certain state change
        - Changes the state after a short delay
        - Waits for the callback to set the async Event with a timeout
    """

    app_name: str = "state_test_app"
    timeout: float = 0.6

    async def _run_callback_test(
        self,
        configured_appdaemon: ConfiguredAppDaemonFunc,
        app_args: dict,
        sign: bool
    ) -> pytest.LogCaptureFixture:
        """Helper method to run callback tests with common logic.

        This method provides a shared test pattern for state callback testing where a callback
        is expected to either fire (sign=True) or not fire (sign=False) based on state matching.
        """
        app_cfgs = {
            self.app_name: {
                "module": "state_test_app",
                "class": "StateTestApp",
                **app_args,
            }
        }

        async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
            await ad.utility.app_update_event.wait()
            match ad.app_management.objects.get(self.app_name):
                case ManagedObject(object=app_obj):
                    execute_event = cast(asyncio.Event, app_obj.execute_event)
                    wait_coro = asyncio.wait_for(execute_event.wait(), timeout=self.timeout)
                    if sign:
                        await wait_coro
                        logger.debug("Callback execute event was set")
                    else:
                        # We expect the timeout because the new state filter doesn't match
                        with pytest.raises(asyncio.TimeoutError):
                            await wait_coro
                        logger.debug("Callback execute event was not set")
                case _:
                    raise ValueError("App object not found in app management")
        return caplog

    @pytest.mark.parametrize("sign", [True, False])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_new_state_callback(
        self,
        configured_appdaemon: ConfiguredAppDaemonFunc,
        sign: bool
    ) -> None:
        """Test the state callback filtering based on new state values.

        State callbacks should only be fired when the new state matches the filter criteria.

        Args:
            configured_appdaemon: Factory fixture for creating configured AppDaemon instances
            sign: If True, the callback should fire (positive case); if False, it should not (negative case)

        Process:
            - A unique value is generated for the new state
            - If positive case, the same value is used for listening; if negative, a different value is used
            - The app listens for the state change and triggers it after a short delay
            - An Event is set if the callback executes

        Coverage:
            - Positive: new state value matches the listen filter, callback executes
            - Negative: new state value doesn't match the listen filter, callback doesn't execute
        """
        new_state = str(uuid.uuid4())
        listen_state = new_state if sign else str(uuid.uuid4())
        app_args = {
            "listen_kwargs": {"new": listen_state},
            "state_kwargs": {"state": new_state},
        }
        caplog = await self._run_callback_test(configured_appdaemon, app_args, sign)
        if sign:
            result = StateTestResult.from_caplog(caplog)
            logger.info(format_timedelta(result.change_callback_delay))

    @pytest.mark.parametrize("sign", [True, False])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_old_state_callback(
        self,
        configured_appdaemon: ConfiguredAppDaemonFunc,
        sign: bool
    ) -> None:
        """Test the state callback filtering based on old state values.

        State callbacks should only be fired when the old state matches the filter criteria.

        Args:
            configured_appdaemon: Factory fixture for creating configured AppDaemon instances
            sign: If True, the callback should fire (positive case); if False, it should not (negative case)

        Process:
            - A unique value is generated for the state
            - If positive case, the same value is used for listening to old state; if negative, a different value is used
            - The app changes state twice to trigger an old state condition
            - An Event is set if the callback executes

        Coverage:
            - Positive: old state value matches the listen filter, callback executes
            - Negative: old state value doesn't match the listen filter, callback doesn't execute
        """
        new_state = str(uuid.uuid4())
        listen_state = "initialized" if sign else str(uuid.uuid4())
        app_args = {
            "listen_kwargs": {"old": listen_state},
            "state_kwargs": {"state": new_state},
        }
        caplog = await self._run_callback_test(configured_appdaemon, app_args, sign)
        if sign:
            result = StateTestResult.from_caplog(caplog)
            logger.info(format_timedelta(result.change_callback_delay))

    @pytest.mark.parametrize("sign", [True, False])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_attribute_callback(
        self,
        configured_appdaemon: ConfiguredAppDaemonFunc,
        sign: bool
    ) -> None:
        """Test the state callback filtering based on attribute values.

        State callbacks should only be fired when the specified attribute's new value matches the filter criteria.

        Args:
            configured_appdaemon: Factory fixture for creating configured AppDaemon instances
            sign: If True, the callback should fire (positive case); if False, it should not (negative case)

        Process:
            - A unique value is generated for the attribute
            - If positive case, the same value is used for listening to the attribute change; if negative, a different value is used
            - The app listens for the attribute change and triggers a state change with the relevant attribute value
            - An Event is set if the callback executes

        Coverage:
            - Positive: attribute's new value matches the listen filter, callback executes
            - Negative: attribute's new value doesn't match the listen filter, callback doesn't execute
        """
        new_state = str(uuid.uuid4())
        listen_state = new_state if sign else str(uuid.uuid4())
        app_args = {
            "listen_kwargs": {"attribute": "test_attr", "new": listen_state},
            "state_kwargs": {"state": "changed", "test_attr": new_state}
        }
        caplog = await self._run_callback_test(configured_appdaemon, app_args, sign)
        if sign:
            result = StateTestResult.from_caplog(caplog)
            logger.info(format_timedelta(result.change_callback_delay))

    @pytest.mark.asyncio(loop_scope="session")
    async def test_immediate_callback(self, configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
        """Test that the immediate flag on state listeners triggers the callback upon registration.
        """
        # new_state = str(uuid.uuid4())
        app_args = {
            "listen_kwargs": {"new": "initialized", "immediate": True},
            # "state_kwargs": {"state": new_state},
        }
        caplog = await self._run_callback_test(configured_appdaemon, app_args, sign=True)
        result = StateTestResult.from_caplog(caplog)

        assert result.init_callback_delay is not None
