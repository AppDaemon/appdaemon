import uuid
import asyncio

from appdaemon.appdaemon import AppDaemon


class Sequences:
    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.logger = ad.logging.get_child("_sequences")

    async def run_sequence_service(self, namespace, domain, service, kwargs):
        if "entity_id" not in kwargs:
            self.logger.warning("entity_id not given in service call, so will not be executing %s", service)
            return

        # await self.run_sequence("_services", namespace, kwargs["entity_id"])
        self.AD.thread_async.call_async_no_wait(self.run_sequence, "_services", namespace, kwargs["entity_id"])

    async def add_sequences(self, sequences):
        for sequence in sequences:
            entity = "sequence.{}".format(sequence)
            attributes = {
                "friendly_name": sequences[sequence].get("name", sequence),
                "loop": sequences[sequence].get("loop", False),
                "steps": sequences[sequence]["steps"],
            }

            if not await self.AD.state.entity_exists("rules", entity):
                # it doesn't exist so add it
                await self.AD.state.add_entity(
                    "rules", entity, "idle", attributes=attributes,
                )
            else:
                await self.AD.state.set_state(
                    "_sequences", "rules", entity, state="idle", attributes=attributes, replace=True
                )

    async def remove_sequences(self, sequences):
        if not isinstance(sequences, list):
            sequences = [sequences]

        for sequence in sequences:
            await self.AD.state.remove_entity("rules", "sequence.{}".format(sequence))

    async def run_sequence(self, _name, namespace, sequence):
        coro = self.prep_sequence(_name, namespace, sequence)

        #
        # OK, lets run it
        #

        future = asyncio.ensure_future(coro)
        self.AD.futures.add_future(_name, future)

        return future

    async def prep_sequence(self, _name, namespace, sequence):
        ephemeral_entity = False
        loop = False
        if isinstance(sequence, str):
            entity_id = sequence
            if await self.AD.state.entity_exists("rules", entity_id) is False:
                self.logger.warning('Unknown sequence "%s" in run_sequence()', sequence)
                return None

            entity = await self.AD.state.get_state("_services", "rules", sequence, attribute="all")
            seq = entity["attributes"]["steps"]
            loop = entity["attributes"]["loop"]
        else:
            #
            # Assume it's a list with the actual commands in it
            #
            entity_id = "sequence.{}".format(uuid.uuid4().hex)
            # Create an ephemeral entity for it
            ephemeral_entity = True

            await self.AD.state.add_entity("rules", entity_id, "idle", attributes={"steps": sequence})

            seq = sequence

        coro = await self.do_steps(namespace, entity_id, seq, ephemeral_entity, loop)

        return coro

    @staticmethod
    async def cancel_sequence(_name, future):
        future.cancel()

    async def do_steps(self, namespace, entity_id, seq, ephemeral_entity, loop):

        await self.AD.state.set_state("_sequences", "rules", entity_id, state="active")

        try:
            while True:
                for step in seq:
                    for command, parameters in step.items():
                        if command == "sleep":
                            await asyncio.sleep(float(parameters))
                        elif command == "sequence":
                            # Running a sub-sequence so just recurse
                            await self.prep_sequence("_sequence", namespace, parameters)
                            pass
                        else:
                            domain, service = str.split(command, "/")
                            if "namespace" in parameters:
                                ns = parameters["namespace"]
                                del parameters["namespace"]
                            else:
                                ns = namespace
                            parameters["__name"] = entity_id
                            await self.AD.services.call_service(ns, domain, service, parameters)
                if loop is not True:
                    break
        finally:
            await self.AD.state.set_state("_sequences", "rules", entity_id, state="idle")

            if ephemeral_entity is True:
                await self.AD.state.remove_entity("rules", entity_id)
