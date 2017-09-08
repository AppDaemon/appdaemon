Writing AppDaemon Apps
=======================

AppDaemon is a loosely coupled, sandboxed, multi-threaded Python
execution environment for writing automation apps for `Home
Assistant <https://home-assistant.io/>`__ home automation software. It
is intended to complement the Automation and Script components that Home
Assistant currently offers.

Examples
--------

Example apps that showcase most of these functions are available in the
AppDaemon repository:

`Apps <https://github.com/home-assistant/appdaemon/tree/dev/conf/example_apps>`__

Anatomy of an App
-----------------

Automations in AppDaemon are performed by creating a piece of code
(essentially a Python Class) and then instantiating it as an Object one
or more times by configuring it as an App in the configuration file. The
App is given a chance to register itself for whatever events it wants to
subscribe to, and AppDaemon will then make calls back into the Object's
code when those events occur, allowing the App to respond to the event
with some kind of action.

The first step is to create a unique file within the apps directory (as
defined in the ``AppDaemon`` section of configuration file - see `The
Installation Page <INSTALL.html>`__ for further information on the
configuration of AppDaemon itself). This file is in fact a Python
module, and is expected to contain one or more classes derived from the
supplied ``AppDaemon`` class, imported from the supplied
``appdaemon.appapi`` module. The start of an app might look like this:

.. code:: python

    import appdaemon.appapi as appapi

    class MotionLights(appapi.AppDaemon):

When configured as an app in the config file (more on that later) the
lifecycle of the App begins. It will be instantiated as an object by
AppDaemon, and immediately, it will have a call made to its
``initialize()`` function - this function must appear as part of every
app:

.. code:: python

      def initialize(self):

The initialize function allows the app to register any callbacks it
might need for responding to state changes, and also any setup
activities. When the ``initialize()`` function returns, the App will be
dormant until any of its callbacks are activated.

There are several circumstances under which ``initialize()`` might be
called:

-  Initial start of AppDaemon
-  Following a change to the Class code
-  Following a change to the module parameters
-  Following initial configuration of an app
-  Following a change in the status of Daylight Saving Time
-  Following a restart of Home Assistant

In every case, the App is responsible for recreating any state it might
need as if it were the first time it was ever started. If
``initialize()`` is called, the app can safely assume that it is either
being loaded for the first time, or that all callbacks and timers have
been cancelled. In either case, the App will need to recreate them.
Depending upon the application, it may be desirable for the App to
establish a state, such as whether or not a particular light is on,
within the ``initialize()`` function to ensure that everything is as
expected or to make immediate remedial action (e.g., turn off a light
that might have been left on by mistake when the app was restarted).

After the ``initialize()`` function is in place, the rest of the app
consists of functions that are called by the various callback
mechanisms, and any additional functions the user wants to add as part
of the program logic. Apps are able to subscribe to two main classes of
events:

-  Scheduled Events
-  State Change Events

These, along with their various subscription calls and helper functions,
will be described in detail in later sections.

Optionally, a class can add a ``terminate()`` function. This function
will be called ahead of the reload to allow the class to perform any
tidy up that is necessary.

WARNING: Unlike other types of callback, calls to ``initialize()`` and
``terminate()`` are synchronous to AppDaemon's management code to ensure
that initialization or cleanup is completed before the App is loaded or
reloaded. This means that any significant delays in the ``terminate()``
code could have the effect of hanging AppDaemon for the duration of that
code - this should be avoided.

To wrap up this section, here is a complete functioning App (with
comments):

.. code:: python

    import appdaemon.appapi as appapi
    import datetime

     Declare Class
    class NightLight(appapi.AppDaemon):
      #initialize() function which will be called at startup and reload
      def initialize(self):
        # Create a time object for 7pm
        time = datetime.time(19, 00, 0)
        # Schedule a daily callback that will call run_daily() at 7pm every night
        self.run_daily(self.run_daily_callback, time)

       # Our callback function will be called by the scheduler every day at 7pm
      def run_daily_callback(self, kwargs):
        # Call to Home Assistant to turn the porch light on
        self.turn_on("light.porch")

To summarize - an App's lifecycle consists of being initialized, which
allows it to set one or more states and/or schedule callbacks. When
those callbacks are activated, the App will typically use one of the
Service Calling calls to effect some change to the devices of the system
and then wait for the next relevant state change. Finally, if the App is
reloaded, there is a call to its ``terminate()`` function if it exists.
That's all there is to it!

About the API
-------------

The implementation of the API is located in the AppDaemon class that
Apps are derived from. The code for the functions is therefore available
to the App simply by invoking the name of the function from the object
namespace using the ``self`` keyword, as in the above examples.
``self.turn_on()`` for example is just a method defined in the parent
class and made available to the child. This design decision was made to
simplify some of the implementation and hide passing of unnecessary
variables during the API invocation.

Configuration of Apps
---------------------

Apps are configured by specifying new sections in the app configuration
file - ``apps.yaml``. The name of the section is the name the App is referred to
within the system in log files etc. and must be unique.

To configure a new App you need a minimum of two directives:

-  ``module`` - the name of the module (without the ``.py``) that
   contains the class to be used for this App
-  ``class`` - the name of the class as defined within the module for
   the APPs code

Although the section/App name must be unique, it is possible to re-use a
class as many times as you want, and conversely to put as many classes
in a module as you want. A sample definition for a new App might look as
follows:

.. code:: yaml

    newapp:
      module: new
      class: NewApp

When AppDaemon sees the following configuration it will expect to find a
class called ``NewApp`` defined in a module called ``new.py`` in the
apps subdirectory. Apps can be placed at the root of the Apps directory
or within a subdirectory, an arbitrary depth down - wherever the App is,
as long as it is in some subdirectory of the Apps dir, or in the Apps
dir itself, AppDaemon will find it. There is no need to include
information about the path, just the name of the file itself (without
the ``.py``) is sufficient. If names in the subdirectories overlap,
AppDir will pick one of them but the exact choice it will make is
undefined.

When starting the system for the first time or when reloading an App or
Module, the system will log the fact in it's main log. It is often the
case that there is a problem with the class, maybe a syntax error or
some other problem. If that is the case, details will be output to the
error log allowing the user to remedy the problem and reload.

