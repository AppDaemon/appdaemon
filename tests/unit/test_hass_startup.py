"""Tests for the HassPlugin startup sequence."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from appdaemon.plugins.hass.hassplugin import HassPlugin

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_ready", "expected"),
    [
        (False, ["ready", "services", "started"]),
        (True, ["started"]),
    ],
)
async def test_services_refreshed_after_home_assistant_started(is_ready: bool, expected: list[str]):
    """Services are fetched again only if the plugin had to wait for Home Assistant to start."""
    calls = []
    plugin = MagicMock()
    plugin.first_time = True
    plugin.is_ready = is_ready
    plugin.config.enable_started_event = True
    plugin.websocket_send_json = AsyncMock(return_value={"success": True, "ad_duration": 0})
    plugin.wait_for_conditions = AsyncMock()
    plugin.ready_event.wait = AsyncMock(side_effect=lambda: calls.append("ready"))
    plugin.get_hass_services = AsyncMock(side_effect=lambda: calls.append("services"))
    plugin.get_hass_config = AsyncMock(return_value={})
    plugin.get_complete_state = AsyncMock(return_value={})
    plugin.notify_plugin_started = AsyncMock(side_effect=lambda **_: calls.append("started"))

    await HassPlugin.__post_auth__(plugin)

    assert calls == expected
