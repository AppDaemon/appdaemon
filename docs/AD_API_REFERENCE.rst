AppDaemon API Reference
=======================

A number of api calls are native to AppDaemon and will exist in any App as they are inherited through the plugin API. These calls are documented below.

State Operations
----------------

get\_state()
~~~~~~~~~~~~

Synopsis
^^^^^^^^

.. code:: python

    get_state(entity=None, attribute=None, namespace=None)

``get_state()`` is used to query the state of any component within Home
Assistant. State updates are continuously tracked so this call runs
locally and does not require AppDaemon to call back to Home Assistant
and as such is very efficient.

Returns
^^^^^^^

``get_state()`` returns a ``dictionary`` or single value, the structure
of which varies according to the parameters used. If an entity or
attribute does not exist, ``get_state()`` will return ``None``.

Parameters
^^^^^^^^^^

All parameters are optional, and if ``get_state()`` is called with no
parameters it will return the entire state of Home Assistant at that
given time. This will consist of a dictionary with a key for each
entity. Under that key will be the standard entity state information.

entity
''''''

This is the name of an entity or device type. If just a device type is
provided, e.g. ``light`` or ``binary_sensor``, ``get_state()`` will
return a dictionary of all devices of that type, indexed by the
entity\_id, containing all the state for each entity.

If a fully qualified ``entity_id`` is provided, ``get_state()`` will
return the state attribute for that entity, e.g. ``on`` or ``off`` for a
light.

attribute
'''''''''

Name of an attribute within the entity state object. If this parameter
is specified in addition to a fully qualified ``entity_id``, a single
value representing the attribute will be returned, or ``None`` if it is
not present.

The value ``all`` for attribute has special significance and will return
the entire state dictionary for the specified entity rather than an
individual attribute value.

namespace
'''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter

Examples
^^^^^^^^

.. code:: python

    # Return state for the entire system
    state = self.get_state()

    # Return state for all switches in the system
    state = self.get_state("switch")

    # Return the state attribute for light.office_1
    state = self.get_state("light.office_1")

    # Return the brightness attribute for light.office_1
    state = self.get_state("light.office_1", attribute="brightness")

    # Return the entire state for light.office_1
    state = self.get_state("light.office_1", attribute="all")
set\_state()
~~~~~~~~~~~~

``set_state()`` will make a call back to Home Assistant and make changes
to the internal state of Home Assistant. Note that for instance, setting the
state of a light to ``on`` won't actually switch the device on, it will
merely change the state of the device in Home Assistant so that it no
longer reflects reality. In most cases, the state will be corrected the
next time Home Assistant polls the device or someone causes a state
change manually. To effect actual changes of devices use one of the
service call functions.

One possible use case for ``set_state()`` is for testing. If for
instance you are writing an App to turn on a light when it gets dark
according to a luminance sensor, you can use ``set_state()`` to
temporarily change the light level reported by the sensor to test your
program. However this is also possible using the developer tools.

At the time of writing, it appears that no checking is done as to
whether or not the entity exists, so it is possible to add entirely new
entries to Home Assistant's state with this call.

Synopsis
^^^^^^^^

.. code:: python

    set_state(entity_id, **kwargs)

Returns
^^^^^^^

``set_state()`` returns a dictionary representing the state of the
device after the call has completed.

Parameters
^^^^^^^^^^

entity\_id
''''''''''

Entity id for which the state is to be set, e.g. ``light.office_1``.

values
''''''

A list of keyword values to be changed or added to the entities state.
e.g. ``state = "off"``. Note that any optional attributes such as colors
for bulbs etc, need to reside in a dictionary called ``attributes``; see
the example.

namespace
'''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter


Examples
^^^^^^^^

.. code:: python

    status = self.set_state("light.office_1", state = "on", attributes = {"color_name": "red"})

listen\_state()
~~~~~~~~~~~~~~~

``listen_state()`` allows the user to register a callback for a wide
variety of state changes.

Synopsis
^^^^^^^^

.. code:: python

    handle = listen_state(callback, entity = None, **kwargs)

Returns
^^^^^^^

A unique identifier that can be used to cancel the callback if required.
Since variables created within object methods are local to the function
they are created in, and in all likelihood the cancellation will be
invoked later in a different function, it is recommended that handles
are stored in the object namespace, e.g. ``self.handle``.

Parameters
^^^^^^^^^^

All parameters except ``callback`` are optional, and if
``listen_state()`` is called with no additional parameters it will
subscribe to any state change within Home Assistant.

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard State Callback format documented `Here <APPGUIDE.html#state-callbacks>`__

entity
''''''

This is the name of an entity or device type. If just a device type is
provided, e.g. ``light`` or ``binary_sensor``, ``listen_state()`` will
subscribe to state changes of all devices of that type. If a fully
qualified ``entity_id`` is provided, ``listen_state()`` will listen for
state changes for just that entity.

When called, AppDaemon will supply the callback function, in old and
new, with the state attribute for that entity, e.g. ``on`` or ``off``
for a light.

attribute =  (optional)
''''''''''''''''''''

Name of an attribute within the entity state object. If this parameter
is specified in addition to a fully qualified ``entity_id``,
``listen_state()`` will subscribe to changes for just that attribute
within that specific entity. The new and old parameters in the callback
function will be provided with a single value representing the
attribute.

