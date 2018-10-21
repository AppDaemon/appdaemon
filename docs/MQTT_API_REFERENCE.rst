MQTT API Reference
==================

A list of API calls and information specific to the MQTT plugin.

Sending Messages
----------------

mqtt\_send()
~~~~~~~~~~~~~~~

``mqtt_send()`` is the way of publishing a MQTT message to a broker, from within an AppDaemon app.
It uses configuration specified in the plugin configuration which simplifies the call within the app significantly. Different brokers can be accessed within an app, as long as they are all declared
when the plugins are configured, and using the ``namespace`` parameter.

Synopsis
^^^^^^^^

.. code:: python

    self.mqtt_send(self, topic, payload, qos = 0, retain = False, **kwargs)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

Topic
'''''''

The topic the payload is to be sent to on the broker e.g. ``homeassistant/bedroom/light``.

Payload
'''''''

The data that is to be sent to on the broker e.g. ``'ON'``.

QOS
'''''''

The Quality of Service (QOS) that is to be used when sending the data to the broker. This is has to be an integer. This defaults to ``0``

Retain
'''''''

This flag is used to specify if the broker is to retain the payload or not. This defaults to ``False``.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the service - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter


\*\*kwargs
''''''''''

Each service has different parameter requirements. This argument allows
you to specify a comma separated list of keyword value pairs, e.g.
``qos = 0`` or ``retain = True``.

Examples
^^^^^^^^

.. code:: python

    self.mqtt_send("homeassistant/bedroom/light", "ON")
    # if wanting to send data to a different broker
    self.mqtt_send("homeassistant/living_room/light", "ON", qos = 0, retain = True, namepace = "mqtt2")

Events
------

listen\_event()
~~~~~~~~~~~~~~~

This is the primary way of listening for changes within the MQTT plugin - unlike other plugins, MQTT does not keep state. All MQTT messages will have an event type of ``MQTT_EVENT``

Synopsis
^^^^^^^^

.. code:: python

    handle = listen_event(callback, event = None, **kwargs):

Returns
^^^^^^^

A handle that can be used to cancel the callback.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Event Callback format documented `Here <APPGUIDE.html#about-event-callbacks>`__.

event
'''''

Name of the event to subscribe to. Can be the declared ``event_name`` parameter as specified
in the plugin configuration. If no event is specified, ``listen_event()`` will
subscribe to all MQTT events within the app's functional namespace.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter. The value ``global`` for namespace has special significance, and means that the callback will lsiten to state updates from any plugin.


\*\*kwargs (optional)
'''''''''''''''''''

One or more keyword value pairs representing App specific parameters to
supply to the callback. If the keywords match values within the event
data, they will act as filters, meaning that if they don't match the
values, the callback will not fire.

As an example of this, a specific topic can be listened to, instead of listening to all topics subscribed to.
For example if data is sent to a subscribed topic, it will generate an event as specified in the config;
if wanting to listen to a specific topic, ``topic`` can be passed in the filter the callback by supplying keyworded
arguments. If you include keyword values, the values supplied to the \`listen\_event()\` call must match the values in the event or it
will not fire. If the keywords do not match any of the data in the event
they are simply ignored.

Filtering will work with any event type, but it will be necessary to
figure out the data associated with the event to understand what values
can be filtered on.

Examples
^^^^^^^^

.. code:: python

    self.listen_event(self.mqtt_message_recieved_event, "MQTT_MESSAGE")
     #Listen for when a specific subscribed topic gets some data:
    self.listen_event(self.mqtt_message_recieved_event, "MQTT_MESSAGE", topic = 'homeassistant/bedroom/light')

MQTT Config
-----------

get_plugin_config()
~~~~~~~~~~~~~~~~~

Get the MQTT configuration data such as client_id or username. This can also be used to get the configuration of
other plugins like if connected to a Home Assistant insteace, this can be used to access the Longitude and Latitude
data of the Hass instance

Synopsis
^^^^^^^^

.. code:: python

    get_plugin_config()

Returns
^^^^^^^

A dictionary containing all the configuration information available from the MQTT plugin.

Examples
^^^^^^^^

.. code:: python

    config = self.get_plugin_config()
    self.log("Current Client ID is {}".format(config["client_id"]))