import asyncio
import logging
import uuid

import pytest
from appdaemon.app_management import ManagedObject

from .utils import AsyncTempTest

logger = logging.getLogger("AppDaemon._test")


@pytest.mark.ci
@pytest.mark.functional
class TestEventCallback:
    """Class to group the various tests for event callbacks."""

    app_name: str = "test_event_app"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_callback(self, run_app_for_time: AsyncTempTest) -> None:
        """Tests the event callback functionality and the passing of kwargs through events.

        Process:
            - Unique values are generated for the event and its kwargs
            - The run_app_for_time context manager is used to run the test_event_app temporarily
            - Event test app listens for an event and fires the same event shortly after
            - Wait for :py:class:`~asyncio.Event` to be set by the callback in the app
            - Clear the :py:class:`~asyncio.Event`
            - Set the app arg to another event name so it will no longer match the event that was initially listened for
            - Fire the new event
            - Wait for the :py:class:`~asyncio.Event` again, expecting a timeout.

        Coverage:
            - ``listen_event`` results in the callback being called for corresponding events
            - keyword arguments provided in ``listen_event`` are passed to the callback in ``kwargs``
            - keyword arguments provided in the ``fire_event`` call are passed to the callback in ``data``
        """
        listen_id = str(uuid.uuid4())
        fire_id = str(uuid.uuid4())
        app_args = {"listen_kwargs": {"test_kwarg": listen_id}, "fire_kwargs": {"test_fire_kwarg": fire_id}}
        async with run_app_for_time(self.app_name, **app_args) as (ad, caplog):
            match ad.app_management.objects.get(self.app_name):
                case ManagedObject(object=app_obj):
                    await asyncio.wait_for(app_obj.execute_event.wait(), timeout=0.5)

                    # Clear the async execute event and fire the AppDaemon event again with a different name
                    app_obj.execute_event.clear()
                    app_obj.args["event"] = "other event"
                    ad.loop.call_soon(app_obj.test_fire)

                    # We expect it to timeout
                    with pytest.raises(asyncio.TimeoutError):
                        await asyncio.wait_for(app_obj.execute_event.wait(), timeout=0.5)
                case _:
                    raise ValueError("App object not found in app management")

            assert "TestEventCallback initialized" in caplog.text
            for record in caplog.records:
                match record:
                    case logging.LogRecord(
                        msg="Event callback data: %s",
                        args={"__thread_id": thread_id, "test_fire_kwarg": fired_kwarg},
                    ):
                        assert thread_id == "thread-0"
                        assert fired_kwarg == fire_id
                    case logging.LogRecord(msg="Event callback kwargs: %s", args={"test_kwarg": tid}):
                        assert tid == listen_id

    @pytest.mark.parametrize("sign", [True, False])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_callback_filtered(self, run_app_for_time: AsyncTempTest, sign: bool) -> None:
        """Test the event callback filtering based on keyword arguments.

        If the event data has a key that matches one of the kwargs provided in the ``listen_event`` call, then the values
        for those keys must also match for the callback to be executed.

        Process:
            - A unique value is generated for firing the event. If the callback is supposed to fire (positive case),
              then the same value is used for listening to the event. Otherwise (negative case), a different, unique
              value is used to listen for the event, which will prevent the callback from executing.
            - The unique fire and listen values are passed to the app as args.
            - The ``test_event_app`` app is run until a python :py:class:`~asyncio.Event` is set.
            - The :py:class:`~asyncio.Event` is created when the app initializes.
            - The app listens for the event and then fires it after a short delay, using the relevant kwargs for each.
            - If the callback is executed, :py:class:`~asyncio.Event` is set, and the unique values are printed in the logs.

        Coverage:
            - Positive
                There is a matching key between the listen kwargs and the event data and the values match, so the callback is executed.
            - Negative
                There is a matching key between the listen kwargs and the event data but the values do not match, so the callback is not executed.
        """
        fire_id = str(uuid.uuid4())
        listen_id = fire_id if sign else str(uuid.uuid4())
        test_kwarg_name = "test_kwarg"
        app_args = {
            "listen_kwargs": {test_kwarg_name: listen_id},
            "fire_kwargs": {test_kwarg_name: fire_id},
        }

        async with run_app_for_time(self.app_name, **app_args) as (ad, caplog):
            match ad.app_management.objects.get(self.app_name):
                case ManagedObject(object=app_obj):
                    wait_coro = asyncio.wait_for(app_obj.execute_event.wait(), timeout=0.5)
                    if sign:
                        await wait_coro
                    else:
                        # We expect the timeout because the namespaces don't match
                        with pytest.raises(asyncio.TimeoutError):
                            await wait_coro
                case _:
                    raise ValueError("App object not found in app management")
            assert "TestEventCallback initialized" in caplog.text
            if sign:
                assert "Event callback executed" in caplog.text

    @pytest.mark.parametrize("sign", [True, False])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_callback_namespace(self, run_app_for_time: AsyncTempTest, sign: bool) -> None:
        """Test the event callback functionality with different namespaces.

        Event callbacks should only be fired for events in the correct namespace.

        Process:
            - The event test app is given namespaces to listen and fire the event in.
            - The app listens for the event and then fires it after a short delay, using the relevant namespaces for each.

        Coverage:
            - Positive
                The listen and fire namespaces match, so the callback is executed.
            - Negative
                The listen and fire namespaces do not match, so the callback is not executed.
        """
        namespace = "test"
        if sign:
            # The listen and fire namespaces have to match for the callback to work
            app_args = {
                "listen_kwargs": {"namespace": namespace},
                "fire_kwargs": {"namespace": namespace},
            }
        else:
            # If the event is listened in a different namespace, then it won't be triggered
            app_args = {"listen_kwargs": {"namespace": namespace}}

        async with run_app_for_time(self.app_name, **app_args) as (ad, caplog):
            match ad.app_management.objects.get(self.app_name):
                case ManagedObject(object=app_obj):
                    wait_coro = asyncio.wait_for(app_obj.execute_event.wait(), timeout=0.5)
                    if sign:
                        await wait_coro
                    else:
                        # We expect the timeout because the namespaces don't match
                        with pytest.raises(asyncio.TimeoutError):
                            await wait_coro
                case _:
                    raise ValueError("App object not found in app management")
            assert "TestEventCallback initialized" in caplog.text
            if sign:
                assert "Event callback executed" in caplog.text

    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_callback_oneshot(self, run_app_for_time: AsyncTempTest) -> None:
        """Test the oneshot functionality of the event callback.

        Event callbacks that are registered with the oneshot flag should only be fired once.

        Process:
            - Listen for an event with the oneshot flag set.
            - Fire the event twice, and ensure that the callback is only fired once.

        Coverage:
            - Event callbacks that are registered with the oneshot flag should only be fired once.
        """
        app_args = {"listen_kwargs": {"oneshot": True}}
        async with run_app_for_time(self.app_name, **app_args) as (ad, caplog):
            match ad.app_management.objects.get(self.app_name):
                case ManagedObject(object=app_obj):
                    await asyncio.wait_for(app_obj.execute_event.wait(), timeout=0.5)

                    # Clear the async execute event and fire the AppDaemon event again
                    app_obj.execute_event.clear()
                    ad.loop.call_soon(app_obj.test_fire)

                    # We expect it to timeout
                    with pytest.raises(asyncio.TimeoutError):
                        await asyncio.wait_for(app_obj.execute_event.wait(), timeout=0.5)
                case _:
                    raise ValueError("App object not found in app management")
            assert "TestEventCallback initialized" in caplog.text
