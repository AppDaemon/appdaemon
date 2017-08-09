History
=======

2.1.1
-----

- Add `get_alexa_slot_value()
- Add `log_size` and `log_generations` config parameters
- Add additional debugging to help Docker users

None

**Fixes**

None

**Breaking Changes**

None

2.1.0
-----

**Features**

- Add a reference to official `vkorn` repository for hass.io
- Add the ability to access hass state as App attributes
- Add RESTFul API Support for Apps
- Add `disable_dash` directive to enable API access without Dashboards
- Add Alexa Helper functions
- Update Material Design Icons to 1.9.32 - contributed by [minchick](https://github.com/minchik)
- Use relative URLs for better remote behavior - contributed by [Daniel Trnka](https://github.com/trnila)
- Add SSL Support
- Add Password security for screens and HASS proxying functions
- Add support for secrets in the AppDaemon configuration file
- Add support for secrets in HADashboard configuration files
- `dash_navigate()` now takes an optional screen to return to

**Fixes**

- Toggle area fixes submitted by [azeroth12](https://github.com/azeroth12) and [minchick](https://github.com/minchik)
- Typo fixes submitted by [Aaron Linville](https://github.com/linville), [vrs01](https://github.com/vrs01), [Gabor SZOLLOSI](https://github.com/szogi), [Ken Davidson](https://github.com/kwdavidson), [Christian Lasaczyk](https://github.com/ChrisLasar), [Klaus](https://github.com/k-laus), [Johan Haals](https://github.com/jhaals)
- Fixed missing skin variables for media player and sensor widgets

**Breaking Changes**

- Compiled dashboards may need to be deleted after this upgrade


2.0.8
-----

**Features**

- Add step parameter to media player
- Add `row` parameter to dashboard
- Add ability to set timeout and return on dash navigation
- Add ability to force dashboard page changes from Apps, Alexa and HASS Automations

**Fixes**

- Add quotes to times in examples.yaml - contributed by [Cecron](https://github.com/Cecron)
- Fix python 3.6 issue with datetime.datetime.fromtimestamp() - contributed by [motir](https://github.com/motir)

**Breaking Changes**

None


2.0.7
-----

**Features**

None

**Fixes**

- Fixed a bug in label and text_sensor widgets

**Breaking Changes**

None

2.0.6
-----

**Features**

None

**Fixes**

- Fix a bug causing an apps `terminate()` to not be called

**Breaking Changes**

None


2.0.5
-----

**Features**

None

**Fixes**

- Change `convert_utc()` to use iso8601 library

**Breaking Changes**

None


2.0.4
-----

**Features**

- AppDaemon is now on PyPi - no more need to use git for installs
- Allow time_zone directive in appdaemon.cfg to override hass supplied time zone
- Add API calls to return info on schedule table and callbacks (get_scheduler_entries(), get_callback_entries())
- Add `get_tracker_details()`
- Add sub entity to sensor
- Add `hass_disconnected` event and allow Apps to run while HASS is disconnected

**Fixes**

- Fix startup examples to match new `-c` semantics and add in docs
- Fix Time Travel
- Fix for crashes on HASS restart if apps weren't in use - contributed by [shprota](https://github.com/shprota)
- Attempted a fix for `NaN` showing for Nest & Ecobee thermostats when in auto mode

**Breaking Changes**

None


2.0.3
-----

**Features**

- Add error display field to weather widget

**Fixes**

- Fix issue with device trackers and `use_hass_icon`

**Breaking Changes**

None

2.0.2
-----

**Features**

- Move docker image to python 3.6

**Fixes**

None

**Breaking Changes**

None

2.0.1
-----

**Features**

- Much Improved Docker support including tutorial - many thanks to [quadportnick](https://community.home-assistant.io/u/quadportnick/summary)

**Fixes**

- Version Change
- Respect cert_path setting when connecting to WebSocket over SSL - contributed by [yawor](https://github.com/yawor)

**Breaking Changes**

None

2.0.0beta4
----------

**Features**

- Migrate timer thread to async
- Add option to turn off verification for self signed certs (contributed by [janwh](https://github.com/janwh))
- AppDaemon configuration now uses YAML, among other things this allows arbitarily complex nested data structures in App parameters
- Added ability to convert from old cfg file to YAML
- AppDaemon Apps can now publish arbitary state to other Apps and the dashboard
- Added Gauge Widget
- Added RSS Widget
- Add next and previous track to media player

**Fixes**

- Slider now works correctly after changes outside of HADashboard
- Climate now works correctly after changes outside of HADashboard
- Media player now works correctly after changes outside of HADashboard
- ha.log now correctly dumps data structures
- on_attributes for lights now correctly supports RGB and XY_COLOR
- Fixed a bug in the scheduler to reduce clock skew messages

**Breaking Changes**

- The cfg file style of configuration is now deprecated although it still works for now for most features
- Argument names passed to Apps are now case sensitive

2.0.0beta3.5
------------

**Features**

- Label now accepts HTML for the value
- IFRAME widget now allows vimeo and youtube videos to go fullscreen when clicked
- IFRAME and Camera widgets now have optional title overlay
- Widgets that display icons can now pick up icons defined in HASS
- aiohttp version 2 support

**Fixes**

-

**Breaking Changes**

-

2.0.0beta3
----------

**Features**

- Added alarm widget
- Added camera widget
- Dimmers and groups now allow you to specify a list of on parameters to control brightness, color etc.
- Edited code for PEP8 Compliance
- Widgets can now have a default size other than `(1x1)`
- Added `empty` to layouts for multiple blank lines
- Numeric values can now have a comma as the decimal separator
- Add Global Parameters
- Rewrote media widget

**Fixes**

- IFrames now follow widget borders better
- IFrame now allows user input
- Fixed a race condition on dashboard reload

**Breaking Changes**

- Media Widget now needs to be 2 cells high

2.0.0beta2
----------

**Features**

- Widget level styles now correctly override just the styles they are replacing in the skin, not the whole style
- Device tracker toggling of state is optional and defaults to off
- Add climate widget
- Add script widget
- Add lock widget
- Add cover widget
- Added optional `monitored_state` argument to group to pick a representative entity to track dimming instead of guessing
- Introduce new widget definition model in preparation for custom widgets
- Rewrite several widgets using the new model
- Add state map and state text functions to sensor, scene, binary_sensor, switch, device_tracker, script, lock, cover, input_boolean
- Allow dashboard accesses to be logged in a separate file
- Flag to force recompilation after startup
- Additional error checks in many places
- Dashboard determines the stream URL dynamically rather than by having it hard coded
- Add IFRAME widget
- Sensor widget now automatically detects units
- Sensor widget has separate styles for text and numeric
- Style fixes
- Active Map for device trackers

**Fixes**

- Various minor skin fixes

**Breaking Changes**

- Widget level styles that relied on overriding the whole skin style may no longer work as expected
- Device trackers must now be explicitly configured to allow the user to toggle state, by setting the `enable` parameter
- Groups of lights must have the `monitored_entity` argument to work properly if they contain any dimmable lights
- `text_sensor` is deprecated and will be removed at some stage. It is now an alias for `sensor`

2.0.0beta1
----------

**Features**

- Initial release of HADashboard v2

**Fixes**

None

**Breaking Changes**

- appdaemon's `-c` option now identifies a directory not a file. The previously identified file must exist in that directory and be named `appdaemon.cfg`

1.5.2 (2017-02-04)
------------------

**Features**

- Code formatted to PEP8, various code optimizations - contributed by [yawor](https://github.com/yawor)
- Version check for WebSockets now understands dev versions - contributed by [yawor](https://github.com/yawor)
- `turn_off()` will now call `turn_on()` for scenes since turning a scene off makes no sense, to allow extra flexibility
- Restored the ability to use __line__, __module__ and __function__ in log messages. Recoded to prevent errors in non-compatible Python versions if the templates are not used.

**Fixes**

None

**Breaking Changes**

None

1.5.1 (2017-01-30)
------------------

**Features**

None

**Fixes**

- Functionality to substitute line numbers and module names in log statements temporarily removed

**Breaking Changes**

- Functionality to substitute line numbers and module names in log statements temporarily removed

1.5.0 (2017-01-21)
------------------

**Features**

- Swap from EventStream to Websockets (Requires Home Assistant 0.34 or later). For earlier versions of HA, AppDaemon will fallback to EventStream.
- Restored less verbose messages on HA restart, but verbose messages can be enabled by setting `-D DEBUG` when starting AppDaemon
- From the command line ctrl-c now results in a clean shutdown.
- Home Assistant config e.g. Latitude, Longitude are now available in Apps in the `self.ha_config` dictionary.
- Logging can now take placeholder strings for line number, function and module which will be appropriately expanded in the actual message
- Add example apps: battery, grandfather, sensor_notification, sound
- Updates to various example apps

**Fixes**

- get_app() will now return `None` if the app is not found rather than throwing an exception.

**Breaking Changes**

- get_app() will now return `None` if the app is not found rather than throwing an exception.

None

1.4.2 (2017-01-21)
------------------

**Features**

None

**Fixes**

- Remove timeout parameter from SSEClient call unless timeout is explicitly specified in the config file

**Breaking Changes**

None

1.4.1 (2017-01-21)
------------------

**Features**

- turn_off() now allows passing of parameters to the underlying service call
- Better handling of scheduler and worker thread errors. More diagnostics, plus scheduler errors now delete the entry where possible to avoid spamming log entries
- More verbose error handling with HA communication errors

**Fixes**

None

**Breaking Changes**

None

1.4.0 (2017-01-20)
------------------

**Features**

- notify() now supports names
- It is now possible to set a timeout value for underlying calls to the HA EventStream
- It is no longer neccesary to specify latitude, longitude and timezone in the config file, the info is pulled from HA
- When being reloaded, Apps are now able to clean up if desired by creating an optional `terminate()` function.
- Added support for module dependencies

**Fixes**

**Breaking Changes**

- To include a title when using the `notify()` call, you must now use the keyword `title` instead of the optional positional parameter

1.3.7 (2017-01-17)
------------------

**Features**

- Add `entity_exists()` call
- List Apps holding up initialization

**Fixes**

- Add documentation for the days constraint
- Various other contributed documentation fixes

**Breaking Changes**

None


1.3.6 (2016-10-01)
------------------

**Features**

- Add device trackers to switch_reset example

**Fixes**

- Fixed a bug in which AppDaemon exited on startup if HA was not listening causing AppDaemon failure to start on reboots
- Fixed some scheduler behavior for appd and ha restart events
- Fix presence example to only notify when state changes (e.g. not just for position updates)
- Change door notify example to explicitly say "open" or "closed" instead of passing through state
- Fix a bug in device_trackers example


**Breaking Changes**

None

1.3.4 (2016-09-20)
------------------

**Features**

- Add Minimote Example
- Add evice trackers to switch_reset example

**Fixes**

- Fixed a minor scheduler bug that didn't honor the delay for callbacks fired from appd and ha restart events

**Breaking Changes**

None

1.3.4 (2016-09-18)
------------------

**Features**

- Add Moementary Switch example
- Add Switch Reset Example

**Fixes**

- Fix a several a race condition in App Initialization
- Fix a bug that overwrote state attributes
- Fix to smart heat example app
- Fix day constraints while using time travel

**Breaking Changes**

None


1.3.3 (2016-09-16)
------------------

**Features**

- Add ability to specify a cert dirctory for self-signed certs
- Add ability for `listen_event()` to listen to any event
- Add filter options to listen_event()

**Fixes**

- Fix a several potential race conditions in the scheduler

**Breaking Changes**

None

1.3.2 (2016-09-08)
------------------

**Features**

- Document "Time Travel" functionality
- Add convenience function to set input_select called `select_option()` - contributed by [jbardi](https://community.home-assistant.io/users/jbardi/activity)
- Add global access to configuration and global configuration variables - suggested by [ReneTode](https://community.home-assistant.io/users/renetode/activity) 

**Fixes**

- Tidy up examples for listen state - suggested by [ReneTode](https://community.home-assistant.io/users/renetode/activity)
- Warning when setting state for a non-existent entity is now only given the first time
- Allow operation with no `ha_key` specified
- AppDaemon will now use the supplied timezone for all operations rather than just for calculating sunrise and sunset
- Reduce the chance of a spurious Clock Skew error at startup

**Breaking Changes**

None

1.3.1 (2016-09-04)
------------------

**Features**

- Add convenience function to set input_selector called `select_value()` - contributed by [Dave Banks](https://github.com/djbanks)

**Fixes**

None

**Breaking Changes**

None

1.3.0 (2016-09-04)
------------------

**Features**

- Add ability to randomize times in scheduler
- Add `duration` to listen_state() to fire event when a state condition has been met for a period of time
- Rewrite scheduler to allow time travel (for testing purposes only, no effect on regular usage!)
- Allow input_boolean constraints to have reversed logic
- Add info_listen_state(), info_listen_event() and info_schedule() calls

**Fixes**

- Thorough proofreading correcting typos and formatting of API.md - contributed by [Robin Lauren](https://github.com/llauren)
- Fixed a bug that was causing scheduled events to fire a second late
- Fixed a bug in `get_app()` that caused it to return a dict instead of an object
- Fixed an error when missing state right after HA restart

**Breaking Changes**

- `run_at_sunrise(`) and `run_at_sunset()` no longer take a fixed offset parameter, it is now a keyword, e.g. `offset = 60`


1.2.2 (2016-31-09)
------------------

**Features**

None

**Fixes**

- Fixed a bug preventing get_state() calls for device types
- Fixed a bug that would cause an error in the last minute of an hour or last hour of a day in run_minutely() and run)hourly() respectively

**Breaking Changes**

None

1.2.1 (2016-26-09)
------------------

**Features**

- Add support for windows

**Fixes**

None

**Breaking Changes**

None


1.2.0 (2016-24-09)
------------------

**Features**

- Add support for recursive directories - suggested by [jbardi](https://github.com/jbardi)

**Fixes**

None

**Breaking Changes**

None

1.1.1 (2016-23-09)
------------------

**Fixes**

- Fix init scripts

1.1.0 (2016-21-09)
------------------

**Features**

- Installation via pip3 - contributed by [Martin Hjelmare](https://github.com/MartinHjelmare)
- Docker support (non Raspbian only) - contributed by [Jesse Newland](https://github.com/jnewland)
- Allow use of STDERR and SDTOUT as logfile paths to redirect to stdout and stderr respectively - contributed by [Jason Hite](https://github.com/jasonmhite)
- Deprecated "timezone" directive on cfg file in favor of "time_zone" for consistency with Home Assistant config
- Added default paths for config file and apps directory
- Log and error files default to STDOUT and STDERR respectively if not specified
- Added systemd service file - contributed by [Jason Hite](https://github.com/jasonmhite)

**Fixes**

- Fix to give more information if initial connect to HA fails (but still avoid spamming logs too badly if it restarts)
- Rename 'init' directory to 'scripts'
- Tidy up docs

**Breaking Changes**

- As a result of the repackaging for PIP3 installation, all apps must be edited to change the import statement of the api to `import appdaemon.appapi as appapi`
- Config must now be explicitly specfied with the -c option if you don't want it to pick a default file location
- Logfile will no longer implicitly redirect to STDOUT if running without the -d flag, instead specify STDOUT in the config file or remove the logfile directive entirely
- timezone is deprecated in favor of time_zone but still works for now

1.0.0 (2016-08-09)
------------------

**Initial Release**
