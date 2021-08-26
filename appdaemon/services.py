import threading
import traceback
import asyncio
from copy import deepcopy
from typing import Any, Optional, Callable, Awaitable

from appdaemon.appdaemon import AppDaemon
from appdaemon.exceptions import NamespaceException
import appdaemon.utils as utils


class Services:
    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.services = {}
        self.services_lock = threading.RLock()
        self.app_registered_services = {}
        self.logger = ad.logging.get_child("_services")

    def register_service(
        self, namespace: str, domain: str, service: str, callback: Callable, **kwargs: Optional[dict]
    ) -> None:
        self.logger.debug(
            "register_service called: %s.%s.%s -> %s", namespace, domain, service, callback,
        )

        __silent = kwargs.pop("__silent", False)

        with self.services_lock:
            name = kwargs.get("__name")
            # first we confirm if the namespace exists
            if name and namespace not in self.AD.state.state:
                raise NamespaceException(f"Namespace '{namespace}', doesn't exist")

            elif not callable(callback):
                raise ValueError(f"The given callback {callback} is not a callable function")

            if namespace not in self.services:
                self.services[namespace] = {}

            if domain not in self.services[namespace]:
                self.services[namespace][domain] = {}

            if service in self.services[namespace][domain]:
                # there was a service already registered before
                # so if a different app, we ask to deregister first
                service_app = self.services[namespace][domain][service].get("__name")
                if service_app and service_app != name:
                    self.logger.warning(
                        f"This service '{domain}/{service}' already registered to a different app '{service_app}'. Do deregister from app first"
                    )
                    return

            self.services[namespace][domain][service] = {"callback": callback, **kwargs}

            if __silent is False:
                data = {
                    "event_type": "service_registered",
                    "data": {"namespace": namespace, "domain": domain, "service": service},
                }
                self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

            if name:
                if name not in self.app_registered_services:
                    self.app_registered_services[name] = set()

                self.app_registered_services[name].add(f"{namespace}:{domain}:{service}")

    def deregister_service(self, namespace: str, domain: str, service: str, **kwargs: dict) -> bool:
        """Used to unregister a service"""

        self.logger.debug(
            "deregister_service called: %s:%s:%s %s", namespace, domain, service, kwargs,
        )

        name = kwargs.get("__name")
        if not name:
            raise ValueError("App must be given to deregister service call")

        if name not in self.app_registered_services:
            raise ValueError("The given App %s has no services registered", name)

        app_service = f"{namespace}:{domain}:{service}"

        if app_service not in self.app_registered_services[name]:
            raise ValueError("The given App %s doesn't have the given service registered it", name)

        # if it gets here, then time to deregister
        with self.services_lock:
            # it belongs to the app
            del self.services[namespace][domain][service]

            data = {
                "event_type": "service_deregistered",
                "data": {"namespace": namespace, "domain": domain, "service": service, "app": name},
            }
            self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

            # now check if that domain is empty
            # if it is, remove it also
            if self.services[namespace][domain] == {}:
                # its empty
                del self.services[namespace][domain]

            # now check if that namespace is empty
            # if it is, remove it also
            if self.services[namespace] == {}:
                # its empty
                del self.services[namespace]

            self.app_registered_services[name].remove(app_service)

            if not self.app_registered_services[name]:
                del self.app_registered_services[name]

            return True

    def clear_services(self, name: str) -> None:
        """Used to clear services"""

        if name not in self.app_registered_services:
            return

        app_services = deepcopy(self.app_registered_services[name])

        for app_service in app_services:
            namespace, domain, service = app_service.split(":")
            self.deregister_service(namespace, domain, service, __name=name)

    def list_services(self, ns: str = "global") -> list:
        result = []
        with self.services_lock:
            for namespace in self.services:
                if ns != "global" and namespace != ns:
                    continue

                for domain in self.services[namespace]:
                    for service in self.services[namespace][domain]:
                        result.append({"namespace": namespace, "domain": domain, "service": service})

        return result

    async def call_service(self, namespace: str, domain: str, service: str, data: dict) -> Any:
        self.logger.debug(
            "call_service: namespace=%s domain=%s service=%s data=%s", namespace, domain, service, data,
        )
        with self.services_lock:
            name = data.pop("__name", None)

            if namespace not in self.services:
                self.logger.warning("Unknown namespace (%s) in call_service from %s", namespace, name)
                return None
            if domain not in self.services[namespace]:
                self.logger.warning(
                    "Unknown domain (%s/%s) in call_service from %s", namespace, domain, name,
                )
                return None
            if service not in self.services[namespace][domain]:
                self.logger.warning(
                    "Unknown service (%s/%s/%s) in call_service from %s", namespace, domain, service, name,
                )
                return None

            # If we have namespace in data it's an override for the domain of the eventual service call, as distinct
            # from the namespace the call itself is executed from. e.g. set_state() is in the AppDaemon namespace but
            # needs to operate on a different namespace, e.g. "default"

            if "namespace" in data:
                ns = data["namespace"]
                del data["namespace"]
            else:
                ns = namespace

            funcref = self.services[namespace][domain][service]["callback"]

            # Decide whether or not to call this as async

            # Default to true
            isasync = True

            # if to wait for results, default to False
            return_result = data.pop("return_result", False)

            # if to return results via callback
            callback = data.pop("callback", None)

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
                coro = funcref(ns, domain, service, data)
            else:
                # It's not a coroutine, , run it in an executor
                coro = utils.run_in_executor(self, funcref, ns, domain, service, data)

            if return_result is True:
                return await self.run_service(coro)

            elif callback is not None and name is not None:
                # results expected and it must belong to an app
                app_object = await self.AD.app_management.get_app(name)
                app_object.create_task(self.run_service(coro), callback=callback)

            else:
                asyncio.create_task(self.run_service(coro))

    async def run_service(self, coro: Awaitable) -> Any:
        """Used to process a service call"""
        try:
            return await coro

        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error in call_service()")
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)
            return None
