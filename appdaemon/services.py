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

    def call_service(self, namespace, domain, service, data):
        with self.services_lock:
            if namespace not in self.services:
                self.logger.warning("Unknown namespace (%s) in call_service", namespace)
                return None
            if domain not in self.services[namespace]:
                self.logger.warning("Unknown domain (%s.%s) in call_service", namespace, domain)
            if service not in self.services[namespace][domain]:
                self.logger.warning("Unknown service (%s.%s.%s) in call_service", namespace, domain, service)

            try:
                funcref = self.services[namespace][domain][service]
                return funcref(namespace, domain, service, data)
            except:
                self.logger.warning('-' * 60)
                self.logger.warning("Unexpected error in namespace setup")
                self.logger.warning('-' * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning('-' * 60)
                return None
