import appdaemon.adbase as adbase
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils


class Mqtt(adbase.ADBase, adapi.ADAPI):
    """
    A list of API calls and information specific to the MQTT plugin.

    App Creation
    ------------

    To create apps based on just the MQTT API, use some code like the following:

    .. code:: python

        import mqttapi as mqtt

        class MyApp(mqtt.Mqtt:

            def initialize(self):

    Making Calls to MQTT
    --------------------

    AD API's ``call_service()`` is used to carry out service calls from within an AppDaemon app. This allows the app to carry out one of the following services:

      - ``Publish``
      - ``Subscribe``
      - ``Unsubscribe``

    By simply specifying within the function what is to be done. It uses configuration specified in the plugin configuration which simplifies the call within the app significantly. Different brokers can be accessed within an app, as long as they are all declared
    when the plugins are configured, and using the ``namespace`` parameter.

    Examples
    ^^^^^^^^

    .. code:: python

        # if wanting to publish data to a broker
        self.call_service("publish", topic = "homeassistant/bedroom/light", payload = "ON")
        # if wanting to unsubscribe a topic from a broker in a different namespace
        self.call_service("unsubscribe", topic = "homeassistant/bedroom/light", namespace = "mqtt2")

    The MQTT API also provides 3 convenience functions to make calling of specific functions easier an more readable. These are documented in the following section.
    """

    def __init__(
        self,
        ad: AppDaemon,
        name,
        logging,
        args,
        config,
        app_config,
        global_vars,
    ):
        """Constructor for the app.

        Args:
            ad: AppDaemon object.
            name: name of the app.
            logging: reference to logging object.
            args: app arguments.
            config: AppDaemon config.
            app_config: config for all apps.
            global_vars: reference to global variables dict.

        """
        # Call Super Classes
        adbase.ADBase.__init__(self, ad, name, logging, args, config, app_config, global_vars)
        adapi.ADAPI.__init__(self, ad, name, logging, args, config, app_config, global_vars)

    #
    # Override listen_event()
    #

    @utils.sync_wrapper
    async def listen_event(self, callback, event=None, **kwargs):
        """Listens for changes within the MQTT plugin.

        Unlike other plugins, MQTT does not keep state. All MQTT messages will have an event
        which is set to ``MQTT_MESSAGE`` by default. This can be changed to whatever that is
        required in the plugin configuration.

        Args:
            callback: Function to be invoked when the requested event occurs. It must conform
                to the standard Event Callback format documented `Here <APPGUIDE.html#about-event-callbacks>`__.
            event: Name of the event to subscribe to. Can be the declared ``event_name`` parameter
                as specified in the plugin configuration. If no event is specified, ``listen_event()``
                will subscribe to all MQTT events within the app's functional namespace.
            **kwargs (optional): One or more keyword value pairs representing App specific parameters to
                supply to the callback. If the keywords match values within the event data, they will act
                as filters, meaning that if they don't match the values, the callback will not fire.

                As an example of this, a specific topic or wildcard can be listened to, instead of listening
                to all topics subscribed to. For example, if data is sent to a subscribed topic, it will
                generate an event as specified in the config; if we want to listen to a specific topic or
                wildcard, ``topic`` or ``wildcard`` can be passed in, and used to filter the callback by
                supplying them as keyword arguments. If you include keyword values, the values supplied
                to the ``listen_event()``call must match the values in the event or it will not fire.
                If the keywords do not match any of the data in the event they are simply ignored.

                Filtering will work with any event type, but it will be necessary to figure out
                the data associated with the event to understand what values can be filtered on.
                If using ``wildcard``, only those used to subscribe to the broker can be used as wildcards.
                The plugin supports the use both single and multi-level wildcards.

        Keyword Args:
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

            binary (bool, optional): If wanting the payload to be returned as binary, this should
                be specified. If not given, AD will return the payload as decoded data. It should
                be noted that it is not possible to have different apps receieve both binary and non-binary
                data on the same topic

        Returns:
            A handle that can be used to cancel the callback.

        Examples:
            Listen all events.

            >>> self.listen_event(self.mqtt_message_received_event, "MQTT_MESSAGE")

            Listen events for a specific subscribed topic.

            >>> self.listen_event(self.mqtt_message_received_event, "MQTT_MESSAGE", topic='homeassistant/bedroom/light')

            Listen events for a specific subscribed high level topic.

            >>> self.listen_event(self.mqtt_message_received_event, "MQTT_MESSAGE", wildcard='homeassistant/#')

            >>> self.listen_event(self.mqtt_message_received_event, "MQTT_MESSAGE", wildcard='homeassistant/+/motion')

            Listen events for binary payload

            >>> self.listen_event(self.mqtt_message_received_event, "MQTT_MESSAGE", topic='hermes/audioServer/#', binary=True)

            Listen plugin's `disconnected` events from the broker.

            >>> self.listen_event(self.mqtt_message_received_event, "MQTT_MESSAGE", state='Disconnected', topic=None)

            Listen plugin's' `connected` events from the broker.

            >>> self.listen_event(self.mqtt_message_received_event, "MQTT_MESSAGE", state='Connected', topic=None)

        Notes:
            At this point, it is not possible to use single level wildcard like using ``homeassistant/+/light`` instead of ``homeassistant/bedroom/light``. This could be added later, if need be.

        """

        namespace = self._get_namespace(**kwargs)
        plugin = await self.AD.plugins.get_plugin_object(namespace)
        topic = kwargs.get("topic", kwargs.get("wildcard"))

        if plugin is not None:
            if kwargs.pop("binary", None) is True:
                if topic is not None:
                    self.logger.debug("Adding topic %s, to binary payload topics", topic)
                    plugin.add_mqtt_binary(topic)

                else:
                    self.logger.warning("Cannot register for binary data, since no topic nor wildcard given")

            else:

                if topic is not None and hasattr(plugin, "mqtt_binary_topics") and topic in plugin.mqtt_binary_topics:
                    self.logger.debug("Removing topic %s, from binary payload topics", topic)
                    plugin.remove_mqtt_binary(topic)

        return await super(Mqtt, self).listen_event(callback, event, **kwargs)

    #
    # service calls
    #
    def mqtt_publish(self, topic, payload=None, **kwargs):
        """Publishes a message to a MQTT broker.

        This helper function used for publishing a MQTT message to a broker, from within
        an AppDaemon app. It uses configuration specified in the plugin configuration which
        simplifies the call within the App significantly.

        Different brokers can be accessed within an app, as long as they are
        all declared when the plugins are configured, and using the ``namespace``
        parameter.

        Args:
            topic (str): topic the payload is to be sent to on the broker
                (e.g., ``homeassistant/bedroom/light``).
            payload: data that is to be sent to on the broker (e.g., ``'ON'``).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            qos (int, optional): The Quality of Service (QOS) that is to be used when sending
                the data to the broker. This is has to be an integer (Default value: ``0``).
            retain (bool, optional): This flag is used to specify if the broker is to retain the
                payload or not (Default value: ``False``).
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            None.

        Examples:

        Send data to the default HA broker.

        >>> self.mqtt_publish("homeassistant/bedroom/light", "ON")

        Send data to a different broker.

        >>> self.mqtt_publish("homeassistant/living_room/light", "ON", qos = 0, retain = True, namespace = "mqtt2")

        """

        kwargs["topic"] = topic
        kwargs["payload"] = payload
        service = "mqtt/publish"
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_subscribe(self, topic, **kwargs):
        """Subscribes to a MQTT topic.

        This helper function used for subscribing to a topic on a broker,
        from within an AppDaemon App.

        This allows the apps to now access events from that topic, in realtime.
        So outside the initial configuration at plugin config, this allows access
        to other topics while the apps runs. It should be noted that if AppDaemon
        was to reload, the topics subscribed via this function will not be available
        by default. On those declared at the plugin config will always be available.
        It uses configuration specified in the plugin configuration which simplifies
        the call within the app significantly.

        Different brokers can be accessed within an app, as long as they are
        all declared when the plugins are configured, and using the ``namespace``
        parameter.

        Args:
            topic (str): The topic to be subscribed to on the broker
                (e.g., ``homeassistant/bedroom/light``).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            None.

        Examples:
            >>> self.mqtt_subscribe("homeassistant/bedroom/light")

        """

        kwargs["topic"] = topic
        service = "mqtt/subscribe"
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_unsubscribe(self, topic, **kwargs):
        """Unsubscribes from a MQTT topic.

        A helper function used to unsubscribe from a topic on a broker,
        from within an AppDaemon app.

        This denies the Apps access events from that topic, in realtime.
        It is possible to unsubscribe from topics, even if they were part
        of the topics in the plugin config; but it is not possible to
        unsubscribe ``#``. It should also be noted that if AppDaemon was
        to reload, the topics unsubscribed via this function will be available
        if they were configured with the plugin by default. It uses
        configuration specified in the plugin configuration which simplifies
        the call within the app significantly.

        Different brokers can be accessed within an app, as long as they are
        all declared when the plugins are configured, and using the ``namespace``
        parameter.

        Args:
            topic (str): The topic to be unsubscribed from on the broker
                (e.g., ``homeassistant/bedroom/light``).
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            None.

        Examples:
            >>> self.mqtt_unsubscribe("homeassistant/bedroom/light")

        """

        kwargs["topic"] = topic
        service = "mqtt/unsubscribe"
        result = self.call_service(service, **kwargs)
        return result

    @utils.sync_wrapper
    async def is_client_connected(self, **kwargs):
        """Returns ``TRUE`` if the MQTT plugin is connected to its broker, ``FALSE`` otherwise.

        This a helper function used to check or confirm within an app if the plugin is connected
        to its broker. This can be useful, if it is necessary to be certain the client is connected,
        so if not the app can internally store the data in a queue, and wait for connection before
        sending the data.

        Different brokers can be accessed within an app, as long as they are
        all declared when the plugins are configured, and using the ``namespace``
        parameter.

        Args:
            **kwargs (optional): Zero or more keyword arguments.

        Keyword Args:
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.

        Returns:
            None.

        Examples:
            Check if client is connected, and send data.
            >>> if self.clientConnected():
            >>>     self.mqtt_publish(topic, payload)

            Check if client is connected in mqtt2 namespace, and send data.

            >>> if self.clientConnected(namespace = 'mqtt2'):
            >>>     self.mqtt_publish(topic, payload, namespace = 'mqtt2')

        """
        namespace = self._get_namespace(**kwargs)
        plugin = await self.AD.plugins.get_plugin_object(namespace)
        return await plugin.mqtt_client_state()
