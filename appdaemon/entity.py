from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils

from typing import Any, Optional, Callable, Union
from logging import Logger


class Entity:
    def __init__(self, logger: Logger, ad: AppDaemon, name: str, namespace: str, entity_id: str):
        # Store args

        self.AD = ad
        self._entity_id = entity_id
        self._namespace = namespace
        self.name = name
        self.logger = logger

    def set_namespace(self, namespace: str) -> None:
        """Sets a new namespace for the App to use from that point forward.

        Args:
            namespace (str): Name of the new namespace

        Returns:
            None.

        Examples:
            >>> self.set_namespace("hass1")

        """
        self._namespace = namespace

    def _get_namespace(self, **kwargs: Optional[dict]) -> str:
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]
            del kwargs["namespace"]
        else:
            namespace = self._namespace

        return namespace

    @utils.sync_wrapper
    async def set_state(self, **kwargs) -> dict:
        """Updates the state of the specified entity.

        Args:
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            state: New state value to be set.
            attributes (optional): Entity's attributes to be updated.
            namespace(str, optional): If a `namespace` is provided, AppDaemon will change
                the state of the given entity in the given namespace. On the other hand,
                if no namespace is given, AppDaemon will use the last specified namespace
                or the default namespace. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.
            replace(bool, optional): If a `replace` flag is given and set to ``True`` and ``attributes``
                is provided, AD will attempt to replace its internal entity register with the newly
                supplied attributes completely. This can be used to replace attributes in an entity
                which are no longer needed. Do take note this is only possible for internal entity state.
                For plugin based entities, this is not recommended, as the plugin will mostly replace
                the new values, when next it updates.

        Returns:
            A dictionary that represents the new state of the updated entity.

        Examples:
            >>> self.my_enitity = self.get_entity("light.living_room")

            Update the state of an entity.

            >>> self.my_enitity.set_state(state="off")

            Update the state and attribute of an entity.

            >>> self.my_enitity.set_state(state = "on", attributes = {"color_name": "red"})

            Update the state of an entity within the specified namespace.

            >>> self.my_enitity.set_state(state="off", namespace ="hass")

        """

        entity_id = self._entity_id

        self.logger.debug("set state: %s, %s", entity_id, kwargs)

        namespace = self._get_namespace(**kwargs)

        if "namespace" in kwargs:
            del kwargs["namespace"]

        return await self.AD.state.set_state(self.name, namespace, entity_id, **kwargs)

    @utils.sync_wrapper
    async def get_state(
        self, attribute: str = None, default: Any = None, copy: bool = True, **kwargs: Optional[dict]
    ) -> dict:
        """Gets the state of any entity within AD.

        State updates are continuously tracked, so this call runs locally and does not require
        AppDaemon to call back to Home Assistant. In other words, states are updated using a
        push-based approach instead of a pull-based one.

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
            namespace(str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases, it is safe to ignore this parameter.

        Returns:
            The entire state of Home Assistant at that given time, if  if ``get_state()``
            is called with no parameters. This will consist of a dictionary with a key
            for each entity. Under that key will be the standard entity state information.

        Examples:
            >>> self.my_enitity = self.get_entity("light.office_1")

            Get the state attribute of `light.office_1`.

            >>> state = self.my_enitity.get_state("light.office_1")

            Get the brightness attribute of `light.office_1`.

            >>> state = self.my_enitity.get_state(attribute="brightness")

            Get the entire state of `light.office_1`.

            >>> state = self.my_enitity.get_state(attribute="all")

        """

        entity_id = self._entity_id

        self.logger.debug("get state: %s, %s", entity_id, kwargs)

        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        return await self.AD.state.get_state(self.name, namespace, entity_id, attribute, default, copy, **kwargs)

    @utils.sync_wrapper
    async def listen_state(self, callback: Callable, **kwargs: Optional[dict]) -> Union[str, list]:
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
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description. In most cases,
                it is safe to ignore this parameter. The value ``global`` for namespace has special
                significance and means that the callback will listen to state updates from any plugin.
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
            >>> self.my_enitity = self.get_entity("light.office_1")

            Listen for a state change involving `light.office1` and return the state attribute.

            >>> self.handle = self.my_enitity.listen_state(self.my_callback)

            Listen for a state change involving `light.office1` and return the entire state as a dict.

            >>> self.handle = self.my_enitity.listen_state(self.my_callback, attribute = "all")

            Listen for a change involving the brightness attribute of `light.office1` and return the
            brightness attribute.

            >>> self.handle = self.my_enitity.listen_state(self.my_callback, attribute = "brightness")

            Listen for a state change involving `light.office1` turning on and return the state attribute.

            >>> self.handle = self.my_enitity.listen_state(self.my_callback, new = "on")

            Listen for a change involving `light.office1` changing from brightness 100 to 200 and return the
            brightness attribute.

            >>> self.handle = self.my_enitity.listen_state(self.my_callback, attribute = "brightness", old = "100", new = "200")

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute.

            >>> self.handle = self.my_enitity.listen_state(self.my_callback, new = "on", duration = 60)

            Listen for a state change involving `light.office1` changing to state on and remaining on for a minute
            trigger the delay immediately if the light is already on.

            >>> self.handle = self.my_enitity.listen_state(self.my_callback, new = "on", duration = 60, immediate = True)
        """

        entity_id = self._entity_id

        self.logger.debug("set state: %s, %s", entity_id, kwargs)

        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
        name = self.name

        self.logger.debug("Calling listen_state for %s", self.name)

        return await self.AD.state.add_state_callback(name, namespace, entity_id, callback, kwargs)

    @utils.sync_wrapper
    async def call_service(self, service: str, **kwargs: Optional[dict]) -> Any:
        """Calls a Service within AppDaemon.

        This function can call any service and provide any required parameters.
        By default, there are standard services that can be called within AD. Other
        services that can be called, are dependent on the plugin used, or those registered
        by individual apps using the `register_service` api.
        In a future release, all available services can be found using AD's Admin UI.
        For `listed services`, the part before the first period is the ``domain``,
        and the part after is the ``service name`. For instance, `light/turn_on`
        has a domain of `light` and a service name of `turn_on`.

        The default behaviour of the call service api is not to wait for any result, typically
        known as "fire and forget". If it is required to get the results of the call, keywords
        "return_result" or "callback" can be added.

        Args:
            service (str): The service name.
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            **kwargs: Each service has different parameter requirements. This argument
                allows you to specify a comma-separated list of keyword value pairs, e.g.,
                `state = on`. These parameters will be different for
                every service and can be discovered using the developer tools.

            namespace(str, optional): If a `namespace` is provided, AppDaemon will change
                the state of the given entity in the given namespace. On the other hand,
                if no namespace is given, AppDaemon will use the last specified namespace
                or the default namespace. See the section on `namespaces <APPGUIDE.html#namespaces>`__
                for a detailed description. In most cases, it is safe to ignore this parameter.
            return_result(str, option): If `return_result` is provided and set to `True` AD will attempt
                to wait for the result, and return it after execution
            callback: The non-async callback to be executed when complete.

        Returns:
            Result of the `call_service` function if any

        Examples:
            HASS

            >>> self.my_enitity = self.get_entity("light.office_1")
            >>> self.my_enitity.call_service("light/turn_on", color_name = "red")

        """

        entity_id = self._entity_id
        kwargs["entity_id"] = entity_id

        if service.count("/") == 1:  # domain given
            d, s = service.split("/")

        else:  # domain not given
            domain, _ = entity_id.split(".")
            d = domain
            s = service

        self.logger.debug("call_service: %s/%s, %s", d, s, kwargs)

        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        kwargs["__name"] = self.name

        return await self.AD.services.call_service(namespace, d, s, kwargs)

    #
    # Helpers
    #

    @utils.sync_wrapper
    async def copy(self, copy: bool = True) -> dict:
        """Gets the complete state of the entity within AD."""

        return await self.get_state(attribute="all", copy=copy, default={})

    @utils.sync_wrapper
    async def is_state(self, state: Any) -> bool:
        """Checks the state of the entity against the given state"""

        entity_state = await self.get_state(copy=False)

        return entity_state == state

    @utils.sync_wrapper
    async def turn_on(self, **kwargs: Optional[dict]) -> Any:
        """Used to turn the entity ON if supported"""

        return await self.call_service("turn_on", **kwargs)

    @utils.sync_wrapper
    async def turn_off(self, **kwargs: Optional[dict]) -> Any:
        """Used to turn the entity OFF if supported"""

        return await self.call_service("turn_off", **kwargs)
