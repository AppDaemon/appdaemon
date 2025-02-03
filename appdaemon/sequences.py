import asyncio
import copy
import traceback
import uuid
from logging import Logger
from typing import TYPE_CHECKING

from appdaemon.entity import Entity
from appdaemon.exceptions import TimeOutException
from appdaemon.models.config.sequence import SequenceConfig

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

    # async def get_state(self):
    #     return

    async def set_state(self, entity_id: str, state: str, replace: bool = False, **kwargs):
        return await self.AD.state.set_state(
            name="_sequences",
            namespace=self.namespace,
            entity=entity_id,
            state=state,
            replace=replace,
            **kwargs
        )

    async def run_sequence_service(self, namespace, domain, service, kwargs):
        if "entity_id" not in kwargs:
            self.logger.warning(
                "entity_id not given in service call, so will not be executing %s", service)
            return

        entity_id = kwargs["entity_id"]

        if service == "run":
            return await self.run_sequence("_services", namespace, entity_id)

        elif service == "cancel" and isinstance(entity_id, str):
            return await self.cancel_sequence(entity_id)

    async def add_sequences(self, sequences: SequenceConfig):
        self.logger.debug(f'Adding sequences: {set(sequences.root.keys())}')

        for seq_name, seq_cfg in sequences.root.items():
            attributes = {
                "friendly_name": seq_cfg.name or seq_name,
                "loop": seq_cfg.loop,
                "steps": seq_cfg.steps
            }

            if seq_cfg.namespace is not None:
                attributes["namespace"] = seq_cfg.namespace

            entity = f"sequence.{seq_name}"
            if self.sequence_exists(entity):
                # means existing before so in case already running already
                await self.cancel_sequence(seq_name)
                await self.set_state(entity, state="idle", replace=True, **attributes)
            else:
                # it doesn't exist so add it
                await self.add_entity(entity, state="idle", **attributes)

            # create sequence objects
            self.AD.app_management.init_sequence_object(f"sequence_{seq_name}", seq_cfg)

    async def remove_sequences(self, sequences):
        if not isinstance(sequences, list):
            sequences = [sequences]

        for sequence in sequences:
            # remove sequence
            await self.cancel_sequence(sequence)
            await self.AD.state.remove_entity("rules", "sequence.{}".format(sequence))

    async def run_sequence(self, _name: str, namespace: str, sequence: str):
        if isinstance(sequence, str):
            if "." in sequence:
                # the entity given
                _, sequence_name = sequence.split(".")

            else:  # just name given
                sequence_name = sequence
                sequence = f"sequence.{sequence}"

            name = f"sequence_{sequence_name}"

        else:
            name = _name

        coro = self.prep_sequence(_name, namespace, sequence)

        #
        # OK, lets run it
        #

        future = asyncio.create_task(coro)
        self.AD.futures.add_future(name, future)

        return future

    async def cancel_sequence(self, sequence):
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

    async def prep_sequence(self, _name: str, namespace: str, sequence: str | list[dict]):
        ephemeral_entity = False
        loop = False

        if isinstance(sequence, str):
            entity_id = sequence
            if not self.sequence_exists(entity_id):
                self.logger.warning('Unknown sequence "%s" in run_sequence()', sequence)
                return

            entity = await self.AD.state.get_state("_services", "rules", sequence, attribute="all")
            seq = entity["attributes"]["steps"]
            loop = entity["attributes"]["loop"]
            ns = entity["attributes"].get("namespace", namespace)

        else:
            #
            # Assume it's a list with the actual commands in it
            #
            entity_id = "sequence.{}".format(uuid.uuid4().hex)
            # Create an ephemeral entity for it
            ephemeral_entity = True

            await self.AD.state.add_entity("rules", entity_id, "idle", attributes={"steps": sequence})

            seq = sequence
            ns = namespace

        coro = await self.do_steps(ns, entity_id, seq, ephemeral_entity, loop)
        return coro

    async def do_steps(self, namespace, entity_id, seq, ephemeral_entity, loop):
        await self.AD.state.set_state("_sequences", "rules", entity_id, state="active")
        try:
            while True:
                steps = copy.deepcopy(seq)
                for step in steps:
                    for command, parameters in step.items():
                        if isinstance(parameters, dict) and "namespace" in parameters:
                            ns = parameters.pop("namespace")
                        else:
                            ns = namespace

                        if command == "sleep":
                            await asyncio.sleep(float(parameters))

                        elif command == "sequence":
                            # Running a sub-sequence so just recurse
                            await self.prep_sequence("_sequence", namespace, parameters)

                        elif command == "wait_state":
                            if ephemeral_entity is True:
                                self.logger.warning(
                                    "Cannot process command 'wait_state', as not supported in sequence")
                                continue

                            _, entity_name = entity_id.split(".")
                            name = f"sequence_{entity_name}"

                            wait_entity = parameters.get("entity_id")

                            if wait_entity is None:
                                self.logger.warning(
                                    "Cannot process command 'wait_state', as entity_id not given")
                                continue

                            state = parameters.get("state")
                            attribute = parameters.get("attribute")
                            duration = parameters.get("duration", 0)
                            timeout = parameters.get("timeout", 15 * 60)

                            # now we create the wait entity object
                            entity_object = Entity(
                                self.logger, self.AD, name, ns, wait_entity)
                            if not await entity_object.exists():
                                self.logger.warning(
                                    f"Waiting for an entity {wait_entity}, in sequence {
                                        entity_name}, that doesn't exist"
                                )

                            try:
                                await entity_object.wait_state(state, attribute, duration, timeout)
                            except TimeOutException:
                                self.logger.warning(
                                    f"{entity_name} sequence wait for {
                                        wait_entity} timed out, so continuing sequence"
                                )

                        else:
                            domain, service = str.split(command, "/")
                            # parameters["__name"] = entity_id
                            loop_step = parameters.pop("loop_step", None)
                            params = copy.deepcopy(parameters)
                            await self.AD.services.call_service(ns, domain, service, entity_id, params)

                            # we need to loop this command multiple times
                            if isinstance(loop_step, dict):
                                await self.loop_step(ns, command, parameters, loop_step)

                if loop is not True:
                    break

        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error in do_steps()")
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)

        finally:
            await self.AD.state.set_state("_sequences", "rules", entity_id, state="idle")

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
