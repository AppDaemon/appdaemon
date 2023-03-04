from appdaemon.appdaemon import AppDaemon
from appdaemon.exceptions import TimeOutException
import appdaemon.utils as utils

from typing import Any, Optional, Callable, Union
from logging import Logger
import asyncio
import uuid
import iso8601
from collections.abc import Iterable


class EntityAttrs:
    def __init__(self):
        pass

    def __get__(self, instance, owner):
        stateattrs = utils.EntityStateAttrs(instance.AD.state.get_state_simple(instance.namespace, instance.entity_id))
        return stateattrs


class Entity:
    states_attrs = EntityAttrs()

    def __init__(self, logger: Logger, ad: AppDaemon, name: str, namespace: str, entity_id: str):
        # Store args

        self.AD = ad
        self.name = name
        self.logger = logger
        self._entity_id = entity_id
        self._namespace = namespace
        self._async_events = {}

    def set_namespace(self, namespace: str) -> None:
        """Sets a new namespace for the Entity to use from that point forward.
        It should be noted that when this function is used, a different entity will be referenced.
        Since each entity is tied to a certain namespace, at every point in time.

        Args:
            namespace (str): Name of the new namespace

        Returns:
            None.

        Examples:
            >>> # access entity in Hass namespace
            >>> self.my_entity = self.get_entity("light.living_room")
            >>> # want to copy the same entity into another namespace
            >>> entity_data = self.my_entity.copy()
            >>> self.my_entity.set_namespace("my_namespace")
            >>> self.my_entity.set_state(**entity_data)

        """
        self._namespace = namespace

    @utils.sync_wrapper
    async def set_state(self, **kwargs: Optional[Any]) -> dict:
        """Updates the state of the specified entity.

        Args:
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            state: New state value to be set.
            attributes (optional): Entity's attributes to be updated.
            replace(bool, optional): If a `replace` flag is given and set to ``True`` and ``attributes``
                is provided, AD will attempt to replace its internal entity register with the newly
                supplied attributes completely. This can be used to replace attributes in an entity
                which are no longer needed. Do take note this is only possible for internal entity state.
                For plugin based entities, this is not recommended, as the plugin will mostly replace
                the new values, when next it updates.

        Returns:
            A dictionary that represents the new state of the updated entity.

        Examples:
            >>> self.my_entity = self.get_entity("light.living_room")

            Update the state of an entity.

            >>> self.my_entity.set_state(state="off")

            Update the state and attribute of an entity.

            >>> self.my_entity.set_state(state = "on", attributes = {"color_name": "red"})

        """

        entity_id = self._entity_id
        namespace = self._namespace

        self.logger.debug("set state: %s, %s from %s", entity_id, kwargs, self.name)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        return await self.AD.state.set_state(self.name, namespace, entity_id, **kwargs)

    @utils.sync_wrapper
    async def get_state(
        self, attribute: str = None, default: Any = None, copy: bool = True, **kwargs: Optional[Any]
    ) -> Any:
        """Gets the state of any entity within AD.

        Args:
            attribute (str, optional): Name of an attribute within the entity state object.
                If this parameter is specified in addition to a fully qualified ``entity_id``,
                a single value representing the attribute will be returned. The value ``all``
                for attribute has special significance and will return the entire state
                dictionary for the specified entity rather than an individual attribute value.
            default (any, optional): The value to return when the requested attribute or the
                whole entity doesn't exist (Default: ``None``).
            copy (bool, optional): By default, a copy of the stored state object is returned.
                When you set ``copy`` to ``False``, you get the same object as is stored
                internally by AppDaemon. Avoiding the copying brings a small performance gain,
                but also gives you write-access to the internal AppDaemon data structures,
                which is dangerous. Only disable copying when you can guarantee not to modify
                the returned state object, e.g., you do read-only operations.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:

        Returns:
            The entire state of the entity at that given time, if  if ``get_state()``
            is called with no parameters. This will consist of a dictionary with a key
            for each entity. Under that key will be the standard entity state information.

        Examples:
            >>> self.my_entity = self.get_entity("light.office_1")

            Get the state attribute of `light.office_1`.

            >>> state = self.my_entity.get_state("light.office_1")

            Get the brightness attribute of `light.office_1`.

            >>> state = self.my_entity.get_state(attribute="brightness")

            Get the entire state of `light.office_1`.

            >>> state = self.my_entity.get_state(attribute="all")

        """

        entity_id = self._entity_id
        namespace = self._namespace

        self.logger.debug("get state: %s, %s from %s", entity_id, kwargs, self.name)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        return await self.AD.state.get_state(self.name, namespace, entity_id, attribute, default, copy)

    @utils.sync_wrapper
    async def listen_state(self, callback: Callable, **kwargs: Optional[Any]) -> str:
        """Registers a callback to react to state changes.

        This function allows the user to register a callback for a wide variety of state changes.

        Args:
            callback: Function to be invoked when the requested state change occurs. It must conform
                to the standard State Callback format documented `here <APPGUIDE.html#state-callbacks>`__
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            attribute (str, optional): Name of an attribute within the entity state object. If this
                parameter is specified in addition to a fully qualified ``entity_id``. ``listen_state()``
                will subscribe to changes for just that attribute within that specific entity.
                The ``new`` and ``old`` parameters in the callback function will be provided with
                a single value representing the attribute.

                The value ``all`` for attribute has special significance and will listen for any
                state change within the specified entity, and supply the callback functions with
                the entire state dictionary for the specified entity rather than an individual
                attribute value.
            new (optional): If ``new`` is supplied as a parameter, callbacks will only be made if the
                state of the selected attribute (usually state) in the new state match the value
                of ``new``. The parameter type is defined by the namespace or plugin that is responsible
                for the entity. If it looks like a float, list, or dictionary, it may actually be a string.
            old (optional): If ``old`` is supplied as a parameter, callbacks will only be made if the
                state of the selected attribute (usually state) in the old state match the value
                of ``old``. The same caveats on types for the ``new`` parameter apply to this parameter.

            duration (int, optional): If ``duration`` is supplied as a parameter, the callback will not
                fire unless the state listened for is maintained for that number of seconds. This
                requires that a specific attribute is specified (or the default of ``state`` is used),
                and should be used in conjunction with the ``old`` or ``new`` parameters, or both. When
                the callback is called, it is supplied with the values of ``entity``, ``attr``, ``old``,
                and ``new`` that were current at the time the actual event occurred, since the assumption
                is that none of them have changed in the intervening period.

                If you use ``duration`` when listening for an entire device type rather than a specific
                entity, or for all state changes, you may get unpredictable results, so it is recommended
                that this parameter is only used in conjunction with the state of specific entities.

            timeout (int, optional): If ``timeout`` is supplied as a parameter, the callback will be created as normal,
                 but after ``timeout`` seconds, the callback will be removed. If activity for the listened state has
                 occurred that would trigger a duration timer, the duration timer will still be fired even though the
                 callback has been deleted.

            immediate (bool, optional): It enables the countdown for a delay parameter to start
                at the time, if given. If the ``duration`` parameter is not given, the callback runs immediately.
                What this means is that after the callback is registered, rather than requiring one or more
                state changes before it runs, it immediately checks the entity's states based on given
                parameters. If the conditions are right, the callback runs immediately at the time of
                registering. This can be useful if, for instance, you want the callback to be triggered
                immediately if a light is already `on`, or after a ``duration`` if given.

                If ``immediate`` is in use, and ``new`` and ``duration`` are both set, AppDaemon will check
                if the entity is already set to the new state and if so it will start the clock
                immediately. If ``new`` and ``duration`` are not set, ``immediate`` will trigger the callback
                immediately and report in its callback the new parameter as the present state of the
                entity. If ``attribute`` is specified, the state of the attribute will be used instead of
                state. In these cases, ``old`` will be ignored and when the callback is triggered, its
                state will be set to ``None``.
            oneshot (bool, optional): If ``True``, the callback will be automatically cancelled
                after the first state change that results in a callback.
            pin (bool, optional): If ``True``, the callback will be pinned to a particular thread.
            pin_thread (int, optional): Sets which thread from the worker pool the callback will be
                run by (0 - number of threads -1).
            *kwargs (optional): Zero or more keyword arguments that will be supplied to the callback
                when it is called.

        Notes:
            The ``old`` and ``new`` args can be used singly or together.

        Returns:
            A unique identifier that can be used to cancel the callback if required. Since variables
            created within object methods are local to the function they are created in, and in all
            likelihood, the cancellation will be invoked later in a different function, it is
            recommended that handles are stored in the object namespace, e.g., `self.handle`.

        Examples:
            >>> self.my_entity = self.get_entity("light.office_1")

            Listen for a state change involving `light.office1` and return the state attribute.

            >>> self.handle = self.my_entity.listen_state(self.my_callback)

            Listen for a change involving the brightness attribute of `light.office1` and return the
            brightness attribute.

            >>> self.handle = self.my_entity.listen_state(self.my_callback, attribute = "brightness")

            Listen for a state change involving `light.office1` turning on and return the state attribute.

            >>> self.handle = self.my_entity.listen_state(self.my_callback, new = "on")

            Listen for a change involving `light.office1` changing from brightness 100 to 200 and return the
            brightness attribute.

            >>> self.handle = self.my_entity.listen_state(self.my_callback, attribute = "brightness", old = "100", new = "200")

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute.

            >>> self.handle = self.my_entity.listen_state(self.my_callback, new = "on", duration = 60)

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute
            trigger the delay immediately if the light is already on.

            >>> self.handle = self.my_entity.listen_state(self.my_callback, new = "on", duration = 60, immediate = True)
        """

        entity_id = self._entity_id
        namespace = self._namespace

        if "namespace" in kwargs:
            del kwargs["namespace"]

        name = self.name

        self.logger.debug("Calling listen_state for %s, %s from %s", entity_id, kwargs, self.name)

        return await self.AD.state.add_state_callback(name, namespace, entity_id, callback, kwargs)

    @utils.sync_wrapper
    async def add(self, state: Union[str, int, float] = None, attributes: dict = None) -> None:
        """Adds a non-existent entity, by creating it within a namespaces.

        It should be noted that this api call, is mainly for creating AD internal entities.
        If wanting to create an entity within an external system, do check the system's documentation

        Args:
            state (optional): The state the new entity is to have
            attributes (optional): The attributes the new entity is to have

        Returns:
            None

        Examples:
            >>> self.my_entity = self.get_entity("zigbee.living_room_light")

            create the entity entity.

            >>> self.my_entity.add(state="off", attributes={"friendly_name": "Living Room Light"})

        """

        namespace = self._namespace
        entity_id = self._entity_id

        if await self.exists():
            self.logger.warning("%s already exists, will not be adding it", entity_id)
            return None

        await self.AD.state.add_entity(namespace, entity_id, state, attributes)

    @utils.sync_wrapper
    async def exists(self) -> bool:
        """Checks the existence of the entity in AD."""

        namespace = self._namespace
        entity_id = self._entity_id

        return await self.AD.state.entity_exists(namespace, entity_id)

    @utils.sync_wrapper
    async def call_service(self, service: str, **kwargs: Optional[Any]) -> Any:
        """Calls an entity supported Service within AppDaemon.

        This function can call only services that are tied to the entity, and provide any required parameters.

        Args:
            service (str): The service name, without the domain (e.g "toggle")
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            **kwargs: Each service has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `state = on`. These parameters will be different for
                every service and can be discovered using the developer tools.

            return_result(bool, option): If `return_result` is provided and set to `True` AD will attempt
                to wait for the result, and return it after execution
            callback: The non-async callback to be executed when complete.

        Returns:
            Result of the `call_service` function if any

        Examples:
            HASS

            >>> self.my_entity = self.get_entity("light.office_1")
            >>> self.my_entity.call_service("turn_on", color_name = "red")

        """

        entity_id = self._entity_id
        namespace = self._namespace

        kwargs["entity_id"] = entity_id

        domain, _ = entity_id.split(".")
        self.logger.debug("call_service: %s/%s, %s", domain, service, kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        kwargs["__name"] = self.name

        return await self.AD.services.call_service(namespace, domain, service, kwargs)

    async def wait_state(
        self,
        state: Any,
        attribute: Union[str, int] = None,
        duration: Union[int, float] = 0,
        timeout: Union[int, float] = None,
    ) -> None:
        """Used to wait for the state of an entity's attribute

        This API call is only functional within an async function. It should be noted that when instanciated,
        the api checks immediately if its already on the required state, and if it is, it will continue.

        Args:
            state (Any): The state to wait for, for the entity to be in before continuing
            attribute (str): The entity's attribute to use, if not using the entity's state
            duration (int|float): How long the state is to hold, before continuing
            timeout (int|float): How long to wait for the state to be achieved, before timing out.
                                When it times out, a appdaemon.exceptions.TimeOutException is raised

        Returns:
            None

        Examples:
            >>> from appdaemon.exceptions import TimeOutException
            >>>
            >>> async def run_my_sequence(self):
            >>>     sequence_object = self.get_entity("sequence.run_the_thing")
            >>>     await sequence_object.call_service("run")
            >>>     try:
            >>>         await sequence_object.wait_state("idle", timeout=30) # wait for it to completely run
            >>>     except TimeOutException:
            >>>         pass # didn't complete on time

        """

        wait_id = uuid.uuid4().hex
        async_event = asyncio.Event()
        async_event.clear()
        self._async_events[wait_id] = async_event

        try:
            handle = await self.listen_state(
                self.entity_state_changed,
                new=state,
                attribute=attribute,
                duration=duration,
                immediate=True,
                oneshot=True,
                __silent=True,
                wait_id=wait_id,
            )
            await asyncio.wait_for(async_event.wait(), timeout=timeout)

        except asyncio.TimeoutError:
            await self.AD.state.cancel_state_callback(handle, self.name)
            self.logger.warning(f"State Wait for {self._entity_id} Timed Out")
            raise TimeOutException("The entity timed out")

    async def entity_state_changed(self, *args: list, **kwargs: dict) -> None:
        """The entity state changed"""

        wait_id = args[4]["wait_id"]
        async_event = self._async_events.pop(wait_id)

        # now release the wait
        async_event.set()

    #
    # Entry point for entity api calls
    #

    @classmethod
    def entity_api(cls, logger: Logger, ad: AppDaemon, name: str, namespace: str, entity: str):
        return cls(logger, ad, name, namespace, entity)

    #
    # helper functions
    #

    @utils.sync_wrapper
    async def copy(self, copy: bool = True) -> dict:
        """Gets the complete state of the entity within AD.

        This is essentially a helper function, to get all data about an entity

        Args:
            copy (bool): If set to False, it will not make a deep copy of the entity. This can help with speed of accessing the data
        """

        return await self.get_state(attribute="all", copy=copy, default={})

    @utils.sync_wrapper
    async def is_state(self, state: Any) -> bool:
        """Checks the state of the entity against the given state

        This helper function supports using both iterable and non-iterable data

        Args:
            state (any): The state or iterable set of state data, to check against

        Example:
            >>> light_entity_object.is_state("on")
            >>> media_object.is_state(["playing", "paused"])

        """

        entity_state = await self.get_state(copy=False)

        if isinstance(state, (str, int, float)):
            return entity_state == state

        elif isinstance(state, Iterable):
            return entity_state in state

        return entity_state == state

    @utils.sync_wrapper
    async def turn_on(self, **kwargs: Optional[Any]) -> Any:
        """Generic helper function, used to turn the entity ON if supported.
        This function will attempt to call the `turn_on` service if registered,
        either by an app or plugin within the entity's namespace. So therefore its
        only functional, if the service `turn_on` exists within the namespace the
        entity is operating in.

        Keyword Args:
            **kwargs: Turn_on services depending on the namespace functioning within
                has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `transition = 3`. These parameters will be different for
                every service being used.
        """

        return await self.call_service("turn_on", **kwargs)

    @utils.sync_wrapper
    async def turn_off(self, **kwargs: Optional[Any]) -> Any:
        """Generic function, used to turn the entity OFF if supported.
        This function will attempt to call the `turn_off` service if registered,
        either by an app or plugin within the entity's namespace. So therefore its
        only functional, if the service `turn_off` exists within the namespace the
        entity is operating in.

        Keyword Args:
            **kwargs: Turn_off services depending on the namespace functioning within
                has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `transition = 3`. These parameters will be different for
                every service being used.
        """

        return await self.call_service("turn_off", **kwargs)

    @utils.sync_wrapper
    async def toggle(self, **kwargs: Optional[Any]) -> Any:
        """Generic function, used to toggle the entity ON/OFF if supported.
        This function will attempt to call the `toggle` service if registered,
        either by an app or plugin within the entity's namespace. So therefore its
        only functional, if the service `toggle` exists within the namespace the
        entity is operating in.

        Keyword Args:
            **kwargs: Toggle services depending on the namespace functioning within
                has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `transition = 3`. These parameters will be different for
                every service being used.
        """

        return await self.call_service("toggle", **kwargs)

    #
    # Properties
    #

    @property
    def entity_id(self) -> str:
        """Get the entity's entity_id"""

        return self._entity_id

    @property
    def state(self) -> Any:
        """Get the entity's state"""

        return self.states_attrs.state

    @property
    def domain(self) -> str:
        """Get the entity's domain name"""

        return self._entity_id.split(".")[0]

    @property
    def namespace(self) -> str:
        """Get the entity's namespace name"""

        return self._namespace

    @property
    def entity_name(self) -> str:
        """Get the entity's name"""

        return self._entity_id.split(".")[1]

    @property
    def attributes(self) -> dict:
        """Get the entity's attributes"""

        return self.states_attrs.attributes

    @property
    def friendly_name(self) -> str:
        """Get the entity's friendly name"""

        return self.states_attrs.attributes.friendly_name

    @property
    def last_changed(self) -> str:
        """Get the entity's last changed time in iso format"""

        return self.states_attrs.last_changed

    @property
    def last_changed_seconds(self) -> float:
        """Get the entity's last changed time in seconds"""

        utc = iso8601.parse_date(self.states_attrs.last_changed)
        now = self.AD.sched.get_now_sync()
        return (now - utc).total_seconds()

    def __repr__(self) -> str:
        return self._entity_id
