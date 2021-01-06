Change Log
==========

4.0.6
-----

**Features**

- Added ability for apps to create namespaces, and remove the created namespace. This namespaces are persistent by default
- Added ability to persist plugin entities. This can be usefule for example if wanting to persist entities within MQTT namespace
- Moved the `appdaemon` reladed services to the `admin` namespace. So no more `appdaemon` namespace
- Added services for creating, editting, removing, enabling, disabling apps
- Added ability to receive binary payload from MQTT broker
- Added `cchardet <https://pypi.org/project/cchardet>`__ and `aiodns <https://pypi.org/project/aiodns>`__ to improve aiohttp speed
- Added the ability to submit tasks to executor threads

**Fixes**

- Documentation fixes - contributed by `Ross Rosen <https://github.com/rr326>`__
- Allowed for both multi and single level MQTT wildcard subscription
- Diabled the ability to use a "." in app name. Contributed by `Xavi Moreno <https://github.com/xaviml>`__

**Breaking Changes**

- If using user defined namespace, there is need to delete the present ones in the ``namespaces`` directory.
- Due to the removal of the `appdaemon` namespace, if anyone was manaully making a service call using it, will need to be updated
- ``binary`` is now a reserved keyword argument used when listening to MQTT events
- When using ``wildcard`` to listen for events within an app, only those used to subscribe to the broker can be used. so if using ``camera/#`` to subscribe to all camera related topics, AD will not recognise ``camera/front-door/#`` as a valid wildcard when listening for events; unless ``camera/front-door/#`` was used for subscription itself.
- Moved the local static folder for serving static files from `web` to `www`. If using ``web`` already, simply add it to `static_dirs` in the ``http`` component as described `here <https://appdaemon.readthedocs.io/en/latest/CONFIGURE.html#configuring-the-http-component>`__

4.0.5 (2020-08-16)
------------------

**Features**

None

**Fixes**

- Fixed a duo of bugs that left entities lying around in the AUI and AD's internals tat eventually led to slowdown and crash

**Breaking Changes**

None

4.0.4 (2020-07-11)
------------------

**Features**

- All module dependencies pinned to exact versions for better environmental predictability
- Bump pyyaml to 5.3
- Bump yarl to 1.4.2
- Bump bcrypt to 3.1.7
- Bump jinja2 to 2.10.3
- Bump aiohttp-jinja2 to 1.2.0
- Bump deepdiff from 4.0.9 to 4.2.0
- Bump jinja2 from 2.11.0 to 2.11.1
- Bump deepdiff from 4.2.0 to 4.3.1
- Bump pygments from 2.5.2 to 2.6.1
- Add Azure pipelines for Black and Flake - contributed by `Bas Nijholt <https://github.com/basnijholt>`__
- Added service call for ``remove_entity``
- Added ability to use ``now`` in ``run_every``. Also seconds can be added by simply using ``now+10`` for example
- Presence convenience functions now support a ``person`` flag to use person entities rather than device trackers for presence detection
- ``constrain_person`` constraints added to support person entities
- Add stream support for SockJS
- Dashboard component now only sends event updates for relevant dashboard entities rather than broadcasting all state_change events
- Admin UI now breaks out App instance and lifetime callback stats separately
- Convert admin and dashboard to get_state from stream
- Increase default work factor for password hashes to 12
- Added `add_entity` api call, alongeside `state/add_entity` service call
- Added the ability to remove plugin entities like `HA` when using the `remove_entity` api
- Cleanup sequences when modified. This ensures removed sequences are also removed from the Admin UI and AD
- Added support to use environment variables using the `!env_var` tag, if not wanting to use the `!secrets` tag
- Additional format for time travel start and end times accepted
- Added the ability to specify a callback to hass get_history. This way,  large amount of data can be retrieved from the database, without AD cancelling the task
- Added retry_secs parameter to the hass plugin

**Fixes**

- Re-added support for SSL in the http module (should also fix dialogflow)
- Add openssl-dev package to docker image (required for RPI)
- Fixed up socketio support to work with the new stream semantics
- Fixed a bug that allowed multiple copies of an App to run if there was an error in the signature of terminate()
- AppDaemon's REST API no longer needs to be active to use the dashboard or Admin interfaces
- Fix tzdata error in docker build for RPI - contributed by `Guy Khmelnitsky <https://github.com/GuyKh>`__
- Fix for `get_tz_offset()` not working in some circumstances - contributed by `sillyfrog <https://github.com/sillyfrog>`__
- Added some locking to prevent array size change errors
- Fix for registering services created in HA, after it had started
- Added additional logic to wait for full HASS startup

**Breaking Changes**

- Changed ``websocket_connected`` and ``websocket_disconnected`` events to ``stream_connected`` and ``stream_disconnected`` respectively
- Changed the `get_history` api, as `entity_id` has been removed from the api

4.0.3 (2020-02-29)
------------------

**Features**

- Pinned astral to v1.10.1

**Fixes**

- Pinned astral to prevent a bug in the latest v2 astral

**Breaking Changes**

None

4.0.2 (2020-02-28)
------------------

**Features**

None

**Fixes**

- Fixed a critical bug that cause multiple scheduler errors during a leap year - contributed by `Chad McCune <https://github.com/chadmccune>`__

**Breaking Changes**

None



4.0.1
-----

**Features**

None

**Fixes**

- Fixed an issue, where when ``http`` is disabled in ``appdaemon.yaml``, AD is unable to start
- Fixed an issue that prevented dashboards from working on older iPads

**Breaking Changes**

None

4.0.0 (2020-01-12)
------------------

**Features**

- Added events for when an app is initialized or terminated
- Added `event_fire` service call
- Added `production_mode` service call
- Added `list_services` api call
- Added the ability to fire an event callback only once, using the `oneshot` flag
- Added the ability to use async functions as endpoint callback
- Added the ability for ``input_select`` to auto-update when the options changes, without need of refreshing the browser page
- Added events for when a websocket client connects and disconnects
- Added the ability for apps to register web routes, thereby utilizing AD's internal web server
- Added static folder `web`, which can used to serve content like images using AD's internal web server
- Added ability for users to define static folders, which can used to serve content like images using AD's internal web server
- Added support for python 3.8