Steps to writing an App
-----------------------

1. Create the code in a new or shared module by deriving a class from
   AppDaemon, add required callbacks and code
2. Add the App to the app configuration file
3. There is no number 3

Reloading Modules and Classes
-----------------------------

Reloading of modules is automatic. When the system spots a change in a
module, it will automatically reload and recompile the module. It will
also figure out which Apps were using that Module and restart them,
causing their ``terminate()`` functions to be called if they exist, all
of their existing callbacks to be cleared, and their ``initialize()``
function to be called.

The same is true if changes are made to an App's configuration -
changing the class, or arguments (see later) will cause that app to be
reloaded in the same way. The system is also capable of detecting if a
new app has been added, or if one has been removed, and it will act
appropriately, starting the new app immediately and removing all
callbacks for the removed app.

The suggested order for creating a new App is to add the module code
first and work until it compiles cleanly, and only then add an entry in
the configuration file to actually run it. A good workflow is to
continuously monitor the error file (using ``tail -f`` on Linux for
instance) to ensure that errors are seen and can be remedied.

Passing Arguments to Apps
-------------------------

There wouldn't be much point in being able to run multiple versions of
an App if there wasn't some way to instruct them to do something
different. For this reason it is possible to pass any required arguments
to an App, which are then made available to the object at runtime. The
arguments themselves can be called anything (apart from ``module`` or
``class``) and are simply added into the section after the 2 mandatory
directives like so:

.. code:: yaml

    MyApp:
      module: myapp
      class: MyApp
      param1: spam
      param2: eggs

Within the Apps code, the 2 parameters (as well as the module and class)
are available as a dictionary called ``args``, and accessed as follows:

.. code:: python

    param1 = self.args["param1"]
    param2 = self.args["param2"]

A use case for this might be an App that detects motion and turns on a
light. If you have 3 places you want to run this, rather than hardcoding
this into 3 separate Apps, you need only code a single app and
instantiate it 3 times with different arguments. It might look something
like this:

.. code:: yaml

    downstairs_motion_light:
      module: motion_light
      class: MotionLight
      sensor: binary_sensor.downstairs_hall
      light: light.downstairs_hall
    upstairs_motion_light:
      module: motion_light
      class: MotionLight
      sensor: binary_sensor.upstairs_hall
      light: light.upstairs_hall
    garage_motion_light:
      module: motion_light
      class: MotionLight
      sensor: binary_sensor.garage
      light: light.garage

Apps can use arbitrarily complex structures within argumens, e.g.:

.. code:: yaml

    entities:
      - entity1
      - entity2
      - entity3

Which can be accessed as a list in python with:

.. code:: python

    for entity in self.args.entities:
      do some stuff

Also, this opens the door to really complex parameter structures if
required:

.. code:: python

    sensors:
      sensor1:
        type:thermometer
        warning_level: 30
        units: degrees
      sensor2:
        type:moisture
        warning_level: 100
        units: %

Module Dependencies
-------------------

It is possible for modules to be dependant upon other modules. Some
examples where this might be the case are:

-  A Global module that defines constants for use in other modules
-  A module that provides a service for other modules, e.g. a TTS module
-  A Module that provides part of an object hierarchy to other modules

In these cases, when changes are made to one of these modules, we also
want the modules that depend upon them to be reloaded. Furthermore, we
also want to guarantee that they are loaded in order so that the modules
dpended upon by other modules are loaded first.

AppDaemon fully supports this through the use of the dependency
directive in the App configuration. Using this directice, each App
identifies modules that it depends upon. Note that the dependency is at
the module level, not the App level, since a change to the module will
force a reload of all apps using it anyway. The dependency directive
will identify the module name of the App it cares about, and AppDaemon
will see to it that the dependency is loaded before the module depending
on it, and that the dependent module will be reloaded if it changes.

For example, an App ``Consumer``, uses another app ``Sound`` to play
sound files. ``Sound`` in turn uses ``Global`` to store some global
values. We can represent these dependencies as follows:

.. code:: yaml

    Global:
      module: global
      class: Global

    Sound
      module: sound
      class: Sound
      dependencies: global # Note - module name not App name

    Consumer:
      module: sound
      class: Sound
      dependencies: sound

It is also possible to have multiple dependencies, added as a comma
separate list (no spaces)

.. code:: yaml

    Consumer:
      module: sound
      class: Sound
      dependencies: sound,global

AppDaemon will write errors to the log if a dependency is missing and it
should also detect circular dependencies.

Callback Constraints
--------------------

Callback constraints are a feature of AppDaemon that removes the need
for repetition of some common coding checks. Many Apps will wish to
process their callbacks only when certain conditions are met, e.g.
someone is home, and it's after sunset. These kinds of conditions crop
up a lot, and use of callback constraints can significantly simplify the
logic required within callbacks.

Put simply, callback constraints are one or more conditions on callback
execution that can be applied to an individual App. An App's callbacks
will only be executed if all of the constraints are met. If a constraint
is absent it will not be checked for.

For example, the presence callback constraint can be added to an App by
adding a parameter to it's configuration like this:

.. code:: yaml

    some_app:
      module: some_module
      class: SomeClass
      constrain_presence: noone

Now, although the ``initialize()`` function will be called for
SomeClass, and it will have a chance to register as many callbacks as it
desires, none of the callbacks will execute, in this case, until
everyone has left. This could be useful for an interior motion detector
App for instance. There are several different types of constraints:

-  input\_boolean
-  input\_select
-  presence
-  time

An App can have as many or as few as are required. When more than one
constraint is present, they must all evaluate to true to allow the
callbacks to be called. Constraints becoming true are not an event in
their own right, but if they are all true at a point in time, the next
callback that would otherwise been blocked due to constraint failure
will now be called. Similarly, if one of the constraints becomes false,
the next callback that would otherwise have been called will be blocked.

They are described individually below.

input\_boolean
~~~~~~~~~~~~~~

By default, the input\_boolean constraint prevents callbacks unless the
specified input\_boolean is set to "on". This is useful to allow certain
Apps to be turned on and off from the user interface. For example:

