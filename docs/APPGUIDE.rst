Writing AppDaemon Apps
=======================

AppDaemon (AD) is a loosely coupled, sandboxed, multi-threaded Python
execution environment for writing automation apps for `Home
Assistant <https://home-assistant.io/>`__, `MQTT <http://mqtt.org/>`__ event broker and other home automation software.

Examples
--------

Example apps that showcase most of these functions are available in the
AppDaemon `repository <https://github.com/home-assistant/appdaemon/tree/dev/conf/example_apps>`__

Anatomy of an App
-----------------

Actions in AppDaemon are performed by creating a piece of code
(essentially a Python Class) and then instantiating it as an Object one
or more times by configuring it as an App in the configuration file. The
App is given a chance to register itself for whatever events it wants to
subscribe to, and AppDaemon will then make calls back into the Object's
code when those events occur, allowing the App to respond to the event
with some kind of action.

The first step is to create a unique file within the apps directory (as
defined `here <INSTALL.html>`__). It should be noted that AD will ignore all files
saved within a hidden directory; essentially those with a "." in its path.
This file, is in fact, a Pythonmodule, and is expected to contain one or more classes derived from a
supplied *AppDaemon class* or a *custom plugin*. For instance, hass support can be used
by importing from the supplied ``hassapi`` module. The start of an App might look like this:

.. code:: python

    from appdaemon.plugins.hass import Hass


    class OutsideLights(Hass):
        def initialize(self):
            ...

For MQTT you would use the mqttapi module:

.. code:: python

    from appdaemon.plugins.mqtt import Mqtt


    class OutsideLights(Mqtt):
        def initialize(self):
            ...

When configured as an app in the config file (more on that later) the
lifecycle of the App begins. It will be instantiated as an object by
AppDaemon, and immediately, it will have a call made to its
``initialize()`` function - this function must appear as part of every
App:

.. code:: python

      def initialize(self):

The initialize function allows the App to register any callbacks it
might need for responding to state changes, and also any setup
activities. When the ``initialize()`` function returns, the App will be
dormant until any of its callbacks are activated.

There are several circumstances under which ``initialize()`` might be
called:

-  Initial start of AppDaemon
-  Following a change to the Class code
-  Following a change to the module parameters
-  Following initial configuration of an App
-  Following a change in the status of Daylight Saving Time
-  Following a restart of a plugin or underlying subsystem such as Home Assistant

In every case, the App is responsible for recreating any state it might
need as if it were the first time it was ever started. If
``initialize()`` is called, the App can safely assume that it is either
being loaded for the first time, or that all callbacks and timers have
been canceled. In either case, the App will need to recreate them.
Depending upon the application, it may be desirable for the App to
establish a state, such as whether or not a particular light is on,
within the ``initialize()`` function to ensure that everything is as
expected or to make immediate remedial action (e.g., turn off a light
that might have been left on by mistake when the App was restarted).

After the ``initialize()`` function is in place, the rest of the App
consists of functions that are called by the various callback
mechanisms, and any additional functions the user wants to add as part
of the program logic. Apps are able to subscribe to three main classes of
events:

-  Scheduled Events
-  State Change Events
-  Other Events

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

To wrap up this section, here is a complete functioning HASS App (with
comments):

.. code:: python

    from appdaemon.plugins.hass import Hass


    # Declare Class
    class NightLight(Hass):
        # function which will be called at startup and reload
        def initialize(self):
            # Schedule a daily callback that will call run_daily() at 7pm every night
            self.run_daily(self.run_daily_callback, "19:00:00")

        # Our callback function will be called by the scheduler every day at 7pm
        def run_daily_callback(self, **kwargs):
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

Apps are configured by specifying new sections in an app configuration
file. These configuration files can be written in either YAML or TOML, but must be the same type as the appdaemon
configuration file, and which variant is used depends on the ``--toml`` flag supplied to AppDaemon at startup.

The App configuration files exist under the apps directory and can be called anything as long as they end in ``.yaml``
or ``.toml``. You can have one single file for configuration of all apps, or break it down to have one configuration
file per App, or anything in between. Coupled with the fact that you can have any number of subdirectories for apps and
configuration files, this gives you the flexibility to structure your apps as you see fit.

It should also be noted that a "dot" ``.`` is not allowed in the app name.

The entry for an individual App within a configuration file is simply a dictionary entry naming the App, with subfields
to supply various parameters.The name of the section is the name the App is referred to within the system in log files
etc. and must be unique.

To configure a new App you need a minimum of two directives:

-  ``module`` - the name of the module (without the ``.py``) that
   contains the class to be used for this App
-  ``class`` - the name of the class as defined within the module for
   the App's code

Although the section/App name must be unique, it is possible to reuse a
class as many times as you want, and conversely to put as many classes
in a module as you want. A sample definition for a new App might look as
follows in YAML:

.. code:: yaml

    newapp:
      module: new
      class: NewApp

The TOML equivalent would look like this:

.. code:: toml

    [newapp]
    module = "new"
    class = "NewApp"

When AppDaemon sees the above configuration, it will expect to find a
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
Module, the system will log the fact in its main log. It is often the
case that there is a problem with the class, maybe a syntax error or
some other problem. If that is the case, details will be output to the
error log allowing the user to remedy the problem and reload.

In general, the user should always keep an eye on the error log - system
errors will be logged to the main log, any errors that are the responsibility
of the user, e.g. that come from app code will be found in the error log.


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
function to be called. It should be noted that if a terminate function exists,
and while executing it AD encounters an error, the app will not be auto reloaded.
The app will only be reloaded, when next the app's file has been changed, presumably
to fix the issue.

The same is true if changes are made to an App's configuration -
changing the class, or arguments (see later) will cause that App to be
reloaded in the same way. The system is also capable of detecting if a
new App has been added, or if one has been removed, and it will act
appropriately, starting the new App immediately and removing all
callbacks for the removed App.

The suggested order for creating a new App is to first add the app configuration file entry
then the module code and work until it compiles cleanly. A good workflow is to
continuously monitor the error file (using ``tail -f`` on Linux for
instance) to ensure that errors are seen and can be remedied.

Passing Arguments to Apps
-------------------------

There wouldn't be much point in being able to run multiple versions of
an App if there wasn't some way to instruct them to do something
different. For this reason, it is possible to pass any required arguments
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

Or in TOML:

.. code:: toml

    [MyApp]
    module = "myapp"
    class = "MyApp"
    param1 = "spam"
    param2 = "eggs"

Within the Apps code, the 2 parameters (as well as the module and class)
are available as a dictionary called ``args``, and accessed as follows:

.. code:: python

    param1 = self.args["param1"]
    param2 = self.args["param2"]

A use case for this might be an App that detects motion and turns on a
light. If you have 3 places you want to run this, rather than hardcoding
this into 3 separate Apps, you need only code a single App and
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

In TOML this would be:

.. code:: toml

    [downstairs_motion_light]
    module = "motion_light"
    class = "MotionLight"
    sensor = "binary_sensor.downstairs_hall"
    light = "light.downstairs_hall"

    [upstairs_motion_light]
    module = "motion_light"
    class = "MotionLight"
    sensor = "binary_sensor.upstairs_hall"
    light = "light.upstairs_hall"

    [garage_motion_light]
    module = "motion_light"
    class = "MotionLight"
    sensor = "binary_sensor.garage"
    light = "light.garage"

Apps can use arbitrarily complex structures within arguments, e.g.:

.. code:: yaml

    entities:
      - entity1
      - entity2
      - entity3

Which can be accessed as a list in python with:

.. code:: python

    for entity in self.args["entities"]:
        ... # do some stuff

Also, this opens the door to really complex parameter structures if
required:

.. code:: yaml

    sensors:
      sensor1:
        type: thermometer
        warning_level: 30
        units: degrees
      sensor2:
        type: moisture
        warning_level: 100
        units: "%"

It is also possible to get some constants like the app directory within apps. This can
be accessed using the attribute ``self.app_dir``.

Secrets
~~~~~~~

AppDaemon supports the ability to pass sensitive arguments to apps, via the use of secrets in the main or app config
file. This will allow separate storage of sensitive information such as passwords. For this to work, AppDaemon expects
to find a file called ``secrets.yaml`` in the configuration directory, or a named file introduced by the top level
``secrets:`` section. The file should be a simple list of all the secrets. The secrets can be referred to using a
``!secret`` tag in the ``apps.yaml`` file.

An example ``secrets.yaml`` might look like this:

.. code:: yaml

    application_api_key: ABCDEFG

The equivalent ``secrets.toml`` would be:

.. code:: toml

    application_api_key = "ABCDEFG"

The secrets can then be referred to in the ``apps.yaml`` file as follows:

.. code:: yaml

    appname:
      class: AppClass
      module: appmodule
      application_api_key: !secret application_api_key

Or in TOML:

.. code:: toml

    [appname]
    class = "AppClass"
    module = "appmodule"
    application_api_key = "!secret application_api_key"

In the App, the api_key can be accessed like every other argument the App can access.

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

If not wanting to use the secrets as above, AppDaemon also supports the ability to pass sensitive arguments to apps, via the use of environment variables in the main or app config file. This will allow separate storage of sensitive information such as passwords, within the os's environment variables. The variables can be referred to using a ``!env_var`` tag in the ``apps.yaml`` file.

An example using the os's time zone for AD:

.. code:: yaml

    appdaemon:
      time_zone: !env_var TZ
      latitude: !env_var LAT
      longitude: !env_var LONG

The variables can also be referred to in the ``apps.yaml`` file as follows:

.. code:: yaml

    appname:
      class: AppClass
      module: appmodule
      application_api_key: !env_var application_api_key

In the App, the api_key can be accessed like every other argument the App can access. This also works for TOML files:

.. code:: toml

    [appname]
    class = "AppClass"
    module = "appmodule"
    application_api_key = "!env_var application_api_key"


Include YAML Files
~~~~~~~~~~~~~~~~~~~~~

If wanting to access data stored in an external yaml file, it is possible to use the ``!include`` tag in either AD or the apps config file.
It should be noted that the full file path is required.

An example storing data in a yaml file can be seen below:

.. code:: yaml

    appdaemon:
      plugins: !include /home/ubuntu/dev/conf/plugins.yaml

The tag can also be referred to in the ``apps.yaml`` file as follows:

.. code:: yaml

    appname:
      class: AppClass
      module: appmodule
      app_users: !include /home/ubuntu/dev/conf/app_users.yaml

In the App, the app_users can be accessed like every other argument the App can access, this works for TOML files also.

App Dependencies
----------------

Apps can interact without any explicit references to each other by using because the calling app only needs
to know the service name ``<domain>/<service>`` to be able to use :py:meth:`~appdaemon.adapi.ADAPI.call_service`. It
doesn't need to reference or know anything about the app that provides the service. See
`service registration <#service-registration>`__ for more details on how to register services.

Sometimes in development it's useful to intentionally create a dependency so that apps get reloaded together as files
change. This can be done with the ``dependencies`` direction in the app configuration.

.. code-block:: yaml
  :emphasize-lines: 9

    # conf/apps/apps.yaml
    my_provider:
      module: provider
      class: Provider

    my_consumer:
      module: consumer
      class: Consumer
      dependencies:
        - my_provider

In this example, both apps would get reloaded if anything in `provider.py` changes, and the ``my_provider`` app is
guaranteed to be loaded after the ``my_provider`` app.

Imports
~~~~~~~

Apps in AppDaemon can import from other python files in the apps directory, and it's a common pattern to have a single
file containing global data that gets imported by multiple other apps.

This shows a complete example of defining some things in a single file `globals.py` that are used by both apps defined
in `app_a.py` and `app_b.py`.

.. code-block:: text
  :caption: Example App Directory Structure with Globals

    conf/apps
    ├── apps.yaml
    ├── globals.py
    └── my_apps
        ├── app_a.py
        └── app_b.py

.. code-block:: yaml
  :caption: Example App Configuration File

    # conf/apps/apps.yaml
    AppA:
      module: app_a
      class: AppA
      dependencies:
        - AppB # This is only set to demonstrate forcing it to load after AppB

    AppB:
      module: app_b
      class: AppB

.. code-block:: python
  :caption: Example Global File

    # conf/apps/globals.py
    from enum import Enum


    GLOBAL_VAR = "Hello, World!"


    class ModeSelect(Enum):
        MODE_A = 'mode_a'
        MODE_B = 'mode_b'
        MODE_C = 'mode_c'

    GLOBAL_MODE = ModeSelect.MODE_B

.. code-block:: python

    # conf/apps/app_a.py
    from appdaemon.adapi import ADAPI
    from globals import GLOBAL_MODE, GLOBAL_VAR


    class AppA(ADAPI):
        def initialize(self) -> None:
            self.log(GLOBAL_VAR)
            self.log(f'Global mode is set to: {GLOBAL_MODE.value}')

        def terminate(self) -> None: ...