**Fixes**

- Fixed issue where the user could potentially create entities in `admin`, `global` or `appdaemon` namespaces

**Breaking Changes**

None

4.0.0 Beta 2 (2019-10-19)
-------------------------

**Features**

- Added a ``timeout`` parameter to ``listen_state()`` and ``listen_event()`` to delete the callback after a pre-determined interval.
- Added render_template() handling
- global_modules can now be declared in multiple yaml files
- It is now possible to inject arbitrary headers in served http content
- Updated camera widget now supports streams and token refreshing
- Added input_text and input_datetime widgets
- Added the ability to control the number of threadpool workers
- Each time a new service is registered, a ``service_registered`` event is fired, which can be picked up by apps
- Added support for async apps
- Added authorization to stream as well as command semantics for various functions
- Added sequences
- Added sequence widget
- Added app access to dashboard directory using ``self.dashboard_dir``
- List of available dashes is now alphabetically sorted
- Changed namespaces implementation to use shelve instead of JSON enabling non JSON-serializable objects to be stored and also potential performance increases  - contributed by `Robert Schindler <https://github.com/efficiosoft>`__
- MDI updated to version 4.4.95 - contributed by `Roeland Van Lembergen <https://github.com/clayhill>`__

**Fixes**

- Fixed a bug in global_modules that caused a exception
- Fixed icon bug in weather widget - contributed by `Roeland Van Lembergen <https://github.com/clayhill>`__

**Breaking Changes**

- ``timeout`` is now an official parameter to ``listen_state()`` and ``listen_event()``. If you were using ``timeout`` in your kwargs section for either you should rename that parameter.
- The camera widget has changed parameters - check the docs for details
- Moved the ``log events`` from global to ``admin`` namespace. if ``listen_log`` is just used for listening to logs, it shouldn't matter
- If you have used persistent namespaces in the previous beta it is necessary to delete all saved namespaces by removing all files in the ``namespaces`` subdirectory under your appdaemon config directory

4.0.0 Beta1 (2019-08-30)
------------------------

**Features**

- Apps can now use a simplified version of the import statement e.g. ``import hassapi as hass`` or ``import mqttapi as mqtt``. The existing import method will continue to work.
- Apps can now use multiple plugin APIs with the ``get_plugin_api()`` function
- Added ``ADBase`` superclass for apps that want to use the ``get_plugin_api()`` style of coding
- Scheduler rewritten to be more efficiant and allow for microsecond resolution
- ``listen_log()`` now sends AppDaemon system messages and has the option to set a log level.
- Bumped aiohttp to v3.4.4
- Added callback locking decorators
- Rearchitected the work Q to allow App pinning and avoid re-entrant and concurrent code if desired
- Implemented multiple worker Ques to avoid Head of Line blocking
- API Calls to control app pinning
- Added the ``run_in_thread()`` api call - with assistance from `Odianosen Ejale <https://github.com/Odianosen25>`__
- reworked log listening functions to be more robust and added the ability to have multiple callbacks per app
- Refactored plugin APIs to remove duplication
- Moved ``constrain_days`` from being Hass only to all app, regardless of plugin used
- Added checking for overdue threads
- Added error checking for callback signatures
- Added app attributes that allows to access AD's ``config`` and ``apps`` directories within apps
- Added ``parse_datetime()``
- ``run_once()``, ``run_at()`` and ``run_daily()`` now optionally take ``parse_time()`` or ``parse_datetime()`` style arguments for specifying time
- Refactored appdaemon.py for greater readability and easier maintenance
- Expanded on the ability to trigger ``listen_state`` callbacks immediately using the ``immediate`` flag, without need of specifying the ``new`` nor ``duration`` parameter.
- Allowed to make use of ``attribute`` when using the ``immediate`` flag in ``listen_state``
- Added initial version of the Admin Interface
- Added User Defined Namespaces
- Rewrote logging to include user defined logs and formats
- Added a unified http component to handle API, ADMIN and DASHBOARD access on a single port
- Added startup conditions to the HASS plugin
- Added duplicate filtering for logs
- Added standalone pidfile functionality
- Added the ability to delete an AD app generated entity from any namespace
- Added the ability to get the history of entities from HASS database
- Added the ability to force a start of the MQTT plugin, even if not connected to broker at startup
- Added the ability to set AD's ``production_mode`` from within apps
- Added the ability to start, stop, restart and reload apps from either other apps or REST API
- Added the ability to register app services
- Added sensors for different internal state of AD, that can be read by apps
- Added Person widget
- Much reworking of docs
- Added ``register_dependency()`` for dynamic dependencies in apps
- Added MQTT support for setting TLS version - contributed by `Miguel <https://github.com/mdps>`__
- Added support for socketio for older tablet devices - inspired by `algirdasc <https://github.com/algirdasc>`__ and `zarya <https://github.com/zarya>`__
- Added support for ``default`` and ``copy`` parameters in ``get_state()`` api call - contributed by `Robert Schindler <https://github.com/efficiosoft>`__
- added a switch to disable the encoding of every log message to ascii - contributed by `Ben Lebherz <https://github.com/benleb>`__
- Various YAML fixes and refactoring - contributed by `Rolf Schäuble <https://github.com/rschaeuble>`__
- Allow more natural addition of commandline arguments to Docker and allow spaces - contributed by `Christoph Roeder <https://github.com/brightdroid>`__
- Allowed for subscribing to MQTT events using wildcards. e.g. ``homeassistant/#`` - contributed by `Odianosen Ejale <https://github.com/Odianosen25>`__
- Allow to specify a MQTT message to be sent when AD shutdowns cleanly e.g. ``offline``
- MQTT Retain setting for birth and will messages - contributed by `Clifford W. Hansen <https://github.com/cliffordwhansen>`__
- Added Note on long lived tokens for Docker users -  contributed by `Bob Anderson <https://github.com/rwa>`__
- Documentation fixes - contributed by `Johann Schmitz <https://github.com/ercpe>`__
- Documentation fixes - contributed by `Brendon Baumgartner <https://github.com/bbrendon>`__
- Documentation fixes - contributed by `Quentin Favrie <https://github.com/tseho>`__
- Documentation fixes, updating and cleaning - contributed by `Humberto Rodríguez A. <https://github.com/rhumbertgz>`__
- Added the ability to set title 2 as friendly name in widgets -  contributed by `Radim <https://github.com/rds76>`__
- Added the ability to listen to ``state_change`` events, without using listen_state() -  contributed by `Thomas Delaet <https://github.com/thomasdelaet>`__
- APIAI updated to dialog flow - contributed by `engrbm87 <https://github.com/engrbm87>`__

