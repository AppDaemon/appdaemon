import asyncio
from typing import Any

from appdaemon.adapi import ADAPI
from appdaemon.entity import Entity

TEST_ENTITY = "test.test_entity"


class EntityTestApp(ADAPI):
    """Test app for entity API tests."""

    execute_event: asyncio.Event

    async def initialize(self) -> None:
        """Initialize the test app."""
        self.set_log_level("DEBUG")
        self.set_namespace("test")
        self.execute_event = asyncio.Event()
        self.run_in(self.do_tests, 0)
        self.log("EntityTestApp initialized")

    @property
    def test_entity(self) -> Entity:
        """Return the test entity ID."""
        return self.get_entity(TEST_ENTITY)

    def do_tests(self, **kwargs):
        self.log("Running entity API tests")
        if not self.test_entity.exists():
            self.log(f"Creating test entity {TEST_ENTITY}")
            self.test_entity.add(state="off", friendly_name="Test Entity")

        initial_state = self.test_entity.get_state()
        assert initial_state == "off", f"Expected initial state 'off', got '{initial_state}'"
        self.log(f"Initial state: {initial_state}")

        initial_full_state = self.test_entity.get_state('all')
        assert isinstance(initial_full_state, dict), "Expected full state to be a dictionary"
        self.log(f"Initial full state: {initial_full_state}")

        self.test_entity.listen_state(self.state_callback, **self.args.get("listen_kwargs", {}))
        self.run_in(self.change_state, 0, state="changed")

    def change_state(self, **kwargs: Any) -> None:
        self.test_entity.set_state(**kwargs)

    def state_callback(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> None:
        self.log(f"State change detected for {entity}: {old} -> {new}")
        self.execute_event.set()
