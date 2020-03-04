AppDaemon API Reference
=======================

A number of api calls are native to AppDaemon and will exist in any App as they are inherited through the plugin API.
If the ``get_plugin_api()`` style of declarations is used, these functions will become available via an object created
by the ``get_ad_api()`` call:

.. code:: python

    import adbase as ad
    import adapi as adapi

    class Test(ad.ADBase):

      def initialize(self):

        adbase = self.get_ad_api()
        handle = self.adbase.run_in(callback, 20)

These calls are documented below.

App Creation
------------

To create apps based on just the AppDaemon base API, use some code like the following:

.. code:: python

    import adbase as ad

    class MyApp(ad.ADBase):

      def initialize(self):

Reference
---------

State
~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.get_state
.. autofunction:: appdaemon.adapi.ADAPI.set_state
.. autofunction:: appdaemon.adapi.ADAPI.listen_state
.. autofunction:: appdaemon.adapi.ADAPI.cancel_listen_state
.. autofunction:: appdaemon.adapi.ADAPI.info_listen_state


Time
~~~~

.. autofunction:: appdaemon.adapi.ADAPI.parse_utc_string
.. autofunction:: appdaemon.adapi.ADAPI.get_tz_offset
.. autofunction:: appdaemon.adapi.ADAPI.convert_utc
.. autofunction:: appdaemon.adapi.ADAPI.sun_up
.. autofunction:: appdaemon.adapi.ADAPI.sun_down
.. autofunction:: appdaemon.adapi.ADAPI.parse_time
.. autofunction:: appdaemon.adapi.ADAPI.parse_datetime
.. autofunction:: appdaemon.adapi.ADAPI.get_now
.. autofunction:: appdaemon.adapi.ADAPI.get_now_ts
.. autofunction:: appdaemon.adapi.ADAPI.now_is_between
.. autofunction:: appdaemon.adapi.ADAPI.sunrise
.. autofunction:: appdaemon.adapi.ADAPI.sunset
.. autofunction:: appdaemon.adapi.ADAPI.time
.. autofunction:: appdaemon.adapi.ADAPI.datetime
.. autofunction:: appdaemon.adapi.ADAPI.date
.. autofunction:: appdaemon.adapi.ADAPI.get_timezone

Scheduler
~~~~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.cancel_timer
.. autofunction:: appdaemon.adapi.ADAPI.info_timer
.. autofunction:: appdaemon.adapi.ADAPI.run_in
.. autofunction:: appdaemon.adapi.ADAPI.run_once
.. autofunction:: appdaemon.adapi.ADAPI.run_at
.. autofunction:: appdaemon.adapi.ADAPI.run_daily
.. autofunction:: appdaemon.adapi.ADAPI.run_hourly
.. autofunction:: appdaemon.adapi.ADAPI.run_minutely
.. autofunction:: appdaemon.adapi.ADAPI.run_every
.. autofunction:: appdaemon.adapi.ADAPI.run_at_sunset
.. autofunction:: appdaemon.adapi.ADAPI.run_at_sunrise

Service
~~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.register_service
.. autofunction:: appdaemon.adapi.ADAPI.list_services
.. autofunction:: appdaemon.adapi.ADAPI.call_service

Sequence
~~~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.run_sequence
.. autofunction:: appdaemon.adapi.ADAPI.cancel_sequence

Events
~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.listen_event
.. autofunction:: appdaemon.adapi.ADAPI.cancel_listen_event
.. autofunction:: appdaemon.adapi.ADAPI.info_listen_event
.. autofunction:: appdaemon.adapi.ADAPI.fire_event

Logging
~~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.log
.. autofunction:: appdaemon.adapi.ADAPI.error
.. autofunction:: appdaemon.adapi.ADAPI.listen_log
.. autofunction:: appdaemon.adapi.ADAPI.cancel_listen_log
.. autofunction:: appdaemon.adapi.ADAPI.get_main_log
.. autofunction:: appdaemon.adapi.ADAPI.get_error_log
.. autofunction:: appdaemon.adapi.ADAPI.get_user_log
.. autofunction:: appdaemon.adapi.ADAPI.set_log_level
.. autofunction:: appdaemon.adapi.ADAPI.set_error_level

Dashboard
~~~~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.dash_navigate

Namespace
~~~~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.set_namespace
.. autofunction:: appdaemon.adapi.ADAPI.get_namespace
.. autofunction:: appdaemon.adapi.ADAPI.list_namespaces
.. autofunction:: appdaemon.adapi.ADAPI.save_namespace

Services
~~~~~~~~~