**Fixes**

- Fixes to listen_state() oneshot function
- Fixes to listen_state() oneshot function when duration is used
- Fixes to listen_state() function when it fires even when new and old states are same
- Fixed an issue causing incorrect busy thread counts when app callbacks had exceptions
- Fixed an issue of when MQTT Plugin not connected to broker, and it holds up AD startup
- Fix to Forecast min/max in weather widget - contributed by `adipose <https://github.com/adipose>`__
- Fix climate widget docs - contributed by `Rene Tode <https://github.com/ReneTode>`__
- Fix to harmonize ``units`` vs ``unit``  - contributed by `Rene Tode <https://github.com/ReneTode>`__
- Added missing import in sound.py example   - contributed by `cclaus <https://github.com/cclauss>`__
- Fix for run_once() - contributed by `engrbm87 <https://github.com/engrbm87>`__
- Fix for onclick not working on IE11 - contributed by `jgrieger1 <https://github.com/jgrieger1>`__
- Fixed issue of AppDaemon loading all ``.yaml`` files, even those starting with a ``.`` which are hidden or binary files. Contributed by `fhirschmann <https://github.com/fhirschmann>`__
- Fix for error generated when a none existent schedule timer is passed to ``info_timer``
- Fix for ``log_type`` flag in ``listen_log`` callback
- Relative paths for appdaemon's config directory now work correctly
- Fix to Dialogflow after format changes
- MQTT fix to subscribing using wildcards - contributed by `Daniel Lashua <https://github.com/dlashua>`__

**Breaking Changes**

- appapi.py has been renamed to adbase.py, and the contained superclass ha been renamed from AppDaemon to ADBase. This should only be a breaking change if you were using unpublished interfaces!
- Time travel semantics have changed to support faster scheduling.
- ``plugin_started`` and ``plugin_stopped`` now go to the appropriate namespace for the plugin and are no longer global
- Apps are no longer concurrent or re-entrant by default. This is most likely a good thing.
- Changed the signature of ``listen_log()`` callbacks
- ``cancel_listen_log()`` now requires a handle supplied by the initial ``listen_log()``
- Removed Daemonize support - please use sysctl instead
- ``set_app_state()`` is deprecated - use ``set_state()`` instead and it should do the right thing
- ``dash_compile_on_start`` now defaults to true
- The ``log`` section of appdaemon.yaml has been deprecated and must be replaced by the new ``logs`` section which has a different format to allow for user defined logs and greater flexibility in formatting etc.
- API no longer has a separate port, all access is configured via the new unified http component
- API has its own top level configuration section
- Some dashboard parameters moved to the ``HTTP`` section and renamed
- ``dash_compile_on_start`` renamed to ``compile_on_start``
- ``dash_force_compile`` renamed to ``force_compile``
- Due to the new ``log`` parameter to allow apps to use user defined logs, any previous parameters named ``log`` should be renamed
- Due to a fix for ``info_timer``, this function can now return ``None`` if the timer handle is invalid
- As a result of a change in the way AD auto generates MQTT client status topic, if not defined previously the new topic needs to be used
- In the appdaemon configuration section, ``latitude``, ``longitude``, ``elevation`` and ``timezone`` are now mandatory
- MQTT client status api change from ``clientConnected`` to ``is_client_connected``

3.0.4 (2019-04-04)
------------------

**Fixes**

- Use yaml.Safeloader to work around known security issue with PyYaml - contributed by `mvn23 <https://github.com/mvn23>`__
- Unpinned PyYaml

3.0.3 (2019-04-02)
------------------

**Fixes**

- Pinned PyYaml to 3.13 to avoid a known issue

3.0.2 (2018-10-31)
------------------

**Features**

- added ``set_textvalue()`` api call.
- added ``app_init_delay`` to delay App Initialization
- Added ability to register apps to receive log entries
- Added instructions for running a dev build
- Added support for Long Lived Access Tokens
- Updated MDI Icons to 3.0.39
- Updated Font Awesome Icons to 5.4.2
- Added MQTT Plugin - contributed by `Tod Schmidt <https://github.com/tschmidty69>`__
- Many MQTT Plugin enhancements - contributed by `Odianosen Ejale <https://github.com/Odianosen25>`__
- Added ``entitypicture`` widget - contributed by `hwmland <https://github.com/hwmland>`__
- Docker start script will now check recursively for additional requirements and install them - contributed by `Kevin Eifinger <https://github.com/eifinger>`__
- Added ability to set units explicitly in widgets - contributed by `Rene Tode <https://github.com/ReneTode>`__
- Added --upgrade to pip3 call for recursive requirements.txt scanning - contributed by `Robert Schindler <https://github.com/efficiosoft>`__
- Added the ability to pass stringified JSON parameters to service calls - contributed by `Clyra <https://github.com/clyra>`__

**Fixes**

