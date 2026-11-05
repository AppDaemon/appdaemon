import asyncio
from typing import Any

from appdaemon.adapi import ADAPI

TEST_ENTITY = "test.some_entity"


class StateTestApp(ADAPI):
    """A simple AppDaemon app to test state management.

    App Args:
        listen_kwargs: Keyword arguments for the state listener (e.g., filters)
        state_kwargs: Keyword arguments for setting the state (e.g., new state value)
        delay: Delay before changing the state (default: 0.1 seconds)

    """

    execute_event: asyncio.Event

    def initialize(self):
        self.set_log_level("DEBUG")
        self.set_namespace("test", persist=False)
        self.execute_event = asyncio.Event()
        self.add_entity(TEST_ENTITY, state="initialized")
        self.listen_state(self.state_callback, TEST_ENTITY, **self.listen_kwargs)
        if "state_kwargs" in self.args:
            self.run_in(self.test_change_state, delay=self.delay, **self.state_kwargs)
        self.logger.info("%s initialized", self.__class__.__name__)

    @property
    def delay(self) -> float:
        return self.args.get("delay", 0.1)

    @property
    def listen_kwargs(self) -> dict[str, Any]:
        return self.args.get("listen_kwargs", {})

    @property
    def state_kwargs(self) -> dict[str, Any]:
        return self.args.get("state_kwargs", {})

    def test_change_state(self, **kwargs):
        self.logger.info("Changing state of %s with kwargs: %s", TEST_ENTITY, kwargs)
        full_state = self.get_state(TEST_ENTITY, attribute="all")
        self.logger.info("Current state of %s: %s", TEST_ENTITY, full_state)
        self.set_state(TEST_ENTITY, **kwargs)

    def state_callback(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> None:
        assert isinstance(entity, str), "Entity should be a string"
        assert isinstance(attribute, str) or attribute is None, "Attribute should be a string or None"

        self.log(f" {entity}.{attribute} ".center(40, "-"))
        self.log(f"{entity}.{attribute} changed from {old} to {new} with kwargs: {kwargs}")

        new_state = self.get_state(entity, attribute="all")
        assert isinstance(new_state, dict), "State should be a dictionary"

        self.log(f"New state for {entity}: {new_state}")
        self.logger.info("State callback executed successfully")
        self.execute_event.set()


class TestImmediate(ADAPI):
    def initialize(self):
        self.set_log_level("DEBUG")
        self.set_namespace("test", persist=False)
        self.execute_event = asyncio.Event()
        self.set_state(TEST_ENTITY, state="on")
        self.listen_state(self.state_callback, TEST_ENTITY, immediate=True, new="on")
        self.logger.info(f"{self.__class__.__name__} initialized")

    def state_callback(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> None:
        self.execute_event.set()
