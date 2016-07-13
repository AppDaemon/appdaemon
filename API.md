# Appdaemon API Documentation

appdaemon is a loosely coupled, sandboxed, multi-threaded Python execution environment for writing automation apps for [Home Assistant](https://home-assistant.io/) home automation software. It is intended to complement the Automation and Script components that Home Assistant currently offers.

## Anatomy of an App

Automations in appdaemon are performed by creating a piece of code (essentially a Python Class) and then instantiating it as an Object one or more times by configuring it as an App in the configuration file. The App is given a chance to register itself for whatever events it wants to subscribe to, and appdaemon will then make calls back into the Object's code when those events occur, allowing the App to respond to the event with some kind of action.

The first step is to create a unique file within the apps directory (as defined in the `[appdaemon]` section of configuration file). See [README](README.md) for further information on the configuration of appdaemon itself. This file is in fact a python module, and is expected to contain exactly one class derived from the supplied `APPDaemon` class, imported from the supplied `appapi` module. In addition, the new module should also import the homeassistant module to gain access to the various API calls and convenience functions. The start of an app might look like this:

```python
import homeassistant as ha
import appapi

class MotionLights(appapi.APPDaemon):
```

When configured as an app in the config file (more on that later) the lifecycle of the App begins. It will be instantiated as an object by appdaemon, and immediately, it will have a call made to it's `initialize()` function - this function must appear as part of every app:

```python
  def initialize(self):
  ```
  
The initialize function alows the app to register any callbacks it might need for responding to state changes, and also any setup activities. When the `initialize()` function returns, the App will be dormant until any of it's callbacks are activated.

There are several circumstances under which `initialize()` might be called:

- Initial start of appdaemon
- Following a change to the Class code
- Following a change to the module parameters
- Following initial configuration of an app

In every case, the App is responsible for recreating any state it might need as if it were the first time it was ever started. For instance, if `initialize()` is called, the app can safely assume that all callbacks and timers have been cancelled and will need to restart them. Depending upon the application it may be desirable for the App to establish state such as whether or not a particular light is on, within the `initialize()` function to ensure that eveyrthing is as expected or to make immediate remedial action (e.g. turn off a light that might have been left on by mistake when the app was restarted).

After the `initialize()` function is in place, the rest of the app consists of functions that are called by the various callback mechanisms, and any additional functions the user wants to add as part of the program logic. Apps are able to subscribe to 2 main classes of events:

- Scheduled Events
- State Change Events

These along with their various subscription calls and helper functions will be described in detail in later sections.

To wrap up this section, here is a complete functioning App (with comments):

```python
import homeassistant as ha
import appapi
import datetime

# Declare Class
class NightLight(appapi.APPDaemon):
  #initialize() function which will be called at startup and reload
  def initialize(self):
    # Create a time object for 7pm
    time = datetime.time(19, 00, 0)
    # Schedule a daily callback that will call run_daily() at 7pm every night
    ha.run_daily(self.name, self.run_daily, time)
   
   # Our callback function will be called by the scheduler every day at 7pm 
  def run_daily(self, args, kwargs):
    # Call to Home Assistant to turn the porch light on
    ha.turn_on("light.porch")
```

## Configuration of Apps

## Passing Arguments to Apps

## State Operations

### A note on Home Assistant State 

State within Home Assistant is stored as a collection of dictionaries, one for each entity. Each entity's dictionary will have some common fields and a number of entity type specific fields The state for an entity will always have the attributes:

- last_updated
- last_changed
- state

Any other attributes such as brightness for a lamp will only be present if the entity supports them, and will be stored in a sub-dictionary called `attributes`. When specifying these optional attributes in the `get_state()` call, no special distinction is required between the main attributes and the optional ones - `get_state()` will figure it out for you.

Bear in mind also, that some attributes such as brightness for a light, will not be present when the light is off.

In most cases, the sttribute `state` has the most important value in it, e.g. for a light or switch this will be `on` or `off`, for a sensor it will be the value of that sensor. Many of the appdaemon API calls and callbacks will implicitly return the value of state unless told to do otherwise.

### get_state()

#### Synopsis

`get_state(device = None, entity = None, attribute = None)`

`get_state()` is used to query the state of any component within Home Assistant. State updates are continuously tracked so this call runs locally and does not require appdaemon to call back to Home Assistant and as such is very efficient.

#### Returns

`get_state()` returns a `dictionary` or single value, the structure of which varies according to the parameters used.

#### Parameters

All parameters are optional, and if `get_state()` is called with no parameters it will return the entire state of Home Assistant at that given time. This will consist of a dictionary with a key for each entity. Under that key will be the standard entity state information.

##### device

This is the name of a device type, e.g. `light` or `binary_sensor`. If just the device type is provided, `get_state()` will return a dictionary of all devices of that type, indexed by the entity_id, containing all the state for each entity. Note the distinction between device, entity and entity_id. Device and entity are derived from the entity_id, and are used as a convenience for specifying the different types of return value from this and other calls, however the correct home_assistant construct is `entity_id`. As an example, the `entity_id` known as `light.office_1` can be specified in `get_state()` using the device and entity values `light` and `office_1` respectively. To find the correct entity id, use the developer tools in the Home Assistant UI. 

##### entity

Name of the entity of the specified device type get state for, e.g. `office` or `lightlevel`. Specifying just a device and an entity will return the state attribute for that entity, (e.g. "on" or "off" for a light), or `None` if it doesn't exist.

##### attribute

Name af an attribute within the entity state object. If this parameter is specified in addition to a device and an entity, a single value representing the attribute will be returned, or `None` if it is not present.

The value `all` for attribute has special significance and will return the entire state dictionary for the specified entity rather than an individual attribute value.

#### Examples

```python
# Return all state for the entire system
state = ha.get_state()

# Return state for all switches in the system
state = ha.get_state("switch")

# Return the state attribute for light.office_1
state = ha.get_state("light", "office_1")

# Return the brightness attribute for light.office_1
state = ha.get_state("light", "office_1", "brightness")

# Return the entire state for light.office_1
state = ha.get_state("light", "office_1", "all")
```

### set_state()

`set_state()` will make a call back to Home Assistant and make changes to the internal state of Home Assistant. This is not something that you would usually want to do and the applications are limited however the call is included for completeness. Note that for instance, setting the state of a light to `on` won;t actually switch the device on, it will merely change the state of the device in Home Assistant so that it no longer reflects reality. In most cases, the state will be corrected the next time Home Assistant polls the device or someone causes a state change manually. To effect actual changes ot devices use one of the service call functions.

One possible use case for `set_state()` is for testing. If forinstance you are writing an App to turn on a light when it gets dark according to a luminance sensor, you can use `set_state()` to temporarily change the light level reported by the sensor to test your program. However this is also possible using the developer tools.

At the time of writing, it appears that no checking is done as to whether or not the entity exists, so it is possible to add entirely new entries to Hoome Assistant's state with this call.

#### Synopsis

`set_state(entity_id, values)`

#### Returns

`set_state()` returns a dictionary representing the state of the device after the call has completed. 

#### Parameters

##### entity_id

Entity id for whcih the state is to be set, e.g. "light.office_1".

##### values

A dictionary of values to be changed or added to the entities stae. e,g, {"state": "off", "color_name": "red"}

#### Examples

```python
status = ha.set_state("light.office_1", {"state": "off"})
```

### About State Callbacks

A large proportion of home automation revolves around waiting for something to happen and then reacting to it - a light level drops, the sun rises, a door opens etc. Home Assistant keeps track of every state change that occurs within the system and stream that information to appdaemon almost immediately.

An individual App however usually doesn't care about the majority of state changes going on in the system, they usually care about something very specific, like a specific sensor or light. Apps need a way to be notified when a state change happens that they care about, and be able to ignore the rest - they do this through registering callbacks. A callback allows the App to describe exactly what it is interested in, and tell appdaemon to make a call into it's code in a specific place to be able to react to it - this is a very familiar concept to anyone familiar with even-based programming.

Appdaemons's state callbacks allow an App to listen to a wide variety of events, from every state change in the system, right down to a change of a single attribute of a particular entity. Setting up of a callback is done using a single API call `listen_state()` that takes various arguments to allow it to do all of the above. Apps can register as many or as few callbacks as they want.

### About State Callback Functions

When calling back into the App, the App must provide a class function with a known signature for appdaemon to call. The callback will provide various information to the function to enable the function to respond appropriately. For state callbacks, a class defined callback funciton should look like this:

```python
  def my_callback(self, entity, attribute, old, new):
    <do some useful work here>
```

You can call the fucntion whatever you like - you will reference it in the `listen_state()` call, and you can create as many callback functions as you need.

The parameters have the following meanings:

#### self
A standard Python object reference
#### entity
Name of the entity the callback was requested for or `None`
#### attribute
Name of the attribute the callback was requested for or `None`
#### old
The value of the state before the state change
#### new
The value of the state after the styate change

`old` and `new` will have varying types depending on the type of callback. 

### listen_state()
#### Synopsis

#### Returns

#### Parameters

#### Examples

```python
# Listen for any state change
ha.listen_state(self.name, self.all_state)

 # Listen for any state change involving a light
ha.listen_state(self.name, self.device, "light")

# Listen for a state change involving light.office1 and return the state attribute
ha.listen_state(self.name, self.entity, "light", "office_1")

# Listen for a state change involving light.office1 and return the entire state
ha.listen_state(self.name, self.attr, "light", "office_1", "all")

# Listen for a state change involving the brightness attribute of light.office1
ha.listen_state(self.name, self.attr, "light", "office_1", "brightness")
```

### cancel_listen_state()
#### Synopsis

#### Returns

#### Parameters

#### Examples
## Scheduler

### About Schedule Callbacks

### Creation of Scheduler Callbacks

#### run_in()
#### Synopsis

#### Returns

#### Parameters

#### Examples
#### run_once()
#### Synopsis

#### Returns

#### Parameters

#### Examples
#### run_daily()
#### Synopsis

#### Returns

#### Parameters

#### Examples
#### run_hourly()
#### Synopsis

#### Returns

#### Parameters

#### Examples
#### run_minutely()
#### Synopsis

#### Returns

#### Parameters

#### Examples
#### run_every()
#### Synopsis

#### Returns

#### Parameters

#### Examples
## Sunrise/Sunset

### run_at_sunrise()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### run_at_sunset()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### sunrise()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### sunset()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### sun_state()
#### Synopsis

#### Returns

#### Parameters

#### Examples
## Calling Services

### About Services

### call_service()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### turn_on()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### turn_off()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### toggle()
#### Synopsis

#### Returns

#### Parameters

#### Examples
## Presence

### get_trackers()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### get_tracker_state()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### everyone_home()
#### Synopsis

#### Returns

#### Parameters

#### Examples
## Introspection

### get_all_device_types()
#### Synopsis

#### Returns

#### Parameters

#### Examples
### get_all_devices()
#### Synopsis

#### Returns

#### Parameters

#### Examples
## Miscelaneous Helper Functions

### convert_utc()

#### Synopsis

`convert_utc(utc_string)`

Home Assistant provides timestamps of several different sorts that may be used to gain additional insight into state changes. These timestamps are in UTC and are coded as ISO 8601 Combined date and time strings. `convert_utc()` will accept one of these strings and convert it to a localised Python datetime object representing the timestamp
#### Returns

`convert_utc(utc_string)` returns a localised Python datetime object representing the timestamp.

#### Parameters

##### utc_string

An ISO 8601 encoded date and time string in the following format: `2016-07-13T14:24:02.040658-04:00`

### Writing to Logfiles

Appdaemon uses 2 separate logs - the general log and the error log. An appdaemon App can write to either of these using the standard [Logger](https://docs.python.org/3/library/logging.html) facility. The App is passed a handle to each logger instance when it is created, and these can be accessed using the instance variables `self.logger` and `self.error` as required. The logger instances accept the usual parameters including the ability to log at different severity levels. The `-D` option of appdaemon can be used to specify what level of logging is required and the logger objects will work as expected.

For example, to write an info level message to the general log use something like:

```python
self.logger.info("Log Test: Parameter is {}".format(some_variable))
```

and a warn level message to the error log:

```python
self.error.warn("Some Error string")
```