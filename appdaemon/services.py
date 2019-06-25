import threading
import traceback

from appdaemon.appdaemon import AppDaemon


class Services:

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.services = {}
        self.services_lock = threading.RLock()
        self.logger = ad.logging.get_child("_services")

    def register_service(self, namespace, domain, service, callback):
        self.logger.debug("register_service called: %s.%s.%s -> %s", namespace, domain, service, callback)
        with self.services_lock:
            if namespace not in self.services:
                self.services[namespace] = {}
            if domain not in self.services[namespace]:
                self.services[namespace][domain] = {}
            self.services[namespace][domain][service] = callback

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

            # If we have namespace in data it's an override for the domain of the eventual serice call, as distinct
            # from the namespace the call itself is executed from. e.g. set_state() is in the AppDaemon namespace but
            # needs to operate on a different namespace, e.g. "default"

            if "namespace" in data:
                ns = data["namespace"]
                del data["namespace"]
            else:
                ns = namespace

            try:
                funcref = self.services[namespace][domain][service]
                return await funcref(ns, domain, service, data)
            except:
                self.logger.warning('-' * 60)
                self.logger.warning("Unexpected error in namespace setup")
                self.logger.warning('-' * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning('-' * 60)
                return None