.. code:: yaml

    some_app:
      module: some_module
      class: SomeClass
      constrain_input_boolean: input_boolean.enable_motion_detection

If you want to reverse the logic so the constraint is only called when
the input\_boolean is off, use the optional state parameter by appending
",off" to the argument, e.g.:

.. code:: yaml

    some_app:
      module: some_module
      class: SomeClass
      constrain_input_boolean: input_boolean.enable_motion_detection,off

input\_select
~~~~~~~~~~~~~

The input\_select constraint prevents callbacks unless the specified
input\_select is set to one or more of the nominated (comma separated)
values. This is useful to allow certain Apps to be turned on and off
according to some flag, e.g. a house mode flag.

.. code:: yaml

     Single value
    constrain_input_select: input_select.house_mode,Day
     or multiple values
    constrain_input_select: input_select.house_mode,Day,Evening,Night

presence
~~~~~~~~

The presence constraint will constrain based on presence of device
trackers. It takes 3 possible values: - ``noone`` - only allow callback
execution when no one is home - ``anyone`` - only allow callback
execution when one or more person is home - ``everyone`` - only allow
callback execution when everyone is home

.. code:: yaml

    constrain_presence: anyone
     or
    constrain_presence: someone
     or
    constrain_presence: noone

time
~~~~

The time constraint consists of 2 variables, ``constrain_start_time``
and ``constrain_end_time``. Callbacks will only be executed if the
current time is between the start and end times. - If both are absent no
time constraint will exist - If only start is present, end will default
to 1 second before midnight - If only end is present, start will default
to midnight

The times are specified in a string format with one of the following
formats: - HH:MM:SS - the time in Hours Minutes and Seconds, 24 hour
format. - ``sunrise``\ \|\ ``sunset`` [+\|- HH:MM:SS]- time of the next
sunrise or sunset with an optional positive or negative offset in Hours
Minutes and seconds

The time based constraint system correctly interprets start and end
times that span midnight.

.. code:: yaml

     Run between 8am and 10pm
    constrain_start_time: 08:00:00
    constrain_end_time: 22:00:00
     Run between sunrise and sunset
    constrain_start_time: sunrise
    constrain_end_time: sunset
     Run between 45 minutes before sunset and 45 minutes after sunrise the next day
    constrain_start_time: sunset - 00:45:00
    constrain_end_time: sunrise + 00:45:00

days
~~~~

The day constraint consists of as list of days for which the callbacks
will fire, e.g.

.. code:: yaml

    constrain_days: mon,tue,wed

Callback constraints can also be applied to individual callbacks within
Apps, see later for more details.

A Note on Threading
-------------------

AppDaemon is multithreaded. This means that any time code within an App
is executed, it is executed by one of many threads. This is generally
not a particularly important consideration for this application; in
general, the execution time of callbacks is expected to be far quicker
than the frequency of events causing them. However, it should be noted
for completeness, that it is certainly possible for different pieces of
code within the App to be executed concurrently, so some care may be
necessary if different callback for instance inspect and change shared
variables. This is a fairly standard caveat with concurrent programming,
and if you know enough to want to do this, then you should know enough
to put appropriate safeguards in place. For the average user however
this shouldn't be an issue. If there are sufficient use cases to warrant
it, I will consider adding locking to the function invocations to make
the entire infrastructure threadsafe, but I am not convinced that it is
necessary.

An additional caveat of a threaded worker pool environment is that it is
the expectation that none of the callbacks tie threads up for a
significant amount of time. To do so would eventually lead to thread
exhaustion, which would make the system run behind events. No events
would be lost as they would be queued, but callbacks would be delayed
which is a bad thing.

Given the above, NEVER use Python's ``time.sleep()`` if you want to
perform an operation some time in the future, as this will tie up a
thread for the period of the sleep. Instead use the scheduler's
``run_in()`` function which will allow you to delay without blocking any
threads.

State Operations
----------------

A note on Home Assistant State
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

State within Home Assistant is stored as a collection of dictionaries,
one for each entity. Each entity's dictionary will have some common
fields and a number of entity type specific fields The state for an
entity will always have the attributes:

-  ``last_updated``
-  ``last_changed``
-  ``state``

Any other attributes such as brightness for a lamp will only be present
if the entity supports them, and will be stored in a sub-dictionary
called ``attributes``. When specifying these optional attributes in the
``get_state()`` call, no special distinction is required between the
main attributes and the optional ones - ``get_state()`` will figure it
out for you.

Also bear in mind that some attributes such as brightness for a light,
will not be present when the light is off.

In most cases, the attribute ``state`` has the most important value in
it, e.g. for a light or switch this will be ``on`` or ``off``, for a
sensor it will be the value of that sensor. Many of the AppDaemon API
calls and callbacks will implicitly return the value of state unless
told to do otherwise.

Although the use of ``get_state()`` (below) is still supported, as of
AppDaemon 2.0.9 it is easier to access HASS state directly as an
attribute of the App itself, under the ``entities`` attribute.

For instance, to access the state of a binary sensor, you could use:

.. code:: python

    sensor_state = self.entities.binary_sensor.downstairs_sensor.state

Similarly, accessing any of the entity attributes is also possible:

.. code:: python

    name = self.entities.binary_sensor.downstairs_sensor.attributes.friendly_name

About Callbacks
~~~~~~~~~~~~~~~

A large proportion of home automation revolves around waiting for
something to happen and then reacting to it; a light level drops, the
sun rises, a door opens etc. Home Assistant keeps track of every state
change that occurs within the system and streams that information to
AppDaemon almost immediately.

An individual App however usually doesn't care about the majority of
state changes going on in the system; Apps usually care about something
very specific, like a specific sensor or light. Apps need a way to be
notified when a state change happens that they care about, and be able
to ignore the rest. They do this through registering callbacks. A
callback allows the App to describe exactly what it is interested in,
and tells AppDaemon to make a call into its code in a specific place to
be able to react to it - this is a very familiar concept to anyone
familiar with event-based programming.

There are 3 types of callbacks within AppDaemon:

-  State Callbacks - react to a change in state
-  Scheduler Callbacks - react to a specific time or interval
-  Event Callbacks - react to specific Home Assistant and Appdaemon
   events.

