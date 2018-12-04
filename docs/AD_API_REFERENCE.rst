AppDaemon API Reference
=======================

A number of api calls are native to AppDaemon and will exist in any App as they are inherited through the plugin API. If the ``get_plugin_api()`` style of declarations is used, these functions will become available via an object created by the ``get_ad_api()`` call:

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

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

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

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

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

Either a Python ``time`` object or a ``parse_time()`` formatted string that specifies when the callback will occur. If the time specified is in the past, the callback will occur the next day
at the specified time.

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

    # Run at 4pm today, or 4pm tomorrow if it is already after 4pm
    import datetime
    ...
    runtime = datetime.time(16, 0, 0)
    handle = self.run_once(self.run_once_c, runtime)

    # With parse_time() formatting
    # run at 10:30
    handle = self.run_once(self.run_once_c, "10:30:00")
    # run at sunset
    handle = self.run_once(self.run_once_c, "sunset")
    # run an hour after sunrise
    handle = self.run_once(self.run_once_c, "sunrise + 01:00:00")

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

Either a Python ``datetime`` object or a ``parse_datetime()`` formatted string that specifies when the callback will
occur.

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

\*\*kwargs
''''''''''

Arbitary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

    # Run at 4pm today
    import datetime
    ...
    runtime = datetime.time(16, 0, 0)
    today = datetime.date.today()
    event = datetime.datetime.combine(today, runtime)
    handle = self.at(self.run_at_c, event)

    # With parse_time() formatting
    # run at 10:30 today
    handle = self.at(self.run_at_c, "10:30:00")
    # Run on a specific date and time
    handle = self.at(self.run_at_c, "2018-12-11 10:30:00")
    # run at the next sunset
    handle = self.at(self.run_at_c, "sunset")
    # run an hour after the next sunrise
    handle = self.at(self.run_at_c, "sunrise + 01:00:00")

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

A Python ``time`` object  or a ``parse_datetime()`` formatted string that specifies when the callback will occur. If
the time specified is in the past, the callback will occur the next day
at the specified time.

When specifying sunrise or sunset relative times using the ``parse_datetime()`` format, the time of the callback will be adjusted every day to track the actual value of sunrise or sunset.

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

\*\*kwargs
''''''''''

Arbitrary keyword parameters to be provided to the callback function when
it is invoked.

Examples
^^^^^^^^

.. code:: python

    # Run daily at 7pm
    import datetime
    ...
    time = datetime.time(19, 0, 0)
    self.run_daily(self.run_daily_c, runtime)

    # With parse_time() formatting
    # run at 10:30 every day
    handle = self.run_daily(self.run_daily_c, "10:30:00")
    # Run every day at sunrise
    handle = self.run_daily(self.run_daily_c, "sunrise")
    # Run every day an hour after sunset
    handle = self.run_daily(self.run_daily_c, "sunset + 01:00:00")

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

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

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
    time = datetime.time(0, 0, 0)
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

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

