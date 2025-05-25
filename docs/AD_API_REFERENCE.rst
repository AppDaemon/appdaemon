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
.. automethod:: appdaemon.entity.Entity.add
.. automethod:: appdaemon.entity.Entity.call_service
.. automethod:: appdaemon.entity.Entity.copy
.. automethod:: appdaemon.entity.Entity.exists
.. automethod:: appdaemon.entity.Entity.get_state
.. automethod:: appdaemon.entity.Entity.listen_state
.. automethod:: appdaemon.entity.Entity.is_state
.. automethod:: appdaemon.entity.Entity.set_namespace
.. automethod:: appdaemon.entity.Entity.set_state
.. automethod:: appdaemon.entity.Entity.toggle
.. automethod:: appdaemon.entity.Entity.turn_off
.. automethod:: appdaemon.entity.Entity.turn_on
.. automethod:: appdaemon.entity.Entity.wait_state

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

.. automethod:: appdaemon.adapi.ADAPI.run_at
.. automethod:: appdaemon.adapi.ADAPI.run_in
.. automethod:: appdaemon.adapi.ADAPI.run_once
.. automethod:: appdaemon.adapi.ADAPI.run_every
.. automethod:: appdaemon.adapi.ADAPI.run_daily
.. automethod:: appdaemon.adapi.ADAPI.run_hourly
.. automethod:: appdaemon.adapi.ADAPI.run_minutely
.. automethod:: appdaemon.adapi.ADAPI.run_at_sunset
.. automethod:: appdaemon.adapi.ADAPI.run_at_sunrise
.. automethod:: appdaemon.adapi.ADAPI.timer_running
.. automethod:: appdaemon.adapi.ADAPI.cancel_timer
.. automethod:: appdaemon.adapi.ADAPI.info_timer
.. automethod:: appdaemon.adapi.ADAPI.reset_timer

Service
~~~~~~~

.. automethod:: appdaemon.adapi.ADAPI.register_service
.. automethod:: appdaemon.adapi.ADAPI.deregister_service
.. automethod:: appdaemon.adapi.ADAPI.list_services
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

Async
~~~~~

.. automethod:: appdaemon.adapi.ADAPI.create_task
.. automethod:: appdaemon.adapi.ADAPI.run_in_executor
.. automethod:: appdaemon.adapi.ADAPI.sleep


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
~~~~~~~~~~

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
.. automethod:: appdaemon.adapi.ADAPI.deregister_endpoint

WebRoute
~~~

.. automethod:: appdaemon.adapi.ADAPI.register_route
.. automethod:: appdaemon.adapi.ADAPI.deregister_route

Other
~~~~~

.. automethod:: appdaemon.adapi.ADAPI.run_in_thread
.. automethod:: appdaemon.adapi.ADAPI.submit_to_executor
.. automethod:: appdaemon.adapi.ADAPI.get_thread_info
.. automethod:: appdaemon.adapi.ADAPI.get_scheduler_entries
.. automethod:: appdaemon.adapi.ADAPI.get_callback_entries
.. automethod:: appdaemon.adapi.ADAPI.depends_on_module