All callbacks allow the user to specify additional parameters to be
handed to the callback via the standard Python ``**kwargs`` mechanism
for greater flexibility, these additional arguments are handed to the
callback as a standard Python dictionary,

About Registering Callbacks
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each of the various types of callback have their own function or
functions for registering the callback:

-  ``listen_state()`` for state callbacks
-  Various scheduler calls such as ``run_once()`` for scheduler
   callbacks
-  ``listen_event()`` for event callbacks.

Each type of callback shares a number of common mechanisms that increase
flexibility.

Callback Level Constraints
^^^^^^^^^^^^^^^^^^^^^^^^^^

When registering a callback, you can add constraints identical to the
Application level constraints described earlier. The difference is that
a constraint applied to an individual callback only affects that
callback and no other. The constraints are applied by adding Python
keyword-value style arguments after the positional arguments. The
parameters themselves are named identically to the previously described
constraints and have identical functionality. For instance, adding:

``constrain_presence="everyone"``

to a callback registration will ensure that the callback is only run if
the callback conditions are met and in addition everyone is present
although any other callbacks might run whenever their event fires if
they have no constraints.

For example:

``self.listen_state(self.motion, "binary_sensor.drive", constrain_presence="everyone")``

User Arguments
^^^^^^^^^^^^^^

Any callback has the ability to allow the App creator to pass through
arbitrary keyword arguments that will be presented to the callback when
it is run. The arguments are added after the positional parameters just
like the constraints. The only restriction is that they cannot be the
same as any constraint name for obvious reasons. For example, to pass
the parameter ``arg1 = "home assistant"`` through to a callback you
would register a callback as follows:

``self.listen_state(self.motion, "binary_sensor.drive", arg1="home assistant")``

Then in the callback it is presented back to the function as a
dictionary and you could use it as follows:

.. code:: python

    def motion(self, entity, attribute, old, new, kwargs):
        self.log("Arg1 is {}".format(kwargs["arg1"]))

State Callbacks
~~~~~~~~~~~~~~~

AppDaemons's state callbacks allow an App to listen to a wide variety of
events, from every state change in the system, right down to a change of
a single attribute of a particular entity. Setting up a callback is done
using a single API call ``listen_state()`` which takes various arguments
to allow it to do all of the above. Apps can register as many or as few
callbacks as they want.

About State Callback Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When calling back into the App, the App must provide a class function
with a known signature for AppDaemon to call. The callback will provide
various information to the function to enable the function to respond
appropriately. For state callbacks, a class defined callback function
should look like this:

.. code:: python

      def my_callback(self, entity, attribute, old, new, kwargs):
        <do some useful work here>

You can call the function whatever you like - you will reference it in
the ``listen_state()`` call, and you can create as many callback
functions as you need.

The parameters have the following meanings:

self
^^^^

A standard Python object reference.

entity
^^^^^^

Name of the entity the callback was requested for or ``None``.

attribute
^^^^^^^^^

Name of the attribute the callback was requested for or ``None``.

old
^^^

The value of the state before the state change.

new
^^^

The value of the state after the state change.

``old`` and ``new`` will have varying types depending on the type of
callback.

\*\*kwargs
^^^^^^^^^^

A dictionary containing any constraints and/or additional user specific
keyword arguments supplied to the ``listen_state()`` call.

Publishing State from an App
----------------------------

Using AppDaemon it is possible to explicitly publish state from an App.
The published state can contain whatever you want, and is treated
exactly like any other HA state, e.g. to the rest of AppDaemon, and the
dashboard it looks like an entity. This means that you can listen for
state changes in other apps and also publish arbitary state to the
dashboard via use of specific entity IDs. To publish state, you will use
``set_app_state()``. State can be retrieved and listened for with the
usual AppDaemon calls.

The Scheduler
-------------

AppDaemon contains a powerful scheduler that is able to run with 1
second resolution to fire off specific events at set times, or after set
delays, or even relative to sunrise and sunset. In general, events
should be fired less than a second after specified but under certain
circumstances there may be short additional delays.

About Schedule Callbacks
~~~~~~~~~~~~~~~~~~~~~~~~

As with State Change callbacks, Scheduler Callbacks expect to call into
functions with a known and specific signature and a class defined
Scheduler callback function should look like this:

.. code:: python

      def my_callback(self, kwargs):
        <do some useful work here>

You can call the function whatever you like; you will reference it in
the Scheduler call, and you can create as many callback functions as you
need.

The parameters have the following meanings:

self
^^^^

A standard Python object reference

\*\*kwargs
^^^^^^^^^^

A dictionary containing Zero or more keyword arguments to be supplied to
the callback.

Creation of Scheduler Callbacks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Scheduler callbacks are created through use of a number of convenience
functions which can be used to suit the situation.

Scheduler Randomization
~~~~~~~~~~~~~~~~~~~~~~~

All of the scheduler calls above support 2 additional optional
arguments, ``random_start`` and ``random_end``. Using these arguments it
is possible to randomize the firing of callbacks to the degree desired
by setting the appropriate number of seconds with the parameters.

-  ``random_start`` - start of range of the random time
-  ``random_end`` - end of range of the random time

``random_start`` must always be numerically lower than ``random_end``,
they can be negative to denote a random offset before and event, or
positive to denote a random offset after an event. The event would be a
an absolute or relative time or sunrise/sunset depending on whcih
scheduler call you use and these values affect the base time by the
spcified amount. If not specified, they will default to ``0``.

For example:

.. code:: python

     Run a callback in 2 minutes minus a random number of seconds between 0 and 60, e.g. run between 60 and 120 seconds from now
    self.handle = self.run_in(callback, 120, random_start = -60, **kwargs)
     Run a callback in 2 minutes plus a random number of seconds between 0 and 60, e.g. run between 120 and 180 seconds from now
    self.handle = self.run_in(callback, 120, random_end = 60, **kwargs)
     Run a callback in 2 minutes plus or minus a random number of seconds between 0 and 60, e.g. run between 60 and 180 seconds from now
    self.handle = self.run_in(callback, 120, random_start = -60, random_end = 60, **kwargs)

Sunrise and Sunset
------------------

