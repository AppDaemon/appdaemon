import threading
import traceback
import asyncio

from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils


class Services:

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.services = {}
        self.services_lock = threading.RLock()
        self.logger = ad.logging.get_child("_services")
        self.sequence = {}

    def register_service(self, namespace, domain, service, callback, **kwargs):
        self.logger.debug("register_service called: %s.%s.%s -> %s", namespace, domain, service, callback)
        with self.services_lock:
            if namespace not in self.services:
                self.services[namespace] = {}
            if domain not in self.services[namespace]:
                self.services[namespace][domain] = {}
            self.services[namespace][domain][service] = {"callback": callback, **kwargs}

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
                self.logger.warning("Unknown namespace (%s) in call_service", namespace)
                return None
            if domain not in self.services[namespace]:
                self.logger.warning("Unknown domain (%s/%s) in call_service", namespace, domain)
                return None
            if service not in self.services[namespace][domain]:
                self.logger.warning("Unknown service (%s/%s/%s) in call_service", namespace, domain, service)
                return None

            # If we have namespace in data it's an override for the domain of the eventual service call, as distinct
            # from the namespace the call itself is executed from. e.g. set_state() is in the AppDaemon namespace but
            # needs to operate on a different namespace, e.g. "default"

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

    async def run_sequence(self, _name, namespace, sequence, **kwargs):
        if isinstance(sequence, str):
            if sequence not in self.sequence:
                self.logger.warning('Unknown sequence "%s" in call_service', sequence)
                return None

            seq = self.sequence[sequence]
        else:
            #
            # Assume it's a dict with the actual commands in it
            #
            seq = sequence

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