\*\*kwargs
''''''''''

Arbitrary keyword parameters to be provided to the callback function when
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

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

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

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

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

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

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

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.


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

Fire an event on the AppDaemon bus, for apps and plugins.

Fire event will propagate the event to whichever namespace is currently active. If a plugin is in use for the namespace, fire_event() will use the plugin to fire the event rather than firing it locally, under the assumption that the event will be returned to AppDamon via the plugin's event monitoring.

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

parse\_datetime()
~~~~~~~~~~~~~

Takes a string representation of a date and time, or sunrise or sunset offset and
converts it to a ``datetime.datetime`` object.

Synopsis
^^^^^^^^

.. code:: python

    parse_time(time_string)

Returns
^^^^^^^

A ``datetime.datetimetime`` object, representing the time and date given in the
``time_string`` argument.

Parameters
^^^^^^^^^^

time\_string
''''''''''''

A representation of the time in a string format with one of the
following formats:

-  YY-MM-DD HH:MM:SS - the date and time in Year, Month, Day, Hours Minutes and Seconds, 24 hour format.
-  HH:MM:SS - the time in Hours Minutes and Seconds, 24 hour format.
-  sunrise\|sunset [+\|- HH:MM:SS]- time of the next sunrise or sunset
   with an optional positive or negative offset in Hours Minutes and
   seconds

If the ``HH:MM:SS`` format is used, the resulting datetime object will have today's date.

Example
^^^^^^^

.. code:: python

    time = self.parse_time("2018-08-09 17:30:00")
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

get\_plugin_api()
~~~~~~~~~~~~~~~~

``get_plugin_api()`` will return an object suitable for running specific API calls on for a particular plugin. This method is used to enable an app to work with multiple plugins. The object will support all methods that an app derived from the plugin's class would, via the self notation, but will contain methods and configuration data for the target plugin rather than the plugin the App itself was derived from.

Synopsis
^^^^^^^^

.. code:: python

    get_app(self, plugin)

Parameters
^^^^^^^^^^

plugin
''''''

Name of the plugin required. This is the name specified as the top level of the plugin configuration. For instance, with the following configuration:

.. code:: yaml

  plugins:
    HASS:
      type: hass
        ...

The name used in the ``get_plugin_api()`` call would be ``HASS``.

Returns
^^^^^^^

An object reference to the class.

Example
^^^^^^^

This example shows an App built using the hassapi also using an mqtt api call.

.. code:: python

    import hassapi as hass

    class GetAPI(hass.Hass):

      def initialize(self):

        # Hass API Call
        self.turn_on("light.office")

        # Grab an object for the MQTT API
        self.mqtt = self.get_plugin_api("MQTT")

        # Make MQTT API Call
        self.mqtt.mqtt_publish("topic", payload = "Payload"):

get\_ad_api()
~~~~~~~~~~~~~~~~

``get_ad_api()`` will return an object suitable for running AppDaemon base API calls, for instance scheduler or state calls, in fact all the calls documented in this section. This call requires an import of ``adbase``.

Synopsis
^^^^^^^^

.. code:: python

    get_app(self, plugin)

Parameters
^^^^^^^^^^

None.

Returns
^^^^^^^

An object reference to the class.

Example
^^^^^^^

This example shows an App getting an ADAPI object to make a scheduler call.

.. code:: python

    import adbase as ad
    import adapi as adapi

    class Test(ad.ADBase):

      def initialize(self):

        adbase = self.get_ad_api()
        handle = self.adbase.run_in(callback, 20)


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

Parameters
^^^^^^^^^^

list
''''

Comma separated list of devices to be split (no spaces)

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

log()
~~~~~

Synopsis
^^^^^^^^

.. code:: python

    log(message, *args, level = "INFO", ascii_encode="True", log="some log", **kwargs)

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

ascii_encode
''''''''''''

Switch to disable the encoding of all log messages to ascii. Set this to
true if you want to log UTF-8 characters. (Default: True)

log
'''

Send the message to a specific log, either system or user_defined. System logs are ``main_log``, ``error_log``, ```diag_log`` or ``access_log``. Any other value in use here must have a corresponding userdefined entyr in the ``logs`` section of appdaemon.yaml.

Examples
^^^^^^^^

.. code:: python

    self.log("Log Test: Parameter is %s", some_variable)
    self.log("Log Test: Parameter is %s", some_variable, log="test_log")
    self.log("Log Test: Parameter is %s", some_variable, level = "ERROR")
    self.log("Line: __line__, module: __module__, function: __function__, Message: Something bad happened")
    self.log("value is %s", some_value)
    self.log("Stack is", some_value, level="WARNING", stack_info=True)

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
~~~~~~~~~~~~~~

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
    log.critical("Log a critical error")


get_error_log()
~~~~~~~~~~~~~~~

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
    error_log.error("Log an error", stack_info=True, exc_info=True)

get_user_log()
~~~~~~~~~~~~~~~

Synopsis
^^^^^^^^

.. code:: python

    self.get_user_log("test_log")

Parameters
^^^^^^^^^^

log
'''

The name of the log you wnat to get the underrlying logger object from, as described in the ``logs`` section of appdaemon.yaml.

Returns
^^^^^^^

The underlying ``logger`` object used for the error log.

Examples
^^^^^^^^

.. code:: python

    error_log = self.get_error_log()
    error_log.error("Log an error", stack_info=True, exc_info=True)

listen_log()
~~~~~~~~~~~~

Register the app to receive a callback every time an app logs a message.

Synopsis
^^^^^^^^

.. code:: python

    self.listen_log(callback, level, **kwargs)

Parameters
^^^^^^^^^^

callback
''''''''

Function to be called when a message is logged