AppDaemon has a number of features to allow easy tracking of sunrise and
sunset as well as a couple of scheduler functions. Note that the
scheduler functions also support the randomization parameters described
above, but they cannot be used in conjunction with the ``offset``
parameter\`.

Calling Services
----------------

About Services
~~~~~~~~~~~~~~

Services within Home Assistant are how changes are made to the system
and its devices. Services can be used to turn lights on and off, set
thermostats and a whole number of other things. Home Assistant supplies
a single interface to all these disparate services that take arbitrary
parameters. AppDaemon provides the ``call_service()`` function to call
into Home Assistant and run a service. In addition, it also provides
convenience functions for some of the more common services making
calling them a little easier.

Events
------

About Events
~~~~~~~~~~~~

Events are a fundamental part of how Home Assistant works under the
covers. HA has an event bus that all components can read and write to,
enabling components to inform other components when important events
take place. We have already seen how state changes can be propagated to
AppDaemon - a state change however is merely an example of an event
within Home Assistant. There are several other event types, among them
are:

-  ``homeassistant_start``
-  ``homeassistant_stop``
-  ``state_changed``
-  ``service_registered``
-  ``call_service``
-  ``service_executed``
-  ``platform_discovered``
-  ``component_loaded``

Using AppDaemon, it is possible to subscribe to specific events as well
as fire off events.

In addition to the Home Assistant supplied events, AppDaemon adds 2 more
events. These are internal to AppDaemon and are not visible on the Home
Assistant bus:

-  ``appd_started`` - fired once when AppDaemon is first started and
   after Apps are initialized
-  ``ha_started`` - fired every time AppDaemon detects a Home Assistant
   restart
-  ``ha_disconnectd`` - fired once every time AppDaemon loses its
   connection with HASS

About Event Callbacks
~~~~~~~~~~~~~~~~~~~~~

As with State Change and Scheduler callbacks, Event Callbacks expect to
call into functions with a known and specific signature and a class
defined Scheduler callback function should look like this:

.. code:: python

      def my_callback(self, event_name, data, kwargs):
        <do some useful work here>

You can call the function whatever you like - you will reference it in
the Scheduler call, and you can create as many callback functions as you
need.

The parameters have the following meanings:

self
^^^^

A standard Python object reference.

event\_name
^^^^^^^^^^^

Name of the event that was called, e.g. ``call_service``.

data
^^^^

Any data that the system supplied with the event as a dict.

kwargs
^^^^^^

A dictionary containing Zero or more user keyword arguments to be
supplied to the callback.

listen\_event()
~~~~~~~~~~~~~~~

Listen event sets up a callback for a specific event, or any event.

Synopsis
^^^^^^^^

.. code:: python

    handle = listen_event(function, event = None, **kwargs):

Returns
^^^^^^^

A handle that can be used to cancel the callback.

Parameters
^^^^^^^^^^

function
''''''''

The function to be called when the event is fired.

event
'''''

Name of the event to subscribe to. Can be a standard Home Assistant
event such as ``service_registered`` or an arbitrary custom event such
as ``"MODE_CHANGE"``. If no event is specified, ``listen_event()`` will
subscribe to all events.

\*\*kwargs (optional)
'''''''''''''''''''''

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

Use of Events for Signalling between Home Assistant and AppDaemon
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Home Assistant allows for the creation of custom events and existing
components can send and receive them. This provides a useful mechanism
for signaling back and forth between Home Assistant and AppDaemon. For
instance, if you would like to create a UI Element to fire off some code
in Home Assistant, all that is necessary is to create a script to fire a
custom event, then subscribe to that event in AppDaemon. The script
would look something like this:

.. code:: yaml

    alias: Day
    sequence:
    - event: MODE_CHANGE
      event_data:
        mode: Day

The custom event ``MODE_CHANGE`` would be subscribed to with:

.. code:: python

    self.listen_event(self.mode_event, "MODE_CHANGE")

Home Assistant can send these events in a variety of other places -
within automations, and also directly from Alexa intents. Home Assistant
can also listen for custom events with it's automation component. This
can be used to signal from AppDaemon code back to home assistant. Here
is a sample automation:

.. code:: yaml

    automation:
      trigger:
        platform: event
        event_type: MODE_CHANGE
        ...
        ...

This can be triggered with a call to AppDaemon's fire\_event() as
follows:

.. code:: python

    self.fire_event("MODE_CHANGE", mode = "Day")

Use of Events for Interacting with HADashboard
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HADashboard listens for certain events. An event type of "hadashboard"
will trigger certain actions such as page navigation. For more
information see the ` Dashboard configuration pages <DASHBOARD.html>`__

AppDaemon provides convenience funtions to assist with this.

Presence
--------

Presence in Home Assistant is tracked using Device Trackers. The state
of all device trackers can be found using the ``get_state()`` call,
however AppDaemon provides several convenience functions to make this
easier.

Writing to Logfiles
~~~~~~~~~~~~~~~~~~~

AppDaemon uses 2 separate logs - the general log and the error log. An
AppDaemon App can write to either of these using the supplied
convenience methods ``log()`` and ``error()``, which are provided as
part of parent ``AppDaemon`` class, and the call will automatically
pre-pend the name of the App making the call. The ``-D`` option of
AppDaemon can be used to specify what level of logging is required and
the logger objects will work as expected.

ApDaemon loggin also allows you to use placeholders for the module,
fucntion and line number. If you include the following in the test of
your message:

::

    __function__
    __module__
    __line__

They will automatically be expanded to the appropriate values in the log
message.

Getting Information in Apps and Sharing information between Apps
----------------------------------------------------------------

Sharing information between different Apps is very simple if required.
Each app gets access to a global dictionary stored in a class attribute
called ``self.global_vars``. Any App can add or read any key as
required. This operation is not however threadsafe so some care is
needed.

In addition, Apps have access to the entire configuration if required,
meaning they can access AppDaemon configuration items as well as
parameters from other Apps. To use this, there is a class attribute
called ``self.config``. It contains a ``ConfigParser`` object, which is
similar in operation to a ``Dictionary``. To access any apps parameters,
simply reference the ConfigParser object using the Apps name (form the
config file) as the first key, and the parameter required as the second,
for instance:

.. code:: python

    other_apps_arg = self.config["some_app"]["some_parameter"].

To get AppDaemon's config parameters, use the key "AppDaemon", e.g.:

.. code:: python

    app_timezone = self.config["AppDaemon"]["time_zone"]

AppDaemon also exposes configuration from Home Assistant such as the
Latitude and Longitude configured in HA. All of the information
available from the Home Assistant ``/api/config`` endpoint is available
in the ``self.ha_config`` dictionary. E.g.:

.. code:: python

    self.log("My current position is {}(Lat), {}(Long)".format(self.ha_config["latitude"], self.ha_config["longitude"]))

And finally, it is also possible to use the AppDaemon as a global area
for sharing parameters across Apps. Simply add the required parameters
to the AppDaemon section of your config:

.. code:: yaml

    AppDaemon:
    ha_url: <some url>
    ha_key: <some key>
    ...
    global_var: hello world

Then access it as follows:

.. code:: python

    my_global_var = conf.config["AppDaemon"]["global_var"]

Development Workflow
--------------------

Developing Apps is intended to be fairly simple but is an exercise in
programming like any other kind of Python programming. As such, it is
expected that apps will contain syntax errors and will generate
exceptions during the development process. AppDaemon makes it very easy
to iterate through the development process as it will automatically
reload code that has changed and also will reload code if any of the
parameters in the configuration file change as well.

The recommended workflow for development is as follows:

-  Open a window and tail the ``appdaemon.log`` file
-  Open a second window and tail the ``error.log`` file
-  Open a third window or the editor of your choice for editing the App

With this setup, you will see that every time you write the file,
AppDaemon will log the fact and let you know it has reloaded the App in
the ``appdaemon.log`` file.

If there is an error in the compilation or a runtime error, this will be
directed to the ``error.log`` file to enable you to see the error and
correct it. When an error occurs, there will also be a warning message
in ``appdaemon.log`` to tell you to check the error log.

Time Travel
-----------

OK, time travel sadly isn't really possible but it can be very useful
when testing Apps. For instance, imagine you have an App that turns a
light on every day at sunset. It might be nice to test it without
waiting for Sunset - and with AppDaemon's "Time Travel" features you
can.

Choosing a Start Time
~~~~~~~~~~~~~~~~~~~~~

Internally, AppDaemon keeps track of it's own time relative to when it
was started. This make is possible to start AppDaemon with a different
start time and date to the current time. For instance to test that
sunset App, start AppDaemon at a time just before sunset and see if it
works as expected. To do this, simply use the "-s" argument on
AppDaemon's command line. e,g,:

.. code:: bash

    $ appdaemon -s "2016-06-06 19:16:00"
    2016-09-06 17:16:00 INFO AppDaemon Version 1.3.2 starting
    2016-09-06 17:16:00 INFO Got initial state
    2016-09-06 17:16:00 INFO Loading Module: /export/hass/appdaemon_test/conf/test_apps/sunset.py
    ...

Note the timestamps in the log - AppDaemon believes it is now just
before sunset and will process any callbacks appropriately.

Speeding things up
~~~~~~~~~~~~~~~~~~

Some Apps need to run for periods of a day or two for you to test all
aspects. This can be time consuming, but Time Travel can also help here
in two ways. The first is by speeding up time. To do this, simply use
the ``-t`` option on the command line. This specifies the amount of time
a second lasts while time travelling. The default of course is 1 second,
but if you change it to ``0.1`` for instance, AppDaemon will work 10x
faster. If you set it to ``0``, AppDaemon will work as fast as possible
and, depending in your hardware, may be able to get through an entire
day in a matter of minutes. Bear in mind however, due to the threaded
nature of AppDaemon, when you are running with ``-t 0`` you may see
actual events firing a little later than expected as the rest of the
system tries to keep up with the timer. To set the tick time, start
AppDaemon as follows:

.. code:: bash

    $ appdaemon -t 0.1

AppDaemon also has an interval flag - think of this as a second
multiplier. If the flag is set to 3600 for instance, each tick of the
scheduler will jump the time forward by an hour. This is good for
covering vast amounts of time quickly but event firing accuracy will
suffer as a result. For example:

.. code:: bash

    $ appdaemon -i 3600

Automatically stopping
~~~~~~~~~~~~~~~~~~~~~~

AppDaemon can be set to terminate automatically at a specific time. This
can be useful if you want to repeatedly rerun a test, for example to
test that random values are behaving as expected. Simply specify the end
time with the ``-e`` flag as follows:

.. code:: bash

    $ appdaemon -e "2016-06-06 10:10:00"
    2016-09-06 17:16:00 INFO AppDaemon Version 1.3.2 starting
    2016-09-06 17:16:00 INFO Got initial state
    2016-09-06 17:16:00 INFO Loading Module: /export/hass/appdaemon_test/conf/test_apps/sunset.py
    ..,

The ``-e`` flag is most useful when used in conjuntion with the ``-s``
flag and optionally the ``-t`` flag. For example, to run from just
before sunset, for an hour, as fast as possible:

.. code:: bash

    $ appdaemon -s "2016-06-06 19:16:00" -e "2016-06-06 20:16:00" -t 0

A Note On Times
~~~~~~~~~~~~~~~

Some Apps you write may depend on checking times of events relative to
the current time. If you are time travelling this will not work if you
use standard python library calls to get the current time and date etc.
For this reason, always use the AppDamon supplied ``time()``, ``date()``
and ``datetime()`` calls, documented earlier. These calls will consult
with AppDaemon's internal time rather than the actual time and give you
the correct values.

Other Functions
~~~~~~~~~~~~~~~

AppDaemon allows some introspection on its stored schedule and callbacks
which may be useful for some applications. The functions:

-  get\_scheduler\_entries()
-  get\_callback\_entries()

Return the internal data structures, but do not allow them to be
modified directly. Their format may change.

About HASS Disconections
~~~~~~~~~~~~~~~~~~~~~~~~

When AppDaemon is unable to connect initially with Home Assistant, it
will hold all Apps in statsis until it initially connects, nothing else
will happen and no initialization routines will be called. If AppDaemon
has been running connected to Home Assitant for a while and the
connection is unexpectedly lost, the following will occur:

-  When HASS first goes down or becomes disconnected, an event called
   ``ha_disconnected`` will fire
-  While disconnected from HASS, Apps will continue to run
-  Schedules will continue to be honored
-  Any operation reading locally cached state will succeed
-  Any operation requiring a call to HASS will log a warning and return
   without attempting to contact hass
-  Changes to Apps will not force a reload until HASS is reconnected

When a connection to HASS is reestablished, all Apps will be restarted
and their ``initialize()`` routines will be called.

RESTFul API Support
-------------------

AppDaemon supports a simple RESTFul API to enable arbitary HTTP
connections to pass data to Apps and trigger actions. API Calls must use
a content type of ``application/json``, and the response will be JSON
encoded. The RESTFul API is disabled by default, but is enabled by
adding an ``ad_port`` directive to the AppDaemon section of the
configuration file. The API can run http or https if desired, separately
from the dashboard.

To call into a specific App, construct a URL, use the regular
HADashboard URL, and append ``/api/appdaemon``, then add the name of the
endpoint as registered by the app on the end, for example:

::

    http://192.168.1.20:5050/api/appdaemon/hello_endpoint

This URL will call into an App that registered an endpoint named ``hello_endpoint``.

Within the app, a call must be made to ``register_endpoint()`` to tell AppDaemon that
the app is expecting calls on that endpoint. When registering an endpoint, the App
supplies a function to be called when a request comes in to that endpoint and an optional
name for the endpoint. If not specified, the name will default to the name of the App
as specified in the configuration file.

Apps can have as many endpoints as required, however the names must be unique across
all of the Apps in an AppDaemon instance.

It is also possible to remove endpoints with the ``unregister_endpoint()`` call, making the
endpoints truly dynamic and under the control of the App.

Here is an example of an App using the API:

.. code:: python

    import appdaemon.appapi as appapi

    class API(appapi.AppDaemon):

        def initialize(self):
            self.register_endpoint(my_callback, test_endpoint)

        def my_callback(self, data):

            self.log(data)

            response = {"message": "Hello World"}

            return response, 200

The response must be a python structure that can be mapped to JSON, or
can be blank, in which case specify ``""`` for the response. You should
also return an HTML status code, that will be reported back to the
caller, ``200`` should be used for an OK response.

As well as any user specified code, the API can return the following
codes:

-  400 - JSON Decode Error
-  401 - Unauthorized
-  404 - App not found

Below is an example of using curl to call into the App shown above:

.. code:: bash

    hass@Pegasus:~$ curl -i -X POST -H "Content-Type: application/json" http://192.168.1.20:5050/api/appdaemon/test_endpoint -d '{"type": "Hello World Test"}'
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=utf-8
    Content-Length: 26
    Date: Sun, 06 Aug 2017 16:38:14 GMT
    Server: Python/3.5 aiohttp/2.2.3

    {"message": "Hello World"}hass@Pegasus:~$

API Security
------------

If you have added a key to the AppDaemon config, AppDaemon will expect
to find a header called "x-ad-access" in the request with a value equal
to the configured key. A security key is added for the API with the
``api_key`` directive described in the `Installation
Documentation <INSTALL.html>`__

If these conditions are not met, the call will fail with a return code
of ``401 Not Authorized``. Here is a succesful curl example:

.. code:: bash

    hass@Pegasus:~$ curl -i -X POST -H "x-ad-access: fred" -H "Content-Type: application/json" http://192.168.1.20:5050/api/appdaemon/api -d '{"type": "Hello World
     Test"}'
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=utf-8
    Content-Length: 26
    Date: Sun, 06 Aug 2017 17:30:50 GMT
    Server: Python/3.5 aiohttp/2.2.3

    {"message": "Hello World"}hass@Pegasus:~$

And an example of a missing key:

.. code:: bash

    hass@Pegasus:~$ curl -i -X POST -H "Content-Type: application/json" http://192.168.1.20:5050/api/appdaemon/api Test"}'ype": "Hello World
    HTTP/1.1 401 Unauthorized
    Content-Length: 112
    Content-Type: text/plain; charset=utf-8
    Date: Sun, 06 Aug 2017 17:30:43 GMT
    Server: Python/3.5 aiohttp/2.2.3

    <html><head><title>401 Unauthorized</title></head><body><h1>401 Unauthorized</h1>Error in API Call</body></html>hass@Pegasus:~$

Alexa Support
-------------

AppDaemon is able to use the API support to accept calls from Alexa.
Amazon Alexa calls can be directed to AppDaemon and arrive as JSON
encoded requests. AppDaemon provides several helper functions to assist
in understanding the request and responding appropriately. Since Alexa
only allows one URL per skill, the mapping will be 1:1 between skills
and Apps. When constructing the URL in the Alexa Intent, make sure it
points to the correct endpoint for the App you are using for Alexa.

In addition, if you are using API security keys (recommended) you will
need to append it to the end of the url as follows:

::

    http://<some.host.com>/api/appdaemon/alexa?api_password=<password>

For more information about configuring Alexa Intents, see the `Home
Assistant Alexa
Documentation <https://home-assistant.io/components/alexa/>`__

