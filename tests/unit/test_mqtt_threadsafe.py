import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from appdaemon.plugins.mqtt.mqttplugin import MqttPlugin

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.asyncio,
]


async def test_message_from_paho_thread_wakes_idle_loop():
    received = asyncio.Event()

    plugin = object.__new__(MqttPlugin)
    plugin.AD = MagicMock(loop=asyncio.get_running_loop())
    plugin.logger = MagicMock()
    plugin.update_perf = MagicMock()
    plugin.mqtt_wildcards = []
    plugin.mqtt_binary_topics = []
    plugin.config = SimpleNamespace(event_name="MQTT_MESSAGE")

    async def send_ad_event(data):
        received.set()

    plugin.send_ad_event = send_ad_event

    sent_at = []

    def paho_thread():
        time.sleep(0.2)  # let the loop go idle first
        sent_at.append(time.monotonic())
        plugin.mqtt_on_message(None, None, SimpleNamespace(topic="a/b", payload=b"x"))

    threading.Thread(target=paho_thread).start()
    await asyncio.wait_for(received.wait(), timeout=3)

    assert time.monotonic() - sent_at[0] < 0.5
