MQTT API Reference
==================

A list of API calls and information specific to the MQTT plugin.

.. _MQTT App Creation:

App Creation
------------

To create apps based on just the MQTT API, use some code like the following:

.. code:: python

    from appdaemon.plugins.mqtt import Mqtt


    class MyApp(Mqtt):
        def initialize(self):
            ... # Your initialization code here

Typed app configuration (Pydantic models)
-----------------------------------------

 App args can be validated and accessed via a typed model by subclassing
 ``appdaemon.models.config.app.AppConfig`` and typing the ``Mqtt`` API with it:
 ``class MyApp(mqtt.Mqtt[MyConfig]):``. The model instance is available as
 ``self.config_model``; the untyped dict ``self.args`` remains available for
 backward compatibility.

 .. code:: python

    import mqttapi as mqtt
    from appdaemon.models.config import AppConfig

    class MyConfig(AppConfig, extra="forbid"):
        required_topic: str
        qos: int = 0

    class MyApp(mqtt.Mqtt[MyConfig]):
        def initialize(self):
            # Typed access
            topic = self.config_model.required_topic
            self.mqtt_publish(topic, payload="ON", qos=self.config_model.qos)
            # Legacy access
            self.call_service("mqtt/publish", topic=self.args["required_topic"], payload="ON")

 .. code:: yaml

    # apps.yaml
    my_mqtt_app:
      module: my_module
      class: MyApp
      required_topic: "homeassistant/bedroom/light"
      qos: 1

 .. note::
    - Validation errors are logged and prevent the app from starting.
    - ``extra="forbid"`` rejects unknown keys; omit it if you want to allow extra args.
    - See the `AD API Reference <AD_API_REFERENCE.html>`__ for the generic
      ``ADAPI`` usage and the ``config_model`` attribute
      (`link <AD_API_REFERENCE.html#appdaemon.adapi.ADAPI.config_model>`__).

 Making Calls to MQTT
 --------------------

The MQTT Plugin uses the inherited ``call_service()`` helper function the AppDaemon API,
to carry out service calls from within an AppDaemon app. See the documentation of this
function `here <AD_API_REFERENCE.html#appdaemon.adapi.ADAPI.call_service>`__
for a detailed description.

The function ``call_service()`` allows the app to carry out one of the following services:

  - ``mqtt/publish``
  - ``mqtt/subscribe``
  - ``mqtt/unsubscribe``

By simply specifying within the function what is to be done. It uses configuration specified
in the plugin configuration which simplifies the call within the app significantly. Different
brokers can be accessed within an App, as long as they are all declared when the plugins are
configured, and using the ``namespace`` parameter. See the section on `namespaces <APPGUIDE.html#namespaces>`__
for a detailed description.

.. _MQTT Examples:

Examples
^^^^^^^^

.. code:: python

    # if wanting to publish data to a broker
    self.call_service("mqtt/publish", topic = "homeassistant/bedroom/light", payload = "ON")
    # if wanting to unsubscribe a topic from a broker in a different namespace
    self.call_service("mqtt/unsubscribe", topic = "homeassistant/bedroom/light", namespace = "mqtt2")

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
