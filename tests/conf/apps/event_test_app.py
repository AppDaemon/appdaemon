import asyncio
from typing import Any

from appdaemon.adapi import ADAPI

TEST_EVENT = "test_event"


class TestEventCallback(ADAPI):
    """App for testing the event callback functionality.

    It listens for an event and fires it after a delay. Tests can add keyword arguments to both the listen_event and
    fire_event calls.

    Args:
        delay: The delay before calling the self.test_fire method
        listen_kwargs: The keyword arguments to pass to the listen_event method
        fire_kwargs: The keyword arguments to pass to the fire_event method
    """

    def initialize(self):
        self.execute_event = asyncio.Event()
        self.listen_event(self.event_callback, self.event, **self.listen_kwargs)
        self.run_in(self.test_fire, delay=self.args.get("delay", 0.1), **self.fire_kwargs)
        self.log(f"{self.__class__.__name__} initialized")

    @property
    def event(self) -> str:
        return self.args.get("event", TEST_EVENT)

    @property
    def listen_kwargs(self) -> dict[str, Any]:
        return self.args.get("listen_kwargs", {})

    @property
    def fire_kwargs(self) -> dict[str, Any]:
        return self.args.get("fire_kwargs", {})

    def test_fire(self, **kwargs):
        self.logger.info("Firing event with kwargs: %s", kwargs)
        self.fire_event(self.event, **kwargs)

    def event_callback(self, event_type: str, data: dict[str, Any], **kwargs: Any) -> None:
        """Callback function for handling events."""
        assert isinstance(event_type, str), "Event type should be a string"
        assert isinstance(data, dict), "Event data should be a dictionary"
        assert all(isinstance(k, str) for k in kwargs.keys()), "All keys in kwargs should be strings"

        self.logger.info("Event callback executed")
        self.logger.info("Event callback data: %s", data)
        self.logger.info("Event callback kwargs: %s", kwargs)
        self.execute_event.set()
