MQTT API Reference
==================

A list of API calls and information specific to the MQTT plugin.

App Creation
------------

To create apps based on just the MQTT API, use some code like the following:

.. code:: python

    import mqttapi as mqtt

    class MyApp(mqtt.Mqtt):

        def initialize(self):

Making Calls to MQTT
--------------------

The MQTT Plugin uses the inherited ``call_service()`` helper function the AppDaemon API,
to carry out service calls from within an AppDaemon app. See the documentation of this
function `here <AD_API_REFERENCE.html#appdaemon.adapi.ADAPI.call_service>`__
for a detailed description.

Th function ``call_service()`` allows the app to carry out one of the following services:

  - ``Publish``
  - ``Subscribe``
  - ``Unsubscribe``

By simply specifying within the function what is to be done. It uses configuration specified
in the plugin configuration which simplifies the call within the app significantly. Different
brokers can be accessed within an App, as long as they are all declared when the plugins are
configured, and using the ``namespace`` parameter. See the section on `namespaces <APPGUIDE.html#namespaces>`__
for a detailed description.

Examples
^^^^^^^^

.. code:: python

    # if wanting to publish data to a broker
    self.call_service("publish", topic = "homeassistant/bedroom/light", payload = "ON")
    # if wanting to unsubscribe a topic from a broker in a different namespace
    self.call_service("unsubscribe", topic = "homeassistant/bedroom/light", namespace = "mqtt2")

The MQTT API also provides 3 convenience functions to make calling of specific functions easier and more readable. These are documented in the following section.

Reference
---------

Services
--------

.. autofunction:: appdaemon.plugins.mqtt.mqttapi.Mqtt.mqtt_subscribe
.. autofunction:: appdaemon.plugins.mqtt.mqttapi.Mqtt.mqtt_unsubscribe
.. autofunction:: appdaemon.plugins.mqtt.mqttapi.Mqtt.mqtt_publish
.. autofunction:: appdaemon.plugins.mqtt.mqttapi.Mqtt.is_client_connected


Events
------

.. autofunction:: appdaemon.plugins.mqtt.mqttapi.Mqtt.listen_event

MQTT Config
-----------

Developers can get the MQTT configuration data (i.e., client_id or username) using the
helper function ``get_plugin_config()`` inherited from the AppDaemon API. See the
documentation of this function `here <AD_API_REFERENCE.html#appdaemon.adapi.ADAPI.get_plugin_config>`__
for a detailed description.

See More
---------

Read the `AppDaemon API Reference <AD_API_REFERENCE.html>`__ to learn other inherited helper functions that
can be used by Hass applications.