level
'''''

Logging level to be used - lower levels will not be forwarded to the app. Defaults to "INFO".

log (optional)
''''''''''''''

Name of the log to listen to, default is all logs. The name should be one of the 4 built in types (``main_log``, ``error`log``, ``diag_log``, ``access_log``) or a user defined log entry.

pin = (optional)
''''''''''''''''

True or False

If True, the callback will be pinned to a particular thread.

pin_thread = (optional)
'''''''''''''''''''''''

0 - number of threads -1

Specify which thread from the worker pool the callback will be run by.

\*\*kwargs
''''''''''

Zero or more keyword arguments that will be supplied to the callback
when it is called.

Returns
^^^^^^^

A unique identifier that can be used to cancel the callback if required.
Since variables created within object methods are local to the function
they are created in, and in all likelihood the cancellation will be
invoked later in a different function, it is recommended that handles
are stored in the object namespace, e.g. ``self.handle``.

Examples
^^^^^^^^

.. code:: python

    self.handle = self.listen_log(self.cb, "WARNING")
    self.handle = self.listen_log(self.cb, "WARNING", log="main_log")
    self.handle = self.listen_log(self.cb, "WARNING", log="my_custom_log")

cancel_log()
~~~~~~~~~~~~

Cancel the log callback for an app.

Synopsis
^^^^^^^^

.. code:: python

    self.cancel_listen_log(handle)

Parameters
^^^^^^^^^^

handle
''''''

The handle returned when the ``listen_log()`` call was made.

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
``type`` is the log the message was sent to - ``log``, ``err``, or ``diag``
``message`` is the text of the message
``kwargs`` any parameters set as keyword values by ``listen_log()``

For AppDaemon system messages, name will be set to "AppDaemon".

App Pinning & Threading
-----------------------

set_app_pin()
~~~~~~~~~~~~~

Set an app to be pinned or unpinned

Synopsis
^^^^^^^^

.. code:: python

    set_app_pin(pin)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

pin
'''

True or false to set whether the App becomes pinned.

Examples
^^^^^^^^

.. code:: python

    def initialize():
        self.set_app_pin(True)

get_app_pin()
~~~~~~~~~~~~~

Find out if the app is currently pinned or not

Synopsis
^^^^^^^^

.. code:: python

    pinned = get_app_pin()

Returns
^^^^^^^

True if the app is pinned, False otherwise.

Parameters
^^^^^^^^^^

None

Examples
^^^^^^^^

.. code:: python

    def initialize():
        if self.get_app_pin(True):
            self.log("I'm pinned!")


set_pin_thread()
~~~~~~~~~~~~~~~~

Set the thread that the app will be pinned to

Synopsis
^^^^^^^^

.. code:: python

    set_pin_thread(thread)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

thread
''''''

Number of the thread to pin to. Threads start at 0 and go up to the number of threads specified in appdaemon.yaml -1.

Examples
^^^^^^^^

.. code:: python

    def initialize():
        self.set_pin_thread(5)

get_pin_thread()
~~~~~~~~~~~~~~~~

Find out which thread the app is pinned to.

Synopsis
^^^^^^^^

.. code:: python

    thread = get_pin_thread()

Returns
^^^^^^^

The thread the app is pinned to or ``-1`` if the thread is not pinned.

Parameters
^^^^^^^^^^

None

Examples
^^^^^^^^

.. code:: python

    def initialize():
        thread = self.get_pin_thread(True):
        self.log("I'm pinned to thread {}".format(thread))

run_in_thread()
~~~~~~~~~~~~~~~~

Schedule a callback to be run in a different thread from the current one.

Synopsis
^^^^^^^^

.. code:: python

    run_in_thread(callback, thread)

Returns
^^^^^^^

None

Parameters
^^^^^^^^^^

callback
''''''

Function to be run on the new thread

thread
''''''

Thread number (0 - number of threads)

Examples
^^^^^^^^

.. code:: python

    self.run_in_thread(my_callback, 8)

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
~~~~~~~~~~~~~~~~~~

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

list_namespaces()
~~~~~~~~~~~~~~~~

List all namespaces curently available

Synopsis
^^^^^^^^

.. code:: python

    set_namespace(self)

Returns
^^^^^^^

A list of available namespaces.

Parameters
^^^^^^^^^^

None

Examples
^^^^^^^^

.. code:: python

    self.list_namespaces()

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
