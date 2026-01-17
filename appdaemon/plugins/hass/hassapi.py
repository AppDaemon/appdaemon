import re
from ast import literal_eval
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, Type, overload

from appdaemon import exceptions as ade
from appdaemon import utils
from appdaemon.adapi import ADAPI
from appdaemon.adbase import ADBase
from appdaemon.appdaemon import AppDaemon
from appdaemon.models.notification.android import AndroidData
from appdaemon.models.notification.base import NotificationData
from appdaemon.models.notification.iOS import iOSData
from appdaemon.plugins.hass.exceptions import ScriptNotFound
from appdaemon.plugins.hass.hassplugin import HassPlugin
from appdaemon.plugins.hass.notifications import AndroidNotification
from appdaemon.services import ServiceCallback

# Check if the module is being imported using the legacy method
if __name__ == Path(__file__).name:
    from appdaemon.logging import Logging

    # It's possible to instantiate the Logging system again here because it's a singleton, and it will already have been
    # created at this point if the legacy import method is being used by an app. Using this accounts for the user maybe
    # having configured the error logger to use a different name than 'Error'
    Logging().get_error().warning(
        "Importing 'hassapi' directly is deprecated and will be removed in a future version. "
        "To use the Hass plugin use 'from appdaemon.plugins.hass import Hass' instead.",
    )


if TYPE_CHECKING:
    from ...models.config.app import AppConfig