When configuring Alexa support for AppDaemon some care is needed. If as
most people are, you are using SSL to access Home Assistant, there is
contention for use of the SSL port (443) since Alexa does not allow you
to change this. This means that if you want to use AppDaemon with SSL,
you will not be able to use Home Assistant remotely over SSL. The way
around this is to use NGINX to remap the specific AppDamon API URL to a
different port, by adding something like this to the config:

::

            location /api/appdaemon/ {
            allow all;
            proxy_pass http://localhost:5000;
            proxy_set_header Host $host;
            proxy_redirect http:// http://;
          }

Here we see the default port being remapped to port 5000 which is where
AppDamon is listening in my setup.

Since each individual Skill has it's own URL it is possible to have
different skills for Home Assitant and AppDaemon.

Putting it together in an App
-----------------------------

The Alexa App is basically just a standard API App that uses Alexa
helper functions to understand the incoming request and format a
response to be sent back to Amazon, to describe the spoken resonse and
card for Alexa.

Here is a sample Alexa App that can be extended for whatever intents you
want to configure.

.. code:: python

    import appdaemon.appapi as appapi
    import random
    import globals

    class Alexa(appapi.AppDaemon):

        def initialize(self):
            pass

        def api_call(self, data):
            intent = self.get_alexa_intent(data)

            if intent is None:
                self.log("Alexa error encountered: {}".format(self.get_alexa_error(data)))
                return "", 201

            intents = {
                "StatusIntent": self.StatusIntent,
                "LocateIntent": self.LocateIntent,
            }

            if intent in intents:
                speech, card, title = intents[intent](data)
                response = self.format_alexa_response(speech = speech, card = card, title = title)
                self.log("Recieved Alexa request: {}, answering: {}".format(intent, speech))
            else:
                response = self.format_alexa_response(speech = "I'm sorry, the {} does not exist within AppDaemon".format(intent))

            return response, 200

        def StatusIntent(self, data):
            response = self.HouseStatus()
            return response, response, "House Status"

        def LocateIntent(self, data):
            user = self.get_alexa_slot_value(data, "User")

            if user is not None:
                if user.lower() == "jack":
                    response = self.Jack()
                elif user.lower() == "andrew":
                    response = self.Andrew()
                elif user.lower() == "wendy":
                    response = self.Wendy()
                elif user.lower() == "brett":
                    response = "I have no idea where Brett is, he never tells me anything"
                else:
                    response = "I'm sorry, I don't know who {} is".format(user)
            else:
                response = "I'm sorry, I don't know who that is"

            return response, response, "Where is {}?".format(user)

        def HouseStatus(self):

            status = "The downstairs temperature is {} degrees farenheit,".format(self.entities.sensor.downstairs_thermostat_temperature.state)
            status += "The upstairs temperature is {} degrees farenheit,".format(self.entities.sensor.upstairs_thermostat_temperature.state)
            status += "The outside temperature is {} degrees farenheit,".format(self.entities.sensor.side_temp_corrected.state)
            status += self.Wendy()
            status += self.Andrew()
            status += self.Jack()

            return status

        def Wendy(self):
            location = self.get_state(globals.wendy_tracker)
            if location == "home":
                status = "Wendy is home,"
            else:
                status = "Wendy is away,"

            return status

        def Andrew(self):
            location = self.get_state(globals.andrew_tracker)
            if location == "home":
                status = "Andrew is home,"
            else:
                status = "Andrew is away,"

            return status

        def Jack(self):
            responses = [
                "Jack is asleep on his chair",
                "Jack just went out bowling with his kitty friends",
                "Jack is in the hall cupboard",
                "Jack is on the back of the den sofa",
                "Jack is on the bed",
                "Jack just stole a spot on daddy's chair",
                "Jack is in the kitchen looking out of the window",
                "Jack is looking out of the front door",
                "Jack is on the windowsill behind the bed",
                "Jack is out checking on his clown suit",
                "Jack is eating his treats",
                "Jack just went out for a walk in the neigbourhood",
                "Jack is by his bowl waiting for treats"
            ]

            return random.choice(responses)