The value ``all`` for attribute has special significance and will listen
for any state change within the specified entity, and supply the
callback functions with the entire state dictionary for the specified
entity rather than an individual attribute value.

new =  (optional)
''''''''''''''''

If ``new`` is supplied as a parameter, callbacks will only be made if
the state of the selected attribute (usually ``state``) in the new state
match the value of ``new``.

old =  (optional)
''''''''''''''''

If ``old`` is supplied as a parameter, callbacks will only be made if
the state of the selected attribute (usually ``state``) in the old state
match the value of ``old``.

Note: ``old`` and ``new`` can be used singly or together.

duration =  (optional)
'''''''''''''''''''''

If duration is supplied as a parameter, the callback will not fire
unless the state listened for is maintained for that number of seconds.
This makes the most sense if a specific attribute is specified (or the
default of ``state`` is used), and in conjunction with the ``old`` or
``new`` parameters, or both. When the callback is called, it is supplied
with the values of ``entity``, ``attr``, ``old`` and ``new`` that were
current at the time the actual event occured, since the assumption is
that none of them have changed in the intervening period.

if you use ``duration`` when listening for an entire device type rather than a specific entity, or for all state changes, you may get unpredictable results, so it is recommended that this parameter is only used in conjunction with the state of specific entities.

immediate = (optional)
''''''''''''''''''''''

True or False

Quick check enables the countdown for a ``delay`` parameter to start at the time
the callback is registered, rather than requiring one or more state changes. This can be useful if
for instance you want the duration to be triggered immediately if a light is already on.

If ``immediate`` is in use, and ``new`` and ``duration`` are both set, AppDaemon will check if the entity
is already set to the new state and if so it will start the clock immediately. In this case, old will be ignored
and when the timer triggers, its state will be set to None. If new or entity are not set, ``immediate`` will be ignored.

oneshot = (optional)
''''''''''''''''''''

True or False

If ``oneshot`` is true, the callback will be automatically cancelled after the first state change that results in a callback.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter. The value ``global`` for namespace has special significance, and means that the callback will listen to state updates from any plugin.


\*\*kwargs
''''''''''

Zero or more keyword arguments that will be supplied to the callback
when it is called.

Examples
^^^^^^^^

.. code:: python

    # Listen for any state change and return the state attribute
    self.handle = self.listen_state(self.my_callback)

    # Listen for any state change involving a light and return the state attribute
    self.handle = self.listen_state(self.my_callback, "light")

    # Listen for a state change involving light.office1 and return the state attribute
    self.handle = self.listen_state(self.my_callback, "light.office_1")

    # Listen for a state change involving light.office1 and return the entire state as a dict
    self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "all")

    # Listen for a state change involving the brightness attribute of light.office1
    self.handle = self.listen_state(self.my_callback, "light.office_1", attribute = "brightness")

    # Listen for a state change involving light.office1 turning on and return the state attribute
    self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on")

    # Listen for a state change involving light.office1 changing from brightness 100 to 200 and return the state attribute
    self.handle = self.listen_state(self.my_callback, "light.office_1", old = "100", new = "200")

    # Listen for a state change involving light.office1 changing to state on and remaining on for a minute
    self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on", duration = 60)

    # Listen for a state change involving light.office1 changing to state on and remaining on for a minute
    # Trigger the delay immediately if the light is already on
    self.handle = self.listen_state(self.my_callback, "light.office_1", new = "on", duration = 60, immediate = True)

cancel\_listen\_state()
~~~~~~~~~~~~~~~~~~~~~~~

Cancel a ``listen_state()`` callback. This will mean that the App will
no longer be notified for the specific state change that has been
cancelled. Other state changes will continue to be monitored.

Synopsis
^^^^^^^^

.. code:: python

    cancel_listen_state(handle)

Returns
^^^^^^^

Nothing

Parameters
^^^^^^^^^^

handle
''''''

The handle returned when the ``listen_state()`` call was made.

Examples
^^^^^^^^

.. code:: python

    self.cancel_listen_state(self.office_light_handle)

info\_listen\_state()
~~~~~~~~~~~~~~~~~~~~~

Get information on state a callback from its handle.

Synopsis
^^^^^^^^

.. code:: python

    entity, attribute, kwargs = self.info_listen_state(self.handle)

Returns
^^^^^^^

entity, attribute, kwargs - the values supplied when the callback was
initially created.

Parameters
^^^^^^^^^^

handle
''''''

The handle returned when the ``listen_state()`` call was made.

Examples
^^^^^^^^

.. code:: python

    entity, attribute, kwargs = self.info_listen_state(self.handle)

Scheduler Calls
---------------

run\_in()
~~~~~~~~~

Run the callback in a defined number of seconds. This is used to add a
delay, for instance a 60 second delay before a light is turned off after
it has been triggered by a motion detector. This callback should always
be used instead of ``time.sleep()`` as discussed previously.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_in(callback, delay, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

delay
'''''

Delay, in seconds before the callback is invoked.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

    self.handle = self.run_in(self.run_in_c, 10)
    self.handle = self.run_in(self.run_in_c, , 5, title = "run_in5")

run\_once()
~~~~~~~~~~~

