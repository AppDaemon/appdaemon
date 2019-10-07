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

.. automethod:: appdaemon.adapi.ADAPI.get_state
.. automethod:: appdaemon.adapi.ADAPI.set_state
.. automethod:: appdaemon.adapi.ADAPI.listen_state
.. automethod:: appdaemon.adapi.ADAPI.cancel_listen_state
.. automethod:: appdaemon.adapi.ADAPI.info_listen_state


Time
~~~~

.. automethod:: appdaemon.adapi.ADAPI.parse_utc_string
.. automethod:: appdaemon.adapi.ADAPI.get_tz_offset
.. automethod:: appdaemon.adapi.ADAPI.convert_utc
.. automethod:: appdaemon.adapi.ADAPI.sun_up
.. automethod:: appdaemon.adapi.ADAPI.sun_down
.. automethod:: appdaemon.adapi.ADAPI.parse_time
.. automethod:: appdaemon.adapi.ADAPI.parse_datetime
.. automethod:: appdaemon.adapi.ADAPI.get_now
.. automethod:: appdaemon.adapi.ADAPI.get_now_ts
.. automethod:: appdaemon.adapi.ADAPI.now_is_between
.. automethod:: appdaemon.adapi.ADAPI.sunrise
.. automethod:: appdaemon.adapi.ADAPI.sunset
.. automethod:: appdaemon.adapi.ADAPI.time
.. automethod:: appdaemon.adapi.ADAPI.datetime
.. automethod:: appdaemon.adapi.ADAPI.date
.. automethod:: appdaemon.adapi.ADAPI.get_timezone

Scheduler
~~~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.cancel_timer
.. automethod:: appdaemon.adapi.ADAPI.info_timer
.. automethod:: appdaemon.adapi.ADAPI.run_in
.. automethod:: appdaemon.adapi.ADAPI.run_once
.. automethod:: appdaemon.adapi.ADAPI.run_at
.. automethod:: appdaemon.adapi.ADAPI.run_daily
.. automethod:: appdaemon.adapi.ADAPI.run_hourly
.. automethod:: appdaemon.adapi.ADAPI.run_minutely
.. automethod:: appdaemon.adapi.ADAPI.run_every
.. automethod:: appdaemon.adapi.ADAPI.run_at_sunset
.. automethod:: appdaemon.adapi.ADAPI.run_at_sunrise

Service
~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.register_service
.. automethod:: appdaemon.adapi.ADAPI.call_service

Sequence
~~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.run_sequence
.. automethod:: appdaemon.adapi.ADAPI.cancel_sequence

Events
~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.listen_event
.. automethod:: appdaemon.adapi.ADAPI.cancel_listen_event
.. automethod:: appdaemon.adapi.ADAPI.info_listen_event
.. automethod:: appdaemon.adapi.ADAPI.fire_event

Logging
~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.log
.. automethod:: appdaemon.adapi.ADAPI.error
.. automethod:: appdaemon.adapi.ADAPI.listen_log
.. automethod:: appdaemon.adapi.ADAPI.cancel_listen_log
.. automethod:: appdaemon.adapi.ADAPI.get_main_log
.. automethod:: appdaemon.adapi.ADAPI.get_error_log
.. automethod:: appdaemon.adapi.ADAPI.get_user_log
.. automethod:: appdaemon.adapi.ADAPI.set_log_level
.. automethod:: appdaemon.adapi.ADAPI.set_error_level

Dashboard
~~~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.dash_navigate

Namespace
~~~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.set_namespace
.. automethod:: appdaemon.adapi.ADAPI.get_namespace
.. automethod:: appdaemon.adapi.ADAPI.list_namespaces
.. automethod:: appdaemon.adapi.ADAPI.save_namespace

Threading
~~~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.set_app_pin
.. automethod:: appdaemon.adapi.ADAPI.get_app_pin
.. automethod:: appdaemon.adapi.ADAPI.set_pin_thread
.. automethod:: appdaemon.adapi.ADAPI.get_pin_thread


Utility
~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.get_app
.. automethod:: appdaemon.adapi.ADAPI.get_ad_version
.. automethod:: appdaemon.adapi.ADAPI.entity_exists
.. automethod:: appdaemon.adapi.ADAPI.split_entity
.. automethod:: appdaemon.adapi.ADAPI.remove_entity
.. automethod:: appdaemon.adapi.ADAPI.split_device_list
.. automethod:: appdaemon.adapi.ADAPI.get_plugin_config
.. automethod:: appdaemon.adapi.ADAPI.friendly_name
.. automethod:: appdaemon.adapi.ADAPI.set_production_mode
.. automethod:: appdaemon.adapi.ADAPI.start_app
.. automethod:: appdaemon.adapi.ADAPI.stop_app
.. automethod:: appdaemon.adapi.ADAPI.restart_app
.. automethod:: appdaemon.adapi.ADAPI.reload_apps

Dialogflow
~~~~~

.. automethod:: appdaemon.adapi.ADAPI.get_dialogflow_intent
.. automethod:: appdaemon.adapi.ADAPI.get_dialogflow_slot_value
.. automethod:: appdaemon.adapi.ADAPI.format_dialogflow_response

Alexa
~~~~~

.. automethod:: appdaemon.adapi.ADAPI.get_alexa_intent
.. automethod:: appdaemon.adapi.ADAPI.get_alexa_slot_value
.. automethod:: appdaemon.adapi.ADAPI.format_alexa_response
.. automethod:: appdaemon.adapi.ADAPI.get_alexa_error

API
~~~

.. automethod:: appdaemon.adapi.ADAPI.register_endpoint
.. automethod:: appdaemon.adapi.ADAPI.unregister_endpoint

Other
~~~~~

.. automethod:: appdaemon.adapi.ADAPI.run_in_thread
.. automethod:: appdaemon.adapi.ADAPI.get_thread_info
.. automethod:: appdaemon.adapi.ADAPI.get_scheduler_entries
.. automethod:: appdaemon.adapi.ADAPI.get_callback_entries
.. automethod:: appdaemon.adapi.ADAPI.depends_on_module