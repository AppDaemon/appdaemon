HASS API Reference
==================

This page provides a list of API calls and specific information related to the HASS plugin.

App Creation
------------

To create apps based on just the AppDaemon base API, use some code like the following:

.. code:: python

    import hassapi as hass

    class MyApp(hass.Hass):

        def initialize(self):

Services
--------

call\_service()
~~~~~~~~~~~~~~~

Call service is the basic way of calling a HASS service within AppDaemon. It
can call any service and provide any required parameters. Available
services can be found using the developer tools in the UI. For listed
services, the part before the first period is the domain, and the part
after is the service name. For instance, ``light/turn_on`` has a domain
of ``light`` and a service name of ``turn_on``.

Synopsis
^^^^^^^^

.. code:: python

    self.call_service(self, service, **kwargs)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

service
'''''''

The service name, e.g., ``light/turn_on``.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter



\*\*kwargs
''''''''''

Each service has different parameter requirements. This argument allows
you to specify a comma-separated list of keyword value pairs, e.g.,
``entity_id = light.office_1``. These parameters will be different for
every service and can be discovered using the developer tools. Most if
not all service calls require an ``entity_id`` however, so use of the
above example is very common with this call.

Examples
^^^^^^^^

.. code:: python

    self.call_service("light/turn_on", entity_id = "light.office_lamp", color_name = "red")
    self.call_service("notify/notify", title = "Hello", message = "Hello World")

turn\_on()
~~~~~~~~~~

This is a convenience function for the ``homassistant.turn_on``
function. It can turn ``on`` pretty much anything in Home Assistant
that can be turned on or run:

-  Lights
-  Switches
-  Scenes
-  Scripts

And many more.

Synopsis
^^^^^^^^

.. code:: python

    self.turn_on(entity_id, **kwargs)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Fully qualified entity\_id of the thing to be turned on, e.g.,
``light.office_lamp`` or ``scene.downstairs_on``

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.

\*\*kwargs
''''''''''

A comma-separated list of key-value pairs to allow the specification of
parameters over and above ``entity_id``.

Examples
^^^^^^^^

.. code:: python

    self.turn_on("switch.patio_lights")
    self.turn_on("scene.bedrrom_on")
    self.turn_on("light.office_1", color_name = "green")

turn\_off()
~~~~~~~~~~~

This is a convenience function for the ``homassistant.turn_off``
function. Like ``homeassistant.turn_on``, it can turn ``off`` pretty
much anything in Home Assistant that can be turned off.

Synopsis
^^^^^^^^

.. code:: python

    self.turn_off(entity_id)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Fully qualified entity\_id of the thing to be turned off, e.g.,
``light.office_lamp`` or ``scene.downstairs_on``.

namespace = (optional)
'''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    self.turn_off("switch.patio_lights")
    self.turn_off("light.office_1")

toggle()
~~~~~~~~

This is a convenience function for the ``homassistant.toggle`` function.
It is able to flip the state of pretty much anything in Home Assistant
that can be turned on or off.

Synopsis
^^^^^^^^

.. code:: python

    self.toggle(entity_id)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Fully qualified entity\_id of the thing to be toggled, e.g.,
``light.office_lamp`` or ``scene.downstairs_on``.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    self.toggle("switch.patio_lights")
    self.toggle("light.office_1", color_name = "green")

set\_value()
~~~~~~~~~~~~~~~

This is a convenience function for the ``input_number.set_value``
function. It can set the value of an input\_number in Home
Assistant.

Synopsis
^^^^^^^^

.. code:: python

    self.set_value(entity_id, value)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Fully qualified entity\_id of the input\_number to be changed, e.g.,
``input_number.alarm_hour``.

value
'''''

The new value to set the input number to.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    self.set_value("input_number.alarm_hour", 6)

set\_textvalue()
~~~~~~~~~~~~~~~

This is a convenience function for the ``input_text.set_value``
function. It can set the value of an input\_text in Home
Assistant.

Synopsis
^^^^^^^^

.. code:: python

    self.set_textvalue(entity_id, value)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Fully qualified entity\_id of the input\_text to be changed, e.g.,
``input_text.text1``.