Run the callback once, at the specified time of day. If the time of day
is in the past, the callback will occur on the next day.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_once(callback, time, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

time
''''

A Python ``time`` object that specifies when the callback will occur. If
the time specified is in the past, the callback will occur the next day
at the specified time.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

     Run at 4pm today, or 4pm tomorrow if it is already after 4pm
    import datetime
    ...
    runtime = datetime.time(16, 0, 0)
    handle = self.run_once(self.run_once_c, runtime)

run\_at()
~~~~~~~~~

Run the callback once, at the specified date and time.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_at(callback, datetime, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer. ``run_at()`` will raise
an exception if the specified time is in the past.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

datetime
''''''''

A Python ``datetime`` object that specifies when the callback will
occur.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

     Run at 4pm today
    import datetime
    ...
    runtime = datetime.time(16, 0, 0)
    today = datetime.date.today()
    event = datetime.datetime.combine(today, runtime)
    handle = self.run_once(self.run_once_c, event)

run\_daily()
~~~~~~~~~~~~

Execute a callback at the same time every day. If the time has already
passed, the function will not be invoked until the following day at the
specified time.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_daily(callback, start, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

start
'''''

A Python ``time`` object that specifies when the callback will occur. If
the time specified is in the past, the callback will occur the next day
at the specified time.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

    # Run daily at 7pm
    import datetime
    ...
    runtime = datetime.time(19, 0, 0)
    self.run_daily(self.run_daily_c, runtime)

run\_hourly()
~~~~~~~~~~~~~

Execute a callback at the same time every hour. If the time has already
passed, the function will not be invoked until the following hour at the
specified time.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_hourly(callback, start, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

start
'''''

A Python ``time`` object that specifies when the callback will occur,
the hour component of the time object is ignored. If the time specified
is in the past, the callback will occur the next hour at the specified
time. If time is not supplied, the callback will start an hour from the
time that ``run_hourly()`` was executed.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

     Run every hour, on the hour
    import datetime
    ...
    runtime = datetime.time(0, 0, 0)
    self.run_hourly(self.run_hourly_c, runtime)

run\_minutely()
~~~~~~~~~~~~~~~

Execute a callback at the same time every minute. If the time has
already passed, the function will not be invoked until the following
minute at the specified time.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_minutely(callback, start, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

start
'''''

A Python ``time`` object that specifies when the callback will occur,
the hour and minute components of the time object are ignored. If the
time specified is in the past, the callback will occur the next hour at
the specified time. If time is not supplied, the callback will start a
minute from the time that ``run_minutely()`` was executed.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

     Run Every Minute on the minute
    import datetime
    ...
    time = datetime.time(0, 0, 0)
    self.run_minutely(self.run_minutely_c, time)

run\_every()
~~~~~~~~~~~~

Execute a repeating callback with a configurable delay starting at a
specific time.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_every(callback, time, repeat, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

time
''''

A Python ``datetime`` object that specifies when the initial callback
will occur.

repeat
''''''

After the initial callback has occurred, another will occur every
``repeat`` seconds.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

     Run every 17 minutes starting in 2 hours time
    import datetime
    ...
    self.run_every(self.run_every_c, time, 17 * 60)

cancel\_timer()
~~~~~~~~~~~~~~~

Cancel a previously created timer

Synopsis
^^^^^^^^

.. code:: python

    self.cancel_timer(handle)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

handle
''''''

A handle value returned from the original call to create the timer.

Examples
^^^^^^^^

.. code:: python

    self.cancel_timer(handle)

info\_timer()
~~~~~~~~~~~~~

Get information on a scheduler event from its handle.

Synopsis
^^^^^^^^

.. code:: python

    time, interval, kwargs = self.info_timer(handle)

Returns
^^^^^^^

time - datetime object representing the next time the callback will be
fired

interval - repeat interval if applicable, ``0`` otherwise.

kwargs - the values supplied when the callback was initially created.

Parameters
^^^^^^^^^^

handle
''''''

The handle returned when the scheduler call was made.

Examples
^^^^^^^^

.. code:: python

    time, interval, kwargs = self.info_timer(handle)

Sunrise and Sunset
------------------

run\_at\_sunrise()
~~~~~~~~~~~~~~~~~~

Run a callback every day at or around sunrise.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_at_sunrise(callback, offset=0, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

offset =
'''''''''

The time in seconds that the callback should be delayed after sunrise. A
negative value will result in the callback occurring before sunrise.
This parameter cannot be combined with ``random_start`` or
``random_end``

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

    import datetime
    ...
     Run 45 minutes before sunset
    self.run_at_sunrise(self.sun, offset = datetime.timedelta(minutes = -45).total_seconds(), "Sunrise -45 mins")
     or you can just do the math yourself
    self.run_at_sunrise(self.sun, offset = 30 * 60, "Sunrise +30 mins")
     Run at a random time +/- 60 minutes from sunrise
    self.run_at_sunrise(self.sun, random_start = -60*60, random_end = 60*60, "Sunrise, random +/- 60 mins")
     Run at a random time between 30 and 60 minutes before sunrise
    self.run_at_sunrise(self.sun, random_start = -60*60, random_end = 30*60, "Sunrise, random - 30 - 60 mins")

run\_at\_sunset()
~~~~~~~~~~~~~~~~~

Run a callback every day at or around sunset.

Synopsis
^^^^^^^^

.. code:: python

    self.handle = self.run_at_sunset(callback, offset=0, **kwargs)

Returns
^^^^^^^

A handle that can be used to cancel the timer.

Parameters
^^^^^^^^^^

callback
''''''''

Function to be invoked when the requested state change occurs. It must
conform to the standard Scheduler Callback format documented `Here <APPGUIDE.html#about-schedule-callbacks>`__.

offset =
'''''''''

The time in seconds that the callback should be delayed after sunrise. A
negative value will result in the callback occurring before sunrise.
This parameter cannot be combined with ``random_start`` or
``random_end``

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

     Example using timedelta
    import datetime
    ...
    self.run_at_sunset(self.sun, offset = datetime.timedelta(minutes = -45).total_seconds(), "Sunset -45 mins")
     or you can just do the math yourself
    self.run_at_sunset(self.sun, offset = 30 * 60, "Sunset +30 mins")
     Run at a random time +/- 60 minutes from sunset
    self.run_at_sunset(self.sun, random_start = -60*60, random_end = 60*60, "Sunset, random +/- 60 mins")
     Run at a random time between 30 and 60 minutes before sunset
    self.run_at_sunset(self.sun, random_start = -60*60, random_end = 30*60, "Sunset, random - 30 - 60 mins")

sunrise()
~~~~~~~~~

Return the time that the next Sunrise will occur.

Synopsis
^^^^^^^^

.. code:: python

    self.sunrise()

Returns
^^^^^^^

A Python datetime that represents the next time Sunrise will occur.

Examples
^^^^^^^^

.. code:: python

    rise_time = self.sunrise()

sunset()
~~~~~~~~

Return the time that the next Sunset will occur.

Synopsis
^^^^^^^^

.. code:: python

    self.sunset()

Returns
^^^^^^^

A Python datetime that represents the next time Sunset will occur.

Examples
^^^^^^^^

.. code:: python

    set_time = self.sunset()

sun\_up()
~~~~~~~~~

A function that allows you to determine if the sun is currently up.

Synopsis
^^^^^^^^

.. code:: python

    result = self.sun_up()

Returns
^^^^^^^

``True`` if the sun is up, False otherwise.

Examples
^^^^^^^^

.. code:: python

    if self.sun_up():
        do something

sun\_down()
~~~~~~~~~~~

A function that allows you to determine if the sun is currently down.

Synopsis
^^^^^^^^

.. code:: python

    result = self.sun_down()

Returns
^^^^^^^

``True`` if the sun is down, False otherwise.

Examples
^^^^^^^^

.. code:: python

    if self.sun_down():
        do something

Events
------

listen\_event()
~~~~~~~~~~~~~~~

Listen event sets up a callback for a specific event, or any event.

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

Name of the event to subscribe to. Can be a standard Home Assistant
event such as ``service_registered`` or an arbitrary custom event such
as ``"MODE_CHANGE"``. If no event is specified, ``listen_event()`` will
subscribe to all events.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter. The value ``global`` for namespace has special significance, and means that the callback will lsiten to state updates from any plugin.


\*\*kwargs (optional)
'''''''''''''''''''

One or more keyword value pairs representing App specific parameters to
supply to the callback. If the keywords match values within the event
data, they will act as filters, meaning that if they don't match the
values, the callback will not fire.

As an example of this, a Minimote controller when activated will
generate an event called ``zwave.scene_activated``, along with 2 pieces
of data that are specific to the event - ``entity_id`` and ``scene``. If
you include keyword values for either of those, the values supplied to
the \`listen\_event()1 call must match the values in the event or it
will not fire. If the keywords do not match any of the data in the event
they are simply ignored.

Filtering will work with any event type, but it will be necessary to
figure out the data associated with the event to understand what values
can be filtered on. This can be achieved by examining Home Assistant's
logfiles when the event fires.

Examples
^^^^^^^^

.. code:: python

    self.listen_event(self.mode_event, "MODE_CHANGE")
     Listen for a minimote event activating scene 3:
    self.listen_event(self.generic_event, "zwave.scene_activated", scene_id = 3)
     Listen for a minimote event activating scene 3 from a specific minimote:
    self.listen_event(self.generic_event, "zwave.scene_activated", entity_id = "minimote_31", scene_id = 3)

cancel\_listen\_event()
~~~~~~~~~~~~~~~~~~~~~~~

Cancels callbacks for a specific event.

Synopsis
^^^^^^^^

.. code:: python

    cancel_listen_event(handle)

Returns
^^^^^^^

None.

Parameters
^^^^^^^^^^

handle
''''''

A handle returned from a previous call to ``listen_event()``.

Examples
^^^^^^^^

.. code:: python

    self.cancel_listen_event(handle)

info\_listen\_event()
~~~~~~~~~~~~~~~~~~~~~

Get information on an event callback from its handle.

Synopsis
^^^^^^^^

.. code:: python

    service, kwargs = self.info_listen_event(handle)

Returns
^^^^^^^

service, kwargs - the values supplied when the callback was initially
created.

Parameters
^^^^^^^^^^

handle
''''''

The handle returned when the ``listen_event()`` call was made.

Examples
^^^^^^^^

.. code:: python

    service, kwargs = self.info_listen_event(handle)

fire\_event()
~~~~~~~~~~~~~

Fire an event on the HomeAssistant bus, for other components to hear.

Synopsis
^^^^^^^^

.. code:: python

    fire_event(event, **kwargs)

Returns
^^^^^^^

None.

Parameters
^^^^^^^^^^

event
'''''

Name of the event. Can be a standard Home Assistant event such as
``service_registered`` or an arbitrary custom event such as
``"MODE_CHANGE"``.

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter



\*\*kwargs
''''''''''

Zero or more keyword arguments that will be supplied as part of the
event.

Examples
^^^^^^^^

.. code:: python

    self.fire_event("MY_CUSTOM_EVENT", jam="true")

Miscellaneous Helper Functions
------------------------------

time()
~~~~~~

Returns a python ``time`` object representing the current time. Use this
in preference to the standard Python ways to discover the current time,
especially when using the "Time Travel" feature for testing.

Synopsis
^^^^^^^^

.. code:: python

    time()

Returns
^^^^^^^

A localised Python time object representing the current AppDaemon time.

Parameters
^^^^^^^^^^

None

Example
^^^^^^^

.. code:: python

    now = self.time()

date()
~~~~~~

Returns a python ``date`` object representing the current date. Use this
in preference to the standard Python ways to discover the current date,
especially when using the "Time Travel" feature for testing.

Synopsis
^^^^^^^^

.. code:: python

    date()

Returns
^^^^^^^

A localised Python time object representing the current AppDaemon date.

Parameters
^^^^^^^^^^

None

Example
^^^^^^^

.. code:: python

    today = self.date()

datetime()
~~~~~~~~~~

Returns a python ``datetime`` object representing the current date and
time. Use this in preference to the standard Python ways to discover the
current time, especially when using the "Time Travel" feature for
testing.

Synopsis
^^^^^^^^

.. code:: python

    datetime()

Returns
^^^^^^^

A localised Python datetime object representing the current AppDaemon
date and time.

Parameters
^^^^^^^^^^

None

Example
^^^^^^^

.. code:: python

    now = self.datetime()

convert\_utc()
~~~~~~~~~~~~~~

Home Assistant provides timestamps of several different sorts that may
be used to gain additional insight into state changes. These timestamps
are in UTC and are coded as ISO 8601 Combined date and time strings.
``convert_utc()`` will accept one of these strings and convert it to a
localised Python datetime object representing the timestamp

Synopsis
^^^^^^^^

.. code:: python

    convert_utc(utc_string)

Returns
^^^^^^^

``convert_utc(utc_string)`` returns a localised Python datetime object
representing the timestamp.

Parameters
^^^^^^^^^^

utc\_string
'''''''''''

An ISO 8601 encoded date and time string in the following format:
``2016-07-13T14:24:02.040658-04:00``

Example
^^^^^^^

parse\_time()
~~~~~~~~~~~~~

Takes a string representation of a time, or sunrise or sunset offset and
converts it to a ``datetime.time`` object.

Synopsis
^^^^^^^^

.. code:: python

    parse_time(time_string)

Returns
^^^^^^^

A ``datetime.time`` object, representing the time given in the
``time_string`` argument.

Parameters
^^^^^^^^^^

time\_string
''''''''''''

A representation of the time in a string format with one of the
following formats:

-  HH:MM:SS - the time in Hours Minutes and Seconds, 24 hour format.
-  sunrise\|sunset [+\|- HH:MM:SS]- time of the next sunrise or sunset
   with an optional positive or negative offset in Hours Minutes and
   seconds

Example
^^^^^^^

.. code:: python

    time = self.parse_time("17:30:00")
    time = self.parse_time("sunrise")
    time = self.parse_time("sunset + 00:30:00")
    time = self.parse_time("sunrise + 01:00:00")

now\_is\_between()
~~~~~~~~~~~~~~~~~~

Takes two string representations of a time, or sunrise or sunset offset
and returns true if the current time is between those 2 times.
``now_is_between()`` can correctly handle transitions across midnight.

Synopsis
^^^^^^^^

.. code:: python

    now_is_between(start_time_string, end_time_string)

Returns
^^^^^^^

``True`` if the current time is within the specified start and end
times, ``False`` otherwise.

Parameters
^^^^^^^^^^

start\_time\_string, end\_time\_string
''''''''''''''''''''''''''''''''''''''

A representation of the start and end time respectively in a string
format with one of the following formats:

-  HH:MM:SS - the time in Hours Minutes and Seconds, 24 hour format.
-  ``sunrise``\ \|\ ``sunset`` [+\|- HH:MM:SS]- time of the next sunrise
   or sunset with an optional positive or negative offset in Hours
   Minutes and seconds

Example
^^^^^^^

.. code:: python

    if self.now_is_between("17:30:00", "08:00:00"):
        do something
    if self.now_is_between("sunset - 00:45:00", "sunrise + 00:45:00"):
        do something

entity\_exists()
~~~~~~~~~~~~~~~~

Synopsis
^^^^^^^^

.. code:: python

    entity_exists(entity)

``entity_exists()`` is used to verify if a given entity exists in Home
Assistant or not. When working with multiple Home Assistant instances, it is
possible to specify the namespace, so that it checks within the right instance in
in the event the app is working in a different instance. Also when using this function,
it is also possible to check if an Appdaemon entity exists.

Returns
^^^^^^^

``entity_exists()`` returns ``True`` if the entity exists, ``False``
otherwise.

Parameters
^^^^^^^^^^

entity
''''''

The fully qualified name of the entity to check for (including the
device type)

namespace = (optional)
''''''''''''''''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this parameter

Examples
^^^^^^^^

.. code:: python

    # Return True if the entity light.living_room exist within the app's namespace
    if self.entity_exists("light.living_room"):
      do something

    # Return True if the entity mqtt.security_settings exist within the mqtt namespace
    # if the app is operating in a different namespace like default
    if self.entity_exists("mqtt.security_settings", namespace = "mqtt"):
      do something

      ...

get\_app()
~~~~~~~~~~

``get_app()`` will return the instantiated object of another app running
within the system. This is useful for calling functions or accessing
variables that reside in different apps without requiring duplication of
code.

Synopsis
^^^^^^^^

.. code:: python

    get_app(self, name)

Parameters
^^^^^^^^^^

name
''''

Name of the app required. This is the name specified in header section
of the config file, not the module or class.

Returns
^^^^^^^

An object reference to the class.

Example
^^^^^^^

.. code:: python

    MyApp = self.get_app("MotionLights")
    MyApp.turn_light_on()

split\_device\_list()
~~~~~~~~~~~~~~~~~~~~~

``split_device_list()`` will take a comma separated list of device types
(or anything else for that matter) and return them as an iterable list.
This is intended to assist in use cases where the App takes a list of
entities from an argument, e.g. a list of sensors to monitor. If only
one entry is provided, an iterable list will still be returned to avoid
the need for special processing.

Synopsis
^^^^^^^^

.. code:: python

    devices = split_device_list(list)

Returns
^^^^^^^

A list of split devices with 1 or more entries.

Example
^^^^^^^

.. code:: python

    for sensor in self.split_device_list(self.args["sensors"]):
        do something for each sensor, e.g. make a state subscription

Logfiles
--------

AppDaemon provides a couple of convenience functions for loggin to bith the main log and the app error log. These will automatically insert the app name for information.

log()
~~~~~

Synopsis
^^^^^^^^

.. code:: python

    log(message, level = "INFO")

Returns
^^^^^^^

Nothing

Parameters
^^^^^^^^^^

Message
'''''''

The message to log.

level
'''''

The log level of the message - takes a string representing the standard
logger levels.

Examples
^^^^^^^^

.. code:: python

    self.log("Log Test: Parameter is {}".format(some_variable))
    self.log("Log Test: Parameter is {}".format(some_variable), level = "ERROR")
    self.log("Line: __line__, module: __module__, function: __function__, Message: Something bad happened")

error()
~~~~~~~

Synopsis
^^^^^^^^

.. code:: python

    error(message, level = "WARNING")

Returns
^^^^^^^

Nothing

Parameters
^^^^^^^^^^

Message
'''''''

The message to log.

level
'''''

The log level of the message - takes a string representing the standard
logger levels.

Examples
^^^^^^^^

.. code:: python

    self.error("Some Warning string")
    self.error("Some Critical string", level = "CRITICAL")


If you want to perform more elaborate logging or formatting, the underlying ``logger`` objects can be obtained:

get_main_log()
~~~~~~~

Synopsis
^^^^^^^^

.. code:: python

    self.get_main_log()


Returns
^^^^^^^

The underlying ``logger`` object used for the main log.

Examples
^^^^^^^^

.. code:: python

    log = self.get_main_log()
    log.log(50, "Log a critical error")


get_error_log()
~~~~~~~

Synopsis
^^^^^^^^

.. code:: python

    self.get_error_log()


Returns
^^^^^^^

The underlying ``logger`` object used for the error log.

Examples
^^^^^^^^

.. code:: python

    error_log = self.get_error_log()
    error_log.log(40, "Log an error")

listen_log()
~~~~~~~

Register the app to receive a callback everytime an app logs a message

Synopsis
^^^^^^^^

.. code:: python

    self.listen_log(cb)


Returns
^^^^^^^

None.

Examples
^^^^^^^^

.. code:: python

    self.listen_log(self.cb)

cancel_log()
~~~~~~~~~~~~

Cancel the log callback for an app.

Synopsis
^^^^^^^^

.. code:: python

    self.cancel_listen_log()

Returns
^^^^^^^

None.

Examples
^^^^^^^^

.. code:: python

    self.cancel_listen_log()

About listen_log() Callbacks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The signature for a callback used with ``listen_log()`` is as follows:

.. code:: python

    def cb(self, name, ts, level, message):


``name`` is the name of the app that logged the message
``ts`` is the timestamp of the message
``level`` is the severity level of the message
``message`` is the text of the message

API
---

register_endpoint()
~~~~~~~~~~~~~~~~~~~

Register an endpoint for API calls into an App.

Synopsis
^^^^^^^^

.. code:: python

    register_endpoint(callback, name = None)

Returns
^^^^^^^

handle - a handle that can be used to remove the registration

Parameters
^^^^^^^^^^

callback
''''''''

The function to be called when a request is made to the named endpoint

name
''''

The name of the endpoint to be used for the call. If ``None`` the name of the App will be used.

Examples
^^^^^^^^

.. code:: python

    self.register_endpoint(my_callback)
    self.register_callback(alexa_cb, "alexa")

It should be noted that the register function, should return a string (can be empty), and a HTTP OK status response.
For example ``'',200``. if this is not added as a returned response, the function will generate an error each time
it is processed

unregister_endpoint()
~~~~~~~~~~~~~~~~~~~~~

Remove a previously registered endpoint.

Synopsis
^^^^^^^^

.. code:: python

    unregister_endpoint(handle)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

handle
''''''

A handle returned by a previous call to ``register_endpoint``

Examples
^^^^^^^^

.. code:: python

    self.unregister_endpoint(handle)


Alexa Helper Functions
----------------------

get_alexa_intent()
~~~~~~~~~~~~~~~~~~

Register an endpoint for API calls into an App.

Synopsis
^^^^^^^^

.. code:: python

    self.get_alexa_intent(data)

Returns
^^^^^^^

A string representing the Intent from the interaction model that was requested

Parameters
^^^^^^^^^^

data
''''

The request data received from Alexa.

Examples
^^^^^^^^

.. code:: python

    intent = self.get_alexa_intent(data)

get_alexa_slot_value()
~~~~~~~~~~~~~~~~~~~~~~

Return values for slots form the interaction model.

Synopsis
^^^^^^^^

.. code:: python

    self.get_alexa_slot_value(data, name = None)

Returns
^^^^^^^

A string representing the value of the slot from the interaction model, or a hash of slots.

Parameters
^^^^^^^^^^

data
''''

The request data received from Alexa.

name
''''

Name of the slot. If a name is not specified, all slots will be returned as a dictionary.
If a name is spedicied but is not found, ``None`` will be returned.

Examples
^^^^^^^^

.. code:: python

    beer_type = self.get_alexa_intent(data, "beer_type")
    all_slots = self.get_alexa_intent(data)


self.format_alexa_response(speech = speech, card = card, title = title)

format_alexa_response()
~~~~~~~~~~~~~~~~~~~~~~~

Format a response to be returned to Alex including speech and a card.

Synopsis
^^^^^^^^

.. code:: python

    self.format_alexa_response(speech = speech, card = card, title = title)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

speech =
''''''''

The text for Alexa to say

card =
''''''

Text for the card

title =
''''''''

Title for the card

Examples
^^^^^^^^

.. code:: python

    format_alexa_response(speech = "Hello World", card = "Greetings to the world", title = "Hello")

Google Home Helper Functions
----------------------------

get_apiai_intent()
~~~~~~~~~~~~~~~~~~

Register an endpoint for API calls into an App.

Synopsis
^^^^^^^^

.. code:: python

    self.get_apiai_intent(data)

Returns
^^^^^^^

A string representing the Intent from the interaction model that was requested

Parameters
^^^^^^^^^^

data
''''

The request data received from Google Home.

Examples
^^^^^^^^

.. code:: python

    intent = self.get_apiai_intent(data)

get_apiai_slot_value()
~~~~~~~~~~~~~~~~~~~~~~

Return values for slots form the interaction model.

Synopsis
^^^^^^^^

.. code:: python

    self.get_apiai_slot_value(data, name = None)

Returns
^^^^^^^

A string representing the value of the slot from the interaction model, or a hash of slots.

Parameters
^^^^^^^^^^

data
''''

The request data received from Google Home.

name
''''

Name of the slot. If a name is not specified, all slots will be returned as a dictionary.
If a name is spedicied but is not found, ``None`` will be returned.

Examples
^^^^^^^^

.. code:: python

    beer_type = self.get_apiai_intent(data, "beer_type")
    all_slots = self.get_apiai_intent(data)


self.format_apiai_response(speech = speech)

format_appapi_response()
~~~~~~~~~~~~~~~~~~~~~~~

Format a response to be returned to Google Home including speech.

Synopsis
^^^^^^^^

.. code:: python

    self.format_apiai_response(speech = speech)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

speech =
''''''''

The text for Google Home to say

Examples
^^^^^^^^

.. code:: python

    format_apiai_response(speech = "Hello World")

Dashboard Functions
-------------------

set\_app\_state()
~~~~~~~~~~~~~~~~~

Publish state information to AppDaemon's internal state and push the
state changes out to listening Apps and Dashboards.

Synopsis
^^^^^^^^

.. code:: python

    self.set_app_state(entity_id, state)

Returns
^^^^^^^

None.

Parameters
^^^^^^^^^^

entity\_id
''''''''''

A name for the new state. It must conform to the standard entity\_id
format, e.g. ``<device_type>.<name>``. however device type and name can
be whatever you like as long as you ensure it doesn't conflict with any
real devices. For clarity, I suggest the convention of using
``appdaemon`` as the device type. A single App can publish to as many
entity ids as desired.

state
'''''

The state to be associated with the entity id. This is a dictionary and
must contain the entirety of the state information, It will replace the
old state information, and calls like ``listen_state()`` should work
correctly reporting the old and the new state information as long as you
keep the dictionary looking similar to HA status updates, e.g. the main
state in a state field, and any attributes in an attributes
sub-dictionary.

attributes
'''''''''

A sub-dictionary of keys and values, to set the attributes within AppDaemon's internal state object. It is optional to set these
values. If this parameter is specified, by default it will update the prexisting ``attributes`` if it was existing. If wanting to
modify the entire attributes for example remove some keys, the best way to do this, is to read the entire ``attributes`` of the entity
using ``self.get_state("appdaemon.alerts", attribute = "all")``. Then modify the dictionary as needed, and when using the
``self.set_app_state()`` again for the entity, set the ``replace`` flag to ``True``. By setting this to ``True``, the internal
dictionary is not just updated with the new set of values but completely replaced with it.

namespace
'''''''''

Namespace to use for the call - see the section on namespaces for a detailed description. In most cases it is safe to ignore this
parameter. When working with multiple namespaces, it is important to set the namespace of the function, either when reading the
entity's value, or settingit to certain values. Without specifying the namespace, it will always seekout the entity within its present
namespace. For example if an app operates within the ``default`` namepace which is Home Assistant, it is possible to modify an entity
within ``mqtt`` namespace, by specifying the namespace during the call.

Examples
^^^^^^^^

.. code:: python

    self.set_app_state("appdaemon.alerts", {"state": number, "attributes": {"unit_of_measurement": ""}})

    # Return state for the entire Appdaemon entities within the namepace
    state = self.get_state(namepace = "default")

    # though working within default namespace, return state of an entity within mqtt namespace
    state = self.get_state("mqtt.security_settings", namepace = "mqtt")

    #though working within default namespace, return state of an entity within mqtt namespace,
    #modify its attributes, and replace with new data
    all_state = self.get_state("mqtt.security_settings", attribute = "all")
    state_attribute = all_state["attributes"] #remove keys as required at this point
    #reload the data with the new values, but this time use the replace flag
    self.set_app_state("mqtt.security_settings", attributes = state_attribute, replace = True, namepace = "mqtt")

This is an example of a state update that can be used with a sensor
widget in HADashboard. "state" is the actual value, and the widget also
expects an attribute called "unit\_of\_measurement" to work correctly.

dash\_navigate()
~~~~~~~~~~~~~~~~

Force all connected Dashboards to navigate to a new URL

Synopsis
^^^^^^^^

.. code:: python

    dash_navigate(self, target, timeout = -1, ret = None)

Returns
^^^^^^^

None.

Parameters
^^^^^^^^^^

target
''''''

A URL for the dashboard to navigate to e.g. ``/MainDash``

ret
'''

Time to wait before the optional second change. If not specified the first change will be permanent.

timeout
'''''''

URL to navigate back to after ``timeout``. If not specified, the dashboard will navigate back to the original panel.

Examples
^^^^^^^^

.. code:: python

    self.dash_navigate("/AlarmStatus", timeout=10)        # Switch to AlarmStatus Panel then return to current panel after 10 seconds
    self.dash_navigate("/Locks", timeout=10, ret="/Main") # Switch to Locks Panel then return to Main panel after 10 seconds

Constraints
-----------

register_constraint()
~~~~~~~~~~~~~~~~~~~~~

Register a custom constraint

Synopsis
^^^^^^^^

.. code:: python

    register_constraint(self, name)

Returns
^^^^^^^

None.

Parameters
^^^^^^^^^^

name
''''''

Name of the function to register for the constraint. Note: this is a string not a function reference.

Examples
^^^^^^^^

.. code:: python

        self.register_constraint("my_custom_constraint")



deregister_constraint()
~~~~~~~~~~~~~~~~~~~~~~~

De-register a custom constraint.

Synopsis
^^^^^^^^

.. code:: python

    deregister_constraint(self, name)

Returns
^^^^^^^

None.

Parameters
^^^^^^^^^^

name
''''''

Name of the function to register for the constraint. Note: this is a string not a function reference.

Examples
^^^^^^^^

.. code:: python

        self.deregister_constraint("my_custom_constraint")

list_constraints()
~~~~~~~~~~~~~~~~~~~~~~~

Get a list of all currently registered custom constraints. Note: this list will include any constraints registered by the plugin itself.

Synopsis
^^^^^^^^

.. code:: python

    constraints = list_constraints()

Returns
^^^^^^^

A list of all currently registered constraints.

Examples
^^^^^^^^

.. code:: python

        list = self.list_constraints()



Namespace
---------

set\_namespace()
~~~~~~~~~~~~~~~~

Set a new namespace for the app to use from that point forward.

Synopsis
^^^^^^^^

.. code:: python

    set_namespace(self, namespace)

Returns
^^^^^^^

None.

Parameters
^^^^^^^^^^

namespace
'''''''''

The value for the namespace to use moving forward.


Examples
^^^^^^^^

.. code:: python

    self.set_namespace("hass1")
    self.set_namespace("default")

Introspection
-------------

get_scheduler_entries()
~~~~~~~~~~~~~~~~~~~~~~~

Get information on AppDaemon scheduler entries.

Synopsis
^^^^^^^^

.. code:: python

    get_scheduler_entries()

Returns
^^^^^^^

A dictionary containing all the information for entries in the AppDaemon scheduler

Examples
^^^^^^^^

.. code:: python

    schedule = self.get_scheduler_entries()

get_callback_entries()
~~~~~~~~~~~~~~~~~~~~~~~

Get information on AppDaemon callback entries.

Synopsis
^^^^^^^^

.. code:: python

    get_callback_entries()

Returns
^^^^^^^

A dictionary containing all the information for entries in the AppDaemon state and event callback table

Examples
^^^^^^^^

.. code:: python

    callbacks = self.get_callback_entries()

get_thread_info()
~~~~~~~~~~~~~~~~~~~~~~~

Get information on AppDaemon worker threads.

Synopsis
^^^^^^^^

.. code:: python

    get_thread_info()

Returns
^^^^^^^

A dictionary containing all the information for AppDaemon worker threads

Examples
^^^^^^^^

.. code:: python

    thread_info = self.get_thread_info()

get_ad_version()
~~~~~~~~~~~~~~~~

Return the cuurent version of AppDaemon

Synopsis
^^^^^^^^

.. code:: python

    get_ad_version()

Returns
^^^^^^^

A string containing the version number

Examples
^^^^^^^^

.. code:: python

    version = self.get_ad_version()