Note: A service call always uses the app's default namespace. Although namespaces allow a new and easy way to work with multiple namespaces from within a single App, it is essential to understand how they work before using them in service's calls.
See the section on `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.

AppDaemon has a predefined list of namespaces that can be used only for particular services. Listed below are the services by namespace.

``appdaemon`` namespace only:

**app/start**

Starts an app that has been terminated. The `app` name arg is required.

    >>> self.call_service("app/start", app="light_app", namespace="appdaemon")

**app/stop**

Stops a running app. The `app` name arg is required.

    >>> self.call_service("app/stop", app="light_app", namespace="appdaemon")

**app/restart**

Restarts a running app. This service basically stops and starts the app. The `app` name arg is required.

    >>> self.call_service("app/restart", app="light_app", namespace="appdaemon")

**app/reload**

Checks for an app update. Useful if AD is running in production mode, and app changes need to be checked and loaded.

    >>> self.call_service("app/reload", namespace="appdaemon")

**production_mode/set**

Sets the production mode AD is running on. The value of the `mode` arg has to be `True` or `False`.

>>> self.call_service("production_mode/set", mode=True, namespace="appdaemon")

All namespaces except ``appdaemon``, ``global``, and ``admin``:

**state/add_entity**

Adds an existing entity to the required namespace.

    >>> self.call_service("state/set", entity_id="sensor.test", state="on", attributes={"friendly_name" : "Sensor Test"}, namespace="default")

**state/set**

Sets the state of an entity. This service allows any key-worded args to define what entity's values need to be set.

    >>> self.call_service("state/set", entity_id="sensor.test", state="on", attributes={"friendly_name" : "Sensor Test"}, namespace="default")

**state/remove_entity**

Removes an existing entity from the required namespace.

    >>> self.call_service("state/remove_entity", entity_id="sensor.test"}, namespace="default")

All namespaces except ``appdaemon``:

**event/fire**

Fires an event within the specified namespace. The `event` arg is required.

    >>> self.call_service("event/fire", event="test_event", entity_id="appdaemon.test", namespace="hass")

``rules`` namespace only:

**sequence/run**

Runs a predefined sequence. The `entity_id` arg with the sequence full-qualified entity name is required.

    >>> self.call_service("sequence/run", entity_id ="sequence.christmas_lights", namespace="rules")


Threading
~~~~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.set_app_pin
.. autofunction:: appdaemon.adapi.ADAPI.get_app_pin
.. autofunction:: appdaemon.adapi.ADAPI.set_pin_thread
.. autofunction:: appdaemon.adapi.ADAPI.get_pin_thread

Async
~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.create_task
.. autofunction:: appdaemon.adapi.ADAPI.run_in_executor
.. autofunction:: appdaemon.adapi.ADAPI.sleep


Utility
~~~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.get_app
.. autofunction:: appdaemon.adapi.ADAPI.get_ad_version
.. autofunction:: appdaemon.adapi.ADAPI.entity_exists
.. autofunction:: appdaemon.adapi.ADAPI.split_entity
.. autofunction:: appdaemon.adapi.ADAPI.remove_entity
.. autofunction:: appdaemon.adapi.ADAPI.split_device_list
.. autofunction:: appdaemon.adapi.ADAPI.get_plugin_config
.. autofunction:: appdaemon.adapi.ADAPI.friendly_name
.. autofunction:: appdaemon.adapi.ADAPI.set_production_mode
.. autofunction:: appdaemon.adapi.ADAPI.start_app
.. autofunction:: appdaemon.adapi.ADAPI.stop_app
.. autofunction:: appdaemon.adapi.ADAPI.restart_app
.. autofunction:: appdaemon.adapi.ADAPI.reload_apps

Dialogflow
~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.get_dialogflow_intent
.. autofunction:: appdaemon.adapi.ADAPI.get_dialogflow_slot_value
.. autofunction:: appdaemon.adapi.ADAPI.format_dialogflow_response

Alexa
~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.get_alexa_intent
.. autofunction:: appdaemon.adapi.ADAPI.get_alexa_slot_value
.. autofunction:: appdaemon.adapi.ADAPI.format_alexa_response
.. autofunction:: appdaemon.adapi.ADAPI.get_alexa_error

API
~~~

.. autofunction:: appdaemon.adapi.ADAPI.register_endpoint
.. autofunction:: appdaemon.adapi.ADAPI.unregister_endpoint

WebRoute
~~~

.. autofunction:: appdaemon.adapi.ADAPI.register_route
.. autofunction:: appdaemon.adapi.ADAPI.unregister_route

Other
~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.run_in_thread
.. autofunction:: appdaemon.adapi.ADAPI.get_thread_info
.. autofunction:: appdaemon.adapi.ADAPI.get_scheduler_entries
.. autofunction:: appdaemon.adapi.ADAPI.get_callback_entries
.. autofunction:: appdaemon.adapi.ADAPI.depends_on_module
