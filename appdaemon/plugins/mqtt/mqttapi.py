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

    By simply specifing within the function what is to be done. It uses configuration specified in the plugin configuration which simplifies the call within the app significantly. Different brokers can be accessed within an app, as long as they are all declared
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

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars,):
        """
        Constructor for the app.

        :param ad: appdaemon object
        :param name: name of the app
        :param logging: reference to logging object
        :param args: app arguments
        :param config: AppDaemon config
        :param app_config: config for all apps
        :param global_vars: referemce to global variables dict
        """
        # Call Super Classes
        adbase.ADBase.__init__(self, ad, name, logging, args, config, app_config, global_vars)
        adapi.ADAPI.__init__(self, ad, name, logging, args, config, app_config, global_vars)


    #
    # Override listen_event()
    #

    def listen_event(self, cb, event=None, **kwargs):

        """
        This is the primary way of listening for changes within the MQTT plugin.

        Unlike other plugins, MQTT does not keep state. All MQTT messages will have an event which is set to ``MQTT_MESSAGE`` by default. This can be changed to whatever that is required in the plugin configuration.

        :param cb: Function to be invoked when the requested state change occurs. It must conform to the standard Event Callback format documented `Here <APPGUIDE.html#about-event-callbacks>`__.
        :param event: Name of the event to subscribe to. Can be the declared ``event_name`` parameter as specified in the plugin configuration. If no event is specified, ``listen_event()`` will subscribe to all MQTT events within the app's functional namespace.
        :param \*\*kwargs: Additional keyword arguments:

            **namespace** (optional):  Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter. The value ``global`` for namespace has special significance, and means that the callback will lsiten to state updates from any plugin.

        :return: A handle that can be used to cancel the callback.
        """

        namespace = self._get_namespace(**kwargs)

        if 'wildcard' in kwargs:
            wildcard = kwargs['wildcard']
            if wildcard[-2:] == '/#' and len(wildcard.split('/')[0]) >= 1:
                plugin = utils.run_coroutine_threadsafe(self, self.AD.plugins.get_plugin_object(namespace))
                utils.run_coroutine_threadsafe(self, plugin.process_mqtt_wildcard(kwargs['wildcard']))
            else:
                self.logger.warning("Using %s as MQTT Wildcard for Event is not valid, use another. Listen Event will not be registered", wildcard)
                return

        return super(Mqtt, self).listen_event(cb, event, **kwargs)

    #
    # service calls
    #
    def mqtt_publish(self, topic, payload = None, **kwargs):
        """
        A helper function used for publishing a MQTT message to a broker, from within an AppDaemon app.

        It uses configuration specified in the plugin configuration which simplifies the call within the app significantly. Different brokers can be accessed within an app, as long as they are all declared when the plugins are configured, and using the ``namespace`` parameter.

        :param topic: topic the payload is to be sent to on the broker e.g. ``homeassistant/bedroom/light``
        :param payload: data that is to be sent to on the broker e.g. ``'ON'``
        :param \*\*kwargs: Additional keyword arguments:

            **qos**: The Quality of Service (QOS) that is to be used when sending the data to the broker. This is has to be an integer. This defaults to ``0``

            **retain**: This flag is used to specify if the broker is to retain the payload or not. This defaults to ``False``.

            **namespace**: Namespace to use for the service - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter

        **Examples**:

        >>> self.mqtt_publish("homeassistant/bedroom/light", "ON")
        # if wanting to send data to a different broker
        >>> self.mqtt_publish("homeassistant/living_room/light", "ON", qos = 0, retain = True, namepace = "mqtt2")
        """

        kwargs['topic'] = topic
        kwargs['payload'] = payload
        service = 'mqtt/publish'
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_subscribe(self, topic, **kwargs):

        """
        A helper function used for subscribing to a topic on a broker, from within an AppDaemon app.

        This allows the apps to now access events from that topic, in realtime. So outside the initial configuration at plugin config, this allows access to other topics while the apps runs. It should be noted that if Appdaemon was to reload, the topics subscribed via this function will not be available by default. On those declared at the plugin config will always be available. It uses configuration specified in the plugin configuration which simplifies the call within the app significantly. Different brokers can be accessed within an app, as long as they are all declared when the plugins are configured, and using the ``namespace`` parameter.

        :param topic: The topic to be subscribed to on the broker e.g. ``homeassistant/bedroom/light``
        """

        kwargs['topic'] = topic
        service = 'mqtt/subscribe'
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_unsubscribe(self, topic, **kwargs):

        """
        A helper function used for unsubscribing from a topic on a broker, from within an AppDaemon app.

        This denies the apps access events from that topic, in realtime. It is possible to unsubscribe from topics, even if they were part of the topics in the plugin config; but it is not possible to unsubscribe ``#``. It should also be noted that if Appdaemon was to reload, the topics unsubscribed via this function will be available if they were configured with the plugin by default. It uses configuration specified in the plugin configuration which simplifies the call within the app significantly. Different brokers can be accessed within an app, as long as they are all declared when the plugins are configured, and using the ``namespace`` parameter.

        :param topic: The topic to be unsubscribed from on the broker e.g. ``homeassistant/bedroom/light``
        """

        kwargs['topic'] = topic
        service = 'mqtt/unsubscribe'
        result = self.call_service(service, **kwargs)
        return result
