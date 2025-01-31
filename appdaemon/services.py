import asyncio
import threading
from copy import deepcopy
from dataclasses import dataclass
from logging import Logger
from typing import TYPE_CHECKING, Any, Callable, Dict, Set, overload

import appdaemon.utils as utils
from appdaemon.exceptions import DomainException, NamespaceException, ServiceException

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


@dataclass
class ServiceDefinition:
    __name: str | None = None
    callback: str | None = None


@dataclass
class DomainServices:
    _services: dict[str, ServiceDefinition]


@dataclass
class NamespaceServices:
    _services: dict[str, DomainServices]


@dataclass
class ServiceCollection:
    _services: dict[str, NamespaceServices]


class Services:
    """Subsystem container for handling services

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"
    logger: Logger
    error: Logger
    services: Dict[str, Dict[str, Any]]
    services_lock: threading.RLock
    app_registered_services: Dict[str, Set]

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.services = {}
        self.services_lock = threading.RLock()
        self.app_registered_services = {}
        self.logger = ad.logging.get_child("_services")

    @property
    def error(self) -> Logger:
        return self.AD.logging.get_error()

    @overload
    def register_service(
        self,
        namespace: str,
        domain: str,
        service: str,
        callback: Callable,
        __slient: bool,
        __name: str,
        **kwargs
    ) -> None: ...

    def register_service(self, namespace: str, domain: str, service: str, callback: Callable, **kwargs) -> None:
        self.logger.debug(
            "register_service called: %s.%s.%s -> %s",
            namespace,
            domain,
            service,
            callback,
        )

        __silent = kwargs.pop("__silent", False)

        with self.services_lock:
            name = kwargs.get("__name")
            # first we confirm if the namespace exists
            if name and namespace not in self.AD.state.state:
                raise NamespaceException(
                    f"Namespace {namespace}, doesn't exist")

            elif not callable(callback):
                raise ValueError(f"The given callback {
                                 callback} is not a callable function")

            if namespace not in self.services:
                self.services[namespace] = {}

            if domain not in self.services[namespace]:
                self.services[namespace][domain] = {}

            if service in self.services[namespace][domain]:
                # there was a service already registered before
                # so if a different app, we ask to deregister first
                service_app = self.services[namespace][domain][service].get(
                    "__name")
                if service_app and service_app != name:
                    self.logger.warning(
                        f"This service '{domain}/{service}' already registered to a different app '{
                            service_app}', and so cannot be registered to {name}. Do deregister from app first"
                    )
                    return

            self.services[namespace][domain][service] = {
                "callback": callback, "__name": name, **kwargs}

            if __silent is False:
                data = {
                    "event_type": "service_registered",
                    "data": {"namespace": namespace, "domain": domain, "service": service},
                }
                self.AD.loop.create_task(
                    self.AD.events.process_event(namespace, data))

            if name:
                if name not in self.app_registered_services:
                    self.app_registered_services[name] = set()

                self.app_registered_services[name].add(
                    f"{namespace}:{domain}:{service}")

    def deregister_service(self, namespace: str, domain: str, service: str, __name: str) -> bool:
        """Used to unregister a service"""

        self.logger.debug(
            "deregister_service called: %s:%s:%s %s",
            namespace,
            domain,
            service,
            __name,
        )

        if __name not in self.app_registered_services:
            raise ValueError(f"The given App {
                             __name} has no services registered")

        app_service = f"{namespace}:{domain}:{service}"

        if app_service not in self.app_registered_services[__name]:
            raise ValueError(f"The given App {
                             __name} doesn't have the given service registered it")

        # if it gets here, then time to deregister
        with self.services_lock:
            # it belongs to the app
            del self.services[namespace][domain][service]

            data = {
                "event_type": "service_deregistered",
                "data": {"namespace": namespace, "domain": domain, "service": service, "app": __name},
            }
            self.AD.loop.create_task(
                self.AD.events.process_event(namespace, data))

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

            self.app_registered_services[__name].remove(app_service)

            if not self.app_registered_services[__name]:
                del self.app_registered_services[__name]

            return True

    def clear_services(self, name: str) -> None:
        """Used to clear services"""

        if name not in self.app_registered_services:
            return

        app_services = deepcopy(self.app_registered_services[name])

        for app_service in app_services:
            self.deregister_service(*app_service.split(":"), name)

    def list_services(self, ns: str = "global") -> list[dict[str, str]]:
        with self.services_lock:
            return [
                {"namespace": namespace, "domain": domain, "service": service}
                for namespace in self.services
                if not (ns != "global" and namespace != ns)
                for domain in namespace
                for service in domain
            ]

    async def call_service(
        self,
        namespace: str,
        domain: str,
        service: str,
        name: str | None = None,
        data: dict[str, Any] | None = None,  # Don't expand with **data
    ) -> Any:
        self.logger.debug(
            "call_service: namespace=%s domain=%s service=%s data=%s",
            namespace,
            domain,
            service,
            data,
        )

        # data can be None, later on we assume it is not!
        if data is None:
            data = {}

        with self.services_lock:
            if namespace not in self.services:
                raise NamespaceException(f"Unknown namespace {
                                         namespace} in call_service from {name}")

            if domain not in self.services[namespace]:
                raise DomainException(
                    f"Unknown domain ({namespace}/{domain}) in call_service from {name}")

            if service not in self.services[namespace][domain]:
                raise ServiceException(
                    f"Unknown service ({namespace}/{domain}/{service}) in call_service from {name}")

            # If we have namespace in data it's an override for the domain of the eventual service call, as distinct
            # from the namespace the call itself is executed from. e.g. set_state() is in the AppDaemon namespace but
            # needs to operate on a different namespace, e.g. "default"

            # This means that data can't be expanded with **data

            ns = data.pop('namespace', namespace)

            service_def = self.services[namespace][domain][service]
            funcref = service_def["callback"]

            match isasync := service_def.pop("__async", 'auto'):
                case 'auto':
                    # Remove any wrappers from the funcref before determining if it's async or not
                    isasync = asyncio.iscoroutinefunction(
                        utils.unwrapped(funcref))
                case bool():
                    pass  # isasync already set as a bool from above
                case _:
                    raise TypeError(f'Invalid __async type: {isasync}')

            use_dictionary_unpacking = utils.has_expanded_kwargs(funcref)

            if isasync:
                # it's a coroutine just await it.
                if use_dictionary_unpacking:
                    coro = funcref(ns, domain, service, **data)
                else:
                    coro = funcref(ns, domain, service, data)
            else:
                # It's not a coroutine, run it in an executor
                if use_dictionary_unpacking:
                    coro = utils.run_in_executor(
                        self, funcref, ns, domain, service, **data)
                else:
                    coro = utils.run_in_executor(
                        self, funcref, ns, domain, service, data)

            @utils.warning_decorator(error_text=f"Unexpected error calling service {ns}/{domain}/{service}")
            async def safe_service(self: 'Services'):
                return await coro

            return await safe_service(self)
