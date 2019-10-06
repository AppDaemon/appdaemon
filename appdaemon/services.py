import threading
import traceback
import asyncio
import uuid

from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils


class Services:

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.services = {}
        self.services_lock = threading.RLock()
        self.logger = ad.logging.get_child("_services")

    def register_service(self, namespace, domain, service, callback, **kwargs):
        self.logger.debug("register_service called: %s.%s.%s -> %s", namespace, domain, service, callback)
        with self.services_lock:
            if namespace not in self.services:
                self.services[namespace] = {}
            if domain not in self.services[namespace]:
                self.services[namespace][domain] = {}
            self.services[namespace][domain][service] = {"callback": callback, **kwargs}
            
            data = {
                "event_type": "service_registered", 
                    "data": {"domain": domain, "service" : service}
                }
            self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

    def list_services(self):
        result = []
        with self.services_lock:
            for namespace in self.services:
                for domain in self.services[namespace]:
                    for service in self.services[namespace][domain]:
                        result.append({"namespace": namespace, "domain": domain, "service": service})

        return result

    async def call_service(self, namespace, domain, service, data):
        self.logger.debug("call_service: namespace=%s domain=%s service=%s data=%s", namespace, domain, service, data)
        with self.services_lock:
            if namespace not in self.services:
                name = data.get("__name", None)
                self.logger.warning("Unknown namespace (%s) in call_service from %s", namespace, name)
                return None
            if domain not in self.services[namespace]:
                name = data.get("__name", None)
                self.logger.warning("Unknown domain (%s/%s) in call_service from %s", namespace, domain, name)
                return None
            if service not in self.services[namespace][domain]:
                name = data.get("__name", None)
                self.logger.warning("Unknown service (%s/%s/%s) in call_service from %s", namespace, domain, service, name)
                return None

            # If we have namespace in data it's an override for the domain of the eventual service call, as distinct
            # from the namespace the call itself is executed from. e.g. set_state() is in the AppDaemon namespace but
            # needs to operate on a different namespace, e.g. "default"
            
            if "__name" in data:
                del data["__name"]

            if "namespace" in data:
                ns = data["namespace"]
                del data["namespace"]
            else:
                ns = namespace

            try:
                funcref = self.services[namespace][domain][service]["callback"]

                # Decide whether or not to call this as async

                # Default to true
                isasync = True

                if "__async" in self.services[namespace][domain][service]:
                    # We have a kwarg to tell us what to do
                    if self.services[namespace][domain][service]["__async"] == "auto":
                        # We decide based on introspection
                        if not asyncio.iscoroutinefunction(funcref):
                            isasync = False
                    else:
                        # We do what the kwarg tells us
                        isasync = self.services[namespace][domain][service]["__async"]

                if isasync is True:
                    # it's a coroutine just await it.
                    return await funcref(ns, domain, service, data)
                else:
                    # It's not a coroutine, , run it in an executor
                    return await utils.run_in_executor(self, funcref, ns, domain, service, data)

            except:
                self.logger.warning('-' * 60)
                self.logger.warning("Unexpected error in call_service()")
                self.logger.warning('-' * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning('-' * 60)
                return None

    async def run_sequence_service(self, ns, domain, service, kwargs):
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]
            del kwargs["namespace"]
        else:
            namespace = "default"

        #await self.run_sequence("_services", namespace, kwargs["entity_id"])
        self.AD.thread_async.call_async_no_wait(self.run_sequence, "_services", namespace, kwargs["entity_id"])

    async def add_sequences(self, sequences):
        for sequence in sequences:
            await self.AD.state.add_entity("rules", "sequence.{}".format(sequence), "idle", attributes={"friendly_name": sequences[sequence].get("name", sequence), "steps": sequences[sequence]["steps"]})

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

                    await self.call_service(ns, domain, service, parameters)

        await self.AD.state.set_state("_services", "rules", entity_id, state="idle")

        if ephemeral_entity is True:
            await self.AD.state.remove_entity("rules", entity_id)