- Fixed incorrect service call in ``set_value()``
- Enforce domain name in rss feed target to avoid issues with other functions
- Previously deleted modules will now be correctly reloaded to reflect changes
- Fixed a bug in ``get_scheduler_entries()``
- Prevent periodic refresh of HASS state from overwriting App created entities - contributed by `Odianosen Ejale <https://github.com/Odianosen25>`__
- Fix to honor cert_path - contributed by `Myles Eftos <https://github.com/madpilot>`__
- Run AD in docker as PID 1 - contributed by `Rolf Schäuble <https://github.com/rschaeuble>`__
- Fix encoding error in log messages - contributed by `Markus Meissner <https://github.com/daringer>`__
- Fix a bug in ``get_plugin_meta()`` - contributed by `Odianosen Ejale <https://github.com/Odianosen25>`__
- Various Doc corrections and additions - contributed by `Odianosen Ejale <https://github.com/Odianosen25>`__
- Various fixes in the Docker docs - contributed by `Simon van der Veldt <https://github.com/simonvanderveldt>`__
- Namespace fixes - contributed by `Odianosen Ejale <https://github.com/Odianosen25>`__
- More namespace fixes - contributed by `Odianosen Ejale <https://github.com/Odianosen25>`__
- Fixes of the namespaces fixes ;) - contributed by `Brian Redbeard <https://github.com/brianredbeard>`__
- Fix typo in sample systemd config - contributed by `Evgeni Kunev <https://github.com/kunev>`__
- Fix to cert path config - contributed by `nevalain <https://github.com/nevalain>`__

**Breaking Changes**

- RSS target names must now consist of a domain as well as the target name, e.g. ``rss.cnn_news``
- SSE Support has been removed
- Use of ha_key for authentication is deprecated and will be removed at some point. For now it will still work
- Many Font Awesome Icon names have changed - any custom icons you have on dashboards will need to be changed to suit - see `docs <https://appdaemon.readthedocs.io/en/latest/DASHBOARD_CREATION.html#a-note-on-font-awesome-upgrade>`__ for more detail.

While working through the upgrade it is strongly advised that you clear your browser cache and force the recompilation of all of your dashboards to flush out references to old icons. This can be done by manually removing the ``compiled`` subdirectory in ``conf_dir``, specifying ``recompile=1`` in the arguments to the dashboard, or setting the hadashboard option ``dash_compile_on_start`` to ``1``.

3.0.1 (2018-04-18)
------------------

**Features**

- Added Production Mode to disable checking of App config or code changes
- RSS Feed can now optionally show a description for each story
- Disabling of zooming and double tap zooming on iOs devices is now optional via the ``scaling`` dashboard argument
- Exiting from the commandline with ctrl-c will now cleanly terminate apps
- Sending SIGTERM to an appdaemon process will cause a clean shutdown, including orderly termination of all apps in dependency order
- Added extra checking for HASS Initialization to prevent a race condition in which metadata could not be read
- Weather widget adds the ability to change sensors, more dynamic units, forecast option, icon options, option to show Rain/Snow depending on precip_type sensor (and change icons), wind icon rotates according to wind bearing - contributed by `Marcin Domański <https://github.com/kabturek>`__

**Fixes**

- Fixed a problem in the Docker initialization script
- Fixed an parameter collision for events with a parameter ``name`` in ``listen_event()``
- Grammar corrections to docs, and a fix to the stop code - contributed by `Matthias Urlichs <https://github.com/smurfix>`__

**Breaking Changes**

- iOS Scaling and tap zooming is no longer disabled by default

3.0.0 (2018-03-18)
------------------

**Features**

- API 200 responses are now logged to the access file
- Add meta tags to prevent double tap zoom on iOS

**Fixes**

- Re-added set_app_state() to the API

**Breaking Changes**

None

3.0.0b5 (2018-03-05)
--------------------

**Features**

 - Added additional error checking for badly formed RSS feeds

**Fixes**

 - Fixed a bug that broke binary_sensor widget.
 - Fixed a bug that broke retries when connecting to Home Assistant
 - Fixed a bug that could cause lockups during app initialization
 - Fixed a bug for Docker that prevented the initial config from working correctly - contributed by `mradziwo <https://github.com/mradziwo>`__
 - Grammar corrections to docs, and a fix to the stop code - contributed by `Matthias Urlichs <https://github.com/smurfix>`__

**Breaking Changes**

None

3.0.0b4 (2018-03-03)
--------------------

**Features**

- Single App dependencies can now be specified on the dependency line itself and don't have to be a list of size 1
- Added ``get_ad_version()``, and ``ad_version`` to the config dictionary
- Added filters for Apps
- Added global module dependency tracking
- Added plugin reload app control
- Added icon widget

**Fixes**

- Apps now correctly reload when HASS comes back up after a restart
- ``get_error()`` now properly returns the error log logger object
- ``get_hass_config()`` is now correctly named
- ``app_args`` now correctly returns args for all apps
- ``get_state()`` now returns fields from the attributes dictionary in preference to the top level dictionary if there is a clash. In particular, this now means it is easier to iterate through group members
- Fixed a bug preventing an objects ``terminate()`` from being called when deleted from apps.yaml
- Fixed a bug in which object info was not being cleaned out at object termination
- Fixed an issue preventing dashboard updates on python 3.6

**Breaking Changes**

None

3.0.0b3 (2018-02-11)
--------------------

**Features**

- Added ``javascript`` widget
- Upgraded MDI Icons to 2.1.19
- Add separate log for diagnostic info
- Per-widget type global parameters
- App level dependencies
- ``listen_state()`` now returns the handle to the callback
- added ``oneshot`` option to ``listen_state()``
- Add step parameter to climate widget - contributed by `Adrian Popa <https://github.com/mad-ady>`__
- Add internationalization options to clock widget - contributed by `Adrian Popa <https://github.com/mad-ady>`__
- Doc improvements - contributed by `Marco <https://github.com/marconett>`__

**Fixes**

- Fixed image path for android devices
- Fix a bug with the time parameter for images
- Fixed ``disable_apps``
- Fixed a bug in ``get_state()`` with ``attributes=all`` returning just the attributes dictionary instead of the entire entity.

**Breaking Changes**

- In apps.yaml, dependencies should now be a proper yaml list rather than a comma separated string
- Dependencies now refer to individual apps rather than modules

3.0.0b2 (2018-01-27)
--------------------

**Features**

- Make int args in appdaemon.yaml a little more robust
- Improve handling for missing app files
- Module loading enhancements
- Moved from requests to aiohttp client for better async behavior
- Added thread monitoring for worker threads
- Give more informative error message if AppDaemon can't locate a valid config dir

