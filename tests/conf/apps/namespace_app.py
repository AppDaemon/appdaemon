import asyncio
import functools
from datetime import timedelta
from typing import Any

from appdaemon.adapi import ADAPI, Entity


class BasicNamespaceTester(ADAPI):
    changed_event: asyncio.Event

    def initialize(self) -> None:
        self.set_log_level("DEBUG")
        self.changed_event = asyncio.Event()
        self.set_namespace(self.custom_test_namespace)
        self.logger.info("Initial namespaces: %s", sorted(self.current_namespaces))

        exists = self.test_entity.exists()
        self.logger.info("Entity exists: %s", exists)
        if not exists:
            self.add_entity("sensor.test", state="initial", attributes={"friendly_name": "Test Sensor"})

        non_existence = "sensor.other_entity"
        self.logger.info("Setting %s in namespace %s", non_existence, self.namespace)
        self.set_state(non_existence, state="other", attributes={"friendly_name": "Other Entity"})

        self.test_entity.listen_state(self.handle_state)
        self.run_in(self.start_test, self.start_delay)
        self.logger.info("Initialized %s", self.name)

    @property
    def current_namespaces(self) -> set[str]:
        return set(self.AD.state.state.keys())

    @property
    def custom_test_namespace(self) -> str:
        return self.args.get("custom_namespace", "test_namespace")

    @property
    def start_delay(self) -> timedelta:
        return timedelta(seconds=self.args.get("start_delay", 1.0))

    @property
    def test_entity(self) -> Entity:
        return self.get_entity("sensor.test", check_existence=False)

    async def show_entities(self, *args, **kwargs) -> None:
        ns = self.AD.state.state.get(self.custom_test_namespace, {})
        entities = sorted(ns.keys())
        self.logger.info("Test entities: %s", entities)

    def start_test(self, *args, **kwargs: Any) -> None:
        match kwargs:
            case {"__thread_id": str(thread_id)}:
                self.logger.info("Change called from thread %s", thread_id)
        self.test_entity.set_state("changed")

    async def handle_state(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> None:
        self.logger.info("State changed for %s: %s = %s -> %s", entity, attribute, old, new)
        self.logger.info("Test val: %s", self.args.get("test_val"))

        full_state = self.test_entity.get_state('all')
        self.log(f"Full state: {full_state}")
        self.changed_event.set()

    def terminate(self) -> None:
        self.set_namespace('default')
        self.remove_namespace(self.custom_test_namespace)


class HybridWritebackTester(ADAPI):
    def initialize(self) -> None:
        self.set_namespace(self.custom_test_namespace, writeback="hybrid", persist=True)
        # self.logger.info("Initialized %s in namespace '%s'", self.name, self.custom_test_namespace)

        self.run_in(self.rapid_changes, self.start_delay)
        self.logger.info("Initialized %s", self.name)

    @property
    def custom_test_namespace(self) -> str:
        return self.args.get("custom_namespace", "test_namespace")

    @property
    def start_delay(self) -> timedelta:
        return timedelta(seconds=self.args.get("start_delay", 1.0))

    @property
    def test_n(self) -> int:
        return self.args.get("test_n", 10)

    async def rapid_changes(self, *args, **kwargs) -> None:
        entity_id = "sensor.hybrid_test"

        for i in range(self.test_n):
            func = functools.partial(self.set_state,  entity_id, state=f"change_{i}")
            delay = i * 0.05
            self.AD.loop.call_later(delay, func)

    def terminate(self) -> None:
        self.set_namespace('default')
        self.remove_namespace(self.custom_test_namespace)
