import asyncio
import copy
import traceback
import uuid
from logging import Logger
from typing import TYPE_CHECKING

from .models.config.sequence import SequenceConfig, SequenceStep, ServiceCallStep, SleepStep, SubSequenceStep, WaitStateStep

if TYPE_CHECKING:
    from .appdaemon import AppDaemon


class Sequences:
    """Subsystem container for managing sequences

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"
    logger: Logger
    namespace: str = "rules"

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child("_sequences")

    def sequence_exists(self, entity_id: str) -> bool:
        return self.AD.state.entity_exists(self.namespace, entity_id)

    async def add_entity(self, entity_id: str, state: str, **kwargs):
        return await self.AD.state.add_entity(
            namespace=self.namespace,
            entity=entity_id,
            state=state,
            attributes=kwargs
        )

    async def set_state(self, entity_id: str, state: str = None, replace: bool = False, **kwargs):
        return await self.AD.state.set_state(
            name="_sequences",
            namespace=self.namespace,
            entity=entity_id,
            state=state,
            replace=replace,
            **kwargs
        )

    async def get_state(self, entity_id: str = None, attribute: str = None, copy: bool = True):
        return await self.AD.state.get_state(
            name="_sequences",
            namespace=self.namespace,
            entity_id=entity_id,
            attribute=attribute,
            copy=copy
        )
    
    def sequence_running(self, entity_id: str) -> bool:
        return self.get_state(entity_id, copy=False) == "active"

    async def running_sequences(self):
        return {
            entity_id: state
            for entity_id, state in (await self.get_state(copy=False)).items()
            if state.get("state") == "active"
        }

    async def run_sequence_service(self, namespace: str, domain: str, service: str, kwargs):
        if entity_id := kwargs.get("entity_id"):
            match service:
                case "run":
                    return await self.run_sequence("_services", namespace, entity_id)
                case "cancel":
                    if isinstance(entity_id, str):
                        return await self.cancel_sequence(entity_id)
        else:
            self.logger.warning(
                f"entity_id not given in service call, so will not be executing {service}"
            )

    async def update_sequence_entities(self, sequences: SequenceConfig):
        for seq_name, seq_cfg in sequences.root.items():
            entity = f"sequence.{seq_name}"

            attributes = {
                "entity_id": entity,
                "state": "idle",
                "friendly_name": seq_cfg.name or seq_name,
                "loop": seq_cfg.loop,
                "steps": seq_cfg.steps
            }

            if self.sequence_exists(entity):
                await self.set_state(replace=True, **attributes)
            else:
                await self.add_entity(**attributes)

            # create sequence objects
            self.AD.app_management.init_sequence_object(f"sequence_{seq_name}", seq_cfg)

    async def remove_sequences(self, sequences):
        if not isinstance(sequences, list):
            sequences = [sequences]

        for sequence in sequences:
            # remove sequence
            await self.cancel_sequence(sequence)
            await self.AD.state.remove_entity("rules", "sequence.{}".format(sequence))

    async def run_sequence(self, calling_app: str, namespace: str, sequence: str):
        """Prepares the sequence and creates a task to run it"""
        if isinstance(sequence, str):
            if "." in sequence:
                # the entity given
                _, sequence_name = sequence.split(".", 2)

            else:  # just name given
                sequence_name = sequence
                sequence = f"sequence.{sequence}"

            name = f"sequence_{sequence_name}"

        else:
            name = calling_app

        coro = self.prep_sequence(namespace, sequence)
        task = asyncio.create_task(coro)
        self.AD.futures.add_future(name, task)
        return task

    async def cancel_sequence(self, sequence):
        self.logger.debug(f'Cancelling sequence: {sequence}')

        if isinstance(sequence, str):
            if "." in sequence:
                # the entity given
                _, sequence_name = sequence.split(".")
                entity_id = sequence

            else:  # just name given
                sequence_name = sequence
                entity_id = f"sequence.{sequence}"

        else:  # future given
            sequence.cancel()
            return

        name = f"sequence_{sequence_name}"
        self.AD.futures.cancel_futures(name)
        await self.AD.state.set_state("_sequences", "rules", entity_id, state="idle")

    async def prep_sequence(self, namespace: str, sequence: str | list[dict[str, dict[str, str]]]):
        match sequence:
            case str():
                seq_eid = sequence
                if not self.sequence_exists(seq_eid):
                    self.logger.warning('Unknown sequence "%s" in run_sequence()', sequence)
                    return

                entity = await self.get_state(sequence, attribute="all")
                seq = entity["attributes"]["steps"]
                loop = entity["attributes"]["loop"]
                ns = entity["attributes"].get("namespace", namespace)
            case list():
                ns = namespace
                seq = sequence
                loop = False
                seq_eid = f"sequence.{uuid.uuid4().hex}"
                await self.add_entity(seq_eid, "active", steps=sequence)

        ephemeral_entity = not isinstance(sequence, str)
        coro = await self.do_steps(ns, seq_eid, seq, ephemeral_entity, loop)
        return coro

    async def do_steps(
        self,
        namespace: str,
        entity_id: str,
        seq: list[SequenceStep],
        ephemeral_entity: bool,
        loop: bool
    ):
        await self.set_state(entity_id, "active", running_namespace=namespace)
        try:
            while True:
                steps = copy.deepcopy(seq)
                for step in steps:
                    try:
                        match step:
                            case ServiceCallStep():
                                kwargs = {
                                    "namespace": step.namespace or namespace,
                                    "domain": step.domain,
                                    "service": step.service,
                                    "name": "sequence",
                                    "data": step.model_extra
                                }

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
                                if ephemeral_entity:
                                    self.logger.warning(
                                        "Cannot process command 'wait_state', as not supported in sequence")
                                    continue
                            case SubSequenceStep():
                                await self.prep_sequence(
                                    namespace=step.namespace or namespace,
                                    sequence=entity_id
                                )
                    except Exception as e:
                        self.logger.error(f"Unexpected error in do_steps(): {e}")
                        raise

                if not loop:
                    break

        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error in do_steps()")
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)

        finally:
            await self.set_state(entity_id, "idle")

            if ephemeral_entity is True:
                await self.AD.state.remove_entity("rules", entity_id)

    async def loop_step(self, namespace: str, command: str, parameters: dict, loop_step: dict) -> None:
        """Used to loop a step command"""

        try:
            times = int(loop_step.get("times", 0))
            interval = float(loop_step.get("interval", 1))
            ran_times = 0

            domain, service = str.split(command, "/")

            while ran_times < times:
                params = copy.deepcopy(parameters)
                await asyncio.sleep(interval)
                await self.AD.services.call_service(namespace, domain, service, params)
                ran_times += 1

        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error in loop_step()")
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)

    #
    # Placeholder for constraints
    #
    def list_constraints(self):
        return []
