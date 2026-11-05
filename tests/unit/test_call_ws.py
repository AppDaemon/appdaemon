"""Tests for the Hass.call_ws() method."""

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


@pytest.fixture
def mock_plugin():
    """Creates a mock HassPlugin with a mock websocket_send_json method."""
    plugin = MagicMock()
    plugin.websocket_send_json = AsyncMock()
    return plugin


@pytest.fixture
def hass_instance(mock_plugin):
    """Creates a minimal Hass-like object with mocked internals for testing call_ws.

    Rather than instantiating the full Hass class (which requires a full AppDaemon instance),
    we import the unbound async method and call it with a mock self that has the necessary
    attributes wired up.
    """
    from appdaemon.plugins.hass.hassplugin import HassPlugin

    mock_self = MagicMock()
    mock_self.namespace = "default"

    # Wire up the plugin resolution: self.AD.plugins.get_plugin_object(namespace) -> mock_plugin
    # The mock_plugin must pass the `case HassPlugin() as plugin:` match, so we use spec
    real_plugin = MagicMock(spec=HassPlugin)
    real_plugin.websocket_send_json = mock_plugin.websocket_send_json
    mock_self.AD.plugins.get_plugin_object.return_value = real_plugin

    return mock_self, real_plugin


class TestCallWsValidation:
    """Tests for input validation in call_ws."""

    @pytest.mark.asyncio
    async def test_missing_type_key_returns_error(self, hass_instance):
        """call_ws should return an error dict when 'type' key is missing."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, _ = hass_instance

        result = await Hass.call_ws.__wrapped__(mock_self, key="my_app")

        assert "error" in result
        mock_self.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_id_key_present_returns_error(self, hass_instance):
        """call_ws should return an error dict when 'id' key is present in the message."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, _ = hass_instance

        result = await Hass.call_ws.__wrapped__(mock_self, type="frontend/get_user_data", id=42)

        assert "error" in result
        mock_self.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_message_returns_error(self, hass_instance):
        """call_ws should return an error dict for an empty call (no kwargs)."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, _ = hass_instance

        result = await Hass.call_ws.__wrapped__(mock_self)

        assert "error" in result
        mock_self.logger.warning.assert_called_once()


class TestCallWsSuccess:
    """Tests for successful call_ws invocations."""

    @pytest.mark.asyncio
    async def test_success_response(self, hass_instance):
        """call_ws should return the full response dict from websocket_send_json."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, mock_plugin = hass_instance
        expected_response = {
            "id": 5,
            "type": "result",
            "success": True,
            "result": {"value": {"version": 1, "entries": []}},
            "ad_status": "OK",
            "ad_duration": 0.015,
        }
        mock_plugin.websocket_send_json.return_value = expected_response

        result = await Hass.call_ws.__wrapped__(
            mock_self,
            type="frontend/get_user_data",
            key="my_app",
        )

        assert result == expected_response
        mock_plugin.websocket_send_json.assert_awaited_once_with(type="frontend/get_user_data", key="my_app")

    @pytest.mark.asyncio
    async def test_message_keys_passed_through(self, hass_instance):
        """All kwargs should be passed through to websocket_send_json."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, mock_plugin = hass_instance
        mock_plugin.websocket_send_json.return_value = {"success": True, "result": None}

        await Hass.call_ws.__wrapped__(
            mock_self,
            type="recorder/statistics_during_period",
            start_time="2026-02-01T00:00:00Z",
            statistic_ids=["sensor.energy"],
            period="hour",
        )

        mock_plugin.websocket_send_json.assert_awaited_once_with(
            type="recorder/statistics_during_period",
            start_time="2026-02-01T00:00:00Z",
            statistic_ids=["sensor.energy"],
            period="hour",
        )

    @pytest.mark.asyncio
    async def test_write_user_data(self, hass_instance):
        """call_ws should handle write-style messages that return minimal results."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, mock_plugin = hass_instance
        mock_plugin.websocket_send_json.return_value = {
            "success": True,
            "result": None,
            "ad_status": "OK",
            "ad_duration": 0.008,
        }

        result = await Hass.call_ws.__wrapped__(
            mock_self,
            type="frontend/set_user_data",
            key="my_app",
            value={"version": 1, "entries": []},
        )

        assert result["success"] is True


class TestCallWsErrorHandling:
    """Tests for error responses from call_ws."""

    @pytest.mark.asyncio
    async def test_error_response_returned(self, hass_instance):
        """call_ws should return the full error response without raising."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, mock_plugin = hass_instance
        error_response = {
            "id": 10,
            "type": "result",
            "success": False,
            "error": {"code": "unknown_command", "message": "Unknown command."},
            "ad_status": "OK",
            "ad_duration": 0.005,
        }
        mock_plugin.websocket_send_json.return_value = error_response

        result = await Hass.call_ws.__wrapped__(
            mock_self,
            type="bogus/not_real",
        )

        assert result["success"] is False
        assert result["error"]["code"] == "unknown_command"

    @pytest.mark.asyncio
    async def test_timeout_response(self, hass_instance):
        """call_ws should return a timeout response when websocket_send_json times out."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, mock_plugin = hass_instance
        timeout_response = {
            "success": False,
            "ad_status": "TIMEOUT",
            "ad_duration": 10.0,
        }
        mock_plugin.websocket_send_json.return_value = timeout_response

        result = await Hass.call_ws.__wrapped__(
            mock_self,
            type="frontend/get_user_data",
            key="my_app",
        )

        assert result["success"] is False
        assert result["ad_status"] == "TIMEOUT"


class TestCallWsNamespace:
    """Tests for namespace resolution in call_ws."""

    @pytest.mark.asyncio
    async def test_default_namespace(self, hass_instance):
        """call_ws should use the app's default namespace when none is specified."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, mock_plugin = hass_instance
        mock_self.namespace = "default"
        mock_plugin.websocket_send_json.return_value = {"success": True, "result": {}}

        await Hass.call_ws.__wrapped__(
            mock_self,
            type="frontend/get_user_data",
            key="test",
        )

        mock_self.AD.plugins.get_plugin_object.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_explicit_namespace(self, hass_instance):
        """call_ws should use the specified namespace when one is provided."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self, mock_plugin = hass_instance
        mock_plugin.websocket_send_json.return_value = {"success": True, "result": {}}

        await Hass.call_ws.__wrapped__(
            mock_self,
            type="frontend/get_user_data",
            key="test",
            namespace="hass2",
        )

        mock_self.AD.plugins.get_plugin_object.assert_called_once_with("hass2")

    @pytest.mark.asyncio
    async def test_non_hass_namespace_returns_error(self):
        """call_ws should return an error dict and log a warning for a non-HASS namespace."""
        from appdaemon.plugins.hass.hassapi import Hass

        mock_self = MagicMock()
        mock_self.namespace = "default"
        # Return something that doesn't match HassPlugin()
        mock_self.AD.plugins.get_plugin_object.return_value = MagicMock(spec=[])

        result = await Hass.call_ws.__wrapped__(
            mock_self,
            type="frontend/get_user_data",
            key="test",
        )

        assert "error" in result
        mock_self.logger.warning.assert_called_once()