**Fixes**

- Fixed a bug that could cause multiple apps.yaml changes or additions to be ignored
- Fixed a bug causing listen_state() callbacks with ``duration`` set to fire immediately
- Pinned yarl library to fix an issue with Docker build
- Fixed a couple of potential event loop hold ups
- Fixed a bug in password security for HADashboard service and state calls
- Changes to apps.yaml now also force a reload of dependent modules
- ``exclude_dirs`` now applies to yaml files as well as python files
- Fixed broken icon on HADashboard logon screen
- Fixed a bug preventing the media title from showing in the media player

**Breaking Changes**

- App modules not listed in an apps.yaml file will no longer be loaded. Python modules may still be imported directly if they are in a directory in which other apps reside.
- ``cert_path`` is deprecated. With the replacement of requests with aiohttp, it is now sufficient to set ``cert_verify`` to False to use a self signed certificate.
- Initial dashboard loads may be slower on less powerful hardware when using password authentication. Updating after the initial load is unaffected.

3.0.0b1 (2018-01-12)
--------------------

**Features**

- Refactored pluggable architecture
- Support for multiple HASS instances
- Custom constraints
- Namespaces
- Path of Secret file can now be specified
- apps.yaml can now be split across multiple files and directories
- Apps can now establish loading priorities to influence their loading order
- IFRAME Refreshes should now be more reliable
- Added calls to access the underlying logger objects for the main and error logs
- Add the ability to ignore specific subdirectories under appdir
- Added error handling for apps that can't be read or have broken links
- Added london Underground Widget - contributed by `mmmmmmtasty <https://github.com/mmmmmtasty>`__
- Added ability to display sensor attributes - contributed by `mmmmmmtasty <https://github.com/mmmmmtasty>`__
- Added Weather Summary Widget - contributed by `mmmmmmtasty <https://github.com/mmmmmtasty>`__
- Added Sticky navigation - contributed by `Lars Englund <https://github.com/larsenglund>`__
- Added Input Select widget - contributed by `Rene Tode <https://github.com/ReneTode>`__
- Redesigned Input Number widget (old is still available as ``input_slider``) - contributed by `Rene Tode <https://github.com/ReneTode>`__
- Added Radial widget - contributed by `Rene Tode <https://github.com/ReneTode>`__
- Added Temperature widget - contributed by `Rene Tode <https://github.com/ReneTode>`__
- Added container style to sensor widget - contributed by `Rene Tode <https://github.com/ReneTode>`__

**Fixes**

- Fixed an issue with the compiled directory not being created early enough

**Breaking Changes**