.. code-block:: python

    # conf/apps/app_b.py
    from appdaemon.adapi import ADAPI
    from globals import GLOBAL_MODE, GLOBAL_VAR


    class AppB(ADAPI):
        def initialize(self) -> None:
            self.log(GLOBAL_VAR)
            self.log(f'Global mode is set to: {GLOBAL_MODE.value}')

        def terminate(self) -> None: ...

AppDaemon understands that both `app_a.py` and `app_b.py` depend on `globals.py` because of the import statement, so any
changes to `globals.py` will effectively trigger a reload of both ``AppA`` and ``AppB``. Just for the example, ``AppA``
was given a dependency on ``AppB``, which will cause it to always stopped before ``AppB`` and always started after
``AppB``.

For example, if ``GLOBAL_MODE`` is set to ``ModeSelect.MODE_C`` in `globals.py`, the log output would look like this:

.. code-block:: text

    INFO AppDaemon: Calling initialize() for AppB
    INFO AppB: Hello, World!
    INFO AppB: Global mode is set to: mode_b
    INFO AppDaemon: Calling initialize() for AppA
    INFO AppA: Hello, World!
    INFO AppA: Global mode is set to: mode_b
    ...
    INFO AppDaemon: Calling terminate() for 'AppA'
    INFO AppDaemon: Calling terminate() for 'AppB'
    INFO AppDaemon: Calling initialize() for AppB
    INFO AppB: AppB Initialized
    INFO AppB: Hello, World!
    INFO AppB: Global mode is set to: mode_c
    INFO AppDaemon: Calling initialize() for AppA
    INFO AppA: AppA Initialized
    INFO AppA: Hello, World!
    INFO AppA: Global mode is set to: mode_c

Globals
~~~~~~~

.. admonition:: Global Modules
  :class: warning

    Global modules are deprecated and will be removed in a future release. AppDaemon now automatically tracks and
    resolves dependencies by parsing files using the :py:mod:`ast <ast>` package from the standard library.

This is a legacy feature, but apps still have the ability to access a variable that's shared globally across all apps in
their ``self.global_vars`` attribute. Accessing this variable is wrapped with a the global lock, so it is safe to read
and write between threads, although it's advised to lock entire methods with the ``global_lock`` decorator.

In this example, the ``global_vars`` would remain locked throughout the duration of the ``do_something`` method.

.. code-block:: python

    # conf/apps/simple.py
    from appdaemon import adbase as ad
    from appdaemon.adapi import ADAPI

    class SimpleApp(ADAPI):
        def initialize(self) -> None:
            self.do_something()

        @ad.global_lock
        def do_something(self):
            vars = self.global_vars
            ... # do some operations
            self.global_vars = vars

App Priorities
~~~~~~~~~~~~~~

The priority system is complementary to the dependency system, but they are trying to solve different problems.
Dependencies should be used when an app literally depends upon another, for instance, it is using variables stored in it
with the ``get_app()`` call. Priorities should be used when an app does some setup for other apps but doesn't provide
variables or code for the dependent app. An example of this might be an app that sets up some sensors in Home Assistant,
or sets some switch or input_slider to a specific value. It may be necessary for that setup to be performed before other
apps are started, but there is no requirement to reload those apps if the first app changes.

To add a priority to an app, simply add a ``priority`` entry to its configuration. e.g.:

.. code:: yaml

    downstairs_motion_light:
      module: motion_light
      class: MotionLight
      sensor: binary_sensor.downstairs_hall
      light: light.downstairs_hall
      priority: 10

Priorities can be any floating point number, and the lower the value, the higher the priority. All apps are guaranteed
to load and start before apps that have a higher priority number. However, explicitly declared dependencies will always
take precedence over priorities. By default all apps have a priority of ``50``. It's therefore possible to cause modules
to be loaded before or after modules without a priority explicitly set.

App Log
-------

Starting from AD 4.0, it is now possible to determine which log as declared by the user, will be used by Apps by default when using the ``self.log()`` within the App; this can be very useful for debugging purposes. This is done by simply adding the ``log:`` directive entry, to its parameters. e.g.:

.. code:: yaml

    downstairs_motion_light:
      module: motion_light
      class: MotionLight
      sensor: binary_sensor.downstairs_hall
      light: light.downstairs_hall
      log: lights_log


By declaring the above, each time the function ``self.log()`` is used within the App, the log entry is sent to the user defined ``lights_log``. It is also possible to write to another log, within the same App if need be. This is done using the function ``self.log(text, log='main_log')``. Without using any of the aforementioned log capabilities, all logs from apps by default will be sent to the ``main_log``.

AppDir Structure
----------------

So far, we have assumed that all apps and their configuration files are placed in a single directory. This works fine
for simple setups but as the number of apps grows, it can be useful to organize them into subdirectories. AppDaemon will
automatically search all subdirectories of the `apps` directory for apps and configuration files. This means that you
can have a directory structure like this:

.. code:: text

    conf/apps
    ├── app1
    │   ├── app1.py
    │   └── app1.yaml
    ├── app2
    │   ├── app2.py
    │   └── app2.yaml
    ├── common
    │   ├── my_globals.py
    │   └── utils.py
    └── some
        └── deep
            └── path
                ├── app3.py
                └── app3.yaml

In this example, AppDaemon will find all the apps defined in `app1.yaml`, `app2.yaml`, and even `app3.yaml`, despite it
being deep in a subdirectory. Each of those files would define apps using ``module: app1`` or ``module: app2`` etc. to
refer to their respective python modules.

Additionally, apps in `app1.py`, `app2.py`, and `app3.py` can import things directly from `my_globals.py` and `utils.py`
like this:

.. code:: python

    # app1/app1.py
    from appdaemon.adapi import ADAPI

    from my_globals import MY_GLOBAL_VAR
    from utils import my_util_function

    class MyApp(ADAPI):
        def initialize(self):
            ... # app code would go here

.. admonition:: Note text
  :class: note

    Note that there are no relative paths here. AppDaemon handles adding all the relevant subdirectories to the import path,
    which allows them to be directly imported, as if the files were next to each other. Furthermore, AppDaemon understands
    that `app1.py` depends on both `my_globals.py` and `utils.py`, so if either of those files change, AppDaemon will reload
    `app1.py` automatically.

App Packages
~~~~~~~~~~~~

As app complexity increases, it's often useful to break the logic apart into multiple files, and sometimes these modules
have the same name as modules in other directories. For example, what if an app needed its own set of utils? The module
names can be managed by using ``__init__.py`` files.

.. code:: text

    conf/apps
    ├── my_app
    │   ├── __init__.py
    │   ├── foo.py
    │   ├── apps.yaml
    │   └── utils.py
    ├── common
    │   ├── ... # other common modules
    │   └── utils.py
    ... # more apps down here

In this example `foo.py` can import from both `utils.py` modules like this, which uses
:py:ref:`package relative imports <relativeimports>` to reference the `utils.py` next to it as distinct from the one in
the `common` directory

.. code-block:: python
  :emphasize-lines: 4,6

    # my_app/foo.py
    from appdaemon.adapi import ADAPI

    from utils import global_util_function

    from .utils import specific_util_function

    class MyApp(ADAPI):
        def initialize(self):
            ... # app code would go here

Using the ``__init__.py`` file indicates to Python/AppDaemon that the directory containing it is a package, and as such
the its import name changes slightly. The `apps.yaml` file needs to be updated to reflect this.

.. code-block:: yaml
  :emphasize-lines: 3

    # my_app/apps.yaml
    my_app:
      module: my_app.foo    # not just `foo`
      class: MyApp


Plugin Reloads
--------------

When a plugin reloads e.g., due to the underlying system restarting, or a network issue,
AppDaemon's default assumption is that all apps could potentially be dependent on that system,
and it will force a restart of every App. It is possible to modify this behavior at the
individual App level, using the ``plugin`` parameter in apps.yaml.
Specifying a specific plugin or list of plugins will force the App to reload after the named plugin restarts.

For a simple AppDaemon install, the appdaemon.yaml file might look something like this:

.. code:: yaml

     appdaemon:
       threads: 10
       plugins:
         HASS:
           type: hass
           ha_url: <some_url>
           ha_key: <some_key>

In this setup, there is only one plugin, and it is called ``HASS`` - this will be the case for most AppDaemon users.

To make an App explicitly reload when only this plugin and no other is restarted (e.g., in the case when HASS restarts or when AppDaemon loses connectivity to HASS), use the ``plugin`` parameter like so:

.. code:: yaml

    appname:
      module: some_module
      class: some_class
      plugin: HASS

If you have more than one plugin, you can make an App dependent on more than one plugin by specifying a YAML list:

.. code:: yaml

    appname:
      module: some_module
      class: some_class
      plugin:
        - HASS
        - OTHERPLUGIN

If you want to prevent the App from reloading at all, just set the ``plugin`` parameter to some value that doesn't match any plugin name, e.g.:

.. code:: yaml

    appname:
      module: some_module
      class: some_class
      plugin: NONE

Note, that this only effects reloading at plugin restart time:

- apps will be reloaded if the module they use changes
- apps will be reloaded if their apps.yaml changes
- apps will be reloaded when a change to or from DST (Daylight Saving Time) occurs
- apps will be reloaded if an App they depend upon is reloaded as part of a plugin restart
- apps will be reloaded if changes are made to a global module that they depend upon

Callback Constraints
--------------------

Users can add constraints when registering callbacks that prevent the callback from being executed
unless certain conditions are met. These constraints only apply to the specific callback and
registration that they're used with.

Constraints are a feature of AppDaemon that removes the need
for repetition of some common coding checks. Many apps will wish to
process their callbacks only when certain conditions are met, e.g.,
someone is home, and it's after sunset. These kinds of conditions crop
up a lot, and use of app constraints can significantly simplify the
logic required within callbacks.

Put simply, constraints are one or more conditions on callback
execution that can be applied in different ways. App's callbacks
will only be executed if all of the constraints are met. If a constraint
is absent, it will not be checked for.

Applying Constraints
~~~~~~~~~~~~~~~~~~~~

Constraints can be applied to callbacks in various ways:

App Level Constraints
^^^^^^^^^^^^^^^^^^^^^

Users can define constraints at the app level in the configuration file. These constraints
apply to every callback registered by that app.

An App can have as many or as few constraints as are required. When more than one
constraint is present, they must all evaluate to true to allow the
callbacks to be called. Constraints becoming true are not an event in
their own right, but if they are all true at a point in time, the next
callback that would otherwise be blocked due to constraint failure
will now be called. Similarly, if one of the constraints becomes false,
the next callback that would otherwise have been called will be blocked.

For example, an app constraint based on time can be added to an App by
adding parameters to its configuration like this:

.. code:: yaml

    some_app:
      module: some_module
      class: SomeClass
      constrain_start_time: sunrise
      constrain_end_time: sunset

The ``initialize()`` function will be called for ``SomeClass``, during which
it can still register as many callbacks as it desires. However, because constraints defined
in the configuration file are checked before any callback for that app is executed, no
callbacks will be executed for ``some_app`` unless it is between sunrise and sunset.

Callback Level Constraints
^^^^^^^^^^^^^^^^^^^^^^^^^^

Constraints can also be applied when registering a callback that will only be applied to that callback.

For example:

.. code:: python

    self.listen_state(self.motion, "binary_sensor.drive", constrain_presence="everyone")

.. code::python

    constraint = "input_select.house_mode,Day"
    self.listen_state(self.motion, "input_select.drive", constrain_input_select=constraint)

.. code:: python

    constraint = "input_select.house_mode,Day,Evening,Night"
    self.listen_state(self.motion, "input_select.drive", constrain_input_select=constraint)

State constraints are a way to constrain callbacks based on the state of an entity. This is useful
when wanting to evaluate a state, to check if it is within a certain range or in a list. They can only be
applied when registering a callback, and will only apply to that registration.

For example:

.. code:: python

    self.listen_state(
        self.state_cb,
        "light.0x0017880103ea737f_light",
        attribute="brightness",
        constrain_state=lambda  x: x > 150)

This constraint will prevent the execution of the callback unless the brightness is a value greater than 150.

AppDaemon Constraints
~~~~~~~~~~~~~~~~~~~~~

Some constraints are supplied by AppDaemon itself and are available to all apps.

time
^^^^

The time constraint consists of 2 variables, ``constrain_start_time``
and ``constrain_end_time``. Callbacks will only be executed if the
current time is between the start and end times.

- If both are absent no time constraint will exist
- If only start is present, end will default to 1 second before midnight
- If only end is present, start will default to midnight

The times are specified in a string format with one of the following
formats:

- HH:MM:SS - the time in Hours Minutes and Seconds, 24 hour format.
- ``sunrise``\ \|\ ``sunset`` [+\|- HH:MM:SS]- time of the next sunrise or sunset with an optional positive or negative offset in Hours Minutes and seconds

The time based constraint system correctly interprets start and end
times that span midnight.

