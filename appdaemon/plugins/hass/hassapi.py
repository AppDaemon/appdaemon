import re
from ast import literal_eval
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Type, overload

from ... import utils
from ...adapi import ADAPI
from ...adbase import ADBase
from ...appdaemon import AppDaemon
from ...models.app_config import AppConfig
from ...models.notification.android import AndroidData
from ...models.notification.base import NotificationData
from ...models.notification.iOS import iOSData
from .hassplugin import HassPlugin
from .notifications import AndroidNotification


class Hass(ADBase, ADAPI):
    """HASS API class for the users to inherit from.

    This class provides an interface to the HassPlugin object that connects to Home Assistant.
    """

    _plugin: HassPlugin

    def __init__(self, ad: AppDaemon, config_model: AppConfig):
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
    async def ping(self) -> float:
        """Gets the number of seconds """
        if (plugin := self._plugin) is not None:
            return (await plugin.ping())['ad_duration']

    @utils.sync_decorator
    async def check_for_entity(self, entity_id: str, namespace: str | None = None) -> bool:
        """Uses the REST API to check if an entity exists instead of checking
        AD's internal state.

        Args:
            entity_id (str): Fully qualified id.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            Bool of whether the entity exists.
        """
        plugin: "HassPlugin" = self.AD.plugins.get_plugin_object(
            namespace or self.namespace
        )
        return await plugin.check_for_entity(entity_id)

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
        namespace = namespace or self.namespace
        domain = service.split('/')[0]

        match entity_id:
            case str():
                assert domain == entity_id.split('.')[0], f'{entity_id} does not match domain for {service}'
                self._check_entity(namespace, entity_id)
            case Iterable():
                entity_id = entity_id if isinstance(entity_id, list) else list(entity_id)
                for e in entity_id:
                    assert domain == e.split('.')[0], f'{e} does not match domain for {service}'
                    self._check_entity(namespace, e)

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

    def anyone_home(self, person: bool = True, namespace: str | None = None) -> bool:
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
        details = self.get_tracker_details(person, namespace, copy=False)
        return any(state['state'] == 'home' for state in details.values())

    def everyone_home(self, person: bool = True, namespace: str | None = None) -> bool:
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
        details = self.get_tracker_details(person, namespace, copy=False)
        return all(state['state'] == 'home' for state in details.values())

    def noone_home(self, person: bool = True, namespace: str | None = None) -> bool:
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
        return not self.anyone_home(person, namespace)

    #
    # Built-in constraints
    #

    def constrain_presence(self, value: Literal["everyone", "anyone", "noone"] | None = None) -> bool:
        """Returns True if unconstrained"""
        match value.lower():
            case "everyone":
                return not self.everyone_home()
            case "anyone":
                return not self.anyone_home()
            case "noone":
                return not self.noone_home()
            case None:
                return True
            case _:
                raise ValueError(f'Invalid presence constraint: {value}')

    def constrain_person(self, value: Literal["everyone", "anyone", "noone"] | None = None) -> bool:
        """Returns True if unconstrained"""
        match value.lower():
            case "everyone":
                return not self.everyone_home(person=True)
            case "anyone":
                return not self.anyone_home(person=True)
            case "noone":
                return not self.noone_home(person=True)
            case None:
                return True
            case _:
                raise ValueError(f'Invalid presence constraint: {value}')

    def constrain_input_boolean(self, value: str | Iterable[str]) -> bool:
        """Returns True if unconstrained - all input_booleans match the desired
        state. Desired state defaults to ``on``
        """
        match value:
            case Iterable():
                constraints = value if isinstance(value, list) else list(value)
            case str():
                constraints = [value]

        assert isinstance(value, list) and all(isinstance(v, str) for v in value)

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
            case Iterable():
                constraints = value if isinstance(value, list) else list(value)
            case str():
                constraints = [value]

        assert isinstance(value, list) and all(isinstance(v, str) for v in value)

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
        minimal_response: bool | None = None,
        no_attributes: bool | None = None,
        significant_changes_only: bool | None = None,
        callback: Callable | None = None,
        namespace: str | None = None,
    ) -> list[list[dict[str, Any]]]:
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

        namespace = namespace or self._namespace

        if days is not None:
            end_time = end_time or await self.get_now()
            start_time = end_time - timedelta(days=days)


        plugin: "HassPlugin" = self.AD.plugins.get_plugin_object(
            namespace or self.namespace
        )

        if plugin is not None:
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

        else:
            self.logger.warning(
                "Wrong Namespace selected, as %s has no database plugin attached to it",
                namespace,
            )

    @utils.sync_decorator
    async def get_logbook(
        self,
        entity: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        days: int | None = None,
        callback: Callable | None = None,
        namespace: str | None = None,
    ) -> list[dict[str, str | datetime]]:
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
            end_time = end_time or await self.get_now()
            start_time = end_time - timedelta(days=days)

        plugin: "HassPlugin" = self.AD.plugins.get_plugin_object(
            namespace or self.namespace
        )
        if plugin is not None:
            coro = plugin.get_logbook(
                entity=entity,
                timestamp=start_time,
                end_time=end_time,
            )

            if callback is not None and callable(callback):
                self.create_task(coro, callback)
            else:
                return await coro

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

    def last_pressed(self, button_id: str, namespace: str | None = None) -> datetime:
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

    def time_since_last_press(self, button_id: str, namespace: str | None = None) -> timedelta:
        """Only works on entities in the input_button domain"""
        return self.get_now() - self.last_pressed(button_id, namespace)

    #
    # Notifications
    #

    @utils.sync_decorator
    async def notify(
        self,
        message: str,
        title: str = None,
        name: str = None,
        namespace: str | None = None,
    ) -> None:
        """Sends a notification.

        This is a convenience function for the ``notify.notify`` service. It
        will send a notification to a named notification service. If the name is
        not specified, it will default to ``notify/notify``.

        Args:
            message (str): Message to be sent to the notification service.
            title (str, optional): Title of the notification.
            name (str, optional): Name of the notification service.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            Result of the `notify` function if any, see `service call notes
            <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            >>> self.notify("Switching mode to Evening")
            >>> self.notify("Switching mode to Evening", title = "Some Subject", name = "smtp")
                # will send a message through notify.smtp instead of the default notify.notify

        """
        return await self.call_service(
            service=f'notify/{name}' if name is not None else 'notify/notify',
            namespace=namespace,
            title=title,
            message=message,
        )

    @utils.sync_decorator
    async def persistent_notification(self, message: str, title=None, id=None) -> None:
        """

        Args:
            message:
            title:
            id:

        Returns:

        Todo:
            * Finish

        """
        kwargs = {"message": message}
        if title is not None:
            kwargs["title"] = title
        if id is not None:
            kwargs["notification_id"] = id
        await self.call_service("persistent_notification/create", **kwargs)

    @overload
    def notify_android(
        self,
        device: str,
        tag: str,
        title: str,
        message: str,
        target: str,
        **data
    ) -> dict: ...

    def notify_android(self, device: str, tag: str = 'appdaemon', **kwargs) -> dict:
        """Convenience method for quickly creating mobile Android notifications"""
        return self._notify_mobile_app(device, AndroidData, tag, **kwargs)

    def notify_ios(self, device: str, tag: str = 'appdaemon', **kwargs) -> dict:
        """Convenience method for quickly creating mobile iOS notifications"""
        return self._notify_mobile_app(device, iOSData, tag, **kwargs)

    def _notify_mobile_app(
        self,
        device: str,
        model: str | Type[NotificationData],
        tag: str = 'appdaemon',
        **kwargs
    ) -> dict:
        match model:
            case NotificationData():
                pass
            case 'android':
                model = AndroidData
            case 'iOS' | 'ios':
                model = iOSData

        model = model.model_validate(kwargs)
        model.data.tag = model.data.tag or tag # Fills in the tag if it's blank
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
        return self.call_service(
            **AndroidNotification.tts(device, tts_text, media_stream, critical).to_service_call()
        )

    def listen_notification_action(self, callback: Callable, action: str) -> str:
        return self.listen_event(callback, 'mobile_app_notification_action', action=action)

    # Backup/Restore

    @overload
    def backup_full(
        self,
        name: str | None = None,
        password: str | None = None,
        compressed: bool = True,
        location: str | None = None,
        homeassistant_exclude_database: bool = False,
        timeout: int | float = 30 # Used by sync_decorator
    ): ...

    @utils.sync_decorator
    async def backup_full(self, name=None, timeout: int | float = 30, **kwargs) -> dict:
        # https://www.home-assistant.io/integrations/hassio/#action-hassiobackup_full
        return await self.call_service("hassio/backup_full", name=name, **kwargs)

    @overload
    async def backup_partial(
        self,
        addons: Iterable[str] = None,
        folders: Iterable[str] = None,
        name: str = None,
        password: str = None,
        compressed: bool = True,
        location: str = None,
        homeassistant: bool = False,
        homeassistant_exclude_database: bool = False,
        timeout: int | float = 30 # Used by sync_decorator
    ): ...

    @utils.sync_decorator
    async def backup_partial(self, name=None, timeout: int | float = 30, **kwargs) -> dict:
        # https://www.home-assistant.io/integrations/hassio/#action-hassiobackup_partial
        return await self.call_service("hassio/backup_partial", name=name, **kwargs)

    @utils.sync_decorator
    async def restore_full(
        self,
        slug: str,
        password: str | None = None,
        timeout: int | float = 30 # Used by sync_decorator
    ) -> dict:
        # https://www.home-assistant.io/integrations/hassio/#action-hassiorestore_full
        return await self.call_service("hassio/restore_full", slug=slug, password=password)

    @overload
    async def restore_parial(
        self,
        slug: str,
        homeassistant: bool = False,
        addons: Iterable[str] = None,
        folders: Iterable[str] = None,
        password: str = None,
        timeout: int | float = 30 # Used by sync_decorator
    ): ...

    async def restore_parial(self, slug: str, timeout: int | float = 30, **kwargs) -> dict:
        # https://www.home-assistant.io/integrations/hassio/#action-hassiorestore_partial
        return await self.call_service("hassio/restore_parial", slug=slug, **kwargs)

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

    #
    # Template functions
    # Functions that use self.render_template

    @utils.sync_decorator
    async def render_template(self, template: str, namespace: str | None = None) -> Any:
        """Renders a Home Assistant Template

        https://www.home-assistant.io/docs/configuration/templating
        https://www.home-assistant.io/integrations/template

        Args:
            template (str): The Home Assistant template to be rendered.
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            The rendered template in a native Python type.

        Examples:
            >>> self.render_template("{{ states('sun.sun') }}")
            Returns (str) above_horizon

            >>> self.render_template("{{ is_state('sun.sun', 'above_horizon') }}")
            Returns (bool) True

            >>> self.render_template("{{ states('sensor.outside_temp') }}")
            Returns (float) 97.2

        """
        plugin: "HassPlugin" = self.AD.plugins.get_plugin_object(
            namespace or self.namespace
        )
        result = await plugin.render_template(self.namespace, template)
        try:
            return literal_eval(result)
        except (SyntaxError, ValueError):
            return result

    # Device IDs

    @utils.sync_decorator
    async def get_device_id(self, entity_id: str) -> str:
        """Uses the ``device_id`` function in a template to get the device ID"""
        return await self.render_template(f'{{{{device_id("{entity_id}")}}}}')

    @utils.sync_decorator
    async def get_device_entities(self, device_id: str) -> list[str]:
        """Uses the ``device_entities`` function in a template to get entities
        associated with a device.
        """
        return await self.render_template(f'{{{{device_entities("{device_id}")}}}}')

    # Labels
    # https://www.home-assistant.io/docs/configuration/templating/#labels

    def _label_command(self, command: str, input: str) -> str | list[str]:
        return self.render_template(f'{{{{ {command}("{input}") }}}}')

    def labels(self, input: str = None) -> list[str]:
        if input is None:
            return self.render_template('{{ labels() }}')
        else:
            return self._label_command('labels', input)

    def label_id(self, lookup_value: str) -> str:
        return self._label_command('label_id', lookup_value)

    def label_name(self, lookup_value: str):
        return self._label_command('label_name', lookup_value)

    def label_areas(self, label_name_or_id: str) -> list[str]:
        return self._label_command('label_areas', label_name_or_id)

    def label_devices(self, label_name_or_id: str) -> list[str]:
        return self._label_command('label_devices', label_name_or_id)

    def label_entities(self, label_name_or_id: str) -> list[str]:
        return self._label_command('label_entities', label_name_or_id)
