import asyncio
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from logging import Logger
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

import appdaemon.utils as utils
from .exceptions import TimeOutException
from .state import StateCallback

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


@dataclass
class Entity:
    """Dataclass to wrap the logic for interacting with a certain entity.

    Primarily stores the namespace, app name, and entity id in order to pre-fill calls to the AppDaemon internals.
    """

    logger: Logger
    AD: "AppDaemon"
    name: str
    namespace: str
    entity_id: str | None
    _async_events: dict[str, asyncio.Event] = field(default_factory=lambda: defaultdict(asyncio.Event))
    # states_attrs = EntityAttrs()

    def set_namespace(self, namespace: str) -> None:
        """Set a new namespace for the Entity to use from that point forward.

        This doesn't change anything about the entity itself, but it does change the namespace that this instance of the
        entity API references. There might not be an entity with the same ID in the new namespace.

        Args:
            namespace (str): Name of the new namespace

        Returns:
            None.

        Examples:
            Get an entity

            >>> self.light = self.get_entity("light.living_room")

            Copy the full state from the entity

            >>> state = self.my_entity.copy()

            Set the new namespace

            >>> self.light.set_namespace("my_namespace")

            Set the state of the entity

            >>> self.light.set_state(**entity_data)

            Verify

            >>> self.light.get_state(attribute="all")

        """
        self.namespace = namespace

    @utils.sync_decorator
    async def set_state(
        self,
        state: Any | None,
        attributes: dict | None = None,
        replace: bool = False,
        **kwargs
    ) -> dict:
        """Update the state of the specified entity.

        This causes a ``state_changed`` event to be emitted in the entity's namespace. If that namespace is associated
        with a Home Assistant plugin, it will use the ``/api/states/<entity_id>`` endpoint of the
        `REST API <https://developers.home-assistant.io/docs/api/rest/>`__ to update the state of the entity. This
        method can be useful to create entities in Home Assistant, but they won't persist across restarts.

        Args:
            state: New state value to be set.
            attributes (dict[str, Any], optional): Optional dictionary to use for the attributes. If replace is
                ``False``, then the attribute dict will use the built-in update method on this dict. If replace is
                ``True``, then the attribute dict will be entirely replaced with this one.
            replace(bool, optional): Whether to replace rather than update the attributes. Defaults to ``False``. For
                plugin based entities, this is not recommended, as the plugin will mostly replace the new values, when
                next it updates.
            **kwargs (optional): Zero or more keyword arguments. These will be applied to the attributes.

        Returns:
            A dictionary that represents the new state of the updated entity.

        Examples:
            >>> self.my_entity = self.get_entity("light.living_room")

            Update the state of an entity.

            >>> self.my_entity.set_state(state="off")

            Update the state and attribute of an entity.

            >>> self.my_entity.set_state(state = "on", attributes = {"color_name": "red"})

        """
        self.logger.debug("set state: %s, %s from %s", self.entity_id, kwargs, self.name)
        return await self.AD.state.set_state(
            name=self.name,
            namespace=self.namespace,
            entity=self.entity_id,
            state=state,
            attributes=attributes,
            replace=replace,
            **kwargs
        )

    @utils.sync_decorator
    async def get_state(
        self,
        attribute: str | None = None,
        default: Any | None = None,
        copy: bool = True
    ) -> Any:
        """Get the state of an entity from AppDaemon's internals.

        Home Assistant emits a ``state_changed`` event for every state change, which it sends to AppDaemon over the
        websocket connection made by the plugin. Appdaemon uses the data in these events to update its internal state.
        This method returns values from this internal state, so it does **not** make any external requests to Home
        Assistant.

        Other plugins that emit ``state_changed`` events will also have their states tracked internally by AppDaemon.

        It's common for entities to have a state that's always one of ``on``, ``off``, or ``unavailable``. This applies
        to entities in the ``light``, ``switch``, ``binary_sensor``, and ``input_boolean`` domains in Home Assistant,
        among others.

        Args:
            attribute (str, optional): Optionally specify an attribute to return. If not used, the state of the entity
                will be returned. The value ``all`` can be used to return the entire state dict rather than a single
                value.
            default (any, optional): The value to return when the entity or the attribute doesn't exist.
            copy (bool, optional): Whether to return a copy of the internal data. This is ``True`` by default in order
                to protect the user from accidentally modifying AppDaemon's internal data structures, which is dangerous
                and can cause undefined behvaior. Only set this to ``False`` for read-only operations.

        Returns:
            The entire state of the entity at that given time, if  if ``get_state()``
            is called with no parameters. This will consist of a dictionary with a key
            for each entity. Under that key will be the standard entity state information.

        Examples:
            >>> self.my_entity = self.get_entity("light.office_1")

            Get the state attribute of `light.office_1`.

            >>> state = self.my_entity.get_state()

            Get the brightness attribute of `light.office_1`.

            >>> state = self.my_entity.get_state(attribute="brightness")

            Get the entire state of `light.office_1`.

            >>> state = self.my_entity.get_state(attribute="all")

        """
        self.logger.debug("get state: %s, %s from %s", self.entity_id, self.namespace, self.name)
        return await self.AD.state.get_state(
            name=self.name,
            namespace=self.namespace,
            entity_id=self.entity_id,
            attribute=attribute,
            default=default,
            copy=copy
        )

    @utils.sync_decorator
    async def listen_state(
        self,
        callback: StateCallback,
        new: str | Callable[[Any], bool] | None = None,
        old: str | Callable[[Any], bool] | None = None,
        duration: str | int | float | timedelta | None = None,
        attribute: str| None = None,
        timeout: str | int | float | timedelta | None = None,
        immediate: bool = False,
        oneshot: bool = False,
        pin: bool = False,
        pin_thread: int | None = None,
        **kwargs: Any
    ) -> str:
        """Registers a callback to react to state changes.

        This function allows the user to register a callback for a wide variety of state changes.

        Args:
            callback: Function to be invoked when the requested state change occurs. It must conform
                to the standard State Callback format documented `here <APPGUIDE.html#state-callbacks>`__
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
            attribute (str, optional): Name of an attribute within the entity state object. If this
                parameter is specified in addition to a fully qualified ``entity_id``. ``listen_state()``
                will subscribe to changes for just that attribute within that specific entity.
                The ``new`` and ``old`` parameters in the callback function will be provided with
                a single value representing the attribute.

                The value ``all`` for attribute has special significance and will listen for any
                state change within the specified entity, and supply the callback functions with
                the entire state dictionary for the specified entity rather than an individual
                attribute value.
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
            **kwargs (optional): Zero or more keyword arguments that will be supplied to the callback
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
        kwargs = dict(
            new=new,
            old=old,
            duration=duration,
            attribute=attribute,
            timeout=timeout,
            pin_app=pin,
            pin_thread=pin_thread,
            **kwargs
        )
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.debug("Calling listen_state for %s, %s from %s", self.entity_id, kwargs, self.name)
        return await self.AD.state.add_state_callback(
            name=self.name,
            namespace=self.namespace,
            entity=self.entity_id,
            cb=callback,
            oneshot=oneshot,
            immediate=immediate,
            kwargs=kwargs
        )

    @utils.sync_decorator
    async def add(self, state: str | int | float = None, attributes: dict = None) -> None:
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

        namespace = self.namespace
        entity_id = self.entity_id

        if self.exists():
            self.logger.warning("%s already exists, will not be adding it", entity_id)
            return None

        await self.AD.state.add_entity(namespace, entity_id, state, attributes)

    def exists(self) -> bool:
        """Checks the existence of the entity in AD."""
        return self.AD.state.entity_exists(self.namespace, self.entity_id)

    @utils.sync_decorator
    async def call_service(
        self,
        service: str,
        timeout: str | int | float | None = None,  # Used by utils.sync_decorator
        callback: Callable[[Any], Any] | None = None,
        **data: Any,
    ) -> Any:
        """Calls an entity supported Service within AppDaemon.

        This function can call only services that are tied to the entity, and provide any required parameters.

        Args:
            service (str): The service name, without the domain (e.g "toggle")
            return_result(bool, option): If `return_result` is provided and set to `True` AD will attempt
                to wait for the result, and return it after execution
            callback: The non-async callback to be executed when complete.
            **kwargs: Each service has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `state = on`. These parameters will be different for
                every service and can be discovered using the developer tools.

        Returns:
            Result of the `call_service` function if any

        Examples:
            HASS

            >>> self.my_entity = self.get_entity("light.office_1")
            >>> self.my_entity.call_service("turn_on", color_name="red")

        """
        kwargs = dict(
            entity_id=self.entity_id,
            **data
        )
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.debug("call_service: %s/%s, %s", self.domain, service, kwargs)
        coro = self.AD.services.call_service(
            namespace=self.namespace,
            domain=self.domain,
            service=service,
            data=data
        )  # fmt: skip
        if callback is None:
            return await coro
        else:
            task = self.AD.loop.create_task(coro)
            task.add_done_callback(lambda f: callback(f.result()))

    async def wait_state(
        self,
        state: Any,
        attribute: str | int = None,
        duration: int | float = 0,
        timeout: int | float = None,
    ) -> None:
        """Used to wait for the state of an entity's attribute

        This API call should only be used async. It should be noted that when instantiated,
        the api checks immediately if it's already in the required state and will continue if it is.

        Args:
            state (Any): The state to wait for, for the entity to be in before continuing
            attribute (str, optional): The entity's attribute to use, if not using the entity's state
            duration (int, float): How long the state is to hold, before continuing
            timeout (int, float): How long to wait for the state to be achieved, before timing out.
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
        async_event = self._async_events[wait_id]

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
        except asyncio.TimeoutError as e:
            await self.AD.state.cancel_state_callback(handle, self.name)
            self.logger.warning(f"State Wait for {self.entity_id} Timed Out")
            raise TimeOutException("The entity timed out") from e
        finally:
            self._async_events.pop(wait_id)

    async def entity_state_changed(self, *args, wait_id: str, **kwargs) -> None:
        """The entity state changed"""
        async_event = self._async_events.pop(wait_id)
        # now release the wait
        async_event.set()

    #
    # Entry point for entity api calls
    #

    @classmethod
    def entity_api(cls, logger: Logger, ad: "AppDaemon", name: str, namespace: str, entity: str):
        return cls(logger, ad, name, namespace, entity)

    #
    # helper functions
    #

    @utils.sync_decorator
    async def copy(self, copy: bool = True) -> dict:
        """Gets the complete state of the entity within AD.

        This is essentially a helper function, to get all data about an entity

        Args:
            copy (bool): If set to False, it will not make a deep copy of the entity. This can help with speed of accessing the data
        """

        return await self.get_state(attribute="all", copy=copy, default={})

    def is_state(self, state: Any) -> bool:
        """Checks the state of the entity against the given state

        This helper function supports using both iterable and non-iterable data

        Args:
            state (any): The state or iterable set of state data, to check against

        Example:
            >>> light_entity_object.is_state("on")
            >>> media_object.is_state(["playing", "paused"])

        """

        entity_state = self.get_state(copy=False)
        match state:
            case str() | int() | float():
                return entity_state == state
            case Iterable():
                return entity_state in state
            case _:
                return entity_state == state

    def is_on(self) -> bool:
        return self.is_state("on")

    @utils.sync_decorator
    async def turn_on(self, **kwargs) -> Any:
        """Generic helper function, used to turn the entity ON if supported.
        This function will attempt to call the `turn_on` service if registered,
        either by an app or plugin within the entity's namespace. So therefore its
        only functional, if the service `turn_on` exists within the namespace the
        entity is operating in.

        The keyword arguments accepted will vary depending on the namespace and
        associated plugin.

        https://www.home-assistant.io/integrations/light/#action-lightturn_on

        Keyword Args:
            **kwargs (optional): Zero or more keyword arguments. These will be applied to the attributes.
        """

        return await self.call_service("turn_on", **kwargs)

    @utils.sync_decorator
    async def turn_off(self, **kwargs: Any | None) -> Any:
        """Generic function, used to turn the entity OFF if supported.
        This function will attempt to call the `turn_off` service if registered,
        either by an app or plugin within the entity's namespace. So therefore its
        only functional, if the service `turn_off` exists within the namespace the
        entity is operating in.

        The keyword arguments accepted will vary depending on the namespace and
        associated plugin.

        https://www.home-assistant.io/integrations/light/#action-lightturn_off

        Keyword Args:
            **kwargs (optional): Zero or more keyword arguments. These will be applied to the attributes.
        """

        return await self.call_service("turn_off", **kwargs)

    @utils.sync_decorator
    async def toggle(self, **kwargs: Any | None) -> Any:
        """Generic function, used to toggle the entity ON/OFF if supported.
        This function will attempt to call the `toggle` service if registered,
        either by an app or plugin within the entity's namespace. So therefore its
        only functional, if the service `toggle` exists within the namespace the
        entity is operating in.

        The keyword arguments accepted will vary depending on the namespace and
        associated plugin.

        https://www.home-assistant.io/integrations/light/#action-lighttoggle

        Keyword Args:
            **kwargs (optional): Zero or more keyword arguments. These will be applied to the attributes.
        """

        return await self.call_service("toggle", **kwargs)

    #
    # Properties
    #

    @property
    def _simple_state(self) -> dict[str, Any]:
        return self.AD.state.get_state_simple(self.namespace, self.entity_id)

    @property
    def entity_id(self) -> str:
        """Get the entity's entity_id"""
        return self._entity_id

    @entity_id.setter
    def entity_id(self, new: str) -> str:
        """Get the entity's entity_id"""
        self._entity_id = new
        try:
            if new is not None:
                self.domain, self.entity_name = self._entity_id.split('.')
        except ValueError:
            # The entity_id could actually be just a domain
            self.domain = self._entity_id

    @property
    def state(self) -> Any:
        """Get the entity's state"""
        return self._simple_state["state"]

    @property
    def namespace(self) -> str:
        """Get the entity's namespace name"""

        return self._namespace

    @namespace.setter
    def namespace(self, new: str):
        self._namespace = new

    @property
    def attributes(self) -> dict[str, Any]:
        """Get the entity's attributes"""
        return self._simple_state.get("attributes", {})

    @property
    def friendly_name(self) -> str:
        """Get the entity's friendly name"""
        return self.attributes.get("friendly_name", self.entity_id)

    @property
    def last_changed(self) -> str:
        """Get the entity's last changed time in iso format"""
        return self._simple_state.get("last_changed")

    @property
    def last_changed_delta(self) -> timedelta | None:
        """The timedelta formatted as a string, with the fractional seconds truncated"""
        if time_str := self.last_changed:
            utc = datetime.fromisoformat(time_str)
            now = self.AD.sched.get_now_sync()
            return (now - utc)

    @property
    def last_changed_delta_str(self) -> str:
        """The timedelta formatted as a string, with the fractional seconds truncated"""
        if (td := self.last_changed_delta) is not None:
            return str(td)[:7]
        else:
            return ''

    @property
    def last_changed_seconds(self) -> float:
        """Get the entity's last changed time in seconds"""
        if td := self.last_changed_delta:
            return td.total_seconds()

    def __repr__(self) -> str:
        return self.entity_id