.. code:: yaml

    # Run between 8am and 10pm
    constrain_start_time: "08:00:00"
    constrain_end_time: "22:00:00"
    # Run between sunrise and sunset
    constrain_start_time: sunrise
    constrain_end_time: sunset
    # Run between 45 minutes before sunset and 45 minutes after sunrise the next day
    constrain_start_time: sunset - 00:45:00
    constrain_end_time: sunrise + 00:45:00


days
^^^^

The day constraint consists of as list of days for which the callbacks
will fire, e.g.,

.. code:: yaml

    constrain_days: mon,tue,wed

Other constraints may be supplied by the plugin in use.

HASS Plugin Constraints
~~~~~~~~~~~~~~~~~~~~~~~

The HASS plugin supplies several types of constraints:

.. list-table:: HASS-Specific Constraints
    :header-rows: 1

    * - Argument
      - Value
      - Description
    * - ``constrain_input_boolean``
      - ``<entity_id>, <value>``
      - Constrain based on the value of an `input boolean <https://www.home-assistant.io/integrations/input_boolean/>`__
    * - ``constrain_input_select``
      - ``<entity_id>,<value>``
      - Constrain based on the value of an `input select <https://www.home-assistant.io/integrations/input_select/>`__
    * - ``constrain_presence``
      - ``everyone``, ``anyone``, or ``noone``
      - Constrain based on presence of device trackers
    * - ``constrain_person``
      - ``<entity_id>``
      - Constrain based on entities in the ``person`` domain

constrain\_input\_boolean
^^^^^^^^^^^^^^^^^^^^^^^^^

By default, ``constrain_input_boolean`` prevents callbacks unless the
specified input\_boolean is set to ``on``. This is useful to allow certain
apps to be turned on and off from the user interface, for example:

.. code:: yaml

    some_app:
      module: some_module
      class: SomeClass
      constrain_input_boolean: input_boolean.enable_motion_detection

If you want to reverse the logic so the constraint is only called when
the input\_boolean is ``off``, use the optional state parameter by appending
``,off`` to the argument, for example:

.. code:: yaml

    some_app:
      module: some_module
      class: SomeClass
      constrain_input_boolean: input_boolean.enable_motion_detection,off

If you want to constrain on multiple input_boolean entities, you can provide
the constraints as a yaml list, for example:

.. code:: yaml

    some_app:
      module: some_module
      class: SomeClass
      constrain_input_boolean:
        - input_boolean.enable_motion_detection
        - binary_sensor.weekend,off

Note that the default behavior if the input_boolean doesn't exist is to not constrain.

constrain\_input\_select
^^^^^^^^^^^^^^^^^^^^^^^^

The ``constrain_input_select`` constraint prevents callbacks unless the specified
input\_select is set to one or more of the nominated (comma separated)
values. This is useful to allow certain apps to be enabled/disabled
according to some flag, e.g., a house mode flag.

.. code:: yaml

    # Single value
    constrain_input_select: input_select.house_mode,Day
    # or multiple values
    constrain_input_select: input_select.house_mode,Day,Evening,Night


If you want to constrain on multiple input_select entities, you can provide
the constraints as a yaml list

.. code:: yaml

    some_app:
      module: some_module
      class: SomeClass
      constrain_input_select:
        - input_select.house_mode,Day
        - sensor.day_of_week,Monday,Wednesday,Friday

constrain\_presence
^^^^^^^^^^^^^^^^^^^

The ``constrain_presence`` constraint will constrain based on presence of device
trackers. It takes 3 possible values:

- ``noone`` - only allow callback execution when no one is home
- ``anyone`` - only allow callback execution when one or more person is home
- ``everyone`` - only allow callback execution when everyone is home

.. code:: yaml

    constrain_presence: anyone
    # or
    constrain_presence: everyone
    # or
    constrain_presence: noone

constrain\_person
^^^^^^^^^^^^^^^^^

The ``constrain_person`` constraint will constrain based on presence of person entities
trackers. It takes 3 possible values:

- ``noone`` - only allow callback execution when no one is home
- ``anyone`` - only allow callback execution when one or more person is home
- ``everyone`` - only allow callback execution when everyone is home

.. code:: yaml

    constrain_person: anyone
    # or
    constrain_person: everyone
    # or
    constrain_person: noone

AppDaemon and Threading
-----------------------

AppDaemon is multi-threaded. This means that any time code within an App
is executed, it is executed by one of many threads. This is generally
not a particularly important consideration for this application; in
general, the execution time of callbacks is expected to be far quicker
than the frequency of events causing them. By default, AppDaemon protects Apps from threading considerations by pinning each App to a specific thread, which means it is not possible for an App to be running in more than one thread at a time. In extremely busy systems this may cause a reduction in performance but this is unlikely.

By default, each App gets its own unique thread to run in. This is generally more threads than are required but it prevents badly behaved apps from blocking other apps pinned to the same thread. This organization can be optimized to use fewer threads if desired by using some of the advanced options below. AppDaemon will dynamically manage the threads for you, creating enough for each App, and adding threads over the lifetime of AppDaemon if new apps are added, to guarantee they all get their own thread.

For most users, threading should be left at the defaults, and things will behave sensibly. If however, you understand concurrency, locking, and re-entrant code, read on for some additional advanced options.

Thread Hygiene
~~~~~~~~~~~~~~

An additional caveat of a threaded worker pool environment is that it is
the expectation that none of the callbacks tie threads up for a
significant amount of time. To do so would eventually lead to thread
exhaustion, which would make the system run behind events. No events
would be lost as they would be queued, but callbacks would be delayed,
which is a bad thing.

Given the above, **NEVER** use Python's ``time.sleep()`` if you want to
perform an operation some time in the future, as this will tie up a
thread for the period of the sleep. Instead, use the scheduler's
``run_in()`` function which will allow you to delay without blocking any
threads.

Disabling App Pinning
~~~~~~~~~~~~~~~~~~~~~

If you know what you are doing and understand the risks, you can disable AppDaemon's App Pinning, partially or totally. AppDaemon gives you a huge amount of control, allowing you to enable or disable pinning of individual apps, all apps of a certain class, or even down to the callback level. AppDaemon also lets you explicitly choose which thread apps or callbacks run on, resulting in extremely fine-grained control.

If you disable App pinning, you will start with a default number of 10 threads, but this can be modified with the ``total_threads`` setting in appdaemon.yaml.

To disable App Pinning globally within AppDaemon set the AppDaemon directive ``pin_apps`` to ``false`` within the AppDaemon.yaml file and App pinning will be disabled for all apps. At this point, it is possible for different pieces of
code within the App to be executed concurrently, so some care may be necessary if different callbacks, for instance, inspect and change shared
variables. This is a fairly standard caveat with concurrent programming, and AppDaemon supplies a simple locking mechanism to help avoid this.

Simple Callback Level Locking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The real issue here is that callbacks in an unpinned App can be called at the same time, and even have multiple threads running through them at the same time. To add locking and avoid this, AppDaemon supplies a decorator called ``ad.app_lock``. If you use this with any callbacks that manipulate instance variables, you will ensure that there will only be one thread accessing the variables at one time.

Consider the following App which schedules 1000 callbacks all to run at the exact same time, and manipulate the value of ``self.important_var``:

.. code:: python

    import datetime

    from appdaemon.plugins.hass import Hass

    class Locking(Hass):
        def initialize(self):
            self.important_var = 0

            now = datetime.datetime.now()
            target = now + datetime.timedelta(seconds=2)
            for i in range (1000):
                self.run_at(self.callback, target)

        def callback(self, **kwargs):
            self.important_var += 1
            self.log(self.important_var)

As it is, it will result in unexpected results because ``self.important_var`` can be manipulated by multiple threads at once - for instance, a thread could get the value, add one to it and be just about to write it when another thread jumps in with a different value, which is immediately overwritten. Indeed, when this is run, the output shows just that:

.. code:: text

    2018-11-04 16:07:01.615683 INFO lock: 981
    2018-11-04 16:07:01.616150 INFO lock: 982
    2018-11-04 16:07:01.616640 INFO lock: 983
    2018-11-04 16:07:01.617781 INFO lock: 986
    2018-11-04 16:07:01.584471 INFO lock: 914
    2018-11-04 16:07:01.621809 INFO lock: 995
    2018-11-04 16:07:01.614406 INFO lock: 978
    2018-11-04 16:07:01.622616 INFO lock: 997
    2018-11-04 16:07:01.619447 INFO lock: 990
    2018-11-04 16:07:01.586680 INFO lock: 919
    2018-11-04 16:07:01.619926 INFO lock: 991
    2018-11-04 16:07:01.620401 INFO lock: 992
    2018-11-04 16:07:01.620897 INFO lock: 993
    2018-11-04 16:07:01.622156 INFO lock: 996
    2018-11-04 16:07:01.603427 INFO lock: 954
    2018-11-04 16:07:01.621381 INFO lock: 994
    2018-11-04 16:07:01.618622 INFO lock: 988
    2018-11-04 16:07:01.623005 INFO lock: 998
    2018-11-04 16:07:01.623968 INFO lock: 1000
    2018-11-04 16:07:01.623519 INFO lock: 999

However, if we add the decorator to the callback function like so:

.. code-block:: python
  :emphasize-lines: 15

    import datetime

    from appdaemon import adbase as ad
    from appdaemon.plugins.hass import Hass

    class Locking(Hass):
        def initialize(self):
            self.important_var = 0

            now = datetime.datetime.now()
            target = now + datetime.timedelta(seconds=2)
            for i in range (1000):
                self.run_at(self.callback, target)

        @ad.app_lock
        def callback(self, **kwargs):
            self.important_var += 1
            self.log(self.important_var)

The result is what we would hope for since ``self.important_var`` is only being accessed by one thread at a time:

.. code:: text

    2018-11-04 16:08:54.545795 INFO lock: 981
    2018-11-04 16:08:54.546202 INFO lock: 982
    2018-11-04 16:08:54.546567 INFO lock: 983
    2018-11-04 16:08:54.546976 INFO lock: 984
    2018-11-04 16:08:54.547563 INFO lock: 985
    2018-11-04 16:08:54.547938 INFO lock: 986
    2018-11-04 16:08:54.548407 INFO lock: 987
    2018-11-04 16:08:54.548815 INFO lock: 988
    2018-11-04 16:08:54.549306 INFO lock: 989
    2018-11-04 16:08:54.549671 INFO lock: 990
    2018-11-04 16:08:54.550133 INFO lock: 991
    2018-11-04 16:08:54.550476 INFO lock: 992
    2018-11-04 16:08:54.550811 INFO lock: 993
    2018-11-04 16:08:54.551170 INFO lock: 994
    2018-11-04 16:08:54.551684 INFO lock: 995
    2018-11-04 16:08:54.552022 INFO lock: 996
    2018-11-04 16:08:54.552651 INFO lock: 997
    2018-11-04 16:08:54.553033 INFO lock: 998
    2018-11-04 16:08:54.553474 INFO lock: 999
    2018-11-04 16:08:54.553890 INFO lock: 1000

The above scenario is only an issue when thread pinning is disabled. However, another issue with threading arises when apps call each other and modify variables using the ``get_app()`` call, regardless of whether or not apps are pinned. If a particular App is called at the same time from several different apps using ``get_app()``, the App in question will potentially be running on many threads at the same time, and any local resources such as instance variables that are updated could be corrupted. ``@ad.app_lock`` will also work well to address this situation, if it is applied to the function in the App that is being called. This will force the function to lock using the local lock of the App being called and will enable thread-safe operation.

app1:

.. code:: python

    my_app = get_app("app2")
    my_app.myfunction()

app2:

.. code:: python

    @ad.app_lock
    def my_function()
        self.variable + = 1

Global Locking
~~~~~~~~~~~~~~~~~

The above style of locking works well for the protection of variables within a single App and across apps using ``get_app()``. However, another area where threading might be of concern is if apps are accessing and modifying the dictionary of the global variables which has no locking.

The solution is a global locking decorator called ``@ad.global_lock``:

.. code:: python

    @ad.global_lock
    def so_something_with_global_vars()
        self.global_vars += 1

Per-App Pinning
~~~~~~~~~~~~~~~

Individual apps can be set to override the global AppDaemon setting for App Pinning by use of the ``pin_app`` directive in apps.yaml:

.. code:: yaml

    module: test
    class: Test
    pin_app: false

So if for instance, AppDaemon is set to globally pin apps, the above example will override that and make the App unpinned.

Likewise, if the default is to globally unpin apps, setting ``pin_app`` to ``true`` will pin the App.

In addition to controlling pinning, it is also possible to specify the exact thread an App's callbacks will run on, using the ``pin_thread`` directive:

.. code:: yaml

    module: test
    class: Test
    pin_app: true
    pin_thread: 6

This will result in all callbacks for this App being run by thread 6. The ``pin_thread`` directive will be ignored if ``pin_app`` is set to false, or if ``pin_app`` is not specified and the global setting is to not pin apps.

