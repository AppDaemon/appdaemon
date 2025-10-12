import asyncio
import logging
import uuid
from time import perf_counter

import pytest
from appdaemon.app_management import ManagedObject

from .utils import AsyncTempTest

logger = logging.getLogger("AppDaemon._test")


@pytest.mark.ci
@pytest.mark.functional
class TestStateCallback:
    """Class to group the various tests for state callbacks."""

    app_name: str = "state_test_app"
    timeout: int | float = 0.6

    async def _run_callback_test(self, run_app_for_time: AsyncTempTest, app_args: dict, sign: bool) -> None:
        """Helper method to run callback tests with common logic.

        This method provides a shared test pattern for state callback testing where a callback
        is expected to either fire (sign=True) or not fire (sign=False) based on state matching.
        """
        start = perf_counter()
        async with run_app_for_time(self.app_name, **app_args) as (ad, caplog):
            match ad.app_management.objects.get(self.app_name):
                case ManagedObject(object=app_obj):
                    wait_coro = asyncio.wait_for(app_obj.execute_event.wait(), timeout=self.timeout)
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
        logger.debug(f"Test completed in {perf_counter() - start:.3f} seconds")

    @pytest.mark.parametrize("sign", [True, False])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_new_state_callback(self, run_app_for_time: AsyncTempTest, sign: bool) -> None:
        """Test the state callback filtering based on new state values.

        State callbacks should only be fired when the new state matches the filter criteria.

        Process:
            - A unique value is generated for the new state. If the callback is supposed to fire (positive case),
              then the same value is used for listening to the state change. Otherwise (negative case), a different, unique
              value is used to listen for the state change, which will prevent the callback from executing.
            - The unique state and listen values are passed to the app as args.
            - The ``state_test_app`` app is run until a python :py:class:`~asyncio.Event` is set.
            - The :py:class:`~asyncio.Event` is created when the app initializes.
            - The app listens for the state change and then triggers it after a short delay, using the relevant kwargs for each.
            - If the callback is executed, :py:class:`~asyncio.Event` is set.

        Coverage:
            - Positive
                The new state value matches the listen filter, so the callback is executed.
            - Negative
                The new state value does not match the listen filter, so the callback is not executed.
        """
        new_state = str(uuid.uuid4())
        listen_state = new_state if sign else str(uuid.uuid4())
        app_args = {
            "listen_kwargs": {"new": listen_state},
            "state_kwargs": {"state": new_state},
        }
        await self._run_callback_test(run_app_for_time, app_args, sign)

    @pytest.mark.parametrize("sign", [True, False])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_old_state_callback(self, run_app_for_time: AsyncTempTest, sign: bool) -> None:
        """Test the state callback filtering based on old state values.

        State callbacks should only be fired when the old state matches the filter criteria.

        Process:
            - A unique value is generated for the state. If the callback is supposed to fire (positive case),
              then the same value is used for listening to the old state. Otherwise (negative case), a different, unique
              value is used to listen for the old state, which will prevent the callback from executing.
            - The unique state and listen values are passed to the app as args.
            - The ``state_test_app`` app is run and the state is changed twice to trigger an old state condition.
            - The app listens for the old state change and waits for the callback execution.
            - If the callback is executed, :py:class:`~asyncio.Event` is set.

        Coverage:
            - Positive
                The old state value matches the listen filter, so the callback is executed.
            - Negative
                The old state value does not match the listen filter, so the callback is not executed.
        """
        new_state = str(uuid.uuid4())
        listen_state = new_state if sign else str(uuid.uuid4())
        app_args = {
            "listen_kwargs": {"old": listen_state},
            "state_kwargs": {"state": new_state},
        }
        async with run_app_for_time(self.app_name, **app_args) as (ad, caplog):
            match ad.app_management.objects.get(self.app_name):
                case ManagedObject(object=app_obj):
                    app_obj.run_in(app_obj.test_change_state, delay=app_obj.delay * 2, state="abc")
                    wait_coro = asyncio.wait_for(app_obj.execute_event.wait(), timeout=self.timeout * 2)
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

    @pytest.mark.parametrize("sign", [True, False])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_attribute_callback(self, run_app_for_time: AsyncTempTest, sign: bool) -> None:
        """Test the state callback filtering based on attribute values.

        State callbacks should only be fired when the specified attribute's new value matches the filter criteria.

        Process:
            - A unique value is generated for the attribute. If the callback is supposed to fire (positive case),
              then the same value is used for listening to the attribute change. Otherwise (negative case), a different,
              unique value is used to listen for the attribute change, which will prevent the callback from executing.
            - The unique attribute and listen values are passed to the app as args.
            - The ``state_test_app`` app is run until a python :py:class:`~asyncio.Event` is set.
            - The :py:class:`~asyncio.Event` is created when the app initializes.
            - The app listens for the attribute change and then triggers a state change with the relevant attribute value.
            - If the callback is executed, :py:class:`~asyncio.Event` is set.

        Coverage:
            - Positive
                The attribute's new value matches the listen filter, so the callback is executed.
            - Negative
                The attribute's new value does not match the listen filter, so the callback is not executed.
        """
        new_state = str(uuid.uuid4())
        listen_state = new_state if sign else str(uuid.uuid4())
        app_args = {"listen_kwargs": {"attribute": "test_attr", "new": listen_state}, "state_kwargs": {"state": "changed", "test_attr": new_state}}
        await self._run_callback_test(run_app_for_time, app_args, sign)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_immediate_callback(self, run_app_for_time: AsyncTempTest) -> None:
        app_args = {
            "listen_kwargs": {
                "new": "on",
                "immediate": True,
            },
        }
        app_name = "test_immediate_state"
        async with run_app_for_time(app_name, **app_args) as (ad, caplog):
            match ad.app_management.objects.get(app_name):
                case ManagedObject(object=app_obj):
                    wait_coro = asyncio.wait_for(app_obj.execute_event.wait(), timeout=self.timeout)
                    await wait_coro
                    logger.debug("Callback execute event was set")
