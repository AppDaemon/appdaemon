AppDaemon API Reference
=======================

A number of api calls are native to AppDaemon and will exist in any App as they are inherited through the plugin API.
If the ``get_plugin_api()`` style of declarations is used, these functions will become available via an object created
by the ``get_ad_api()`` call:

.. code:: python

    import adbase as ad

    class Test(ad.ADBase):

        def initialize(self):

            self.adapi = self.get_ad_api()
            handle = self.adapi.run_in(callback, 20)

These calls are documented below.

App Creation
------------

To create apps based on just the AppDaemon base API, use some code like the following:

.. code:: python

    import adbase as ad

    class MyApp(ad.ADBase):

      def initialize(self):

Entity Class
------------

As manipulating entities is a core center point of writing automation apps, easy access and manipulation of entities is very important.
AppDaemon supports the ability to access entities as class in their own right, via the api call ``get_entity(entity)``.
When this is done, the returned object allows to maximise the OOP nature of python while working with entities.
for example:

.. code:: python

    import adbase as ad

    class TestApp(ad.ADBase):

        def initialize(self):

            self.adapi = self.get_ad_api()
            self.adapi.run_in(self.callback, 20)

            # get light entity class
            self.kitchen_light = self.adapi.get_entity("light.kitchen_ceiling_light", namespace="hass")

        def callback(self, kwargs):
            if self.kitchen_ceiling_light.is_state("off"):
                self.kitchen_ceiling_light.turn_on(brightness=200)

Reference
---------

Entity API
~~~~~~~~~~
.. autofunction:: appdaemon.entity.Entity.add
.. autofunction:: appdaemon.entity.Entity.call_service
.. autofunction:: appdaemon.entity.Entity.copy
.. autofunction:: appdaemon.entity.Entity.exists
.. autofunction:: appdaemon.entity.Entity.get_state
.. autofunction:: appdaemon.entity.Entity.listen_state
.. autofunction:: appdaemon.entity.Entity.is_state
.. autofunction:: appdaemon.entity.Entity.set_namespace
.. autofunction:: appdaemon.entity.Entity.set_state
.. autofunction:: appdaemon.entity.Entity.toggle
.. autofunction:: appdaemon.entity.Entity.turn_off
.. autofunction:: appdaemon.entity.Entity.turn_on
.. autofunction:: appdaemon.entity.Entity.wait_state

In addition to the above, there are a couple of propery attributes the Entity class supports
- entity_id
- namespace
- domain
- entity_name
- state
- attributes
- friendly_name
- last_changed
- last_changed_seconds


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

.. autofunction:: appdaemon.adapi.ADAPI.timer_running
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
.. autofunction:: appdaemon.adapi.ADAPI.deregister_service
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

``admin`` namespace only:

**app/create**

Used to create a new app. For this service to be used, the module must be existing and provided with the module's class. If no `app` name is given, the module name will be used as the app's name by default. The service call also accepts ``app_file`` if wanting to create the app within a certain `yaml` file. Or ``app_dir``, if wanting the created app's `yaml` file within a certain directory. If no file or directory is given, by default the app `yaml` file will be generated in a directory ``ad_apps``, using the app's name. It should be noted that ``app_dir`` and ``app_file`` when specified, will be created within the AD's apps directory.

.. code:: python
    data = {}
    data["module"] = "web_app"
    data["class"] = "WebApp"
    data["namespace"] = "admin"
    data["app"] = "web_app3"
    data["endpoint"] = "endpoint3"
    data["app_dir"] = "web_apps"
    data["app_file"] = "web_apps.yaml"

    self.call_service("app/create", **data)

**app/edit**

Used to edit an existing app. This way, an app' args can be edited in realtime with new args

    >>> self.call_service("app/edit", app="light_app", module="light_system", namespace="admin")

**app/remove**

Used to remove an existing app. This way, an existing app will be deleted. If the app is the last app in the ``yaml`` file, the file will be delected

    >>> self.call_service("app/remove", app="light_app", namespace="admin")

**app/start**

Starts an app that has been terminated. The `app` name arg is required.

    >>> self.call_service("app/start", app="light_app", namespace="admin")

**app/stop**

Stops a running app. The `app` name arg is required.

    >>> self.call_service("app/stop", app="light_app", namespace="admin")

**app/restart**

Restarts a running app. This service basically stops and starts the app. The `app` name arg is required.

    >>> self.call_service("app/restart", app="light_app", namespace="admin")

**app/reload**

Checks for an app update. Useful if AD is running in production mode, and app changes need to be checked and loaded.

    >>> self.call_service("app/reload", namespace="admin")

**app/enable**

Enables a disabled app, so it can be loaded by AD.

    >>> self.call_service("app/enable", app="living_room_app", namespace="admin")

**app/disable**

Disables an enabled app, so it cannot be loaded by AD. This service call is persistent, so even if AD restarts, the app will not be restarted

    >>> self.call_service("app/disable", app="living_room_app", namespace="admin")

**production_mode/set**

Sets the production mode AD is running on. The value of the `mode` arg has to be `True` or `False`.

    >>> self.call_service("production_mode/set", mode=True, namespace="admin")

All namespaces except ``global``, and ``admin``:

**state/add_entity**

Adds an existing entity to the required namespace.

    >>> self.call_service("state/set", entity_id="sensor.test", state="on", attributes={"friendly_name" : "Sensor Test"}, namespace="default")

**state/set**

Sets the state of an entity. This service allows any key-worded args to define what entity's values need to be set.

    >>> self.call_service("state/set", entity_id="sensor.test", state="on", attributes={"friendly_name" : "Sensor Test"}, namespace="default")

**state/remove_entity**

Removes an existing entity from the required namespace.

    >>> self.call_service("state/remove_entity", entity_id="sensor.test", namespace="default")

All namespaces except ``admin``:

**event/fire**

Fires an event within the specified namespace. The `event` arg is required.

    >>> self.call_service("event/fire", event="test_event", entity_id="appdaemon.test", namespace="hass")

``rules`` namespace only:

**sequence/run**

Runs a predefined sequence. The `entity_id` arg with the sequence full-qualified entity name is required.

    >>> self.call_service("sequence/run", entity_id ="sequence.christmas_lights", namespace="rules")

**sequence/cancel**

Cancels a predefined sequence. The `entity_id` arg with the sequence full-qualified entity name is required.

    >>> self.call_service("sequence/cancel", entity_id ="sequence.christmas_lights", namespace="rules")


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
.. autofunction:: appdaemon.adapi.ADAPI.deregister_endpoint

WebRoute
~~~

.. autofunction:: appdaemon.adapi.ADAPI.register_route
.. autofunction:: appdaemon.adapi.ADAPI.deregister_route

Other
~~~~~

.. autofunction:: appdaemon.adapi.ADAPI.run_in_thread
.. autofunction:: appdaemon.adapi.ADAPI.submit_to_executor
.. autofunction:: appdaemon.adapi.ADAPI.get_thread_info
.. autofunction:: appdaemon.adapi.ADAPI.get_scheduler_entries
.. autofunction:: appdaemon.adapi.ADAPI.get_callback_entries
.. autofunction:: appdaemon.adapi.ADAPI.depends_on_module