Per Class Pinning
~~~~~~~~~~~~~~~~~

In addition to per-App pinning, it is possible to pin an entire class so that all apps running that code can be pinned or not. This is achieved using an API call, usually in the ``initialize()`` function that will control whether or not the App is pinned, which will also apply to all apps of the same type since they share the code. Pinning can be enabled or disabled, and thread selected using the pinning API calls:

- ``set_app_pin()``
- ``get_app_pin()``
- ``set_pin_thread()``
- ``get_pin_thread()``

These API calls are dynamic, so it is possible to pin and unpin an App as required as well as select the thread it will run on at any point in the Apps lifetime. Callbacks for the scheduler, events or state changes will inherit the values currently set at the time the callback is registered:

.. code:: python

    # Turn on app pinning
    self.set_app_pin(True)
    # Select a thread
    self.set_pin_thread(5)
    # Set a scheduler callback for an hour hence
    self.run_in(my_callback, 3600)
    # Change the thread
    self.set_pin_thread(3)
    # Set a scheduler callback for 2 hours hence
    self.run_in(my_callback, 7200)

The code above will result in 2 callbacks, the first will run on thread 5, the second will run on thread 3.

Per Callback Pinning
~~~~~~~~~~~~~~~~~~~~

Per Class Pinning described above, despite its dynamic nature is really intended to be a set and forget setup activity in the apps ``initialize()`` function. For more dynamic use, it is possible to set the pinning and thread at the callback level, using the ``pin`` and ``pin_thread`` parameters to scheduler calls and ``listen_state()`` and ``listen_event()``. These parameters will override the default settings for the App as set in apps.yaml or via the API calls above, but just for the callback in question.

.. code:: python

    # Turn off app pinning
    self.set_app_pin(True)
    # Select a thread
    self.set_pin_thread(5)
    # Set a scheduler callback for an hour hence
    self.run_in(my_callback, 3600, pin=False)

The above callback will not be pinned.

.. code:: python

    # Turn off app pinning
    set_app_pin(True)
    # Select a thread
    set_pin_thread(5)
    # Set a scheduler callback for an hour hence
    run_in(my_callback, 3600, pin_thread=9)

The above callback will be run on thread 9, overriding the call to ``set_pin_thread()``.

.. code:: python

    # Set a scheduler callback for an hour hence
    run_in(my_callback, 3600, pin=True)

The above code is an edge case, if the global or App default is set to not pin. In this case, there won't be an obvious thread to use since it isn't specified, so the callback will default to run on thread 0.

Restricting Threads for Pinned Apps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For some usages in mixed pinned and non-pinned environments, it may be desirable to reserve a block of thread specifically for pinned apps. This can be achieved by setting the ``pin_threads`` directive in AppDamon.yaml:

.. code:: YAML

    pin_threads: 5

In the above example, 5 threads will be reserved for pinned apps, meaning that pinned apps will only run on threads 0 - 4, and will be distributed among them evenly. If the system has 10 threads total, threads 5 - 9 will have no pinned apps running on them, representing spare capacity. In order to utilize the spare threads, you can code apps to explicitly run on them, or set them in the apps.yaml, perhaps reserving threads for specific high priority apps, while the rest of the apps share the lower priority threads. Another way to manage this is via the selection of an appropriate scheduler algorithm.

``pin_threads`` will default to the actual number of threads, if App pinning is turned on globally, and it will default to 0 if App pinning is turned off globally. In a mixed setting, if you have any unpinned apps at all you must ensure that ``pin_threads`` is set to a value less than threads.

Scheduler Algorithms
~~~~~~~~~~~~~~~~~~~~

When apps are pinned, there is no choice necessary as to which thread will run a given callback. It will either be selected by AppDaemon, or explicitly specified by the user for each App. For the remainder of unpinned Apps, AppDaemon must make a choice as to which thread to use, in an attempt to keep the load balanced. There is a choice of 3 strategies, set by the ``load_distribution`` directive in appdaemon.yaml:

- ``roundrobin`` (default) - distribute callbacks to threads in a sequential fashion, one thread after another, starting at the beginning when all threads have had their turn. Round Robin scheduling will honor the ``pin_threads`` directive and only use threads not reserved for pinned apps.
- ``random`` - distribute callbacks to available threads in a random fashion. Random will also honor the ``pin_threads`` directive
- ``load`` - distribute callbacks to the least busy threads (measured by their Q size). Since Load based scheduling is dynamically responding to load, it will take all threads into consideration, including those reserved for pinned apps.

For example:

.. code:: YAML

    load_distribution: random

A Final Thought on Threading and Pinning
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Although pinning and scheduling has been thoroughly tested, in current real-world applications for AppDaemon, very few of these considerations matter, since in most cases AppDaemon will be able to respond to a callback immediately, and it is unlikely that any significant scheduler queueing will occur unless there are problems with apps blocking threads. At the rate that most people are using AppDaemon, events come in a few times a second, and modern hardware can usually handle the load pretty easily. The considerations above will start to matter more when event rates become a lot faster, by at least an order of magnitude. That is now a possibility with the recent upgrade to the scheduler allowing sub-second tick times, so the ability to lock and pin apps were added in anticipation of new applications for AppDaemon that may require more robust management of apps and much higher event rates.

Async Apps
----------

.. admonition:: Almost always unnecessary
    :class: warning

    It's **almost never** advantageous to use async programming in AppDaemon apps. The AppDaemon thread model already
    effectively runs every app's callback in an async way. Regular callbacks are submitted to thread workers in a
    non-blocking way from the async loop in the main thread and then awaited. Async callbacks will be run in the main
    thread, so you can accidentally block the entire AppDaemon process if you're not careful. Only use async programming
    sparingly and if you know what you're doing.

Despite not being recommended, AppDaemon does support the partial or complete use of async programming in apps.
Coroutine functions (defined with ``async def``) can be used in place of regular callback functions. AppDaemon will
create an async task that schedules it to run in the main thread whenever the callback is triggered.

Apps can be a mix of `sync` and `async` callbacks as desired. A fully async app might look like this:

.. code-block:: python
  :emphasize-lines: 8

    from appdaemon.plugins.hass import Hass


    class AsyncApp(Hass):
        async def initialize(self):
            # Runs self.delayed_callback in 10 seconds
            # Maybe access an async library to initialize something
            self.handle = await self.run_in(self.delayed_callback, delay=10)

        async def delayed_callback(self, **kwargs):
            # do some async stuff

            # Sleeps are perfectly acceptable
            await self.sleep(10)

            # Call another coroutine
            await my_function()

        async def my_function(self):
            ... # More async stuff here

Async Pitfalls
~~~~~~~~~~~~~~

A major complication of using async callbacks is that because they are run in the main thread, many methods for the API
classes return async :py:class:`~asyncio.Task` objects instead of the result of the method. In the example above,
`self.run_in` returns a :py:class:`~asyncio.Task` object instead of a `str` handle like it normally would. To get
the normal result of the method, the task needs to be `awaited`.

This will not give the expected result - the handle will be a `Task` object, not a `str`:

.. code:: python

    async def some_method(self):
        handle = self.run_in(self.callback, delay=30)

This, however, will return a `str` handle as expected:

.. code:: python

    async def some_method(self):
        handle = await self.run_in(self.callback, delay=30)

Async Advantages
~~~~~~~~~~~~~~~~

- Async programming can sometimes provide performance benefits in situations where there are many simulatneous I/O bound tasks happening at once.
- Some external libraries are designed with an async interface, and intended to be used that way.
- Scheduling heavily concurrent tasks is very easy using async
- Using :py:meth:`~appdaemon.adapi.ADAPI.sleep` in async apps is not harmful to the overall performance of AppDaemon as it is in regular sync apps

Async Tools
~~~~~~~~~~~

AppDaemon supplies a number of helper functions to make things a little easier:

Creating Tasks
^^^^^^^^^^^^^^

Although it's possible to use the :py:func:`asyncio.create_task` function from inside async
callbacks, it's not recommended because if any tasks created this way are not done when the app is reloaded or
terminated, they won't be cleaned up. This can lead to unexpected behavior, as the tasks will continue to run in the
background and might get recreated when the app starts again. Instead, it's recommended to use a helper method called
:py:meth:`~appdaemon.adapi.ADAPI.create_task` method that wraps
:py:func:`asyncio.create_task` with logic to clean up the task when the app is reloaded or
terminated.

Using the Thread Pool
^^^^^^^^^^^^^^^^^^^^^

The `ADAPI` class provides a method called :py:meth:`~appdaemon.adapi.ADAPI.run_in_executor` that
allows the user to run a function in the internal :py:class:`~concurrent.futures.ThreadPoolExecutor`.
This effectively allows the user to run blocking, sync code in a separate thread as if it was async, which prevents
blocking any of the worker threads or the main thread. Otherwise, a long-running callback would block whatever thread
it's in, which can cause problems. A standard pattern is to use other threads for I/O bound tasks, such as file or
network access.

Sleeping
^^^^^^^^

Sleeping in Apps is perfectly fine using the async model. For this purpose, AppDaemon provides the
:py:meth:`~appdaemon.adapi.ADAPI.sleep` method. If this function is used in a non-async callback, it will raise
an exception.

Async Threading Considerations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Bear in mind, that although the async programming model is single threaded, in an event-driven environment such as AppDaemon, concurrency is still possible, whereas in the pinned threading model it is eliminated. This may lead to requirements to lock data structures in async apps.
- By default, AppDaemon creates a thread for each App (unless you are managing the threads yourself). For a fully async app, the thread will be created but never used.
- If you have a 100% async environment, you can prevent the creation of any threads by setting ``total_threads: 0`` in ``appdaemon.yaml``


Callbacks
---------

A large proportion of home automation revolves around waiting for
something to happen and then reacting to it - a light level drops, the
sun rises, a door opens, etc. Apps are able to register callbacks
for these events, and AppDaemon will handle calling them as necessary.

Apps in AppDaemon are merely groups of these callbacks, so when the callbacks
are not being executed, apps consume very little resources.

There are 4 kinds of callback in AppDaemon, each with their own methods in :class:`~appdaemon.adapi.ADAPI`.

.. list-table:: AppDaemon Callbacks
    :header-rows: 1

    * - Type
      - API Method
      - Description
    * - Event
      - :meth:`~appdaemon.adapi.ADAPI.listen_event`
      - react to a specific event being fired
    * - Scheduler
      - :meth:`~appdaemon.adapi.ADAPI.run_once`, :meth:`~appdaemon.adapi.ADAPI.run_in`, :meth:`~appdaemon.adapi.ADAPI.run_at`, etc.
      - react to a specific time or interval
    * - State
      - :meth:`~appdaemon.adapi.ADAPI.listen_state`
      - react to a change in state
    * - Log
      - :meth:`~appdaemon.adapi.ADAPI.listen_log`
      - called whenever a log entry is made

Event Callbacks
~~~~~~~~~~~~~~~

`More information <#events>`__ on events in AppDaemon.

Users can register event callbacks with calls to :meth:`~appdaemon.adapi.ADAPI.listen_event`. AppDaemon will handle
executing the callback when the event is fired.

For example, this registers a callback for an event ``some_event``:

.. code:: python

    self.listen_event(self.my_callback, "some_event")

Event callbacks are expected to have a specific signature. For legacy compatibility, callbacks without the ``**kwargs``
expansion will still work. AppDaemon will automatically determine the correct way to call the function when it's
executed.

.. code:: python

    def my_callback(self, event_type: str, data: dict[str, Any], **kwargs: Any) -> None:
        ... # do some useful work here

    def my_legacy_callback(self, event_type, data, kwargs) -> None:
        ... # do some useful work here

The ``data`` argument is a dict containing data sent with the event when it's fired, which varies depending on the
event, and ``kwargs`` is a dict of data that comes from the call to :meth:`~appdaemon.adapi.ADAPI.listen_event`.

.. code:: python

    self.listen_event(self.my_callback, "some_event", my_kwarg=123)

These callbacks are equivalent:

.. code:: python

    def my_callback(self, event_type, data, **kwargs):
        my_kwarg = kwargs["my_kwarg"]
        self.log(f'My kwarg: {my_kwarg}')

    def my_callback(self, *_, my_kwarg: int, **kwargs):
        self.log(f'My kwarg: {my_kwarg}')

Filtering Events
^^^^^^^^^^^^^^^^

Arguments that were used to register the event callback will be used to filter the events, but only if the events have
keys that match the arguments. For example, registering a callback like this will cause it to only be called when the
event has a matching ``entity_id`` key in its data:

.. code-block:: python
  :emphasize-lines: 13

    from datetime import datetime

    from appdaemon.adapi import ADAPI


    class ButtonHandler(ADAPI):
        def initialize(self):
            # Listen for a button press event with a specific entity_id
            self.listen_event(
                self.minimal_callback,
                'call_service',
                service='press',
                entity_id='input_button.test_button,
            )

        def minimal_callback(self, event_type: str, data: dict[str, Any], **kwargs: Any) -> None:
            self.log(f'Button pressed')

        # Another example callback
        def alternate_callback(self, event_type: str, data: dict[str, Any], **kwargs: Any) -> None:
            match data:
                case {
                    "service_data": {"entity_id": eid},
                    "metadata": {"time_fired": time_fired}
                }:
                    friendly_name = self.get_state(eid, attribute='friendly_name')
                    time_fired = datetime.fromisoformat(time_fired).astimezone(self.AD.tz)
                    fmt = "%I:%M:%S %p"
                    self.log(f'{friendly_name} was pressed at {time_fired.strftime(fmt)}')
                    self.log(f'Kwargs: {kwargs}')
                case _:
                    self.log(f'Unhandled button press: {data}', level='WARNING')


More examples:

.. code:: python

    self.listen_event(self.mode_event, "MODE_CHANGE")

    # Listen for a minimote event activating scene 3:
    self.listen_event(self.generic_event, "zwave_js_value_notification", value=3)

    # Listen for a minimote event activating scene 3 from a specific minimote:
    self.listen_event(self.generic_event, "zwave_js_value_notification", node_id="11", value=3)

    # Listen for a minimote event activating scene 3 from one of several minimotes:
    self.listen_event(
        self.generic_event, "zwave_js_value_notification",
        node_id=lambda x: x in ["11", "14", "22"],
        value=3
    )

Scheduler Callbacks
~~~~~~~~~~~~~~~~~~~

`More information <#the-scheduler>`__ about AppDaemon's scheduler.

Users can schedule callbacks in the AppDaemon scheduler using various time-based methods such as
``run_in``, ``run_at``, ``run_daily``, etc. AppDaemon will handle executing the callback at the scheduled time.

Scheduled callbacks are expected to have a specific signature, which looks like this:

.. code:: python

    def my_callback(self, **kwargs):
        ... # do some useful work here

For legacy compatibility, callbacks without the keyword argument expansion will still work.
AppDaemon will automatically determine the correct way to call the function when it executes it.

.. code:: python

    def my_callback(self, kwargs):
        ... # do some useful work here

State Callbacks
~~~~~~~~~~~~~~~

`More information <#state-operations>`__ on states in AppDaemon.

Users can register callbacks for state changes with calls to
:meth:`self.listen_state(...) <appdaemon.adapi.ADAPI.listen_state>`. AppDaemon will handle executing
the callback when the state changes.

For example, this registers a callback for all state changes on the entity ``binary_sensor.drive``:

.. code:: python

    self.listen_state(self.my_callback, "binary_sensor.drive")

This example only executes when the state changes to ``on``:

.. code:: python

    self.listen_state(self.my_callback, "binary_sensor.drive", new="on")

State callbacks can be named anything, but are expected to have a specific signature, which looks like this:

.. code:: python

    def my_callback(self, entity, attribute, old, new, **kwargs):
        ... # do some useful work here

For legacy compatibility, callbacks without the keyword argument expansion will still work.
AppDaemon will automatically determine the correct way to call the function when it executes it.

.. code:: python

    def my_callback(self, entity, attribute, old, new, kwargs):
        ... # do some useful work here

.. The cb_args dictionary will also contain a field called ``handle`` that
.. provides the callback with the handle that identifies the
.. :meth:`self.listen_state(...) <appdaemon.adapi.ADAPI.listen_state>` entry that resulted in the callback.

Log Callbacks
~~~~~~~~~~~~~

Constraints
~~~~~~~~~~~

Constraints can be applied when registering a callback. Refer to
`callback level constraints <#callback-level-constraints>`_ for more information.

User Arguments
~~~~~~~~~~~~~~

Users are able to specify additional keyword arguments to be passed to the
callback via the standard Python ``**kwargs`` mechanism. Keyword arguments
are then available as a standard Python dictionary in the callback.

The only restriction is that they cannot be the same as any constraint name
for obvious reasons. For example, to pass the parameter ``arg1=123``
through to a callback you would register a callback as follows:

.. code:: python

    self.listen_state(self.motion, "binary_sensor.motion_sensor_01", arg1=123)

The value is available in the callback as follows. Note that ``arg1`` can be renamed
to anything as long as it doesn't conflict with the names of other arguments.

.. code:: python

    def motion(self, entity, attribute, old, new, arg1, **kwargs):
        self.log(f"Arg1 is {arg1}")

Which is equivalent to:

.. code:: python

    def motion(self, entity, attribute, old, new, **kwargs):
        arg1 = kwargs["arg1"]
        self.log(f"Arg1 is {arg1}")

Events
------

Events are a fundamental part of how AppDaemon works internally. Plugins fire
events and AppDaemon communicates them to apps as required.

For instance, the MQTT plugin will fire an event when a message is
received, and the HASS plugin will fire events for all Home Assistant
events.

`Event Callbacks <#event-callbacks>`_
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Refer to the callbacks section for more information.

AppDaemon Events
~~~~~~~~~~~~~~~~

In addition to the HASS and MQTT supplied events, AppDaemon adds 3 more
events. These are internal to AppDaemon and are not visible on the Home
Assistant bus:

.. list-table:: AppDaemon Internal Events
   :header-rows: 1
   :widths: 20 6 80

   * - **Event Type**
     - **Namespace**
     - **Description**
   * - ``appd_started``
     - ``global``
     - Fired once when AppDaemon is first started and after Apps are initialized.
   * - ``app_initialized``
     - ``admin``
     - Fired when each app is started with :code:`{"app": <app_name>}` for its data.
   * - ``app_terminated``
     - ``admin``
     - Fired when each app is terminated with :code:`{"app": <app_name>}` for its data after all its callbacks have been removed.
   * - ``plugin_started``
     - ``<plugin>``
     - Fired when a plugin notifies AppDaemon that is has started with :code:`{"name": <plugin_name>}`. Called in the namespace of the plugin.
   * - ``plugin_stopped``
     - ``<plugin>``
     - Fired when a plugin notifies AppDaemon that is has stopped with :code:`{"name": <plugin_name>}`. Called in the namespace of the plugin.
   * - ``service_registered``
     - ``<service>``
     - Fired when AppDaemon registers a service with :code:`{"namespace": <namespace>, "domain": <domain>, "service": <service>}`. Called in the namespace of the service.
   * - ``service_deregistered``
     - ``<service>``
     - Fired when AppDaemon deregisters a service with :code:`{"namespace": <namespace>, "domain": <domain>, "service": <service>}`. Called in the namespace of the service.
   * - ``stream_connected``
     - ``admin``
     - Fired when the AD stream connects
   * - ``stream_disconnected``
     - ``admin``
     - Fired when the AD stream disconnects

Home Assistant Events
~~~~~~~~~~~~~~~~~~~~~

We have already seen how state changes can be propagated to AppDaemon via the HASS plugin - a state change however is merely an example of an event within Home Assistant. There are several other event types, among them are:

-  ``homeassistant_start``
-  ``homeassistant_stop``
-  ``state_changed``
-  ``service_registered``
-  ``call_service``
-  ``service_executed``
-  ``platform_discovered``
-  ``component_loaded``

Using the HASS plugin, it is possible to subscribe to specific events as well
as fire off events.

MQTT Events
~~~~~~~~~~~

The MQTT plugin uses events as its primary (and only interface) to MQTT. The model is fairly simple - every time an MQTT message is received, and event of type ``MQTT_MESSAGE`` is fired. Apps are able to subscribe to this event and process it appropriately.

Use of Events for Signalling between Home Assistant and AppDaemon
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Home Assistant allows for the creation of custom events, and existing
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
can also listen for custom events with its automation component. This
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
information see the `Dashboard configuration pages <DASHBOARD.html>`__

AppDaemon provides convenience functions to assist with this.

HASS Presence
~~~~~~~~~~~~~

Presence in Home Assistant is tracked using Device Trackers. The state
of all device trackers can be found using the ``get_state()`` call.
However, AppDaemon provides several convenience functions to make this
easier.

Writing to Logfiles
~~~~~~~~~~~~~~~~~~~

AppDaemon uses 2 separate logs - the general log and the error log. An
App can write to either of these using the supplied
convenience methods ``log()`` and ``error()``, which are provided as
part of parent ``AppDaemon`` class, and the call will automatically
prepend the name of the App making the call.

The functions are based on the Python ``logging`` module and are able to pass through parameters for interpolation, and additional parameters such as ``exc_info`` just as with the usual style of invocation. Use of loggers interpolation method over the use of ``format()`` is recommended for performance reasons, as logger will only interpolate of the line is actually written whereas ``format()`` will always do the substitution.

The ``-D`` option of AppDaemon can be used to specify a global logging level, and Apps can individually have their logging level set as required. This can be achieved using the ``set_log_level()`` API call, or by using the special ``debug`` argument to the apps settings in ``apps.yaml``:

.. code:: yaml

    log_level: DEBUG

In addition, apps can select a default log for the `log()` call using the `log` directive in apps.yaml, referencing the section name in appdaemon.yaml. This can be one of the 4 builtin logs, ``main_log``, ``error_log``, ``diag_log`` and ``access_log``, or a user-defined log, e.g.:

.. code:: yaml

    log: test_log

If an App has set a default log other than one of the 4 built in logs, these logs can still be accessed specifically using either the `log=` parameter of the `log()` call, or by getting the appropriate logger object using the `get_user_log()` call, which also works for default logs.

AppDaemon's logging mechanism also allows you to use placeholders for the module,
function, and line number. If you include the following in the test of
your message:

::

    __function__
    __module__
    __line__

They will automatically be expanded to the appropriate values in the log
message.

State Operations
----------------

AppDaemon maintains a master state dictionary in memory locally, which is segmented
by namespace. When a plugin gets notified of state changes, AppDaemon updates
the states namespaces associated with that plugin.

AppDaemon internally fires an event when an entity changes state. This occurs for every
state change of every entity, as well as every attribute change. Apps can respond to any
or all of these events by registering a callback, which AppDaemon will call when the event
gets fired. Apps register callbacks using a :meth:`self.listen_state(...) <appdaemon.adapi.ADAPI.listen_state>`
call.

The MQTT plugin does not use state at all, and it relies on events to trigger
actions, whereas the Home Assistant plugin makes extensive use of state.

`State Change Callbacks <#state-callbacks>`_
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Refer to the callbacks section for more information.

A note on Home Assistant State
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

State within Home Assistant is stored as a collection of dictionaries,
one for each entity. Each entity's dictionary will have some common
fields and a number of entity type-specific fields. The state for an
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

Also, bear in mind that some attributes such as brightness for a light,
will not be present when the light is off.

In most cases, the attribute ``state`` has the most important value in
it, e.g., for a light or switch this will be ``on`` or ``off``, for a
sensor it will be the value of that sensor. Many of the AppDaemon API
calls and callbacks will implicitly return the value of state unless
told to do otherwise.

Although the use of ``get_state()`` (below) is still supported, as of
AppDaemon 2.0.9 it is possible to access HASS state directly as an
attribute of the App itself, under the ``entities`` attribute.

For instance, to access the state of a binary sensor, you could use:

.. code:: python

    sensor_state = self.entities.binary_sensor.downstairs_sensor.state

Similarly, accessing any of the entity attributes is also possible:

.. code:: python

    name = self.entities.binary_sensor.downstairs_sensor.attributes.friendly_name

Publishing State from an App
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using AppDaemon, it is possible to explicitly publish state from an App.
The published state can contain whatever you want, and is treated
exactly like any other HA state, e.g., to the rest of AppDaemon, and the
dashboard it looks like an entity. This means that you can listen for
state changes in other apps and also publish arbitrary state to the
dashboard via the use of specific entity IDs. To publish state, you will use
``set_state()``. State can be retrieved and listened for with the
usual AppDaemon calls.

The Scheduler
-------------

AppDaemon contains a powerful scheduler that is able to run with microsecond
resolution to fire off specific events at set times, or after set delays, or
even relative to sunrise and sunset.

`Scheduled Callbacks <#scheduler-callbacks>`_
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Refer to the callbacks section for more information.

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
positive to denote a random offset after an event. The event would be an
absolute or relative time or sunrise/sunset depending on which
scheduler call you use, and these values affect the base time by the
specified amount. If not specified, they will default to ``0``.

For example:

.. code:: python

    # Run a callback in 2 minutes minus a random number of seconds between 0 and 60, e.g. run between 60 and 120 seconds from now
    self.handle = self.run_in(callback, 120, random_start=-60)
    # Run a callback in 2 minutes plus a random number of seconds between 0 and 60, e.g. run between 120 and 180 seconds from now
    self.handle = self.run_in(callback, 120, random_end=60, **kwargs)
    # Run a callback in 2 minutes plus or minus a random number of seconds between 0 and 60, e.g. run between 60 and 180 seconds from now
    self.handle = self.run_in(callback, 120, random_start=-60, random_end=60)

