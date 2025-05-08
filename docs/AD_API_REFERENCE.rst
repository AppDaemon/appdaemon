AppDaemon APIs
==============

The AppDaemon API comes in the form of a class called ``ADAPI``, which provides high-level functionality for users to
create their apps. This includes common functions such as listening for events/state changes, scheduling, manipulating
entities, and calling services. The API is designed to be easy to use and understand, while still providing the power
and flexibility needed to create complex automations.

App Creation
------------

To use the API, create a new class that inherits from ``ADAPI`` and implement the ``initialize()`` method. This method
is required for all apps and is called when the app is started.

.. code:: python

    from appdaemon.adapi import ADAPI


    class MyApp(ADAPI):
        def initialize(self):
            self.log("MyApp is starting")

            # Use any of the ADAPI methods
            # handle = self.listen_state(...)
            # handle = self.listen_event(...)
            # handle = self.run_in(...)
            # handle = self.run_every(...)

Alternatively, the ``ADBase`` class can be used, which can provide some advantages, such as being able to access APIs
for plugins in mulitple namespaces.

.. code:: python

    from appdaemon.adapi import ADAPI
    from appdaemon.adbase import ADBase
    from appdaemon.plugins.mqtt import Mqtt


    class MyApp(ADBase):
        adapi: ADAPI    # This type annotation helps your IDE with autocompletion
        mqttapi: Mqtt

        def initialize(self):
            self.adapi = self.get_ad_api()
            self.adapi.log("MyApp is starting")

            # This requires having defined a plugin in the mqtt namespace in appdaemon.yaml
            self.mqttapi = self.get_plugin_api('mqtt')

            # Use any of the ADAPI methods through self.adapi
            # handle = self.adapi.listen_state(...)
            # handle = self.adapi.listen_event(...)
            # handle = self.adapi.run_in(...)
            # handle = self.adapi.run_every(...)

Entity Class
------------

Interacting with entities is a core part of writing automation apps, so being able to easily access and manipulate them
is important. AppDaemon supports this by providing entities as python objects.

The ``Entity`` class is essentially a light wrapper around ``ADAPI`` methods that pre-fills some arguments. Because of
this, the entity doesn't have to actually exist for the ``Entity`` object to be created and used. If the entity doesn't
exist, some methods will fail, but others will not. For example, ``get_state()`` will fail, but calling ``set_state()``
for an entity that doesn't exist will create it. This is useful for creating sensor entities that are available in Home
Assistant.

.. code:: python

    from appdaemon.adapi import ADAPI


    class MyApp(ADAPI):
        def initialize(self):
            self.log("MyApp is starting")

            # Get light entity class
            self.kitchen_light = self.get_entity("light.kitchen_ceiling_light")

            # Assign a callback for when the state changes to on
            self.kitchen_light.listen_state(
                self.state_callback,
                attribute="brightness",
                new='on'
            )

        def state_callback(self, entity, attribute, old, new, **kwargs):
            self.log(f'{self.kitchen_light.friendly_name} turned on')

Services
--------

AppDaemon provides some services from some built-in namespaces. These services can be called from any app, provided they
use the correct namepsace. These services are listed below

Note: A service call always uses the app's default namespace. See the section on
`namespaces <APPGUIDE.html#namespaces>`__ for more information.

admin
~~~~~

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

.. code:: python

    self.call_service("app/edit", app="light_app", module="light_system", namespace="admin")

**app/remove**

Used to remove an existing app. This way, an existing app will be deleted. If the app is the last app in the ``yaml``
file, the file will be deleted

.. code:: python

    self.call_service("app/remove", app="light_app", namespace="admin")

**app/start**

Starts an app that has been terminated. The `app` name arg is required.

.. code:: python

    self.call_service("app/start", app="light_app", namespace="admin")

**app/stop**

Stops a running app. The `app` name arg is required.

.. code:: python

    self.call_service("app/stop", app="light_app", namespace="admin")

**app/restart**

Restarts a running app. This service basically stops and starts the app. The `app` name arg is required.

.. code:: python

    self.call_service("app/restart", app="light_app", namespace="admin")

**app/reload**

Checks for an app update. Useful if AD is running in production mode, and app changes need to be checked and loaded.

.. code:: python

    self.call_service("app/reload", namespace="admin")

**app/enable**

Enables a disabled app, so it can be loaded by AD.

.. code:: python

    self.call_service("app/enable", app="living_room_app", namespace="admin")

**app/disable**

Disables an enabled app, so it cannot be loaded by AD. This service call is persistent, so even if AD restarts, the app
will not be restarted

.. code:: python

    self.call_service("app/disable", app="living_room_app", namespace="admin")

**production_mode/set**

Sets the production mode AD is running on. The value of the `mode` arg has to be `True` or `False`.

.. code:: python

    self.call_service("production_mode/set", mode=True, namespace="admin")

All namespaces except ``global``, and ``admin``:

**state/add_entity**

Adds an existing entity to the required namespace.

.. code:: python

    self.call_service(
        "state/set",
        entity_id="sensor.test",
        state="on",
        attributes={"friendly_name" : "Sensor Test"},
        namespace="default"
    )

**state/set**

Sets the state of an entity. This service allows any key-worded args to define what entity's values need to be set.

.. code:: python

    self.call_service(
        "state/set",
        entity_id="sensor.test",
        state="on",
        attributes={"friendly_name" : "Sensor Test"},
        namespace="default"
    )

**state/remove_entity**

Removes an existing entity from the required namespace.

.. code:: python

    self.call_service("state/remove_entity", entity_id="sensor.test", namespace="default")

All namespaces except ``admin``:

**event/fire**

Fires an event within the specified namespace. The `event` arg is required.

.. code:: python

    self.call_service("event/fire", event="test_event", entity_id="appdaemon.test", namespace="hass")

rules
~~~~~

**sequence/run**

Runs a predefined sequence. The `entity_id` arg with the sequence full-qualified entity name is required.

.. code:: python

    self.call_service("sequence/run", entity_id ="sequence.christmas_lights", namespace="rules")

**sequence/cancel**

Cancels a predefined sequence. The `entity_id` arg with the sequence full-qualified entity name is required.

.. code:: python

    self.call_service("sequence/cancel", entity_id ="sequence.christmas_lights", namespace="rules")

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

In addition to the above, there are a couple of property attributes the Entity class supports:
-  entity_id
-  namespace
-  domain
-  entity_name
-  state
-  attributes
-  friendly_name
-  last_changed
-  last_changed_seconds


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

.. autofunction:: appdaemon.adapi.ADAPI.run_at
.. autofunction:: appdaemon.adapi.ADAPI.run_in
.. autofunction:: appdaemon.adapi.ADAPI.run_once
.. autofunction:: appdaemon.adapi.ADAPI.run_every
.. autofunction:: appdaemon.adapi.ADAPI.run_daily
.. autofunction:: appdaemon.adapi.ADAPI.run_hourly
.. autofunction:: appdaemon.adapi.ADAPI.run_minutely
.. autofunction:: appdaemon.adapi.ADAPI.run_at_sunset
.. autofunction:: appdaemon.adapi.ADAPI.run_at_sunrise
.. autofunction:: appdaemon.adapi.ADAPI.timer_running
.. autofunction:: appdaemon.adapi.ADAPI.cancel_timer
.. autofunction:: appdaemon.adapi.ADAPI.info_timer
.. autofunction:: appdaemon.adapi.ADAPI.reset_timer

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
~~~~~~~~~~

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