- Apps need to change the import and super class
- ``info_listen_state()`` now returns the namespace in addition to the previous parameters
- AppDaemon no longer supports python 3.4
- --commtype command line argument has been moved to the appdaemon.cfg file
- The "ha_started" event has been renamed to "plugin_started"
- RSS Feed parameters have been moved to the hadashboard section
- Log directives now have their own section
- `AppDaemon` section renamed to `appdaemon`, `HADashboard` section renamed to `hadashboard`
- Accessing other Apps arguments is now via the ``app_config`` attribute, ``config`` retains just the AppDaemon configuration parameters
- Plugins (such as the HASS plugin now have their own parameters under the plugin section of the config file
- The !secret directive has been moved to the top level of appdaemon.yaml
- the self.ha_config attribute has been replaced by the ``self.get_hass_config()`` api call and now supports namespaces.
- apps.yaml in the config directory has now been deprecated
- select_value() has been renamed to set_value() to harmonize with HASS
- It is no longer possible to automatically migrate from the legacy cfg style of config, and support for cfg files has been dropped.


2.1.12 (2017-11-07)
-------------------

**Features**

None

**Fixes**

- Fixed passwords causing 500 error on HADashboard - contributed by `wchan.ranelagh <https://community.home-assistant.io/u/wchan.ranelagh/summary>`__

**Breaking Changes**

None

2.1.11 (2017-10-25)
-------------------

**Features**

None

**Fixes**

- Fixed an issue with ``run_at_sunset()`` firing multiple times

**Breaking Changes**

None

2.1.10 (2017-10-11)
------------------

**Features**

- Renamed the HADashboard input_slider to input_number to support HASS' change
- Fixed ``select_value()`` to work with input_number entities

**Fixes**

None

**Breaking Changes**

The ``input_select`` widget has been renamed to ``input_number`` to support the change in HASS

2.1.9 (2017-09-08)
------------------

**Features**

None

**Fixes**

- broken `disable_apps` temporary workaround

**Breaking Changes**

None

2.1.8 (2017-09-08)
------------------

**Features**

- Refactor of dashboard code in preparation for HASS integration
- Addition of check to highlight excessive time in scheduler loop
- Split app configuration out into a separate file in preparation for HASS integration
- Enhance widget API to handle all event types instead of just click
- Add example HADashboard focused Apps for Oslo City Bikes, Caching of local AppDaemon events, Monitoring events and logging, Google Calendar Feed, Oslo Public Transport, YR Weather - contributed by `Torkild Retvedt <https://github.com/torkildr>`__

**Fixes**

- Fixed a bug that gave a spurious "text widget not found" error

**Breaking Changes**

- App configuration is now separate from AppDaemon, HASS and HADashboard configuration
- The Widget API has changed to accommodate different event types and now needs an ``action`` parameter to specify what the event type to be listened for is


2.1.7 (2017-08-20)
------------------

**Features**

- Converted docs to rst for better readthedocs support
- Added custom widget development
- Enhanced API support to handle multiple endpoints per App
- Added helper functions for Google Home's APP.AI - contributed by `engrbm87 <https://github.com/engrbm87>`__
- Added ``immediate`` parameter to listen state to trigger immediate evaluation of the ``delay`` parameter

**Fixes**

None

**Breaking Changes**

- Existing API Apps need to register their endpoint with `register_endpoint()`

2.1.6 (2017-08-11)
------------------

**Features**

-  API now runs on a separate port to the dashboard

**Fixes**

None

**Breaking Changes**

-  API requires the ``api_port`` configuration value to be set and now
   runs on a different port from the dashboard
-  SSL Setup for API now requires ``api_ssl_certificate`` and
   ``api_ssl_key to be set``
-  ``ad_key`` has been renamed to ``api_key``

2.1.5 (2017-08-10)
------------------

**Features**

None

**Fixes**

None

**Breaking Changes**

-  ``get_alexa_slot_value()`` now requires a keyword argument for
   slotname

2.1.4 (2017-08-10)
------------------

**Features**

None

**Fixes**

-  .cfg file fixes

**Breaking Changes**

None

2.1.3 (2017-08-10)
------------------

**Features**

-  Restructure docs for readthedocs.io

None

**Fixes**

None

**Breaking Changes**

None

2.1.2 (2017-08-08)
-----

**Features**

-  Add \`get\_alexa\_slot\_value()
-  Add ``log_size`` and ``log_generations`` config parameters
-  Add additional debugging to help Docker users

**Fixes**

None

**Breaking Changes**

None

2.1.0 (2017-08-08)
------------------

**Features**

-  Add a reference to official ``vkorn`` repository for hass.io
-  Add the ability to access hass state as App attributes
-  Add RESTFul API Support for Apps
-  Add ``disable_dash`` directive to enable API access without
   Dashboards
-  Add Alexa Helper functions
-  Update Material Design Icons to 1.9.32 - contributed by
   `minchick <https://github.com/minchik>`__
-  Use relative URLs for better remote behavior - contributed by `Daniel
   Trnka <https://github.com/trnila>`__
-  Add SSL Support
-  Add Password security for screens and HASS proxying functions
-  Add support for secrets in the AppDaemon configuration file
-  Add support for secrets in HADashboard configuration files
-  ``dash_navigate()`` now takes an optional screen to return to

**Fixes**

-  Toggle area fixes submitted by
   `azeroth12 <https://github.com/azeroth12>`__ and
   `minchick <https://github.com/minchik>`__
-  Typo fixes submitted by `Aaron
   Linville <https://github.com/linville>`__,
   `vrs01 <https://github.com/vrs01>`__, `Gabor
   SZOLLOSI <https://github.com/szogi>`__, `Ken
   Davidson <https://github.com/kwdavidson>`__, `Christian
   Lasaczyk <https://github.com/ChrisLasar>`__,
   `Klaus <https://github.com/k-laus>`__, `Johan
   Haals <https://github.com/jhaals>`__
-  Fixed missing skin variables for media player and sensor widgets

**Breaking Changes**

-  Compiled dashboards may need to be deleted after this upgrade

2.0.8 (2017-07-23)
------------------

**Features**

-  Add step parameter to media player
-  Add ``row`` parameter to dashboard
-  Add ability to set timeout and return on dash navigation
-  Add ability to force dashboard page changes from Apps, Alexa and HASS
   Automations

**Fixes**

-  Add quotes to times in examples.yaml - contributed by
   `Cecron <https://github.com/Cecron>`__
-  Fix python 3.6 issue with datetime.datetime.fromtimestamp() -
   contributed by `motir <https://github.com/motir>`__

**Breaking Changes**

None

2.0.7 (2017-07-20)
------------------

**Features**

None

**Fixes**

-  Fixed a bug in label and text\_sensor widgets

**Breaking Changes**

None

2.0.6 (2017-07-20)
------------------

**Features**

None

**Fixes**

-  Fix a bug causing an apps ``terminate()`` to not be called

**Breaking Changes**

None

2.0.5 (2017-07-16)
------------------

**Features**

None

**Fixes**

-  Change ``convert_utc()`` to use iso8601 library

**Breaking Changes**

None

2.0.4 (2017-07-16)
------------------

**Features**

-  AppDaemon is now on PyPi - no more need to use git for installs
-  Allow time\_zone directive in appdaemon.cfg to override hass supplied
   time zone
-  Add API calls to return info on schedule table and callbacks
   (get\_scheduler\_entries(), get\_callback\_entries())
-  Add ``get_tracker_details()``
-  Add sub entity to sensor
-  Add ``hass_disconnected`` event and allow Apps to run while HASS is
   disconnected

**Fixes**

-  Fix startup examples to match new ``-c`` semantics and add in docs
-  Fix Time Travel
-  Fix for crashes on HASS restart if apps weren't in use - contributed
   by `shprota <https://github.com/shprota>`__
-  Attempted a fix for ``NaN`` showing for Nest & Ecobee thermostats
   when in auto mode

**Breaking Changes**

None

2.0.3 (2017-07-09)
------------------

**Features**

-  Add error display field to weather widget

**Fixes**

-  Fix issue with device trackers and ``use_hass_icon``

**Breaking Changes**

None

2.0.2 (2017-07-08)
------------------

**Features**

-  Move docker image to python 3.6

**Fixes**

None

**Breaking Changes**

None

2.0.1 (2017-07-08)
------------------

**Features**

-  Much Improved Docker support including tutorial - many thanks to
   `quadportnick <https://community.home-assistant.io/u/quadportnick/summary>`__

**Fixes**

-  Version Change
-  Respect cert\_path setting when connecting to WebSocket over SSL -
   contributed by `yawor <https://github.com/yawor>`__

**Breaking Changes**

None

2.0.0beta4 (2017-06-18)
-----------------------

**Features**

-  Migrate timer thread to async
-  Add option to turn off verification for self signed certs
   (contributed by `janwh <https://github.com/janwh>`__)
-  AppDaemon configuration now uses YAML, among other things this allows
   arbitrarily complex nested data structures in App parameters
-  Added ability to convert from old cfg file to YAML
-  AppDaemon Apps can now publish arbitrary state to other Apps and the
   dashboard
-  Added Gauge Widget
-  Added RSS Widget
-  Add next and previous track to media player

**Fixes**

-  Slider now works correctly after changes outside of HADashboard
-  Climate now works correctly after changes outside of HADashboard
-  Media player now works correctly after changes outside of HADashboard
-  ha.log now correctly dumps data structures
-  on\_attributes for lights now correctly supports RGB and XY\_COLOR
-  Fixed a bug in the scheduler to reduce clock skew messages

**Breaking Changes**

-  The cfg file style of configuration is now deprecated although it
   still works for now for most features
-  Argument names passed to Apps are now case sensitive

2.0.0beta3.5 (2017-04-09)
-------------------------

**Features**

-  Label now accepts HTML for the value
-  IFRAME widget now allows vimeo and youtube videos to go fullscreen
   when clicked
-  IFRAME and Camera widgets now have optional title overlay
-  Widgets that display icons can now pick up icons defined in HASS
-  aiohttp version 2 support

**Fixes**

-

**Breaking Changes**

-

2.0.0beta3 (2017-03-27)
-----------------------

**Features**

-  Added alarm widget
-  Added camera widget
-  Dimmers and groups now allow you to specify a list of on parameters
   to control brightness, color etc.
-  Edited code for PEP8 Compliance
-  Widgets can now have a default size other than ``(1x1)``
-  Added ``empty`` to layouts for multiple blank lines
-  Numeric values can now have a comma as the decimal separator
-  Add Global Parameters
-  Rewrote media widget

**Fixes**

-  IFrames now follow widget borders better
-  IFrame now allows user input
-  Fixed a race condition on dashboard reload

**Breaking Changes**

-  Media Widget now needs to be 2 cells high

2.0.0beta2 (2017-03-12)
-----------------------

**Features**

-  Widget level styles now correctly override just the styles they are
   replacing in the skin, not the whole style
-  Device tracker toggling of state is optional and defaults to off
-  Add climate widget
-  Add script widget
-  Add lock widget
-  Add cover widget
-  Added optional ``monitored_state`` argument to group to pick a
   representative entity to track dimming instead of guessing
-  Introduce new widget definition model in preparation for custom
   widgets
-  Rewrite several widgets using the new model
-  Add state map and state text functions to sensor, scene,
   binary\_sensor, switch, device\_tracker, script, lock, cover,
   input\_boolean
-  Allow dashboard accesses to be logged in a separate file
-  Flag to force recompilation after startup
-  Additional error checks in many places
-  Dashboard determines the stream URL dynamically rather than by having
   it hard coded
-  Add IFRAME widget
-  Sensor widget now automatically detects units
-  Sensor widget has separate styles for text and numeric
-  Style fixes
-  Active Map for device trackers

**Fixes**

-  Various minor skin fixes

**Breaking Changes**

-  Widget level styles that relied on overriding the whole skin style
   may no longer work as expected
-  Device trackers must now be explicitly configured to allow the user
   to toggle state, by setting the ``enable`` parameter
-  Groups of lights must have the ``monitored_entity`` argument to work
   properly if they contain any dimmable lights
-  ``text_sensor`` is deprecated and will be removed at some stage. It
   is now an alias for ``sensor``

2.0.0beta1 (2017-03-04)
-----------------------

**Features**

-  Initial release of HADashboard v2

**Fixes**

None

**Breaking Changes**

-  appdaemon's ``-c`` option now identifies a directory not a file. The
   previously identified file must exist in that directory and be named
   ``appdaemon.cfg``

1.5.2 (2017-02-04)
------------------

**Features**

-  Code formatted to PEP8, various code optimizations - contributed by
   `yawor <https://github.com/yawor>`__
-  Version check for WebSockets now understands dev versions -
   contributed by `yawor <https://github.com/yawor>`__
-  ``turn_off()`` will now call ``turn_on()`` for scenes since turning a
   scene off makes no sense, to allow extra flexibility
-  Restored the ability to use **line**, **module** and **function** in
   log messages. Recoded to prevent errors in non-compatible Python
   versions if the templates are not used.

**Fixes**

None

**Breaking Changes**

None

1.5.1 (2017-01-30)
------------------

**Features**

None

**Fixes**

-  Functionality to substitute line numbers and module names in log
   statements temporarily removed

**Breaking Changes**

-  Functionality to substitute line numbers and module names in log
   statements temporarily removed

1.5.0 (2017-01-21)
------------------

**Features**

-  Swap from EventStream to Websockets (Requires Home Assistant 0.34 or
   later). For earlier versions of HA, AppDaemon will fallback to
   EventStream.
-  Restored less verbose messages on HA restart, but verbose messages
   can be enabled by setting ``-D DEBUG`` when starting AppDaemon
-  From the command line ctrl-c now results in a clean shutdown.
-  Home Assistant config e.g. Latitude, Longitude are now available in
   Apps in the ``self.ha_config`` dictionary.
-  Logging can now take placeholder strings for line number, function
   and module which will be appropriately expanded in the actual message
-  Add example apps: battery, grandfather, sensor\_notification, sound
-  Updates to various example apps

**Fixes**

-  get\_app() will now return ``None`` if the app is not found rather
   than throwing an exception.

**Breaking Changes**

-  get\_app() will now return ``None`` if the app is not found rather
   than throwing an exception.

None

1.4.2 (2017-01-21)
------------------

**Features**

None

**Fixes**

-  Remove timeout parameter from SSEClient call unless timeout is
   explicitly specified in the config file

**Breaking Changes**

None

1.4.1 (2017-01-21)
------------------

**Features**

-  turn\_off() now allows passing of parameters to the underlying
   service call
-  Better handling of scheduler and worker thread errors. More
   diagnostics, plus scheduler errors now delete the entry where
   possible to avoid spamming log entries
-  More verbose error handling with HA communication errors

**Fixes**

None

**Breaking Changes**

None

1.4.0 (2017-01-20)
------------------

**Features**

-  notify() now supports names
-  It is now possible to set a timeout value for underlying calls to the
   HA EventStream
-  It is no longer necessary to specify latitude, longitude and timezone
   in the config file, the info is pulled from HA
-  When being reloaded, Apps are now able to clean up if desired by
   creating an optional ``terminate()`` function.
-  Added support for module dependencies

**Fixes**

**Breaking Changes**

-  To include a title when using the ``notify()`` call, you must now use
   the keyword ``title`` instead of the optional positional parameter

1.3.7 (2017-01-17)
------------------

**Features**

-  Add ``entity_exists()`` call
-  List Apps holding up initialization

**Fixes**

-  Add documentation for the days constraint
-  Various other contributed documentation fixes

**Breaking Changes**

None

1.3.6 (2016-10-01)
------------------

**Features**

-  Add device trackers to switch\_reset example

**Fixes**

-  Fixed a bug in which AppDaemon exited on startup if HA was not
   listening causing AppDaemon failure to start on reboots
-  Fixed some scheduler behavior for appd and ha restart events
-  Fix presence example to only notify when state changes (e.g. not just
   for position updates)
-  Change door notify example to explicitly say "open" or "closed"
   instead of passing through state
-  Fix a bug in device\_trackers example

**Breaking Changes**

None

1.3.4 (2016-09-20)
------------------

**Features**

-  Add Minimote Example
-  Add device trackers to switch\_reset example

**Fixes**

-  Fixed a minor scheduler bug that didn't honor the delay for callbacks
   fired from appd and ha restart events

**Breaking Changes**

None

1.3.4 (2016-09-18)
------------------

**Features**

-  Add Momentary Switch example
-  Add Switch Reset Example

**Fixes**

-  Fix a race condition in App Initialization
-  Fix a bug that overwrote state attributes
-  Fix to smart heat example app
-  Fix day constraints while using time travel

**Breaking Changes**

None

1.3.3 (2016-09-16)
------------------

**Features**

-  Add ability to specify a cert directory for self-signed certs
-  Add ability for ``listen_event()`` to listen to any event
-  Add filter options to listen\_event()

**Fixes**

-  Fix several potential race conditions in the scheduler

**Breaking Changes**

None

1.3.2 (2016-09-08)
------------------

**Features**

-  Document "Time Travel" functionality
-  Add convenience function to set input\_select called
   ``select_option()`` - contributed by
   `jbardi <https://community.home-assistant.io/users/jbardi/activity>`__
-  Add global access to configuration and global configuration variables
   - suggested by
   `ReneTode <https://community.home-assistant.io/users/renetode/activity>`__

**Fixes**

-  Tidy up examples for listen state - suggested by
   `ReneTode <https://community.home-assistant.io/users/renetode/activity>`__
-  Warning when setting state for a non-existent entity is now only
   given the first time
-  Allow operation with no ``ha_key`` specified
-  AppDaemon will now use the supplied timezone for all operations
   rather than just for calculating sunrise and sunset
-  Reduce the chance of a spurious Clock Skew error at startup

**Breaking Changes**

None

1.3.1 (2016-09-04)
------------------

**Features**

-  Add convenience function to set input\_selector called
   ``select_value()`` - contributed by `Dave
   Banks <https://github.com/djbanks>`__

**Fixes**

None

**Breaking Changes**

None

1.3.0 (2016-09-04)
------------------

**Features**

-  Add ability to randomize times in scheduler
-  Add ``duration`` to listen\_state() to fire event when a state
   condition has been met for a period of time
-  Rewrite scheduler to allow time travel (for testing purposes only, no
   effect on regular usage!)
-  Allow input\_boolean constraints to have reversed logic
-  Add info\_listen\_state(), info\_listen\_event() and info\_schedule()
   calls

**Fixes**

-  Thorough proofreading correcting typos and formatting of API.md -
   contributed by `Robin Lauren <https://github.com/llauren>`__
-  Fixed a bug that was causing scheduled events to fire a second late
-  Fixed a bug in ``get_app()`` that caused it to return a dict instead
   of an object
-  Fixed an error when missing state right after HA restart

**Breaking Changes**

-  ``run_at_sunrise(``) and ``run_at_sunset()`` no longer take a fixed
   offset parameter, it is now a keyword, e.g. ``offset = 60``

1.2.2 (2016-08-31)
------------------

**Features**

None

**Fixes**

-  Fixed a bug preventing get\_state() calls for device types
-  Fixed a bug that would cause an error in the last minute of an hour
   or last hour of a day in run\_minutely() and run)hourly()
   respectively

