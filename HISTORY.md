=======
History
=======

1.3.7 (2016-10-20)
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