Sunrise and Sunset
~~~~~~~~~~~~~~~~~~

AppDaemon has a number of features to allow easy tracking of sunrise and
sunset as well as a couple of scheduler functions. Note that the
scheduler functions also support the randomization parameters described
above, but they cannot be used in conjunction with the ``offset``
parameter.

Services
--------

Services within AppDaemon are called to make something happen. For instance, instructing Home Assistant to turn a
light on, or instructing AppDaemon itself to reload an App. They're a way for apps to interact with plugins and other
apps without any direct coupling to either.

Services are pre-registered functions that can be called by using their domain and service names with
:py:meth:`call_service <appdaemon.adapi.ADAPI.call_service>` method of one of the API classes. Any app can call any
service with this single method, and the services can each accept and return arbitrary parameters. Calling services is
the foundation of many of the methods in the API classes.

Services each have a name and are hierarchically organized by namespace and domain, so they are uniquely identified by
``namespace/domain/service_name``. In most cases the namespace is ``default``, so the services are referred to by just
``domain/service_name``.

Changes to Service Calls
~~~~~~~~~~~~~~~~~~~~~~~~

As of AppDaemon v4.5.0, how services are called internally has changed. Previously services were "fire and forget". The
service call was sent to the AppDaemon internals and control was returned immediately to the app, which meant that there
was no way to know if the service call was actually successful or not.

Now there is always some kind of result. Even if the service itself doesn't return anything, the result will still be a
dict that has some status information from AppDaemon.

Service Registration
~~~~~~~~~~~~~~~~~~~~

Services are generally registered by plugins, but user can also register custom services from apps that can then be
called by themselves or other apps. This is useful for apps to interact with each other without any direct coupling.

Registering a custom service is very simple. All that is required is a call to the
:py:meth:`register_service <appdaemon.adapi.ADAPI.register_service>` method with a service name and a reference to the
desired function (the callback), and it becomes immediately available for all the other apps to use.

.. admonition:: Service Namespace
  :class: note

    Inter-app callbacks should be assigned to a `User Defined Namespace <APPGUIDE.html#user-defined-namespaces>`__ to
    avoid collisions with services in other namespaces.

Function Format
^^^^^^^^^^^^^^^

The function used for the service only has to have a compatible signature, and the value returned from the function will
be returned from later calls to the :py:meth:`call_service <appdaemon.adapi.ADAPI.call_service>` method. For example:

.. code-block:: python

    def my_custom_service(self, namespace: str, domain: str, service: str, **kwargs: Any) -> None:
        self.log(f"Called my custom service: {domain}/{service}")

The service callbacks get called with some positional arguments as well as keyword arguments provided with the service
call. The first 3 arguments are the `namespace`, `domain`, and `service name` of the service being called, which can be
collected by usings ``*args`` like this:

.. code-block:: python

    def my_custom_service(self, *args: str, **kwargs: Any) -> None:
        self.log(f'Called my custom service: {"/".join(args)}')

Service callbacks can also accept their own keyword arguments, which can be passed to it when the service is called.
This example expects an `int` as an additional argument called ``my_arg``:

.. code-block:: python

    def my_custom_service(self, *args: str, my_arg: int, **kwargs: Any) -> None:
        self.log(f'Called my custom service: {"/".join(args)} with my_arg={my_arg}')

Values can be returned from services the same way as any other Python function.

.. code-block:: python

    def my_custom_service(self, *args: str, **kwargs: Any) -> float:
        self.log(f'Called my custom service: {"/".join(args)}')
        return 42.0  # This value will be returned from the service call

Full Example
^^^^^^^^^^^^

We can define the service as a custom method of ``App1``, and call it later from ``App2``. To make ensure that the apps
get initialized in the correct order, we also specify a dependency in the ``apps.yaml`` file.

.. code-block:: python

    # conf/apps/my_apps.py
    from appdaemon.adapi import ADAPI


    class App1(ADAPI):
        def initialize(self):
            self.register_service("my_domain/my_exciting_service", self.my_exciting_cb)

        def my_exciting_cb(self, *args: str, my_arg: int, **kwargs: Any) -> Any:
            # this will be "default/my_domain/my_exciting_service"
            unique_service_name = "/".join(args)
            self.log(f"{unique_service_name} called with {kwargs}")

            return 63 + my_arg


    class App2(ADAPI):
        def initialize(self):
            return_value = self.call_service("my_domain/my_exciting_service", my_arg=37)
            self.log(f"Service returned: {return_value}")


.. code-block:: yaml

    # conf/apps/apps.yaml
    apps:
      App1:
        module: my_apps
        class: App1
      App2:
        module: my_apps
        class: App2
        dependencies:
          - App1 # Ensures App2 is initialized after App1

Here, ``return_value`` in ``App2`` will be set to ``100``, the return value from the callback in ``App1``. The values
for `domain` and `service name`, which are ``my_domain`` and ``my_exciting_service`` respectively, are arbitrary, and
can be changed to anything.

One trick is to use the name of an app if you have multiple apps using the same class. This enables you to register services distinct to each instance of the app And call
their services separately. For instance:

.. code:: python

    name = self.name.replace(" ", "_").lower()
    self.register_service(
        f"occupancy/set_occupancy_{name}",
        self.occupancy_service,
        namespace="sanctuary",
    )

Returning Results
~~~~~~~~~~~~~~~~~

Values can be returned from service calls the same way as any other Python function. However, for potentially
long-running service calls, AppDaemon also supports returning values with a callback. This is useful because it avoids
hitting the AppDaemon ``internal_function_timeout``.

Specifying a callback when calling a service will cause it to run in the background and return control to the app
immediately. Whenever the service finishes, the callback function will be called with the result of the service call.

.. code:: python

    self.call_service("my_domain/my_exciting_service", callback=self.my_cool_callback)

    ...

    def my_cool_callback(self, result: Any) -> None:
        self.log(f"Callback result: {result}")

Getting Information in Apps and Sharing information between Apps
----------------------------------------------------------------

Sharing information between different Apps is very simple if required.
Each App gets access to a global dictionary stored in a class attribute
called ``self.global_vars``. Any App can add or read any key as
required. This operation is not, however, threadsafe so some care is
needed - see the section on threading for more details.

In addition, Apps have access to the entire configuration if required,
meaning they can access AppDaemon configuration items as well as
parameters from other Apps. To use this, there is a class attribute
called ``self.config``. It contains a standard Python nested ``Dictionary``.

To get AppDaemon's config parameters for example:

.. code:: python

    app_timezone = self.config["time_zone"]


To access any apps parameters, use the class attribute called ``app_config``. This is
a Python Dictionary with an entry for each App, keyed on the App's name.

.. code:: python

    other_apps_arg = self.app_config["some_app"]["some_parameter"].


AppDaemon also exposes the configurations from configured plugins. For example, that of the HA plugin
allows accessing configurations from Home Assistant such as the
Latitude and Longitude configured in HA. All of the information
available from the Home Assistant ``/api/config`` endpoint is available
using the ``get_config()`` call. E.g.:

.. code:: python

    config = self.get_config()
    self.log("My current position is {}(Lat), {}(Long)".format(config["latitude"], config["longitude"]))

Using this method, it is also possible to use this function to access configurations of other plugins,
from within apps in a different namespace. This is done by simply passing in the ``namespace`` parameter. E.g.:

.. code:: python

    ## from within a HASS App, and wanting to access the client Id of the MQTT Plugin

    config = self.get_config(namespace = 'mqtt')
    self.log("The Mqtt Client ID is ".format(config["client_id"]))


And finally, it is also possible to use ``config`` as a global area
for sharing parameters across Apps. Simply add the required parameters
inside the appdaemon section in the appdaemon.yaml file:

.. code:: yaml

    logs:
    ...
    appdaemon:
      global_var: hello world

Then access it as follows:

.. code:: python

    my_global_var = self.config["global_var"]

Development Workflow
--------------------

Developing Apps is intended to be fairly simple but is an exercise in
programming like any other kind of Python program. As such, it is
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

Scheduler Speed
---------------

The scheduler has been redesigned in 4.0 with a new tickles algorithm that allows you to specify timed events to the limit of the host system's accuracy (this is usually down to the microsecond level).

Time Travel
-----------

OK, time travel sadly isn't really possible but it can be very useful
when testing Apps. For instance, imagine you have an App that turns a
light on every day at sunset. It might be nice to test it without
waiting for Sunset - and with AppDaemon's "Time Travel" features you
can.

Choosing a Start Time
~~~~~~~~~~~~~~~~~~~~~

Internally, AppDaemon keeps track of its own time relative to when it
was started. This make it possible to start AppDaemon with a different
start time and date to the current time. For instance, to test that
sunset App, start AppDaemon at a time just before sunset and see if it
works as expected. To do this, simply use the "-s" argument on
AppDaemon's command line. e.g.:

.. code:: bash

    $ apprun -s "2018-23-27 16:30:00"
    ...
    2018-12-27 09:31:20.794106 INFO     AppDaemon  App initialization complete
    2018-23-27 16:30:00.000000 INFO     AppDaemon  Starting time travel ...
    2018-23-27 16:30:00:50.000000 INFO     AppDaemon  Setting clocks to 2018-23-27 16:30:00
    2018-23-27 16:30:00.000000 INFO     AppDaemon  Time displacement factor 1.0
    ...

Note the timestamps in the log - AppDaemon believes it is now just
before sunset and will process any callbacks appropriately.

Speeding things up
~~~~~~~~~~~~~~~~~~

Some Apps need to run for periods of a day or two for you to test all aspects. This can be time-consuming, but Time Travel can also help here by speeding uptime. To do this, simply use the ``-t`` (timewarp) option on the command line. This option is a simple multiplier for the speed that time will run. If set to 10, time as far as AppDaemon is concerned will run 10 times faster than usual. Set it to 0,1, and time will run 10 times slower. A few examples:

Set appdaemon to run 10x faster than normal:

.. code:: bash

    $ appdaemon -t 10

Set appdaemon to run as fast as possible:

.. code:: bash

    $ appdaemon -t 0


The ``timewarp`` flag in ``appdaemon.yaml`` is an alternative way of changing the speed, and will override the ``-t`` command line setting.

Automatically stopping
~~~~~~~~~~~~~~~~~~~~~~

AppDaemon can be set to terminate automatically at a specific time. This
can be useful if you want to repeatedly rerun a test, for example, to
test that random values are behaving as expected. Simply specify the end
time with the ``-e`` flag as follows:

.. code:: bash

    $ appdaemon -e "2016-06-06 10:10:00"
    2016-09-06 17:16:00 INFO AppDaemon Version 1.3.2 starting
    2016-09-06 17:16:00 INFO Got initial state
    2016-09-06 17:16:00 INFO Loading Module: /export/hass/appdaemon_test/conf/test_apps/sunset.py
    ..,

The ``-e`` flag is most useful when used in conjunction with the ``-s``
flag and optionally the ``-t`` flag. For example, to run from just
before sunset, for an hour, as fast as possible:

.. code:: bash

    $ appdaemon -s "2016-06-06 19:16:00" -e "2016-06-06 20:16:00" -t 10

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

About Plugin Disconnections
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a plugin is unable to connect initially with the underlying system, e.g., Home Assistant, it
will hold all Apps in stasis until it initially connects, nothing else
will happen, and no initialization routines will be called. If AppDaemon
has been running connected to Home Assistant for a while and the
connection is unexpectedly lost, the following will occur:

-  When the plugin first goes down or becomes disconnected, an event called
   ``plugin_disconnected`` will fire
-  While disconnected from the plugin, Apps will continue to run
-  Schedules will continue to be honored
-  Any operation reading locally cached state will succeed
-  Any operation requiring a call to the plugin will log a warning and return
   without attempting to contact hass

When a connection to the plugin is reestablished, all Apps will be restarted
and their ``initialize()`` routines will be called.

RESTFul API Support
-------------------

AppDaemon supports a simple RESTFul API to enable arbitrary HTTP
connections to pass data to Apps and trigger actions via `GET` or `POST` requests.
API Calls can be anything, and the response will be JSON
encoded. The RESTFul API is disabled by default, but is enabled by
setting up the `http` component in the configuration file.
The API can run http or https if desired, separately from the dashboard.

To call into a specific App, construct a URL, use the regular
AppDaemon URL, and append ``/api/appdaemon``, then add the name of the
endpoint as registered by the App on the end, for example:

::

    http://192.168.1.20:5050/api/appdaemon/hello_endpoint

This URL will call into an App that registered an endpoint named ``hello_endpoint``.

Within the App, a call must be made to ``register_endpoint()`` to tell AppDaemon that
the App is expecting calls on that endpoint. When registering an endpoint, the App
supplies a function to be called when a request comes into that endpoint and an optional
name for the endpoint. If not specified, the name will default to the name of the App
as specified in the configuration file.