**Breaking Changes**

None

1.2.1 (2016-08-26)
------------------

**Features**

-  Add support for windows

**Fixes**

None

**Breaking Changes**

None

1.2.0 (2016-08-24)
------------------

**Features**

-  Add support for recursive directories - suggested by
   `jbardi <https://github.com/jbardi>`__

**Fixes**

None

**Breaking Changes**

None

1.1.1 (2016-08-23)
------------------

**Fixes**

-  Fix init scripts

1.1.0 (2016-08-21)
------------------

**Features**

-  Installation via pip3 - contributed by `Martin
   Hjelmare <https://github.com/MartinHjelmare>`__
-  Docker support (non Raspbian only) - contributed by `Jesse
   Newland <https://github.com/jnewland>`__
-  Allow use of STDERR and SDTOUT as logfile paths to redirect to stdout
   and stderr respectively - contributed by `Jason
   Hite <https://github.com/jasonmhite>`__
-  Deprecated "timezone" directive on cfg file in favor of "time\_zone"
   for consistency with Home Assistant config
-  Added default paths for config file and apps directory
-  Log and error files default to STDOUT and STDERR respectively if not
   specified
-  Added systemd service file - contributed by `Jason
   Hite <https://github.com/jasonmhite>`__

**Fixes**

-  Fix to give more information if initial connect to HA fails (but
   still avoid spamming logs too badly if it restarts)
-  Rename 'init' directory to 'scripts'
-  Tidy up docs

**Breaking Changes**

-  As a result of the repackaging for PIP3 installation, all apps must
   be edited to change the import statement of the api to
   ``import appdaemon.appapi as appapi``
-  Config must now be explicitly specified with the -c option if you
   don't want it to pick a default file location
-  Logfile will no longer implicitly redirect to STDOUT if running
   without the -d flag, instead specify STDOUT in the config file or
   remove the logfile directive entirely
-  timezone is deprecated in favor of time\_zone but still works for now

1.0.0 (2016-08-09)
------------------

**Initial Release**
