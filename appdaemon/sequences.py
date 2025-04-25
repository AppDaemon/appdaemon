import asyncio
import uuid
from collections.abc import Iterable
from logging import Logger
from typing import TYPE_CHECKING

from pydantic import ValidationError

from . import exceptions as ade
from . import utils
from .models.config.sequence import Sequence, SequenceConfig, SequenceStep, ServiceCallStep, SleepStep, SubSequenceStep, WaitStateStep

if TYPE_CHECKING:
    from .appdaemon import AppDaemon


class Sequences:
    """Subsystem container for managing sequences

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"
    logger: Logger
    error: Logger
    namespace: str = "rules"
    name: str = "_sequences"  # needed for the sync decorator to work

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child("_sequences")
        self.error = ad.logging.get_error()

    @property
    def config(self) -> SequenceConfig | None:
        return self.AD.app_management.sequence_config

    @staticmethod
    def normalized(sequence: str) -> str:
        """Ensures the sequence name is prefixed with ``sequence.``"""
        if sequence.startswith("sequence."):
            return sequence
        return f"sequence.{sequence}"

    def sequence_exists(self, sequence: str) -> bool:
        return self.AD.state.entity_exists(self.namespace, self.normalized(sequence))

    async def set_state(self, entity_id: str, state: str = None, replace: bool = False, **kwargs):
        return await self.AD.state.set_state(name="_sequences", namespace=self.namespace, entity=self.normalized(entity_id), state=state, replace=replace, **kwargs)

    async def get_state(self, entity_id: str = None, attribute: str = None, copy: bool = True):
        return await self.AD.state.get_state(name=self.name, namespace=self.namespace, entity_id=self.normalized(entity_id) if entity_id else None, attribute=attribute, copy=copy)

    async def sequence_running(self, sequence: str) -> bool:
        state = await self.get_state(sequence, copy=False)
        return state == "active"

    async def running_sequences(self):
        return {entity_id: state for entity_id, state in (await self.get_state()).items() if state.get("state") == "active"}

    async def run_sequence_service(self, namespace: str, domain: str, service: str, kwargs):
        if entity_id := kwargs.get("entity_id"):
            match service:
                case "run":
                    return await self.run_sequence("_services", namespace, entity_id)
                case "cancel":
                    if isinstance(entity_id, str):
                        return await self.cancel_sequence(entity_id)
        else:
            self.logger.warning(f"entity_id not given in service call, so will not be executing {service}")

    async def update_sequence_entities(self, config: SequenceConfig | None = None):
        if config is None:
            return
        else:
            for seq_name, cfg in config.root.items():
                # Entities will get created if they don't exist
                await self.set_state(
                    entity_id=self.normalized(seq_name),
                    state="idle",
                    friendly_name=cfg.name or seq_name,
                    loop=cfg.loop,
                    steps=cfg.steps,
                    replace=True,
                    _silent=True,
                )

    async def remove_sequences(self, sequences: str | Iterable[str]):
        if isinstance(sequences, str):
            sequences = [sequences]

        for sequence in sequences:
            await self.cancel_sequence(sequence)
            await self.AD.state.remove_entity(self.namespace, self.normalized(sequence))

    async def run_sequence(
        self,
        calling_app: str,
        namespace: str,
        sequence: str | list[dict[str, dict[str, str]]],
    ) -> asyncio.Task:
        """Prepares the sequence and creates a task to run it"""
        try:
            match sequence:
                # Sequence was defined in the config
                case str():
                    ephemeral_entity = False
                    seq_eid = self.normalized(sequence)
                    seq_name = seq_eid.split(".", 2)[1]

                    if (cfg := self.config.root.get(seq_name)) is None:
                        self.logger.warning(f'Unknown sequence "{seq_name}" in run_sequence()')
                        return

                    is_running = await self.sequence_running(seq_eid)
                    if is_running:
                        self.logger.warning(f"Sequence '{seq_name}' is already running")
                        return

                # Sequence was defined in-line
                case list():
                    ephemeral_entity = True
                    seq_name = uuid.uuid4().hex
                    seq_eid = f"sequence.{seq_name}"
                    try:
                        cfg = Sequence(name=seq_eid, namespace=namespace, steps=sequence)
                    except ValidationError as e:
                        self.logger.error(f"Error creating inline sequence:\n{e}")
                        return
        except Exception as e:
            raise ade.SequenceExecutionFail(sequence) from e

        coro = self._exec_seq(calling_app=calling_app, namespace=namespace, entity_id=seq_eid, steps=cfg.steps, loop=cfg.loop)
        task = asyncio.create_task(coro, name=seq_eid)
        self.AD.futures.add_future(calling_app, task)

        if ephemeral_entity:
            task.add_done_callback(lambda _: self.AD.loop.create_task(self.AD.state.remove_entity(self.namespace, seq_eid)))

        if cfg.hot_reload:
            deps = self.AD.app_management.dependency_manager.app_deps.dep_graph.get(calling_app, set())
            deps.add(seq_eid)
            task.add_done_callback(lambda _: deps.remove(seq_eid))

        return task

    async def cancel_sequence(self, sequence: str):
        sequence = self.normalized(sequence)
        for app_futures in self.AD.futures.futures.values():
            for future in app_futures:
                if isinstance(future, asyncio.Task) and future.get_name() == sequence:
                    self.AD.futures.cancel_future(future)

    @utils.warning_decorator(error_text="Unexpected error executing sequence")
    async def _exec_seq(self, calling_app: str, namespace: str, entity_id: str, steps: list[SequenceStep], loop: bool = False):
        await self.set_state(entity_id, "active", _silent=True)
        try:
            while not self.AD.stopping:
                for i, step in enumerate(steps):
                    try:
                        await self._exec_step(step, namespace, calling_app)
                    except ade.AppDaemonException as exc:
                        raise ade.SequenceStepExecutionFail(i + 1, step) from exc
                if not loop:
                    break
        finally:
            await self.set_state(entity_id, "idle")

    async def _exec_step(self, step: SequenceStep, default_namespace: str, calling_app: str):
        match step:
            case ServiceCallStep():
                kwargs = {
                    "namespace": step.namespace or default_namespace,
                    "domain": step.domain,
                    "service": step.service,
                    "data": step.model_extra
                }  # fmt: skip

                if loop_step := step.loop_step:
                    for _ in range(loop_step.times):
                        await self.AD.services.call_service(**kwargs)
                        await asyncio.sleep(loop_step.interval.total_seconds())
                else:
                    await self.AD.services.call_service(**kwargs)
            case SleepStep():
                self.logger.debug(f"Sleeping for {step.sleep}")
                await asyncio.sleep(step.sleep.total_seconds())
            case WaitStateStep():
                self.logger.warning("Cannot process command 'wait_state', as not supported in sequence")
            case SubSequenceStep():
                task = self.run_sequence(calling_app=calling_app, namespace=step.namespace or default_namespace, sequence=self.normalized(step.sequence))
                await task

    #
    # Placeholder for constraints
    #
    def list_constraints(self):
        return []