value
'''''

The new value to set the input text to.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    self.set_textvalue("input_text.text1", "hello world")

select\_option()
~~~~~~~~~~~~~~~~

This is a convenience function for the ``input_select.select_option``
function. It can set the value of an input\_select in Home
Assistant.

Synopsis
^^^^^^^^

.. code:: python

    self.select_option(entity_id, option)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Fully qualified entity\_id of the input\_select to be changed, e.g.,
``input_select.mode``.

value
'''''

The new value to set the input slider to.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    self.select_option("input_select.mode", "Day")

notify()
~~~~~~~~

This is a convenience function for the ``notify.notify`` service. It
will send a notification to a named notification service. If the name is
not specified, it will default to ``notify/notify``.

Synopsis
^^^^^^^^

.. code:: python

    notify(message, **kwargs)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

message
'''''''

Message to be sent to the notification service.

title = (optional)
''''''''''''''''''

Title of the notification - optional.

name = (optional)
'''''''''''''''''

Name of the notification service - optional.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    self.notify("Switching mode to Evening")
    self.notify("Switching mode to Evening", title = "Some Subject", name = "smtp")

Presence
--------

get\_trackers()
~~~~~~~~~~~~~~~

Return a list of all device tracker names. This is designed to be
iterated over.

Synopsis
^^^^^^^^

.. code:: python

    tracker_list = get_trackers()

Parameters
^^^^^^^^^^

namespace = (optional)
'''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.



Returns
^^^^^^^

An iterable list of all device trackers.

Examples
^^^^^^^^

.. code:: python

    trackers = self.get_trackers()
    for tracker in trackers:
        do something

get\_tracker\_details()
~~~~~~~~~~~~~~~~~~~~~~~

Return a list of all device trackers and their associated state.

Synopsis
^^^^^^^^

.. code:: python

    tracker_list = get_tracker_details()

Parameters
^^^^^^^^^^

namespace = (optional)
'''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.

Returns
^^^^^^^

A list of all device trackers with their associated state.

Examples
^^^^^^^^

.. code:: python

    trackers = self.get_tracker_details()
    for tracker in trackers:
        do something

get\_tracker\_state()
~~~~~~~~~~~~~~~~~~~~~

Get the state of a tracker. The values returned depend in part on the
configuration and type of device trackers in the system. Simpler tracker
types like ``Locative`` or ``NMAP`` will return one of 2 states:

-  ``home``
-  ``not_home``

Some types of device tracker are in addition able to supply locations
that have been configured as Geofences, in which case the name of that
location can be returned.

Synopsis
^^^^^^^^

.. code:: python

    location = self.get_tracker_state(tracker_id)

Returns
^^^^^^^

A string representing the location of the tracker.

Parameters
^^^^^^^^^^

tracker\_id
'''''''''''

Fully qualified entity\_id of the device tracker to query, e.g.,
``device_tracker.andrew``.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    trackers = self.get_trackers()
    for tracker in trackers:
      self.log("{} is {}".format(tracker, self.get_tracker_state(tracker)))

everyone\_home()
~~~~~~~~~~~~~~~~

A convenience function to determine if everyone is home. Use this in
preference to getting the state of ``group.all_devices()`` as it avoids
a race condition when using state change callbacks for device trackers.

Synopsis
^^^^^^^^

.. code:: python

    result = self.everyone_home()

Returns
^^^^^^^

Returns ``True`` if everyone is at home, ``False`` otherwise.

Parameters
^^^^^^^^^^

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    if self.everyone_home():
        do something

anyone\_home()
~~~~~~~~~~~~~~

A convenience function to determine if one or more person is home. Use
this in preference to getting the state of ``group.all_devices()`` as it
avoids a race condition when using state change callbacks for device
trackers.

Synopsis
^^^^^^^^

.. code:: python

    result = self.anyone_home()

Returns
^^^^^^^

Returns ``True`` if anyone is at home, ``False`` otherwise.

Parameters
^^^^^^^^^^

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    if self.anyone_home():
        do something

noone\_home()
~~~~~~~~~~~~~

A convenience function to determine if no people are at home. Use this
in preference to getting the state of group.all\_devices() as it avoids
a race condition when using state change callbacks for device trackers.

Synopsis
^^^^^^^^

.. code:: python

    result = self.noone_home()

Returns
^^^^^^^

Returns ``True`` if no one is home, ``False`` otherwise.

Parameters
^^^^^^^^^^

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.


Examples
^^^^^^^^