Apps can have as many endpoints as required, however, the names must be unique across
all of the Apps in an AppDaemon instance.

It is also possible to remove endpoints with the ``deregister_endpoint()`` call, making the
endpoints truly dynamic and under the control of the App.

Here is an example of an App using the API:

.. code:: python

    from appdaemon.plugins.hass import Hass


    class API(Hass):
        def initialize(self):
            self.register_endpoint(my_callback, "test_endpoint")

        def my_callback(self, json_obj, **kwargs):
            self.log(json_obj)

            response = {"message": "Hello World"}

            return response, 200

The callback will accept `GET` or `POST` requests. If the request is a `POST` AppDaemon
will attempt to decode JSON arguments and supply them in the
args parameter. If the method is `GET`, any arguments will also be
supplied via the args parameter. \*\*kwargs will be supplied with
any parameters defined at the time of the `register_endpoint()`.

The response must be a python structure that can be mapped to JSON, or
can be blank, in which case specify ``""`` for the response. You should
also return an HTML status code, that will be reported back to the
caller, ``200`` should be used for an OK response.

As well as any user specified code, the API can return the following
codes:

-  400 - JSON Decode Error
-  401 - Unauthorized
-  404 - App not found
-  500 - Internal Server Error

Below is an example of using curl to call into the App shown above:

.. code:: bash

    $ curl -i -X POST -H "Content-Type: application/json" http://192.168.1.20:5050/api/appdaemon/test_endpoint -d '{"type": "Hello World Test"}'
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=utf-8
    Content-Length: 26
    Date: Sun, 06 Aug 2017 16:38:14 GMT
    Server: Python/3.5 aiohttp/2.2.3

    {"message": "Hello World"}hass@Pegasus:~$

API Security
------------

If you have added a key to the AppDaemon config, AppDaemon will expect
to find a header called "*x-ad-access*" in the request with a value equal
to the configured key. A security key is added for the API with the
``api_key`` directive described in the `Installation
Documentation <INSTALL.html>`__

If these conditions are not met, the call will fail with a return code
of ``401 Not Authorized``. Here is a successful curl example:

.. code:: bash

    $ curl -i -X POST -H "x-ad-access: fred" -H "Content-Type: application/json" http://192.168.1.20:5050/api/appdaemon/api -d '{"type": "Hello World Test"}'
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=utf-8
    Content-Length: 26
    Date: Sun, 06 Aug 2017 17:30:50 GMT
    Server: Python/3.5 aiohttp/2.2.3

    {"message": "Hello World"}hass@Pegasus:~$

And an example of a missing key:

.. code:: bash

    $ curl -i -X POST -H "Content-Type: application/json" http://192.168.1.20:5050/api/appdaemon/api -d '{"type": "Hello World Test"}'
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
need to append it to the end of the URL as follows:

.. code-block:: text

    http://<some.host.com>/api/appdaemon/alexa?api_password=<password>

For more information about configuring Alexa Intents, see the `Home
Assistant Alexa
Documentation <https://home-assistant.io/components/alexa/>`__

When configuring Alexa support for AppDaemon some care is needed. If you are as
most people, you are using SSL to access Home Assistant, there is
contention for the use of the SSL port (443) since Alexa does not allow you
to change this. This means that if you want to use AppDaemon with SSL,
you will not be able to use Home Assistant remotely over SSL. The way
around this is to use NGINX to remap the specific AppDamon API URL to a
different port, by adding something like this to the config:

.. code-block:: text

    location /api/appdaemon/ {
        allow all;
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_redirect http:// http://;
    }

Here we see the default port being remapped to port 5000 which is where
AppDamon is listening in my setup.

Since each individual Skill has its own URL it is possible to have
different skills for Home Assistant and AppDaemon.

Putting it together in an App
-----------------------------

The Alexa App is basically just a standard API App that uses Alexa
helper functions to understand the incoming request and format a
response to be sent back to Amazon, to describe the spoken response and
card for Alexa.

Here is a sample of an Alexa App that can be extended for whatever intents you
want to configure.

.. code-block:: python

    from appdaemon.plugins.hass import Hass

    import random
    import globals

    class Alexa(Hass):
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
                self.log("Received Alexa request: {}, answering: {}".format(intent, speech))
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

            status = "The downstairs temperature is {} degrees fahrenheit,".format(self.entities.sensor.downstairs_thermostat_temperature.state)
            status += "The upstairs temperature is {} degrees fahrenheit,".format(self.entities.sensor.upstairs_thermostat_temperature.state)
            status += "The outside temperature is {} degrees fahrenheit,".format(self.entities.sensor.side_temp_corrected.state)
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
                "Jack just went out for a walk in the neighbourhood",
                "Jack is by his bowl waiting for treats"
            ]

            return random.choice(responses)

Dialogflow API
--------------

Similarly, Dialogflow API for Google home is supported - here is the Google version of the same App. To set up Dialogflow with your google home refer to the `apiai` component in home-assistant. Once it is setup you can use the AppDaemon API as the webhook.

.. code:: python

    from appdaemon.plugins.hass import Hass

    import random
    import globals

    class Apiai(hass.Hass):

        def initialize(self):
            pass

        def api_call(self, data):
            intent = self.get_dialogflow_intent(data)

            if intent is None:
                self.log("Dialogflow error encountered: Result is empty")
                return "", 201

            intents = {
                "StatusIntent": self.StatusIntent,
                "LocateIntent": self.LocateIntent,
            }

            if intent in intents:
                speech = intents[intent](data)
                response = self.format_dialogflow_response(speech)
                self.log("Received Dialogflow request: {}, answering: {}".format(intent, speech))
            else:
                response = self.format_dialogflow_response(speech = "I'm sorry, the {} does not exist within AppDaemon".format(intent))

            return response, 200

        def StatusIntent(self, data):
            response = self.HouseStatus()
            return response

        def LocateIntent(self, data):
            user = self.get_dialogflow_slot_value(data, "User")

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

            status = "The downstairs temperature is {} degrees fahrenheit,".format(self.entities.sensor.downstairs_thermostat_temperature.state)
            status += "The upstairs temperature is {} degrees fahrenheit,".format(self.entities.sensor.upstairs_thermostat_temperature.state)
            status += "The outside temperature is {} degrees fahrenheit,".format(self.entities.sensor.side_temp_corrected.state)
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
                "Jack just went out for a walk in the neighbourhood",
                "Jack is by his bowl waiting for treats"
            ]

            return random.choice(responses)

Plugins
-------

As of version 3.0, AppDaemon has been rewritten to use a pluggable architecture for connection to the systems it monitors.

It is possible to create plugins that interface with other systems, for instance, MQTT support was recently added and it would also be possible to connect to other home automation systems, or anything else for that matter, and expose their operation to AppDaemon and write Apps to monitor and control them.

An interesting caveat of this is that the architecture has been designed so that multiple instances of each plugin can be configured, meaning for instance that it is possible to connect AppDaemon to 2 or more instances of Home Assistant.

To configure additional plugins of any sort, simply add a new section in the list of plugins in the AppDaemon section.

Here is an example of a plugin section with 2 hass instances and 2 dummy instances:

.. code:: yaml

  plugins:
    HASS1:
      type: hass
      ha_key: !secret home_assistant1_key
      ha_url: http://192.168.1.20:8123
    HASS2:
      namespace: hass2
      type: hass
      ha_key: !secret home_assistant2_key
      ha_url: http://192.168.1.21:8123
    MQTT:
      type: mqtt
      namespace: mqtt
      client_host: 192.168.1.20
      client_port: 1883
      client_id: Fred
      client_user: homeassistant
      client_password: my_password

The ``type`` parameter defines which of the plugins are used, and the parameters for each plugin type will be different.
As you can see, the parameters for both hass instances are similar, and it supports all the parameters described in the
installation section of the docs - here I am just using a subset.

Namespaces
----------

A critical piece of this is the concept of ``namespaces``. Each plugin has an optional ``namespace`` directive. If you have more than 1 plugin of any type, their state is separated into namespaces, and you need to name those namespaces using the ``namespace`` parameter. If you don't supply a namespace, the namespace defaults to ``default`` and this is the default for all areas of AppDaemon meaning that if you only have one plugin you don't need to worry about namespace at all.

In the case above, the first instance had no namespace so its namespace will be called ``default``. The second hass namespace will be ``hass2`` and so on.

These namespaces can be accessed separately by the various API calls to keep things separate, but individual Apps can switch between namespaces at will as well as monitor all namespaces in certain calls like ``listen_state()`` or ``listen_event()`` by setting the namespace to ``global``.

Use of Namespaces in Apps
~~~~~~~~~~~~~~~~~~~~~~~~~

Each App maintains a current namespace at all times. At initialization, this is set to ``default``. This means that if you only have a single plugin, you don't need to worry about namespaces at all as everything will just work.

There are 2 ways to work with namespaces in apps. The first is to make a call to ``set_namespace()`` whenever you want to change namespaces. For instance, if in the configuration above, you wanted a particular App to work entirely with the ``HASS2`` plugin instance, all you would need to do is put the following code at the top of your ``initialize()`` function:

.. code:: python

    self.set_namespace("hass2")

Note that you should use the value of the namespace parameter, not the name of the plugin section. From that point on, all state changes, events, service calls, etc. will apply to the ``HASS2`` instance and the ``HASS1`` and ``DUMMY`` instances will be ignored. This is convenient for the case in which you don't need to switch between namespaces.

In addition, most of the API calls allow you to optionally supply a namespace for them to operate under. This will override the namespace set by ``set_namespace()`` for that call only.

For example:

.. code:: python

    self.set_namespace("hass2")
    # Get the entity value from the HASS2 plugin
    # Since the HASS2 plugin is configured with a namespace of "hass2"
    state = self.get_state("light.light1")

    # Get the entity value from the HASS1 plugin
    # Since the HASS1 plugin is configured with a namespace of "default"
    state = self.get_state("light.light1", namespace="default")

In this way it is possible to use a single App to work with multiple namespaces easily and quickly.

A Note on Callbacks
~~~~~~~~~~~~~~~~~~~

One important thing to note, when working with namespaces is that callbacks will honor the namespace they were created with. So if for instance, you create a ``listen_state()`` callback with a namespace of ``default`` then later change the namespace to ``hass1``, that callback will continue to listen to the ``default`` namespace.

For instance:

.. code:: python

    self.set_namespace("default")
    self.listen_state(callback)
    self.set_namespace("hass2")
    self.listen_state(callback)
    self.set_namespace("dummy1")

This will leave us with 2 callbacks, one listening for state changes in ``default`` and one for state changes in ``hass2``, regardless of the final value of the namespace.

Similarly:

.. code:: python

    self.set_namespace("dummy2")
    self.listen_state(callback, namespace="default")
    self.listen_state(callback, namespace="hass2")
    self.set_namespace("dummy1")

This code fragment will achieve the same result as above since the namespace is being overridden, and will
keep the same value for that callback regardless of what the namespace is set to.

User Defined Namespaces
~~~~~~~~~~~~~~~~~~~~~~~

Each plugin has it's own unique namespace as described above, and they are pretty much in control of those
namespaces. It is possible to set a state in a plugin managed namespace which can be used as a temporary
variable or even as a way of signalling other apps using ``listen_state()`` however this is not recommended:

- Plugin managed namespaces may be overwritten at any time by the plugin
- They will likely be overwritten when the plugin restarts even if AppDaemon does not
- They will not survive a restart of AppDaemon because it is regarded as the job of the plugin to reconstruct it's state and it knows nothing about any additional variables you have added. Although this technique can still be useful, for example, to add sensors to Home Assistant, a better alternative for Apps to use are User Defined Namespaces.


A User Defined Namespace is a new area of storage for entities that is not managed by a plugin. UDMs are guaranteed
not to be changed by any plugin and are available to all apps just the same as a plugin-based namespace. UDMs also
survive AppDaemon restarts and crashes, creating durable storage for saving the information and communicating with
other apps via ``listen_state()`` and ``set_state()``.

They are configured in the ``appdaemon.yaml`` file as follows:

.. code:: yaml

    namespaces:
        my_namespace:
          # writeback is safe or hybrid
          writeback: safe
        my_namespace2:
          writeback: hybrid

Here we are defining 3 new namespaces - you can have as many as you want. Their names are ``my_namespace1``, ``my_namespace2`` and ``my_namespace3``. UDMs are written to disk so that they survive restarts, and this can be done in 3 different ways, set by the writeback parameter for each UDM. They are:

