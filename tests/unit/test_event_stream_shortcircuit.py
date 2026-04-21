"""Regression tests for the /stream short-circuit in Events.process_event.

When no clients are subscribed to /stream the deepcopy + stream_update
work is pure waste — ADStream.process_event already returns immediately
when ``handlers`` is empty. The fix returns before the deepcopy runs.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from appdaemon.events import Events

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.asyncio,
]


def _make_events(handlers):
    """Build a minimally-mocked Events with a fake http.stream.handlers."""
    ad = MagicMock()
    ad.stopping = False
    ad.sched = None
    ad.apps_enabled = False
    ad.logging = MagicMock()
    ad.logging.get_child.return_value = MagicMock()
    ad.logging.has_log_callback = AsyncMock(return_value=False)
    ad.http = MagicMock()
    ad.http.stream.handlers = handlers
    ad.http.stream_update = AsyncMock()
    ad.state = MagicMock()
    ad.state.set_state_simple = AsyncMock()
    ad.state.process_state_callbacks = AsyncMock()
    return Events(ad), ad


def _state_changed_event():
    return {
        "event_type": "state_changed",
        "data": {
            "entity_id": "sensor.x",
            "new_state": {"state": "on"},
            "old_state": {"state": "off"},
        },
    }


async def test_stream_update_skipped_when_no_handlers():
    events, ad = _make_events(handlers={})
    await events.process_event("default", _state_changed_event())
    ad.http.stream_update.assert_not_called()


async def test_stream_update_called_when_handler_present():
    events, ad = _make_events(handlers={"client-1": object()})
    await events.process_event("default", _state_changed_event())
    ad.http.stream_update.assert_called_once()


async def test_no_op_when_http_disabled():
    events, ad = _make_events(handlers={"client-1": object()})
    ad.http = None
    # Should not raise even though stream is unreachable.
    await events.process_event("default", _state_changed_event())