.. code:: python

    if self.noone_home():
        do something
        
Database
--------

get\_history()
~~~~~~~~~~~~~~~

This is a convenience function that allows accessing the HA Database, so the history state of a device can be retrieved.
It allows for a level of flexibility when retrieving the data, and returns it as a dictionary list.
Caution must be taken when using this, as depending on the size of the database, it can take a long time to process.

Synopsis
^^^^^^^^

.. code:: python

    data = self.get_history()

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Fully qualified entity\_id of the thing to be turned on, e.g.,
``light.office_lamp`` or ``scene.downstairs_on``
This can be any entity\_id in the database. If this is left empty, the state of 
all entities will be retrieved within the specified time. If both ``end_time``
and ``start_time`` explained below are declared, and ``entity_id`` is specified,
the specified ``entity_id`` will be ignored and the history states of all entity\_id
in the database will be retrieved within the specified time.

days
''''

The days from the present-day walking backwards that is required from the database.

.. code:: python
    #get device state over the last 5 days
    data = self.get_history("light.office_lamp", days = 5)
    

start_time
''''''''''

The start time from when the data should be retrieved. This should be the furthest time backwards,
like if we wanted to get data from now until two days ago. Your start time will be the last two days datetime.
``start_time`` time can be either a UTC aware time string like ``2019-04-16 12:00:03+01:00`` or
a ``datetime.datetime`` object.

.. code:: python
    #get device state over the last 2 days and walk forward
    import datetime
    from datetime import timedelta
    start_time = datetime.datetime.now() - timedelta(days = 2)
    data = self.get_history("light.office_lamp", start_time = start_time)
    
end_time
''''''''

The end time from when the data should be retrieved. This should be the latest time
like if we wanted to get data from now until two days ago. Your end time will be today's datetime
``end_time`` time can be either a UTC aware time string like ``2019-04-16 12:00:03+01:00`` or
a ``datetime.datetime`` object. It should be noted that it is not possible to declare only ``end_time``.
If only ``end_time`` is declared without ``start_time`` or ``days``, it will revert to default 
to the latest history state. When ``end_time`` is specified, it is not possible to declare ``entity_id``.
If ``entity_id`` is specified, ``end_time`` will be ignored.

.. code:: python
    #get device state from yesterday and walk 5 days back
    import datetime
    from datetime import timedelta
    end_time = datetime.datetime.now() - timedelta(days = 1)
    data = self.get_history(end_time = end_time, days = 5)

namespace = (optional)
'''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases, it is safe to ignore this parameter.

Returns
^^^^^^^

An iterable list of entity\_ids and their history state.


Miscellaneous Helper Functions
------------------------------

friendly\_name()
~~~~~~~~~~~~~~~~

``frindly_name()`` will return the Friendly Name of an entity if it has
one.

Synopsis
^^^^^^^^

.. code:: python

    Name = self.friendly_name(entity_id)

Returns
^^^^^^^

The friendly name of the entity if it exists or the entity id if not.

Example
^^^^^^^

.. code:: python

    tracker = "device_tracker.andrew"
    self.log("{}  ({}) is {}".format(tracker, self.friendly_name(tracker), self.get_tracker_state(tracker)))

split\_entity()
~~~~~~~~~~~~~~~

``split_entity()`` will take a fully qualified entity id of the form
``light.hall_light`` and split it into 2 values, the device and the
entity, e.g. ``light`` and ``hall_light``.

Synopsis
^^^^^^^^

.. code:: python

    device, entity = self.split_entity(entity_id)

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Fully qualified entity id to be split.

Returns
^^^^^^^

A list with 2 entries, the device and entity respectively.

Example
^^^^^^^

.. code:: python

    device, entity = self.split_entity(entity_id)
    if device == "scene":
        do something specific to scenes


Home Assistant Config
---------------------

get_plugin_config()
~~~~~~~~~~~~~~~~~

Get Home Assistant configuration data such as latitude and longitude.

Synopsis
^^^^^^^^

.. code:: python

    get_hass_config()

Returns
^^^^^^^

A dictionary containing all the configuration information available from the Home Assistant ``/api/config`` endpoint.

Examples
^^^^^^^^

.. code:: python

    config = self.get_hass_config()
    self.log("My current position is {}(Lat), {}(Long)".format(config["latitude"], config["longitude"]))
