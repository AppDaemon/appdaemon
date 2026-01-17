import functools
from datetime import timedelta
from typing import Any

from appdaemon.adapi import ADAPI, Entity


class BasicNamespaceTester(ADAPI):
    handle: str | None

    def initialize(self) -> None:
        self.set_namespace(self.custom_test_namespace)
        self.logger.info('Current namespaces: %s', sorted(self.current_namespaces))
        self.run_in(self.show_entities, 0)

        exists = self.test_entity.exists()
        self.logger.info(f"Entity exists: {exists}")
        if not exists:
            self.add_entity("sensor.test", state="initial", attributes={"friendly_name": "Test Sensor"})

        self.run_in(self.show_entities, 0)

        non_existence = "sensor.other_entity"
        self.logger.info("Setting %s in default namespace", non_existence)
        self.set_state(non_existence, state="other", attributes={"friendly_name": "Other Entity"})

        self.run_in(self.start_test, self.start_delay)
        self.test_entity.listen_state(self.handle_state)
        self.log(f"Initialized {self.name}")

        self.set_namespace('default')
        self.remove_namespace(self.custom_test_namespace)

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
        self.log('Test entities: %s', entities)

    def start_test(self, *args, **kwargs: Any) -> None:
        match kwargs:
            case {"__thread_id": str(thread_id)}:
                self.log(f"Change called from thread {thread_id}")
        self.test_entity.set_state("changed")

    def handle_state(self, entity: str, attribute: str, old: Any, new: Any, **kwargs: Any) -> None:
        self.log(f"State changed for {entity}: {attribute} = {old} -> {new}")
        self.log(f"Test val: {self.args.get('test_val')}")

        full_state = self.test_entity.get_state('all')
        self.log(f"Full state: {full_state}")

    def terminate(self) -> None:
        self.set_namespace('default')
        self.remove_namespace(self.custom_test_namespace)


class HybridWritebackTester(ADAPI):
    def initialize(self) -> None:
        self.AD.logging.get_child("_state")
        self.set_namespace(self.custom_test_namespace, writeback="hybrid", persist=True)
        self.logger.info("Initialized %s in namespace '%s'", self.name, self.custom_test_namespace)

        self.run_in(self.rapid_changes, self.start_delay)

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
        for i in range(self.test_n):
            func = functools.partial(self.set_state,  "sensor.hybrid_test", state=f"change_{i}")
            delay = i * 0.05
            self.AD.loop.call_later(delay, func)

    def terminate(self) -> None:
        self.set_namespace('default')
        self.remove_namespace(self.custom_test_namespace)