class Hass(ADBase, ADAPI):
    """HASS API class for the users to inherit from.

    This class provides an interface to the HassPlugin object that connects to Home Assistant.
    """

    _plugin: HassPlugin

    def __init__(self, ad: AppDaemon, config_model: "AppConfig"):
        # Call Super Classes
        ADBase.__init__(self, ad, config_model)
        ADAPI.__init__(self, ad, config_model)

        #
        # Register specific constraints
        #
        self.register_constraint("constrain_presence")
        self.register_constraint("constrain_person")
        self.register_constraint("constrain_input_boolean")
        self.register_constraint("constrain_input_select")

    @utils.sync_decorator
    async def ping(self) -> float | None:
        """Gets the number of seconds """
        if (plugin := self._plugin) is not None:
            match await plugin.ping():
                case {"ad_status": "OK", "ad_duration": ad_duration}:
                    return ad_duration
                case _:
                    return None

    @utils.sync_decorator
    async def check_for_entity(self, entity_id: str, namespace: str | None = None) -> bool:
        """Uses the REST API to check if an entity exists instead of checking AppDaemon's internal state.

        Args:
            entity_id (str): Fully qualified id.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            Bool of whether the entity exists.
        """
        namespace = namespace if namespace is not None else self.namespace
        match self.AD.plugins.get_plugin_object(namespace):
            case HassPlugin() as plugin:
                match await plugin.check_for_entity(entity_id):
                    case dict():
                        return True
        return False


    #
    # Internal Helpers
    # Methods that other methods

    async def _entity_service_call(self, service: str, entity_id: str, namespace: str | None = None, **kwargs):
        """Wraps up a common pattern in methods that use a service call with an entity_id

        Namespace defaults to that of the plugin

        Displays a warning if the entity doesn't exist in the namespace.
        """
        namespace = namespace or self.namespace
        self._check_entity(namespace, entity_id)
        return await self.call_service(
            service=service,
            namespace=namespace,
            entity_id=entity_id,
            **kwargs
        )

    async def _domain_service_call(
        self,
        service: str,
        entity_id: str | Iterable[str],
        namespace: str | None = None,
        **kwargs
    ):
        """Wraps up a common pattern in methods that have to use a certain domain.

            - Namespace defaults to that of the plugin.
            - Asserts that the entity is in the right domain.
            - Displays a warning if the entity doesn't exist in the namespace.
        """
        namespace = namespace if namespace is not None else self.namespace
        service_domain = service.split('/')[0]

        def _check(entity_ids: Iterable[str]) -> None:
            for eid in entity_ids:
                entity_domain = eid.split('.')[0]
                # This check needs to work for domains like "number" and "input_number"
                assert entity_domain in service_domain, (
                    f"Entity domain '{entity_domain}' does not match service domain '{service_domain}'"
                )
                self._check_entity(namespace, eid)

        match entity_id:
            case str():
                _check([entity_id])
            case list(entity_ids):
                _check(entity_ids)
            case Iterable() as entity_ids:
                entity_id = entity_ids if isinstance(entity_ids, list) else list(entity_ids)
                _check(entity_id)
            case _:
                raise TypeError('entity_id must be a string or an iterable of strings')

        return await self.call_service(
            service=service,
            namespace=namespace,
            entity_id=entity_id,
            **kwargs
        )

    async def _create_helper(
        self,
        friendly_name: str,
        initial_val: Any,
        type: str,
        entity_id: str = None,
        namespace: str | None = None
    ) -> dict:
        """Creates a new input number entity by using ``set_state`` on a non-existent one with the right format

        Entities created this way do not persist after Home Assistant restarts.
        """
        assert type.startswith('input')

        if entity_id is None:
            cleaned_name = friendly_name.lower().replace(' ', '_').replace('-', '_')
            entity_id = f'{type}.{cleaned_name}'

        assert entity_id.startswith(f'{type}.')

        if not (await self.entity_exists(entity_id, namespace)):
            return await self.set_state(
                entity_id=entity_id,
                state=initial_val,
                friendly_name=friendly_name,
                namespace=namespace,
                check_existence=False,
            )
        else:
            self.log(f'Entity already exists: {friendly_name}')
            return self.get_state(entity_id, 'all')

    #
    # Device Trackers
    # Methods relating to entities in the person and device_tracker domains

    def get_tracker_details(self, person: bool = True, namespace: str | None = None, copy: bool = True) -> dict[str, Any]:
        """Returns a list of all device tracker and the associated states.

        Args:
            person (boolean, optional): If set to True, use person rather than device_tracker
                as the device type to query
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
            copy (bool, optional): Whether to return a copy of the state dictionary. This is usually
                the desired behavior because it prevents accidental modification of the internal AD
                data structures. Defaults to True.

        Examples:
            >>> trackers = self.get_tracker_details()
            >>> for tracker in trackers:
            >>>     do something

        """
        device = "person" if person else "device_tracker"
        return self.get_state(device, namespace=namespace, copy=copy)

    def get_trackers(self, person: bool = True, namespace: str | None = None) -> list[str]:
        """Returns a list of all device tracker names.

        Args:
            person (boolean, optional): If set to True, use person rather than device_tracker
                as the device type to query
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Examples:
            >>> trackers = self.get_trackers()
            >>> for tracker in trackers:
            >>>     do something
            >>> people = self.get_trackers(person=True)
            >>> for person in people:
            >>>     do something

        """
        return list(self.get_tracker_details(person, namespace, copy=False).keys())

    @overload
    def get_tracker_state(
        self,
        entity_id: str,
        attribute: str | None = None,
        default: Any | None = None,
        namespace: str | None = None,
        copy: bool = True,
    ) -> str: ...

    def get_tracker_state(self, *args, **kwargs) -> str:
        """Gets the state of a tracker.

        Args:
            entity_id (str): Fully qualified entity id of the device tracker or person to query, e.g.,
                ``device_tracker.andrew`` or ``person.andrew``.
            attribute (str, optional): Name of the attribute to return
            default (Any, optional): Default value to return when the attribute isn't found
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
            copy (bool, optional): Whether to return a copy of the state dictionary. This is usually
                the desired behavior because it prevents accidental modification of the internal AD
                data structures. Defaults to True.

        Returns:
            The values returned depend in part on the
            configuration and type of device trackers in the system. Simpler tracker
            types like ``Locative`` or ``NMAP`` will return one of 2 states:

            -  ``home``
            -  ``not_home``

            Some types of device tracker are in addition able to supply locations
            that have been configured as Geofences, in which case the name of that
            location can be returned.

        Examples:
            >>> state = self.get_tracker_state("device_tracker.andrew")
            >>>     self.log(f"state is {state}")
            >>> state = self.get_tracker_state("person.andrew")
            >>>     self.log(f"state is {state}")

        """
        return self.get_state(*args, **kwargs)

    @utils.sync_decorator
    async def anyone_home(self, person: bool = True, namespace: str | None = None) -> bool:
        """Determines if the house/apartment is occupied.

        A convenience function to determine if one or more person is home. Use
        this in preference to getting the state of ``group.all_devices()`` as it
        avoids a race condition when using state change callbacks for device
        trackers.

        Args:
            person (boolean, optional): If set to True, use person rather than device_tracker
                as the device type to query
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            Returns ``True`` if anyone is at home, ``False`` otherwise.

        Examples:
            >>> if self.anyone_home():
            >>>     do something
            >>> if self.anyone_home(person=True):
            >>>     do something

        """
        details = await self.get_tracker_details(person, namespace, copy=False)
        return any(state['state'] == 'home' for state in details.values())

    @utils.sync_decorator
    async def everyone_home(self, person: bool = True, namespace: str | None = None) -> bool:
        """Determine if all family's members at home.

        A convenience function to determine if everyone is home. Use this in
        preference to getting the state of ``group.all_devices()`` as it avoids
        a race condition when using state change callbacks for device trackers.

        Args:
            person (boolean, optional): If set to True, use person rather than device_tracker
                as the device type to query
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            Returns ``True`` if everyone is at home, ``False`` otherwise.

        Examples:
            >>> if self.everyone_home():
            >>>    do something
            >>> if self.everyone_home(person=True):
            >>>    do something

        """
        details = await self.get_tracker_details(person, namespace, copy=False)
        return all(state['state'] == 'home' for state in details.values())

    @utils.sync_decorator
    async def noone_home(self, person: bool = True, namespace: str | None = None) -> bool:
        """Determines if the house/apartment is empty.

        A convenience function to determine if no people are at home. Use this
        in preference to getting the state of ``group.all_devices()`` as it avoids
        a race condition when using state change callbacks for device trackers.

        Args:
            person (boolean, optional): If set to True, use person rather than device_tracker
                as the device type to query
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments.

        Returns:
            Returns ``True`` if no one is home, ``False`` otherwise.

        Examples:
            >>> if self.noone_home():
            >>>     do something
            >>> if self.noone_home(person=True):
            >>>     do something

        """
        return not await self.anyone_home(person, namespace)

    #
    # Built-in constraints
    #

    def constrain_presence(self, value: Literal["everyone", "anyone", "noone"] | None = None) -> bool:
        """Returns True if unconstrained"""
        match value:
            case None:
                return True
            case str(value_str):
                match value_str.strip().lower():
                    case "everyone":
                        return self.everyone_home()
                    case "anyone":
                        return self.anyone_home()
                    case "noone":
                        return self.noone_home()
        raise ValueError(f'Invalid presence constraint: {value}')

    def constrain_person(self, value: Literal["everyone", "anyone", "noone"] | None = None) -> bool:
        """Returns True if unconstrained"""
        match value:
            case None:
                return True
            case str(value_str):
                match value_str.strip().lower():
                    case "everyone":
                        return self.everyone_home(person=True)
                    case "anyone":
                        return self.anyone_home(person=True)
                    case "noone":
                        return self.noone_home(person=True)
        raise ValueError(f'Invalid presence constraint: {value}')

    def constrain_input_boolean(self, value: str | Iterable[str]) -> bool:
        """Returns True if unconstrained - all input_booleans match the desired
        state. Desired state defaults to ``on``
        """
        match value:
            case str():
                constraints = [value]
            case Iterable():
                constraints = value if isinstance(value, list) else list(value)

        assert isinstance(constraints, list) and all(isinstance(v, str) for v in constraints)

        for constraint in constraints:
            parts = re.split(r',\s*', constraint)
            match len(parts):
                case 2:
                    entity, desired_state = parts
                case 1:
                    entity = constraint
                    desired_state = "on"

            if self.get_state(entity, copy=False) != desired_state.strip():
                return False

        return True

    def constrain_input_select(self, value: str | Iterable[str]) -> bool:
        """Returns True if unconstrained - all inputs match a desired state."""
        match value:
            case str():
                constraints = [value]
            case Iterable():
                constraints = value if isinstance(value, list) else list(value)

        assert isinstance(constraints, list) and all(isinstance(v, str) for v in constraints)

        for constraint in constraints:
            # using re.split allows for an arbitrary amount of whitespace after the comma
            parts = re.split(r',\s*', constraint)
            entity = parts[0]
            desired_states = parts[1:]
            if self.get_state(entity, copy=False) not in desired_states:
                return False

        return True

    #
    # Helper functions for services
    #

    @overload
    @utils.sync_decorator
    async def call_service(
        self,
        service: str,
        namespace: str | None = None,
        timeout: str | int | float | None = None,
        callback: ServiceCallback | None = None,
        hass_timeout: str | int | float | None = None,
        suppress_log_messages: bool = False,
        return_response: bool | None = None,
        **data,
    ) -> Any: ...

    @utils.sync_decorator
    async def call_service(
        self,
        service: str,
        namespace: str | None = None,
        timeout: str | int | float | None = None,  # used by the sync_decorator
        callback: Callable[[Any], Any] | None = None,
        **kwargs,
    ) -> Any:
        """Calls a Service within AppDaemon.

        Services represent specific actions, and are generally registered by plugins or provided by AppDaemon itself.
        The app calls the service only by referencing the service with a string in the format ``<domain>/<service>``, so
        there is no direct coupling between apps and services. This allows any app to call any service, even ones from
        other plugins.

        Services often require additional parameters, such as ``entity_id``, which AppDaemon will pass to the service
        call as appropriate, if used when calling this function. This allows arbitrary data to be passed to the service
        calls.

        Apps can also register their own services using their ``self.regsiter_service`` method.

        Args:
            service (str): The service name in the format `<domain>/<service>`. For example, `light/turn_on`.
            namespace (str, optional): It's safe to ignore this parameter in most cases because the default namespace
                will be used. However, if a `namespace` is provided, the service call will be made in that namespace. If
                there's a plugin associated with that namespace, it will do the service call. If no namespace is given,
                AppDaemon will use the app's namespace, which can be set using the ``self.set_namespace`` method. See
                the section on `namespaces <APPGUIDE.html#namespaces>`__ for more information.
            timeout (str | int | float, optional): The internal AppDaemon timeout for the service call. If no value is
                specified, the default timeout is 60s. The default value can be changed using the
                ``appdaemon.internal_function_timeout`` config setting.
            callback (callable): The non-async callback to be executed when complete. It should accept a single
                argument, which will be the result of the service call. This is the recommended method for calling
                services which might take a long time to complete. This effectively bypasses the ``timeout`` argument
                because it only applies to this function, which will return immediately instead of waiting for the
                result if a `callback` is specified.
            hass_timeout (str | int | float, optional): Only applicable to the Hass plugin. Sets the amount of time to
                wait for a response from Home Assistant. If no value is specified, the default timeout is 10s. The
                default value can be changed using the ``ws_timeout`` setting the in the Hass plugin configuration in
                ``appdaemon.yaml``. Even if no data is returned from the service call, Home Assistant will still send an
                acknowledgement back to AppDaemon, which this timeout applies to. Note that this is separate from the
                ``timeout``. If ``timeout`` is shorter than this one, it will trigger before this one does.
            suppress_log_messages (bool, optional): Only applicable to the Hass plugin. If this is set to ``True``,
                Appdaemon will suppress logging of warnings for service calls to Home Assistant, specifically timeouts
                and non OK statuses. Use this flag and set it to ``True`` to suppress these log messages if you are
                performing your own error checking as described `here <APPGUIDE.html#some-notes-on-service-calls>`__
            return_response (bool, optional): Indicates whether Home Assistant should return a response to the service
                call. This is only supported for some services and Home Assistant will return an error if used with a
                service that doesn't support it. If returning a response is required or optional (based on the service
                definitions given by Home Assistant), this will automatically be set to ``True``.
            service_data (dict, optional): Used as an additional dictionary to pass arguments into the ``service_data``
                field of the JSON that goes to Home Assistant. This is useful if you have a dictionary that you want to
                pass in that has a key like ``target`` which is otherwise used for the ``target`` argument.
            **data: Any other keyword arguments get passed to the service call as ``service_data``. Each service takes
                different parameters, so this will vary from service to service. For example, most services require
                ``entity_id``. The parameters for each service can be found in the actions tab of developer tools in
                the Home Assistant web interface.

        Returns:
            Result of the `call_service` function if any, see
            `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            HASS
            ^^^^

            >>> self.call_service("light/turn_on", entity_id="light.office_lamp", color_name="red")
            >>> self.call_service("notify/notify", title="Hello", message="Hello World")
            >>> events = self.call_service(
                    "calendar/get_events",
                    entity_id="calendar.home",
                    start_date_time="2024-08-25 00:00:00",
                    end_date_time="2024-08-27 00:00:00",
                )["result"]["response"]["calendar.home"]["events"]

            MQTT
            ^^^^

            >>> self.call_service("mqtt/subscribe", topic="homeassistant/living_room/light", qos=2)
            >>> self.call_service("mqtt/publish", topic="homeassistant/living_room/light", payload="on")

            Utility
            ^^^^^^^

            It's important that the ``namespace`` arg is set to ``admin`` for these services, as they do not exist
            within the default namespace, and apps cannot exist in the ``admin`` namespace. If the namespace is not
            specified, calling the method will raise an exception.

            >>> self.call_service("app/restart", app="notify_app", namespace="admin")
            >>> self.call_service("app/stop", app="lights_app", namespace="admin")
            >>> self.call_service("app/reload", namespace="admin")

        """
        # We just wrap the ADAPI.call_service method here to add some additional arguments and docstrings
        kwargs = utils.remove_literals(kwargs, (None,))
        # We intentionally don't pass the timeout kwarg here because it's applied by the sync_decorator
        return await super().call_service(service, namespace, callback=callback, **kwargs)

    def get_service_info(self, service: str) -> dict | None:
        """Get some information about what kind of data the service expects to receive, which is helpful for debugging.

        The resulting dict is identical to the one returned sending ``get_services`` to the websocket. See
        `fetching service actions <https://developers.home-assistant.io/docs/api/websocket#fetching-service-actions>`__
        for more information.

        Args:
            service (str): The service name in the format ``<domain>/<service>``. For example, ``light/turn_on``.

        Returns:
            Information about the service in a dict with the following keys: ``name``, ``description``, ``target``, and
            ``fields``.
        """
        match self._plugin:
            case HassPlugin() as plugin:
                domain, service_name = service.split("/", 2)
                if info := plugin.services.get(domain, {}).get(service_name):
                    # Return a copy of the info dict to prevent accidental modification
                    return deepcopy(info)
        self.logger.warning("Service info not found for domain '%s", domain)

    # Methods that use self.call_service

    # Home Assistant General

    @utils.sync_decorator
    async def turn_on(self, entity_id: str, namespace: str | None = None, **kwargs) -> dict:
        """Turns `on` a Home Assistant entity.

        This is a convenience function for the ``homeassistant.turn_on``
        function. It can turn ``on`` pretty much anything in Home Assistant
        that can be turned ``on`` or ``run`` (e.g., `Lights`, `Switches`,
        `Scenes`, `Scripts`, etc.).

        Note that Home Assistant will return a success even if the entity name is invalid.

        Args:
            entity_id (str): Fully qualified id of the thing to be turned ``on`` (e.g.,
                `light.office_lamp`, `scene.downstairs_on`).
             namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments that get passed to the
                service call.

        Returns:
            Result of the `turn_on` function if any, see `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            Turn `on` a switch.

            >>> self.turn_on("switch.backyard_lights")

            Turn `on` a scene.

            >>> self.turn_on("scene.bedroom_on")

            Turn `on` a light and set its color to green.

            >>> self.turn_on("light.office_1", color_name = "green")

        """
        return await self._entity_service_call(
            service="homeassistant/turn_on",
            entity_id=entity_id,
            namespace=namespace,
            **kwargs
        )

    @utils.sync_decorator
    async def turn_off(self, entity_id: str, namespace: str | None = None, **kwargs) -> dict:
        """Turns `off` a Home Assistant entity.

        This is a convenience function for the ``homeassistant.turn_off``
        function. It can turn ``off`` pretty much anything in Home Assistant
        that can be turned ``off`` (e.g., `Lights`, `Switches`, etc.).

        Args:
            entity_id (str): Fully qualified id of the thing to be turned ``off`` (e.g.,
                `light.office_lamp`, `scene.downstairs_on`).
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments that get passed to the
                service call.

        Returns:
            Result of the `turn_off` function if any, see `service call notes
            <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            Turn `off` a switch.

            >>> self.turn_off("switch.backyard_lights")

            Turn `off` a scene.

            >>> self.turn_off("scene.bedroom_on")

        """
        return await self._entity_service_call(
            service="homeassistant/turn_off",
            entity_id=entity_id,
            namespace=namespace,
            **kwargs
        )

    @utils.sync_decorator
    async def toggle(self, entity_id: str, namespace: str | None = None, **kwargs) -> dict:
        """Toggles between ``on`` and ``off`` for the selected entity.

        This is a convenience function for the ``homeassistant.toggle`` function.
        It is able to flip the state of pretty much anything in Home Assistant
        that can be turned ``on`` or ``off``.

        Args:
            entity_id (str): Fully qualified id of the thing to be turned ``off`` (e.g.,
                `light.office_lamp`, `scene.downstairs_on`).
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments that get passed to the
                service call.

        Returns:
            Result of the `toggle` function if any, see `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            >>> self.toggle("switch.backyard_lights")
            >>> self.toggle("light.office_1", color_name="green")

        """
        return await self._entity_service_call(
            service="homeassistant/toggle",
            entity_id=entity_id,
            namespace=namespace,
            **kwargs
        )

    @utils.sync_decorator
    async def get_history(
        self,
        entity_id: str | list[str],
        days: int | None = None,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        minimal_response: bool = False,
        no_attributes: bool = False,
        significant_changes_only: bool = False,
        callback: Callable | None = None,
        namespace: str | None = None,
    ) -> list[list[dict[str, Any]]] | None:
        """Gets access to the HA Database.
        This is a convenience function that allows accessing the HA Database, so the
        history state of a device can be retrieved. It allows for a level of flexibility
        when retrieving the data, and returns it as a dictionary list. Caution must be
        taken when using this, as depending on the size of the database, it can take
        a long time to process.

        Hits the ``/api/history/period/<timestamp>`` endpoint. See
        https://developers.home-assistant.io/docs/api/rest for more information

        Args:
            entity_id (str, optional): Fully qualified id of the device to be querying, e.g.,
                ``light.office_lamp`` or ``scene.downstairs_on`` This can be any entity_id
                in the database. If this is left empty, the state of all entities will be
                retrieved within the specified time. If both ``end_time`` and ``start_time``
                explained below are declared, and ``entity_id`` is specified, the specified
                ``entity_id`` will be ignored and the history states of `all` entity_id in
                the database will be retrieved within the specified time.
            days (int, optional): The days from the present-day walking backwards that is
                required from the database.
            start_time (optional): The start time from when the data should be retrieved.
                This should be the furthest time backwards, like if we wanted to get data from
                now until two days ago. Your start time will be the last two days datetime.
                ``start_time`` time can be either a UTC aware time string like ``2019-04-16 12:00:03+01:00``
                or a ``datetime.datetime`` object.
            end_time (optional): The end time from when the data should be retrieved. This should
                be the latest time like if we wanted to get data from now until two days ago. Your
                end time will be today's datetime ``end_time`` time can be either a UTC aware time
                string like ``2019-04-16 12:00:03+01:00`` or a ``datetime.datetime`` object. It should
                be noted that it is not possible to declare only ``end_time``. If only ``end_time``
                is declared without ``start_time`` or ``days``, it will revert to default to the latest
                history state. When ``end_time`` is specified, it is not possible to declare ``entity_id``.
                If ``entity_id`` is specified, ``end_time`` will be ignored.
            minimal_response (bool, optional):
            no_attributes (bool, optional):
            significant_changes_only (bool, optional):
            callback (callable, optional): If wanting to access the database to get a large amount of data,
                using a direct call to this function will take a long time to run and lead to AD cancelling the task.
                To get around this, it is better to pass a function, which will be responsible of receiving the result
                from the database. The signature of this function follows that of a scheduler call.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            An iterable list of entity_ids and their history state.

        Examples:
            Get device state over the last 5 days.

            >>> data = self.get_history(entity_id = "light.office_lamp", days = 5)

            Get device state over the last 2 days and walk forward.

            >>> import datetime
            >>> from datetime import timedelta
            >>> start_time = datetime.datetime.now() - timedelta(days = 2)
            >>> data = self.get_history(entity_id = "light.office_lamp", start_time = start_time)

            Get device state from yesterday and walk 5 days back.

            >>> import datetime
            >>> from datetime import timedelta
            >>> end_time = datetime.datetime.now() - timedelta(days = 1)
            >>> data = self.get_history(end_time = end_time, days = 5)

        """
        if days is not None:
            end_time = self.parse_datetime(end_time) if end_time is not None else await self.get_now()
            start_time = end_time - timedelta(days=days)

        namespace = namespace if namespace is not None else self.namespace
        match self.AD.plugins.get_plugin_object(namespace):
            case HassPlugin() as plugin:
                coro = plugin.get_history(
                    filter_entity_id=entity_id,
                    timestamp=start_time,
                    end_time=end_time,
                    minimal_response=minimal_response,
                    no_attributes=no_attributes,
                    significant_changes_only=significant_changes_only,
                )

                if callback is not None and callable(callback):
                    self.create_task(coro, callback)
                else:
                    return await coro
            case _:
                self.logger.warning("HASS plugin not found in namespace '%s'", namespace)

    @utils.sync_decorator
    async def get_logbook(
        self,
        entity: str | None = None,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        days: int | None = None,
        callback: Callable | None = None,
        namespace: str | None = None,
    ) -> list[dict[str, str | datetime]] | None:
        """Gets access to the HA Database.
        This is a convenience function that allows accessing the HA Database.
        Caution must be taken when using this, as depending on the size of the
        database, it can take a long time to process.

        Hits the ``/api/logbook/<timestamp>`` endpoint. See
        https://developers.home-assistant.io/docs/api/rest for more information

        Args:
            entity (str, optional): Fully qualified id of the device to be
                querying, e.g., ``light.office_lamp`` or
                ``scene.downstairs_on``. This can be any entity_id in the
                database. This method does not support multiple entity IDs. If
                no ``entity`` is specified, then all logbook entries for the
                period will be returned.
            start_time (datetime, optional): The start time of the period
                covered. Defaults to 1 day before the time of the request.
            end_time (datetime, optional): The end time of the period covered.
                Defaults to the current time if the ``days`` argument is also used.
            days (int, optional): Number of days before the end time to include
            callback (Callable, optional): Callback to run with the results of the
                request. The callback needs to take a single argument, a future object.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            A list of dictionaries, each representing a single entry for a
            single entity. The value for the ``when`` key of each dictionary
            gets converted to a ``datetime`` object with a timezone.

        Examples:
            >>> data = self.get_logbook("light.office_lamp")
            >>> data = self.get_logbook("light.office_lamp", days=5)

        """
        if days is not None:
            end_time = self.parse_datetime(end_time) if end_time is not None else await self.get_now()
            start_time = end_time - timedelta(days=days)

        namespace = namespace if namespace is not None else self.namespace
        match self.AD.plugins.get_plugin_object(namespace):
            case HassPlugin() as plugin:
                coro = plugin.get_logbook(
                    entity=entity,
                    timestamp=start_time,
                    end_time=end_time,
                )

                if callback is not None and callable(callback):
                    self.create_task(coro, callback)
                else:
                    return await coro
            case _:
                self.logger.warning("HASS plugin not found in namespace '%s'", namespace)

    # Input Helpers

    @utils.sync_decorator
    async def set_value(self, entity_id: str, value: int | float, namespace: str | None = None) -> None:
        """Sets the value of an `input_number`.

        This is a convenience function for the ``input_number.set_value``
        function. It can set the value of an ``input_number`` in Home Assistant.

        Args:
            entity_id (str): Fully qualified id of `input_number` to be changed (e.g.,
                `input_number.alarm_hour`).
            value (int or float): The new value to set the `input_number` to.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments that get passed to the
                service call.

        Returns:
            Result of the `set_value` function if any, see `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            >>> self.set_value("input_number.alarm_hour", 6)

        """
        return await self._domain_service_call(
            service="input_number/set_value",
            entity_id=entity_id,
            value=value,
            namespace=namespace
        )

    @utils.sync_decorator
    async def set_textvalue(self, entity_id: str, value: str, namespace: str | None = None) -> None:
        """Sets the value of an `input_text`.

        This is a convenience function for the ``input_text.set_value``
        function. It can set the value of an `input_text` in Home Assistant.

        Args:
            entity_id (str): Fully qualified id of `input_text` to be changed (e.g.,
                `input_text.text1`).
            value (str): The new value to set the `input_text` to.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            Result of the `set_textvalue` function if any, see `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            >>> self.set_textvalue("input_text.text1", "hello world")

        """
        # https://www.home-assistant.io/integrations/input_text/
        return await self._domain_service_call(
            service="input_text/set_value",
            entity_id=entity_id,
            value=value,
            namespace=namespace
        )

    @utils.sync_decorator
    async def set_options(self, entity_id: str, options: list[str], namespace: str | None = None) -> dict:
        # https://www.home-assistant.io/integrations/input_select/#actions
        return await self._domain_service_call(
            service="input_select/set_options",
            entity_id=entity_id,
            options=options,
            namespace=namespace,
        )

    @utils.sync_decorator
    async def select_option(self, entity_id: str, option: str, namespace: str | None = None) -> None:
        """Sets the value of an `input_option`.

        This is a convenience function for the ``input_select.select_option``
        function. It can set the value of an `input_select` in Home Assistant.

        Args:
            entity_id (str): Fully qualified id of `input_select` to be changed (e.g.,
                `input_select.mode`).
            option (str): The new value to set the `input_select` to.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
            **kwargs (optional): Zero or more keyword arguments that get passed to the
                service call.

        Returns:
            Result of the `select_option` function if any, see `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            >>> self.select_option("input_select.mode", "Day")

        """
        return await self._domain_service_call(
            service="input_select/select_option",
            entity_id=entity_id,
            option=option,
            namespace=namespace,
        )

    @utils.sync_decorator
    async def select_next(self, entity_id: str, cycle: bool = True, namespace: str | None = None) -> dict:
        # https://www.home-assistant.io/integrations/input_select/#action-input_selectselect_next
        return await self._domain_service_call(
            service="input_select/select_next",
            entity_id=entity_id,
            cycle=cycle,
            namespace=namespace,
        )

    @utils.sync_decorator
    async def select_previous(self, entity_id: str, cycle: bool = True, namespace: str | None = None) -> dict:
        # https://www.home-assistant.io/integrations/input_select/#action-input_selectselect_previous
        return await self._domain_service_call(
            service="input_select/select_previous",
            entity_id=entity_id,
            cycle=cycle,
            namespace=namespace,
        )

    @utils.sync_decorator
    async def select_first(self, entity_id: str, namespace: str | None = None) -> dict:
        return await self._domain_service_call(
            service="input_select/select_first",
            entity_id=entity_id,
            namespace=namespace,
        )

    @utils.sync_decorator
    async def select_last(self, entity_id: str, namespace: str | None = None) -> dict:
        return await self._domain_service_call(
            service="input_select/select_last",
            entity_id=entity_id,
            namespace=namespace,
        )

    @utils.sync_decorator
    async def press_button(self, button_id: str, namespace: str | None = None) -> dict:
        # https://www.home-assistant.io/integrations/input_button/#actions
        return await self._domain_service_call(
            service="input_button/press",
            entity_id=button_id,
            namespace=namespace,
        )

    def last_pressed(self, button_id: str, namespace: str | None = None) -> datetime | None:
        """Only works on entities in the input_button domain"""
        assert button_id.split('.')[0] == 'input_button'
        state = self.get_state(button_id, namespace=namespace)
        match state:
            case str():
                return datetime.fromisoformat(state).astimezone(self.AD.tz)
            case datetime():
                return state
            case _:
                self.logger.warning(f'Unknown time: {state}')

    def time_since_last_press(self, button_id: str, namespace: str | None = None) -> timedelta | None:
        """Only works on entities in the input_button domain"""
        match self.last_pressed(button_id, namespace):
            case datetime() as dt:
                return self.get_now() - dt
            case _:
                self.logger.warning("Unknown last pressed time for %s", button_id)

    #
    # Notifications
    #
    @utils.sync_decorator
    async def notify(
        self,
        message: str,
        title: str | None = None,
        name: str | None = None,
        namespace: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Sends a notification.

        This is a convenience function for the ``notify`` service. It
        will send a notification to a named notification service. If the name is
        not specified, it will default to ``notify/notify``.

        Args:
            message (str): Message to be sent to the notification service.
            title (str, optional): Title of the notification.
            name (str, optional): Name of the notification service.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description. In most cases it is safe to ignore
                this parameter.

        Returns:
            Result of the `notify` function if any, see `service call notes
            <HASS_API_REFERENCE.html#advanced-service-calls>`__ for more details.

        Examples:
            >>> self.notify("Switching mode to Evening")
            >>> self.notify("Switching mode to Evening", title = "Some Subject", name = "smtp")
                # will send a message through notify.smtp instead of the default notify.notify

        """
        service = f'notify/{name}' if name is not None else 'notify/notify'
        return await self.call_service(
            service=service,
            message=message,
            title=title,
            namespace=namespace,
            **kwargs,
        )

    @utils.sync_decorator
    async def persistent_notification(self, message: str, title: str | None = None, id: int | None = None) -> None:
        kwargs: dict[str, Any] = {"message": message}
        if title is not None:
            kwargs["title"] = title
        if id is not None:
            kwargs["notification_id"] = id
        await self.call_service("persistent_notification/create", **kwargs)

    def notify_android(
        self,
        device: str,
        tag: str = 'appdaemon',
        title: str | None = None,
        message: str | None = None,
        target: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Convenience method for quickly creating mobile Android notifications"""
        kwargs.update({
            'title': title,
            'message': message,
            'target': target,
        })
        return self._notify_mobile_app(device, AndroidData, tag, **kwargs)

    def notify_ios(self, device: str, tag: str = 'appdaemon', **kwargs) -> dict:
        """Convenience method for quickly creating mobile iOS notifications"""
        return self._notify_mobile_app(device, iOSData, tag, **kwargs)

    def _notify_mobile_app(
        self,
        device: str,
        type_: str | Type[NotificationData],
        tag: str = 'appdaemon',
        **kwargs
    ) -> dict:
        match type_:
            case NotificationData():
                pass
            case 'android':
                model = AndroidData
            case 'iOS' | 'ios':
                model = iOSData
            case _:
                raise ValueError(f'Unknown model type: {type_}')

        model = model.model_validate(kwargs)
        if model.data is not None:
            # Fills in the tag if it's blank
            model.data.tag = model.data.tag or tag
        return self.call_service(
            service=f'notify/mobile_app_{device}',
            **model.model_dump(mode='json', exclude_none=True, by_alias=True)
        )

    def android_tts(
        self,
        device: str,
        tts_text: str,
        media_stream: Literal['music_stream', 'alarm_stream', 'alarm_stream_max'] | None = 'music_stream',
        critical: bool = False,
    ) -> dict:
        """Convenience method for correctly creating a TTS notification for Android devices.

        For more information see: `Text-to-Speech Notifications <https://companion.home-assistant.io/docs/notifications/notifications-basic#text-to-speech-notifications>`_

        Args:
            device (str): Name of the device to notify on. This gets combined with ``notify/mobile_app_<device>`` to
                determine which notification service to call.
            tts_text (str): String of text to translate into speech
            media_stream (optional): Defaults to ``music_stream``.
            critical (bool, optional): Defaults to False. If set to ``True``, the notification will use the correct
                settings to have the TTS at the maximum possible volume. For more information see
                `Critical Notifications <https://companion.home-assistant.io/docs/notifications/critical-notifications/#android>`_
        """
        return self.call_service(
            **AndroidNotification.tts(device, tts_text, media_stream, critical).to_service_call()
        )

    def listen_notification_action(self, callback: Callable, action: str) -> str:
        return self.listen_event(callback, 'mobile_app_notification_action', action=action)

    # Backup/Restore

    @utils.sync_decorator
    async def backup_full(
        self,
        name: str | None = None,
        password: str | None = None,
        compressed: bool | None = None,
        location: str | None = None,
        homeassistant_exclude_database: bool | None = None,
        timeout: str | int | float = 30,  # Used by sync_decorator
        hass_timeout: str | int | float = 10,
    ) -> dict:
        """Create a full backup.

        Action `hassio.backup_full <https://www.home-assistant.io/integrations/hassio/#action-hassiobackup_full>`_

        Args:
            name (str, optional): By default, the current date and time are used in your local time, which you have set in your general settings.
            password (str, optional): Optional password for backup.
            compressed (bool, optional): False to create uncompressed backups.
            location (str, optional): Alternate backup location instead of using the default location for backups.
            homeassistant_exclude_database (bool, optional): Exclude the Home Assistant database file from backup.
            timeout (str | int | float, optional): Timeout for the app thread to wait for a response from the main
                thread.
            hass_timeout (str | int | float, optional): Timeout for AppDaemon waiting on a response from Home Assistant
                to respond to the backup request. Cannot be set lower than the timeout value.

        Returns:
            dict: Response from the backup service.
        """
        return await self.call_service(
            "hassio/backup_full",
            name=name,
            password=password,
            compressed=compressed,
            location=location,
            homeassistant_exclude_database=homeassistant_exclude_database,
            hass_timeout=max(timeout, hass_timeout),
        )

    @utils.sync_decorator
    async def backup_partial(
        self,
        addons: Iterable[str] | None = None,
        folders: Iterable[str] | None = None,
        name: str | None = None,
        password: str | None = None,
        compressed: bool | None = None,
        location: str | None = None,
        homeassistant: bool | None = None,
        homeassistant_exclude_database: bool | None = None,
        timeout: str | int | float = 30,  # Used by sync_decorator
        hass_timeout: str | int | float = 10,
    ) -> dict:
        """Create a partial backup.

        Action `hassio.backup_partial <https://www.home-assistant.io/integrations/hassio/#action-hassiobackup_partial>`_

        Args:
            addons (Iterable[str], optional): List of add-on slugs to backup.
            folders (Iterable[str], optional): List of directories to backup.
            name (str, optional): Name of the backup file. Default is the current date and time in the user's local time.
            password (str, optional): Optional password for backup.
            compressed (bool, optional): False to create uncompressed backups. Defaults to True.
            location (str, optional): Alternate backup location instead of using the default location for backups.
            homeassistant (bool, optional): Include Home Assistant and associated config in backup. Defaults to False.
            homeassistant_exclude_database (bool, optional): Exclude the Home Assistant database file from backup.
                Defaults to False.
            timeout (str | int | float, optional): Timeout for the app thread to wait for a response from the main
                thread.
            hass_timeout (str | int | float, optional): Timeout for AppDaemon waiting on a response from Home Assistant
                to respond to the backup request. Cannot be set lower than the timeout value.

        Returns:
            dict: Response from the backup service.
        """
        return await self.call_service(
            "hassio/backup_partial",
            name=name,
            addons=addons,
            folders=folders,
            password=password,
            compressed=compressed,
            location=location,
            homeassistant=homeassistant,
            homeassistant_exclude_database=homeassistant_exclude_database,
            hass_timeout=max(timeout, hass_timeout),
        )

    @utils.sync_decorator
    async def restore_full(
        self,
        slug: str,
        password: str | None = None,
        timeout: str | int | float = 30,  # Used by sync_decorator
        hass_timeout: str | int | float = 10,
    ) -> dict:
        """Restore from full backup.

        Action `hassio.restore_full <https://www.home-assistant.io/integrations/hassio/#action-hassiorestore_full>`_

        Args:
            slug (str): Slug of backup to restore from.
            password (str, optional): Optional password for backup.
            timeout (str | int | float, optional): Timeout for the app thread to wait for a response from the main
                thread.
            hass_timeout (str | int | float, optional): Timeout for AppDaemon waiting on a response from Home Assistant
                to respond to the backup request. Cannot be set lower than the timeout value.
        """
        return await self.call_service(
            "hassio/restore_full",
            slug=slug,
            password=password,
            hass_timeout=max(timeout, hass_timeout),
        )

    @utils.sync_decorator
    async def restore_partial(
        self,
        slug: str,
        homeassistant: bool | None = None,
        addons: Iterable[str] | None = None,
        folders: Iterable[str] | None = None,
        password: str | None = None,
        timeout: str | int | float = 30,  # Used by sync_decorator
        hass_timeout: str | int | float = 10,
    ) -> dict:
        """Restore from partial backup.

        Action `hassio.restore_partial <https://www.home-assistant.io/integrations/hassio/#action-hassiorestore_partial>`_

        Args:
            slug (str): Slug of backup to restore from.
            homeassistant (bool, optional): Whether to restore Home Assistant, true or false. Defaults to False.
            addons (Iterable[str], optional): List of add-on slugs to restore.
            folders (Iterable[str], optional): List of directories to restore.
            password (str, optional): Optional password for backup.
            timeout (str | int | float, optional): Timeout for the app thread to wait for a response from the main
                thread.
            hass_timeout (str | int | float, optional): Timeout for AppDaemon waiting on a response from Home Assistant
                to respond to the backup request. Cannot be set lower than the timeout value.

        Returns:
            dict: Response from the restore service.
        """
        return await self.call_service(
            "hassio/restore_partial",
            slug=slug,
            homeassistant=homeassistant,
            addons=addons,
            folders=folders,
            password=password,
            hass_timeout=max(timeout, hass_timeout),
        )

    # Media

    @utils.sync_decorator
    async def media_play(self, entity_id: str | Iterable[str]) -> dict:
        return await self._domain_service_call('media_player/media_play', entity_id)

    @utils.sync_decorator
    async def media_pause(self, entity_id: str | Iterable[str]) -> dict:
        return await self._domain_service_call('media_player/media_pause', entity_id)

    @utils.sync_decorator
    async def media_play_pause(self, entity_id: str | Iterable[str]) -> dict:
        return await self._domain_service_call('media_player/media_play_pause', entity_id)

    @utils.sync_decorator
    async def media_mute(self, entity_id: str | Iterable[str]) -> dict:
        # https://www.home-assistant.io/integrations/media_player/#action-media_playervolume_mute
        return await self._domain_service_call('media_player/volume_mute', entity_id)

    @utils.sync_decorator
    async def media_set_volume(self, entity_id: str | Iterable[str], volume: float = 0.5) -> dict:
        # https://www.home-assistant.io/integrations/media_player/#action-media_playervolume_set
        return await self._domain_service_call(
            service='media_player/volume_set',
            entity_id=entity_id,
            volume_level=volume,
        )

    @utils.sync_decorator
    async def media_seek(self, entity_id: str | Iterable[str], seek_position: float | timedelta) -> dict:
        if isinstance(seek_position, timedelta):
            seek_position = seek_position.total_seconds()

        # https://www.home-assistant.io/integrations/media_player/#action-media_playermedia_seek
        return await self._domain_service_call(
            service='media_player/media_seek',
            entity_id=entity_id,
            seek_position=seek_position
        )

    # Calendar

    def get_calendar_events(
        self,
        entity_id: str = "calendar.localcalendar",
        days: int = 1,
        hours: int | None = None,
        minutes: int | None = None,
        namespace: str | None = None
    ) -> list[dict[str, str | datetime]] | None:
        """
        Retrieve calendar events for a specified entity within a given number of days.

        Each dict contains the following keys: ``summary``, ``description``, ``start``,
        and ``end``. The ``start`` and ``end`` keys are converted to ``datetime`` objects.

        Args:
            entity_id (str): The ID of the calendar entity to retrieve events from. Defaults to
                "calendar.localcalendar".
            days (int): The number of days to look ahead for events. Defaults to 1.
            hours (int, optional): The number of hours to look ahead for events. Defaults to None.
            minutes (int, optional): The number of minutes to look ahead for events. Defaults to None.
            namespace(str, optional): If provided, changes the namespace for the service call. Defaults to the current
                namespace of the app, so it's safe to ignore this parameter most of the time. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.

        Returns:
            list[dict]: A list of dicts representing the calendar events.

        Examples:
            >>> events = self.get_calendar_events()
            >>> for event in events:
            >>>     self.log(f'{event["summary"]} starts at {event["start"]}')
        """
        duration = {
            'days': days,
            'hours': hours,
            'minutes': minutes,
        }
        duration = {k:v for k,v in duration.items() if v is not None}

        res = self.call_service(
            'calendar/get_events',
            namespace=namespace,
            entity_id=entity_id,
            duration=duration,
        )
        match res:
            case {"success": True, "result": {"response": resp}}:
                return [
                    {
                        k: datetime.fromisoformat(v) if k in ('start', 'end') else v
                        for k, v in event.items()
                    }
                    for event in resp[entity_id]['events']
                ]
            case _:
                self.logger.error("Failed to get calendar events for '%s'", entity_id)

    # Scripts

    def run_script(
        self,
        entity_id: str,
        namespace: str | None = None,
        return_immediately: bool = True,
        **kwargs
    ) -> dict:
        """Runs a script in Home Assistant

        Args:
            entity_id (str): The entity ID of the script to run, if it doesn't start with ``script``, it will be added.
            namespace (str, optional): The namespace to use. Defaults to the namespace of the calling app.
            return_immediately (bool, optional): Whether to return immediately or wait for the script
                to complete. Defaults to True. See the Home Assistant documentation for more information.
                https://www.home-assistant.io/integrations/script/#waiting-for-script-to-complete
            **kwargs: Additional keyword arguments to pass to the service call.

        Returns:
            dict: The result of the service call.
        """
        if entity_id.startswith('script.'):
            domain, script_name = entity_id.split('.', 1)
        elif entity_id.startswith('script/'):
            domain, script_name = entity_id.split('/', 1)
        else:
            domain = 'script'
            script_name = entity_id

        entity_id = f'{domain}.{script_name}'

        if return_immediately:
            service = 'script/turn_on'
            service_data = {"variables": kwargs}
        else:
            service = f'{domain}/{script_name}'
            service_data = kwargs

        namespace = namespace if namespace is not None else self.namespace
        try:
            return self.call_service(
                service, namespace,
                entity_id=entity_id,
                service_data=service_data,
            )
        except ade.ServiceException:
            plugin_name = self.AD.plugins.get_plugin_from_namespace(namespace)
            raise ScriptNotFound(script_name, namespace, plugin_name)

    #
    # Template functions
    # Functions that use self.render_template

    @utils.sync_decorator
    async def render_template(self, template: str, namespace: str | None = None, **kwargs) -> Any:
        """Renders a Home Assistant Template.

        See the documentation for the `Template Integration <https://www.home-assistant.io/integrations/template>`__ and
        `Templating Configuration <https://www.home-assistant.io/docs/configuration/templating>`__ for more information.

        Args:
            template (str): The Home Assistant template to be rendered.
            namespace (str, optional): Optional namespace to use. Defaults to using the app's current namespace. See the
                `namespace documentation <APPGUIDE.html#namespaces>`__ for more information.
            **kwargs (optional): Zero or more keyword arguments that get passed to the template rendering.

        Returns:
            The rendered template in a native Python type.

        Examples:
            >>> self.render_template("{{ states('sun.sun') }}")
            above_horizon

            >>> self.render_template("{{ is_state('sun.sun', 'above_horizon') }}")
            True

            >>> self.render_template("{{ states('sensor.outside_temp') }}")
            97.2

            >>> self.render_template("hello {{ name }}", variables={"name": "bob"})
            hello bob

        """
        namespace = namespace if namespace is not None else self.namespace
        match self.AD.plugins.get_plugin_object(namespace):
            case HassPlugin() as plugin:
                result = await plugin.render_template(self.namespace, template, **kwargs)
                if result is not None:
                    try:
                        return literal_eval(result)
                    except (SyntaxError, ValueError):
                        return result

    def _template_command(self, command: str, *args: str) -> Any:
        """Internal AppDaemon function to format calling a single template command correctly."""
        if len(args) == 0:
            return self.render_template(f'{{{{ {command}() }}}}')
        else:
            args = tuple(a for a in args if a is not None)
            assert all(isinstance(i, str) for i in args), f"All inputs must be strings, got {args}"
            arg_str = ', '.join(f"'{i}'" for i in args)
            cmd_str = f'{{{{ {command}({arg_str}) }}}}'
            self.logger.debug("Template command: %s", cmd_str)
            return self.render_template(cmd_str)

    # Devices
    # https://www.home-assistant.io/docs/configuration/templating/#devices

    def device_entities(self, device_id: str) -> list[str]:
        """Get a list of entities that are associated with a given device ID.

        See `device functions <https://www.home-assistant.io/docs/configuration/templating/#devices>`_ for more
        information.
        """
        return self._template_command('device_entities', device_id)

    def device_attr(self, device_or_entity_id: str, attr_name: str) -> str:
        """Get the value of attr_name for the given device or entity ID.

        See `device functions <https://www.home-assistant.io/docs/configuration/templating/#devices>`_ for more
        information.

        Attributes vary by device , but some common device attributes include:
        - ``area_id``
        - ``configuration_url``
        - ``manufacturer``
        - ``model``
        - ``name_by_user``
        - ``name``
        - ``sw_version``
        """
        return self._template_command('device_attr', device_or_entity_id, attr_name)

    def is_device_attr(self, device_or_entity_id: str, attr_name: str, attr_value: str | int | float) -> bool:
        """Get returns whether the value of attr_name for the given device or entity ID matches attr_value.

        See `device functions <https://www.home-assistant.io/docs/configuration/templating/#devices>`_ for more
        information.
        """
        return self._template_command('is_device_attr', device_or_entity_id, attr_name, str(attr_value))

    def device_id(self, entity_id: str) -> str:
        """Get the device ID for a given entity ID or device name.

        See `device functions <https://www.home-assistant.io/docs/configuration/templating/#devices>`_ for more
        information.
        """
        return self._template_command('device_id', entity_id)

    # Areas
    # https://www.home-assistant.io/docs/configuration/templating/#areas

    def areas(self) -> list[str]:
        """Get the full list of area IDs.

        See `area functions <https://www.home-assistant.io/docs/configuration/templating/#areas>`_ for more information.
        """
        return self._template_command('areas')

    def area_id(self, lookup_value: str) -> str:
        """Get the area ID for a given device ID, entity ID, or area name.

        See `area functions <https://www.home-assistant.io/docs/configuration/templating/#areas>`_ for more information.
        """
        return self._template_command('area_id', lookup_value)

    def area_name(self, lookup_value: str) -> str:
        """Get the area name for a given device ID, entity ID, or area ID.

        See `area functions <https://www.home-assistant.io/docs/configuration/templating/#areas>`_ for more information.
        """
        return self._template_command('area_name', lookup_value)

    def area_entities(self, area_name_or_id: str) -> list[str]:
        """Get the list of entity IDs tied to a given area ID or name.

        See `area functions <https://www.home-assistant.io/docs/configuration/templating/#areas>`_ for more information.
        """
        return self._template_command('area_entities', area_name_or_id)

    def area_devices(self, area_name_or_id: str) -> list[str]:
        """Get the list of device IDs tied to a given area ID or name.

        See `area functions <https://www.home-assistant.io/docs/configuration/templating/#areas>`_ for more information.
        """
        return self._template_command('area_devices', area_name_or_id)

    # Entities for an Integration
    # https://www.home-assistant.io/docs/configuration/templating/#entities-for-an-integration

    def integration_entities(self, integration: str) -> list[str]:
        """Get a list of entities that are associated with a given integration, such as ``hue`` or ``zwave_js``.

        See `entities for an integration
        <https://www.home-assistant.io/docs/configuration/templating/#entities-for-an-integration>`_ for more
        information.
        """
        entities = self._template_command('integration_entities', integration)
        assert isinstance(entities, list) and all(isinstance(e, str) for e in entities), \
            'Invalid return type from integration_entities'
        return entities

    # Labels
    # https://www.home-assistant.io/docs/configuration/templating/#labels

    def labels(self) -> list[str]:
        """Get the full list of label IDs, or those for a given area ID, device ID, or entity ID.

        See `label functions <https://www.home-assistant.io/docs/configuration/templating/#labels>`_ for more
        information.
        """
        return self._template_command('labels')

    def label_id(self, lookup_value: str) -> str:
        """Get the label ID for a given label name.

        See `label functions <https://www.home-assistant.io/docs/configuration/templating/#labels>`_ for more
        information.
        """
        return self._template_command('label_id', lookup_value)

    def label_name(self, lookup_value: str) -> str:
        """Get the label name for a given label ID.

        See `label functions <https://www.home-assistant.io/docs/configuration/templating/#labels>`_ for more
        information.
        """
        return self._template_command('label_name', lookup_value)

    def label_areas(self, label_name_or_id: str) -> list[str]:
        """Get the list of area IDs tied to a given label ID or name.

        See `label functions <https://www.home-assistant.io/docs/configuration/templating/#labels>`_ for more
        information.
        """
        return self._template_command('label_areas', label_name_or_id)

    def label_devices(self, label_name_or_id: str) -> list[str]:
        """Get the list of device IDs tied to a given label ID or name.

        See `label functions <https://www.home-assistant.io/docs/configuration/templating/#labels>`_ for more
        information.
        """
        return self._template_command('label_devices', label_name_or_id)

    def label_entities(self, label_name_or_id: str) -> list[str]:
        """Get the list of entity IDs tied to a given label ID or name.

        See `label functions <https://www.home-assistant.io/docs/configuration/templating/#labels>`_ for more
        information.
        """
        return self._template_command('label_entities', label_name_or_id)

    # Conversation
    # https://developers.home-assistant.io/docs/intent_conversation_api

    def process_conversation(
        self,
        text: str,
        language: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        *,
        namespace: str | None = None,
        timeout: str | int | float | None = None,
        hass_timeout: str | int | float | None = None,
        callback: ServiceCallback | None = None,
        return_response: bool = True,
    ) -> dict[str, Any]:
        """Send a message to a conversation agent for processing with the
        `conversation.process action <https://www.home-assistant.io/integrations/conversation/#action-conversationprocess>`_

        This action is able to return
        `response data <https://www.home-assistant.io/docs/scripts/perform-actions/#use-templates-to-handle-response-data>`_.
        The response is the same as the one returned by the `/api/conversation/process` API; see
        `<https://developers.home-assistant.io/docs/intent_conversation_api#conversation-response>`_ for details.

        See the docs on the `conversation integration <https://www.home-assistant.io/integrations/conversation/>`__ for
        more information.

        Args:
            text (str): Transcribed text input to send to the conversation agent.
            language (str, optional): Language of the text. Defaults to None.
            agent_id (str, optional): ID of conversation agent. The conversation agent is the brains of the assistant.
                It processes the incoming text commands. Defaults to None.
            conversation_id (str, optional): ID of a new or previous conversation. Will continue an old conversation
                or start a new one. Defaults to None.
            namespace (str, optional): If provided, changes the namespace for the service call. Defaults to the current
                namespace of the app, so it's safe to ignore this parameter most of the time. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
            timeout (str | int | float, optional): Timeout for the app thread to wait for a response from the main
                thread.
            hass_timeout (str | int | float, optional): Timeout for AppDaemon waiting on a response from Home Assistant
                to respond to the backup request. Cannot be set lower than the timeout value.
            callback (ServiceCallback, optional): Function to call with the results of the request.
            return_response (bool, optional): Whether Home Assistant should return a response to the service call. Even
                if it's False, Home Assistant will still respond with an acknowledgement. Defaults to True

        Returns:
            dict: The response from the conversation agent. See the docs on
            `conversation response <https://developers.home-assistant.io/docs/intent_conversation_api/#conversation-response>`_
            for more information.

        Examples:
            Extracting the text of the speech response, continuation flag, and conversation ID:

            >>> full_response = self.process_conversation("Hello world!")
            >>> match full_response:
            ...     case {'success': True, 'result': dict(result)}:
            ...         match result['response']:
            ...             case {
            ...                 'response': dict(response),
            ...                 'continue_conversation': bool(continue_conv),
            ...                 'conversation_id': str(conv_id),
            ...             }:
            ...                 speech: str = response['speech']['plain']['speech']
            ...                 self.log(speech, ascii_encode=False)
            ...                 self.log(continue_conv)
            ...                 self.log(conv_id)

            Extracting entity IDs from a successful action response:

            >>> full_response = self.process_conversation("Turn on the living room lights")
            >>> match full_response:
            ...     case {'success': True, 'result': dict(result)}:
            ...         match result['response']:
            ...             case {'response': {'data': {'success': list(entities)}}}:
            ...                 eids = [e['id'] for e in entities]
            ...                 self.log(eids)
        """
        return self.call_service(
            service='conversation/process',
            text=text,
            language=language,
            agent_id=agent_id,
            conversation_id=conversation_id,
            namespace=namespace if namespace is not None else self.namespace,
            timeout=timeout,
            callback=callback,
            hass_timeout=hass_timeout,
            return_response=return_response,
        )

    def reload_conversation(
        self,
        language: str | None = None,
        agent_id: str | None = None,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Reload the intent cache for a conversation agent.

        See the docs on the `conversation integration <https://www.home-assistant.io/integrations/conversation/>`__ for
        more information.

        Args:
            language (str, optional): Language to clear intent cache for. No value clears all languages. Defaults to None.
            agent_id (str, optional): ID of conversation agent. Defaults to the built-in Home Assistant agent.
            namespace (str, optional): If provided, changes the namespace for the service call. Defaults to the current
                namespace of the app, so it's safe to ignore this parameter most of the time. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.

        Returns:
            dict: The acknowledgement response from Home Assistant.
        """
        return self.call_service(
            service='conversation/reload',
            language=language,
            agent_id=agent_id,
            namespace=namespace if namespace is not None else self.namespace,
        )