Google API.AI
-------------

Similarly, Google's API.AI for Google home is supported - here is the Google version of the same App.To set up Api.ai with your google home refer to the apiai component in home-assistant. Once it is setup you can use the appdaemon API as the webhook.

import appdaemon.appapi as appapi
import random
import globals

class Apiai(appapi.AppDaemon):

    def initialize(self):
        pass

    def api_call(self, data):
        intent = self.get_apiai_intent(data)

        if intent is None:
            self.log("Apiai error encountered: Result is empty")
            return "", 201

        intents = {
            "StatusIntent": self.StatusIntent,
            "LocateIntent": self.LocateIntent,
        }

        if intent in intents:
            speech = intents[intent](data)
            response = self.format_apiai_response(speech)
            self.log("Recieved Apai request: {}, answering: {}".format(intent, speech))
        else:
            response = self.format_apaiai_response(speech = "I'm sorry, the {} does not exist within AppDaemon".format(intent))

        return response, 200

    def StatusIntent(self, data):
        response = self.HouseStatus()
        return response

    def LocateIntent(self, data):
        user = self.get_apiai_slot_value(data, "User")

        if user is not None:
            if user.lower() == "jack":
                response = self.Jack()
            elif user.lower() == "andrew":
                response = self.Andrew()
            elif user.lower() == "wendy":
                response = self.Wendy()
            elif user.lower() == "brett":
                response = "I have no idea where Brett is, he never tells me anything"
            else:
                response = "I'm sorry, I don't know who {} is".format(user)
        else:
            response = "I'm sorry, I don't know who that is"

        return response

    def HouseStatus(self):

        status = "The downstairs temperature is {} degrees farenheit,".format(self.entities.sensor.downstairs_thermostat_temperature.state)
        status += "The upstairs temperature is {} degrees farenheit,".format(self.entities.sensor.upstairs_thermostat_temperature.state)
        status += "The outside temperature is {} degrees farenheit,".format(self.entities.sensor.side_temp_corrected.state)
        status += self.Wendy()
        status += self.Andrew()
        status += self.Jack()

        return status

    def Wendy(self):
        location = self.get_state(globals.wendy_tracker)
        if location == "home":
            status = "Wendy is home,"
        else:
            status = "Wendy is away,"

        return status

    def Andrew(self):
        location = self.get_state(globals.andrew_tracker)
        if location == "home":
            status = "Andrew is home,"
        else:
            status = "Andrew is away,"

        return status

    def Jack(self):
        responses = [
            "Jack is asleep on his chair",
            "Jack just went out bowling with his kitty friends",
            "Jack is in the hall cupboard",
            "Jack is on the back of the den sofa",
            "Jack is on the bed",
            "Jack just stole a spot on daddy's chair",
            "Jack is in the kitchen looking out of the window",
            "Jack is looking out of the front door",
            "Jack is on the windowsill behind the bed",
            "Jack is out checking on his clown suit",
            "Jack is eating his treats",
            "Jack just went out for a walk in the neigbourhood",
            "Jack is by his bowl waiting for treats"
        ]

        return random.choice(responses)