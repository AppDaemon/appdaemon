import uuid
import asyncio

from appdaemon.appdaemon import AppDaemon


class Sequences:

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.logger = ad.logging.get_child("_sequences")


    async def run_sequence_service(self, ns, domain, service, kwargs):
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]
            del kwargs["namespace"]
        else:
            namespace = "default"

        # await self.run_sequence("_services", namespace, kwargs["entity_id"])
        self.AD.thread_async.call_async_no_wait(self.run_sequence, "_services", namespace, kwargs["entity_id"])


    async def add_sequences(self, sequences):
        for sequence in sequences:
            await self.AD.state.add_entity("rules", "sequence.{}".format(sequence), "idle",
                                           attributes={"friendly_name": sequences[sequence].get("name", sequence),
                                                       "steps": sequences[sequence]["steps"]})


    async def run_sequence(self, _name, namespace, sequence):
        ephemeral_entity = False

        if isinstance(sequence, str):
            entity_id = sequence
            if await self.AD.state.entity_exists("rules", entity_id) is False:
                self.logger.warning('Unknown sequence "%s" in run_sequence()', sequence)
                return None

            entity = await self.AD.state.get_state("_services", "rules", sequence, attribute="all")
            seq = entity["attributes"]["steps"]
        else:
            #
            # Assume it's a list with the actual commands in it
            #
            entity_id = "sequence.{}".format(uuid.uuid4().hex)
            # Create an ephemeral entity for it
            ephemeral_entity = True

            await self.AD.state.add_entity("rules", entity_id, "idle", attributes={"steps": sequence})

            seq = sequence

        #
        # OK, lets run it
        #

        await self.AD.state.set_state("_services", "rules", entity_id, state="active")

        for step in seq:
            for command, parameters in step.items():
                if command == "sleep":
                    await asyncio.sleep(float(parameters))
                else:
                    domain, service = str.split(command, "/")
                    if "namespace" in parameters:
                        ns = parameters["namespace"]
                        del parameters["namespace"]
                    else:
                        ns = namespace

                    await self.AD.services.call_service(ns, domain, service, parameters)

        await self.AD.state.set_state("_services", "rules", entity_id, state="idle")

        if ephemeral_entity is True:
            await self.AD.state.remove_entity("rules", entity_id)