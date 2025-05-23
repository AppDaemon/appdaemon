import asyncio
import functools
import threading
from collections import defaultdict
from logging import Logger
from typing import TYPE_CHECKING, Any, Callable, Protocol

from appdaemon import utils
from appdaemon.exceptions import DomainException, NamespaceException, ServiceException

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class ServiceCallback(Protocol):
    def __call__(self, result: Any) -> None: ...


class Services:
    """Subsystem container for handling services

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"
    name: str = "_services"
    logger: Logger
    error: Logger
    services: dict[
        str,                    # namespace
        dict[
            str,                # domain
            dict[
                str,            # service
                dict[str, Any]  # service info
            ]
        ]
    ] = {}
    services_lock: threading.RLock = threading.RLock()
    app_registered_services: defaultdict[str, set[str]] = defaultdict(set)

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child(self.name)
        self.error = ad.logging.get_error()

    def register_service(
        self,
        namespace: str,
        domain: str,
        service: str,
        callback: Callable,
        silent: bool = False,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Register a service with AppDaemon. This method should only be used by AppDaemon internals.

        Services are tracked with a nested dicts structure.

        Args:
            namespace (str): Namespace of the service
            domain (str): Domain of the service
            service (str): Name of the service
            callback (Callable): Callback function to be called when the service is invoked
            __silent (bool, optional): If True, do not send a registration event. Defaults to False.
            __name (str | None, optional): Name of the app registering the service. Defaults to None.
            **kwargs: Additional keyword arguments to be passed to the callback function.
        """
        self.logger.debug(
            "register_service called: %s.%s.%s -> %s",
            namespace,
            domain,
            service,
            callback,
        )

        with self.services_lock:
            # first we confirm if the namespace exists
            if name and not self.AD.state.namespace_exists(namespace):
                raise NamespaceException(f"Namespace {namespace}, doesn't exist")

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
                        f"This service '{domain}/{service}' already registered to a "
                        f"different app '{service_app}', and so cannot be registered "
                        f"to {name}. Do deregister from app first"
                    )
                    return

            self.services[namespace][domain][service] = {
                "callback": callback,
                "__name": name,
                **kwargs
            }

            if name:
                self.app_registered_services[name].add(f"{namespace}:{domain}:{service}")

            if not silent:
                data = {
                    "event_type": "service_registered",
                    "data": {"namespace": namespace, "domain": domain, "service": service},
                }
                self.AD.loop.create_task(self.AD.events.process_event(namespace, data))

    def deregister_service(self, namespace: str, domain: str, service: str, name: str) -> bool:
        """Used to unregister a service"""

        self.logger.debug(
            "deregister_service called: %s:%s:%s %s",
            namespace,
            domain,
            service,
            name,
        )

        if name not in self.app_registered_services:
            raise ValueError(f"The given App {name} has no services registered")

        app_service = f"{namespace}:{domain}:{service}"

        if app_service not in self.app_registered_services[name]:
            raise ValueError(f"The given App {name} doesn't have the given service registered it")

        # if it gets here, then time to deregister
        with self.services_lock:
            # it belongs to the app
            del self.services[namespace][domain][service]

            data = {
                "event_type": "service_deregistered",
                "data": {"namespace": namespace, "domain": domain, "service": service, "app": name},
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

            self.app_registered_services[name].remove(app_service)

            if not self.app_registered_services[name]:
                del self.app_registered_services[name]

            return True

    def clear_services(self, name: str) -> None:
        """Clear any services registered by the app with the given name."""
        with self.services_lock:
            for app_service in self.list_app_services(name):
                self.deregister_service(**app_service)

    def list_services(self, ns: str = "global") -> list[dict[str, str]]:
        with self.services_lock:
            return [
                {"namespace": namespace, "domain": domain, "service": service}
                for namespace, ns_services in self.services.items()
                if ns == "global" or ns == namespace
                for domain, domain_services in ns_services.items()
                for service in domain_services
            ]

    def list_app_services(self, app_name: str) -> list[dict[str, str]]:
        return [
            dict(
                namespace=namespace,
                domain=domain,
                service=service_name,
                name=app_name,
            )
            for namespace, ns_services in self.services.items()
            for domain, domain_services in ns_services.items()
            for service_name, info in domain_services.items()
            if info.get("__name") == app_name
        ]

    async def call_service(
        self,
        namespace: str,
        domain: str,
        service: str,
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
            if ns_services := self.services.get(namespace):
                if domain_services := ns_services.get(domain):
                    if service not in domain_services:
                        raise ServiceException(namespace, domain, service, list(domain_services.keys()))
                else:
                    raise DomainException(namespace, domain)
            else:
                raise NamespaceException(namespace)

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
                    isasync = asyncio.iscoroutinefunction(utils.unwrapped(funcref))
                case bool():
                    pass  # isasync already set as a bool from above
                case _:
                    raise TypeError(f'Invalid __async type: {isasync}')

            use_dictionary_unpacking = utils.has_expanded_kwargs(funcref)
            funcref = functools.partial(funcref, ns, domain, service)

            if isasync:
                # it's a coroutine just await it.
                if use_dictionary_unpacking:
                    coro = funcref(**data)
                else:
                    coro = funcref(data)
            else:
                # It's not a coroutine, run it in an executor
                if use_dictionary_unpacking:
                    coro = utils.run_in_executor(self, funcref, **data)
                else:
                    coro = utils.run_in_executor(self, funcref, data)

            @utils.warning_decorator(error_text=f"Unexpected error calling service {ns}/{domain}/{service}")
            async def safe_service(self: 'Services'):
                return await coro

            return await safe_service(self)