- ``safe`` - the namespace is written to disk every time a change is made so will be up to date even if a crash happens. The downside is that there is a possible performance impact for systems with slower disks, or that set state on many UDMs at a time.
- ``hybrid`` - a compromise setting in which the namespaces are saved periodically (once each time around the utility loop, usually once every second- with this setting a maximum of 1 second of data will be lost if AppDaemon crashes.

Using Multiple APIs From One App
--------------------------------

The way apps are constructed, they inherit from a superclass that contains all the methods needed to access a particular plugin. This is convenient as it hides a lot of the complexity by automatically selecting the right configuration information based on namespaces. One drawback of this approach is that an App cannot inherently speak to multiple plugin types as the API required is different, and the App can only choose one API to inherit from.

To get around this, a function called ``get_plugin_api()`` is provided to instantiate API objects to handle multiple plugins, as a distinct objects, not part of the APPs inheritance. Once the new API object is obtained, you can make plugin-specific API calls on it directly, as well as call ``listen_state()`` on it to listen for state changes specific to that plugin.

In this case, it is cleaner not to have the App inherit from one or the other specific APIs, and for this reason, the ADBase class is provided to create an App without any specific plugin API. The App will also use ``get_ad_api()`` to get access to the AppDaemon API for the various scheduler calls.

As an example, this App is built using ADBase, and uses ``get_plugin_api()`` to access both HASS and MQTT, as well as ``get_ad_api()`` to access the AppDaemon base functions.

.. code:: python

    from appdaemon import adbase as ad

    class GetAPI(ad.ADBase):
      def initialize(self):

        # Grab an object for the HASS API
        hass = self.get_plugin_api("HASS")
        # Hass API Call
        hass.turn_on("light.office")
        # Listen for state changes for this plugin only
        hass.listen_state(my_callback, "light.kitchen")

        # Grab an object for the MQTT API
        mqtt = self.get_plugin_api("MQTT")
        # Make MQTT API Call
        mqtt.mqtt_publish("topic", "Payload"):

        # Make a scheduler call using the ADBase class
        adbase = self.get_ad_api()
        handle = adbase.run_in(callback, 20)

By default, each plugin API object has it's namespace correctly set for that plugin, which makes it much more convenient to handle calls and callbacks form that plugin. This way of working can often be more convenient and clearer than changing namespaces within apps or on the individual calls, so is the recommended way to handle multiple plugins of the same or even different types. The AD base API's namespace defaults to "default":

.. code:: python

    # Listen for state changes specific to the "HASS" plugin
    hass.listen_state(hass_callback, "light.office")
    # Listen for state changes specific to the "MQTT" plugin
    mqtt.listen_state(mqtt_callback, "light.office")
    # Listen for global state changes
    adbase.listen_state(global_callback, namespace="global")

API objects are fairly lightweight and can be created and discarded at will. There may be a slight performance increase by creating an object for each API in the initialize function and using it throughout the App, but this is likely to be minimal.

Custom Constraints
------------------

An App can also register its own custom constraints which can then be used in exactly the same way as
App level or callback level constraints. A custom constraint is simply a Python function that returns ``True`` or ``False`` when presented with the constraint argument. If it returns ``True``, the constraint is regarded as satisfied, and the callback will be made (subject to any other constraints also evaluating to ``True``. Likewise, a False return means that the callback won't fire. Custom constraints are a handy way to control multiple callbacks that have some complex logic and enable you to avoid duplicating code in all callbacks.

To use a custom constraint, it is first necessary to register the function to be used to evaluate it using the ``register_constraint()`` API call. Constraints can also be unregistered using the ``deregister_constraint()`` call, and the ``list_constraints()`` call will return a list of currently registered constraints.

Here is an example of how this all fits together.

We start off with a python function that accepts a value to be evaluated like this:

.. code:: python

    def is_daylight(self, value):
        if self.sun_up():
            return True
        else:
            return False

To use this in a callback level constraint simply use:

.. code:: python

        self.register_constraint("is_daylight")
        handle = self.run_every(self.callback, time, 1, is_daylight=1)

Now ``callback()`` will only fire if the sun is up.

Using the value parameter you can parameterize the constraint for more complex behavior and use in different situations for different callbacks. For instance:

.. code:: python

    def sun(self, value):
        if value == "up":
            if self.sun_up():
            return True
        elif value == "down":
            if self.sun_down():
            return True
        return False


You can use this with 2 separate constraints like so:

.. code:: python

        self.register_constraint("sun")
        handle = self.run_every(self.up_callback, time, 1, sun="up")
        handle = self.run_every(self.down_callback, time, 1, sun="down")

Sequences
---------

AppDaemon supports `sequences` as a simple way of reusing predefined steps of commands. The initial usecase for sequences
is to allow users to create scenes within AppDaemon, however they are useful for many other things. Sequences
are fairly simple and allow the user to define 3 types of activities:

- A call_service command with arbitrary parameters
- A configurable delay between steps.
- Pause execution, until an entity has a certain state

In the case of a scene, of course you would not want to use the delay, and would just list all the devices to be switched
on or off, however, if you wanted a light to come on for 30 seconds, you could use a script to turn the light on,
wait 30 seconds and then turn it off. Unlike in synchronous apps, delays are fine in scripts as they will
not hold the apps_thread up.

There are 2 types of sequence - predefined sequences and inline sequences.

Defining a Sequence
~~~~~~~~~~~~~~~~~~~

A predefined sequence is created by adding a ``sequence`` section to your apps.yaml file. If you have apps.yaml split into
multiple files, you can have sequences defined in each one if desired. For clarity, it is strongly recommended that
sequences are created in their own standalone yaml files, ideally in a separate directory from the app argument files.

An example of a simple sequence entry to create a couple of scenes might be:

.. code:: yaml

    sequence:
      office_on:
        name: Office On
        namespace: hass
        steps:
        - homeassistant/turn_on:
            entity_id: light.office_1
            brightness: 254
        - homeassistant/turn_on:
            entity_id: light.office_2
            brightness: 254
      office_off:
        name: Office Off
        steps:
        - homeassistant/turn_off:
            entity_id: light.office_1
        - homeassistant/turn_off:
            entity_id: light.office_2


The names of the sequences defined above are ``sequence.office_on`` and ``sequence.office_off``. The ``name`` entry is optional and is used to provide
a friendly name for HADashboard. The ``steps`` entry is simply a list of steps to be taken. They will be processed in
the order defined, however without any delays the steps will be processed practically instantaneously.

A sequence to turn a light on then off after a delay might look like this:

.. code:: yaml

    sequence:
      outside_motion_light:
        name: Outside Motion
        steps:
        - homeassistant/turn_on:
            entity_id: light.outside
            brightness: 254
        - sleep: 30
        - homeassistant/turn_off:
            entity_id: light.outside

If you prefer, you can use YAML's inline capabilities for a more compact representation that looks better for longer sequences:

.. code:: yaml

    sequence:
      outside_motion_light:
        name: Outside Motion
        steps:
        - homeassistant/turn_on: {"entity_id": "light.outside", "brightness": 254}
        - sleep: 30
        - homeassistant/turn_off: {"entity_id": "light.outside"}

Looping a Sequence
~~~~~~~~~~~~~~~~~~~

Sequences can be created that will loop forever by adding the value ``loop: True`` to the sequence:

.. code:: yaml

    sequence:
      outside_motion_light:
        name: Outside Motion
        loop: True
        steps:
        - homeassistant/turn_on: {"entity_id": "light.outside", "brightness": 254}
        - sleep: 30
        - homeassistant/turn_off: {"entity_id": "light.outside"}

This sequence once started will loop until either the sequence is canceled, the app is restarted or terminated, or AppDaemon is shutdown.

Not only can the whole sequence be looped, but steps can be looped to if wanting to run a certain step multiple times.
Below is an example of increasing the volume of a device 5 times with 0.5 interval

.. code:: yaml

    sequence:
      setup_tv:
        name: Setup TV
        namespace: hass
        steps:
        - homeassistant/turn_on:
            entity_id: switch.living_room_tv

        - sleep: 30

        - remote/send_command:
            entity_id: roku.living_room
            loop_step:
                times: 5
                interval: 0.5

Defining a Sequence Call Namespace
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, a sequence will run on entities in the current namespace, however , the namespace can be specified on a per call
basis if required. Also it can be specified at the top tier level, allowing for all service calls in the sequence to use the same namespace

.. code:: yaml

    sequence:
      office_on:
        name: Office On
        namespace: hass
        steps:
        - homeassistant/turn_on:
            entity_id: light.office_1
            brightness: 254
            namespace: "hass1"
        - homeassistant/turn_on:
            entity_id: light.office_2
            brightness: 254
            namespace: "hass2"

Just like app parameters and code, sequences will be reloaded after any change has been made allowing scenes to be
developed and modified without restarting AppDaemon.

Sequence Commands
~~~~~~~~~~~~~~~~~

In addition to a straightforward service name plus data, sequences can take a few additional commands:

- sleep - pause execution of the sequence for a number of seconds. e.g. `sleep: 30` will pause the sequence for 30 seconds
- sequence - run a sub sequence. This must be a predefined sequence, and cannot be an inline sequence. Provide the entity name of the sub-sequence to be run, e.g. `sequence: sequcene.my_sub_sequence`. Sub sequences can be nested arbitrarily to any desired level.

Sequence Wait State
~~~~~~~~~~~~~~~~~~~

In addition to a straightforward service name plus data, sequences can paused, to continue after an entity's state is a condition.
This allows formore powerful use of sequence calls, for example you want to turn activate the conditioner, only after the window has been shut.
Entities can be created in user defined namespaces, which will hold the state of conditions of interest and the sequence made to make use of the entity.

.. code:: yaml

    sequence:
      air_condition_on:
        name: Air Con On
        namespace: mqtt
        steps:
        - mqtt/publish:
            topic: "hermes/tts"
            payload: "Turning on the AirCon, ensure windows are shut"

        - wait_state:
            entity_id: condition.living_room_window
            state: "closed"
            timeout: 60 # defaults to 15 minutes
            namespace: rules

        - mqtt/publish:
            topic: "air_condition/state"
            payload: "on"

Running a Sequence
~~~~~~~~~~~~~~~~~~

Once you have the sequence defined, you can run it in one of 2 ways:

- using the ``self.run_sequence()`` api call
- Using a sequence widget in HADashboard

A call to run the above sequence would look like this:

.. code:: python

    handle = self.run_sequence("sequence.outside_motion_light")

The handle value can be used to terminate a running sequence by supplying it to the ``cancel_sequence()`` call.

When an app is terminated or reloaded, all running sequences that it started are immediately terminated. There is no way
to terminate a sequence started using HADashboard.

Inline Sequences
~~~~~~~~~~~~~~~~

Sequences can be run without the need to predefine them by specifying the steps to the ``run_sequence()`` command like so:

.. code:: python

     handle = self.run_sequence([
            {'light/turn_on': {'entity_id': 'light.office_1', 'brightness': '5', 'color_name': 'white', 'namespace': 'default'}},
            {'sleep': 1},
            {'light/turn_off': {'entity_id': 'light.office_1'}},
            ])

Keeping Your IDE Happy
----------------------

Although it is possible to develop AppDaemon apps using a straight forward text editor, most users prefer to use some flavor of IDE.
In order to simplify App development however, AppDaemon hides some of the complexity of import paths which makes for simpler coding
but does have the side effect of confusing modern IDEs that are much stricter with import paths, and will show errors for modules
that don't conform to these rules, and will not understand enough about the import paths to supply helpful information about AppDaemon's
API. Fortunately however, with a few simple steps, the IDE can be persuaded to work as desired. In addition, AppDaemon's APIs now
have full type hints to make use of a modern IDE a lot easier and more helpful. This capability has been tested in Microsoft's VS Code but these
steps should apply equally to other IDEs such as PyCharm.

To set your IDE up properly there are a few initial steps, and a couple of rules to follow.

Initial Setup
~~~~~~~~~~~~~

In order for your IDE to properly understand AppDaemon's API, we need to give the IDE access to AppDaemon's code, although this is not normally
necessary for developing apps. The way to do this is to simply use `pip` to install AppDaemon in the virtual environment that your IDE is using.
How this works varies between IDEs, but once you have worked out which virtual environment to target, simply activate it then use `pip`` to install
AppDaemon:

.. code-block:: shell

    $ source /path/to/venv/bin/activate
    $ pip install appdaemon

After this step, your IDE will have access to the code for AppDaemon's APIs and will understand how to assist with error checking and completions etc.

Import Statements
~~~~~~~~~~~~~~~~~

For your IDE to be able to link things appropriately, it needs to be pointed at the interpreter you are using, with
AppDaemon installed in it. This is usually done by setting the interpreter in the IDE's settings, and pointing it at the
virtual environment you are using.

The AppDaemon API classes can be imported as in the below example, or any other standard way you prefer.

.. code:: python

    from appdaemon import adbase as ad      # Minimalist app base
    from appdaemon.adapi import ADAPI       # Basic API
    from appdaemon.plugins.hass import Hass # Home Assistant-specific API
    from appdaemon.plugins.mqtt import Mqtt # MQTT-specific API

Imports of other python modules/packages from your apps can be done in the standard python ways. See the
`section on the app directory <#appdir-structure>`__ for more information.

With these preparations in place your IDE should give you correct error reporting and completion of API functions along
with type hints and help text.
