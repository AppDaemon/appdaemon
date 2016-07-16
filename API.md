# Appdaemon API Documentation

appdaemon is a loosely coupled, sandboxed, multi-threaded Python execution environment for writing automation apps for [Home Assistant](https://home-assistant.io/) home automation software. It is intended to complement the Automation and Script components that Home Assistant currently offers.

## Anatomy of an App

Automations in appdaemon are performed by creating a piece of code (essentially a Python Class) and then instantiating it as an Object one or more times by configuring it as an App in the configuration file. The App is given a chance to register itself for whatever events it wants to subscribe to, and appdaemon will then make calls back into the Object's code when those events occur, allowing the App to respond to the event with some kind of action.

The first step is to create a unique file within the apps directory (as defined in the `[appdaemon]` section of configuration file - see [README](README.md) for further information on the configuration of appdaemon itself). This file is in fact a python module, and is expected to contain one or more classes derived from the supplied `APPDaemon` class, imported from the supplied `appapi` module. The start of an app might look like this:

```python
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
- Following a change in the status of Daylight Savings Time

In every case, the App is responsible for recreating any state it might need as if it were the first time it was ever started. If `initialize()` is called, the app can safely assume that it is either being loaded for the first time, or that all callbacks and timers have been cancelled. In either case, the APP will need to recreate them. Depending upon the application it may be desirable for the App to establish state such as whether or not a particular light is on, within the `initialize()` function to ensure that eveyrthing is as expected or to make immediate remedial action (e.g. turn off a light that might have been left on by mistake when the app was restarted).

After the `initialize()` function is in place, the rest of the app consists of functions that are called by the various callback mechanisms, and any additional functions the user wants to add as part of the program logic. Apps are able to subscribe to 2 main classes of events:

- Scheduled Events
- State Change Events

These along with their various subscription calls and helper functions will be described in detail in later sections.

To wrap up this section, here is a complete functioning App (with comments):

```python
import appapi
import datetime

# Declare Class
class NightLight(appapi.APPDaemon):
  #initialize() function which will be called at startup and reload
  def initialize(self):
    # Create a time object for 7pm
    time = datetime.time(19, 00, 0)
    # Schedule a daily callback that will call run_daily() at 7pm every night
    self.run_daily(self.run_daily_callback, time)
   
   # Our callback function will be called by the scheduler every day at 7pm 
  def run_daily_callback(self, args, kwargs):
    # Call to Home Assistant to turn the porch light on
    self.turn_on("light.porch")
```

## About the API

The implementation of the API is located in the APPDaemon class that Apps are derived from. The code for the functions is therefore available to the App simply by invoking the name of the function from the object namespace using the `self` keyword, as in the above examples. `self.turn_on()` for example is just a method defined in the parent class and made available to the child. This design decision was made to simplify some of the implementation and hide passing of unnecessary variables during the API invocation.

## Configuration of Apps
Apps are configured by specifying new sections in the configuration file. `[appdaemon]` is a reserved section, described in the [README](README.md) for configutration of appdaemon itself. The name of the section is the name the App is referred to within the systrem in logfiles etc. and must be unique.

To configure a new App you need a minimum of two directives:

- `module` - the name of the module (without the `.py`) that contains the class to be used for this App
- `class` - the name of the class as defined within the module for the APPs code

Although the section/App name must be unique, it is possible to re-use a class as many times as you want, and conversely to put as many classes in a module as you want. A sample definition for a new App might loo as follows:

```ini
[newapp]
module = new
class = NewApp
```

When appdaemon sees the follwoing configuration it will expect to find a class called `NewApp` defined in a module called `new.py` in the apps subdirectory.

WHen starting the system for the first time or when reloading an App or Module, the system will log the fact in it's main log. It is oftenm the case that there is a problem with th class, maybe a syntax error or some other problem. If that is the case, details will be output to the error log allowing the user to remedy the problem and reload.

## Steps to writing an App

1. Create the code in a new or shared module by deriving a class from APPDaemon, add required callbacks and code
2. Add the App to the configuration file
3. There is no number 3 ...

## Reloading Modules and Classes

Reloading of modules is automatic. When the system spots a change in a module, it will automatically reload and recompile the module. It will also figure out which Apps were using that Module and restart them, causing all of their existing callbacks to be cleared, and their `initialize()` function to be called.

The same is true if changes are made to an App's configuration - chaning the class, or arguments (see later) will cause that app to be reloaded in the same way. The system is also capable of detecting if a new app has been added, or if one has been removed, and it will act appropriately, staring the new app immediately and removing all callbacks for the removed app.

The suggested order for creating a new App is to add the module code first and work until it comiles cleanly, and only then add an entry in the configuration file to actually run it. A good workflow is to continuously monitor the error file (using `tail -f` on Linux for instance) to ensure that errors are seen and can be remedied.

## Passing Arguments to Apps

There wouldn't be much point in being able to run multiple versions of an App if there wasnpt some way to instruct them to do something different. For this reaosn it is possible to pass any required arguments to an App, which are then made available to the object at runtime. The arguments themselves can be called anything (apart from `module` or `class`) and are simply added into the section after the 2 mandatory directives like so:

```ini
[MyApp]
module = myapp
class = MyApp
param1 = spam
param2 = eggs
```

Within the Apps code, the 2 parameters (as well as the module and class) are available as a dictionary called `args`, and accessed as follows:

```python
param1 = self.args["param1"]
param2 = self.args["param2"]
```

A usecase for this might be an App that detectys motion and turns on a light. If you have 3 places you want to run this, rather than hardcoding this into 3 separate Apps, you need only code a single app and instantiate it 3 times with different arguments. It might look something like this:

```ini
[downstairs_motion_light]
module = motion_light
class = MotionLight
sensor = binary_sensor.downstairs_hall
light = light.downstairs_hall
[upstairs_motion_light]
module = motion_light
class = MotionLight
sensor = binary_sensor.upstairs_hall
light = light.upstairs_hall
[garage_motion_light]
module = motion_light
class = MotionLight
sensor = binary_sensor.garage
light = light.garage
```

## A Note on Threading

Appdeamon is a multi threaded design. This means that any time code within an App is executed, it is executed by one of many threads. This is generally not a particularly important consideration for this application, as in general, the execution time of callbacks is expected to be far quicker than the frequency of events causing them. However, it should be noted for completeness, that it is certainly possible for different pieces of code within the App to be executed concurrently, so some care may be necessary if different callback for instance inspect and change shared variables. This is a fairly standard caveat with concurrent programming, and if you know enough to want to do this, then you should know enough to put appropriate safeguards in place. For the average user however this shouldn't be an issue. If there are sufficient usecases to warrant it I will consider adding locking to the function invocations to make the entire infrastructure threadsafe but I am not convinced that it is necessary.

An additional caveat of a threaded worker pool environment is that it is the expectation that none of the callbacks tie threads up for a significant amount of time. To do so would eventually lead to thread exhaustion, which would make the system run behind events. No events would be lost as they would be queued, but callbacks would be delayed which is a bad thing. 

Given the above, NEVER use Python's `time.sleep()` if you want to perform an operation some time in the future, as this will tie up a thread for the period of the sleep. Instead use the scheduler's `run_in()` function which will allow you to delay without blocking any threads.

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

`get_state(entity = None, attribute = None)`

`get_state()` is used to query the state of any component within Home Assistant. State updates are continuously tracked so this call runs locally and does not require appdaemon to call back to Home Assistant and as such is very efficient.

#### Returns

`get_state()` returns a `dictionary` or single value, the structure of which varies according to the parameters used.

#### Parameters

All parameters are optional, and if `get_state()` is called with no parameters it will return the entire state of Home Assistant at that given time. This will consist of a dictionary with a key for each entity. Under that key will be the standard entity state information.

##### entity

This is the name of an entity or device type. If just a device type is provided, e.g. `light` or `binary_sensor`, `get_state()` will return a dictionary of all devices of that type, indexed by the entity_id, containing all the state for each entity.

If a fully qualified `entity_id` is provided, `get_state()` will return the state attirbute for that entity, e.g. `on` or `off` for a light.

##### attribute

Name af an attribute within the entity state object. If this parameter is specified in addition to a fully qualified `entity_id`, a single value representing the attribute will be returned, or `None` if it is not present.

The value `all` for attribute has special significance and will return the entire state dictionary for the specified entity rather than an individual attribute value.

#### Examples

```python
# Return all state for the entire system
state = self.get_state()

# Return state for all switches in the system
state = self.get_state("switch")

# Return the state attribute for light.office_1
state = self.get_state("light.office_1")

# Return the brightness attribute for light.office_1
state = self.get_state("light.office_1", "brightness")

# Return the entire state for light.office_1
state = self.get_state("light.office_1", "all")
```

### set_state()

`set_state()` will make a call back to Home Assistant and make changes to the internal state of Home Assistant. This is not something that you would usually want to do and the applications are limited however the call is included for completeness. Note that for instance, setting the state of a light to `on` won;t actually switch the device on, it will merely change the state of the device in Home Assistant so that it no longer reflects reality. In most cases, the state will be corrected the next time Home Assistant polls the device or someone causes a state change manually. To effect actual changes ot devices use one of the service call functions.

One possible use case for `set_state()` is for testing. If forinstance you are writing an App to turn on a light when it gets dark according to a luminance sensor, you can use `set_state()` to temporarily change the light level reported by the sensor to test your program. However this is also possible using the developer tools.

At the time of writing, it appears that no checking is done as to whether or not the entity exists, so it is possible to add entirely new entries to Hoome Assistant's state with this call.

#### Synopsis

`set_state(entity_id, **kwargs)`

#### Returns

`set_state()` returns a dictionary representing the state of the device after the call has completed. 

#### Parameters

##### entity_id

Entity id for whcih the state is to be set, e.g. "light.office_1".

##### values

A list of keyword values to be changed or added to the entities state. e,g, state = "off". Note that any optional attributes such as colors for bulbs etc, need to reside in a dictionary called "attributes", see the example.

#### Examples

```python
status = self.set_state("light.office_1", state = "on", attributes = {"color_name": "red"})
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

`listen_state()` allows the user to register a callback for a wide variety of state changes.

#### Synopsis

`handle = listen_state(callback, entity = None, attribute = None)`

#### Returns

A unique identifier that can be used to cancel the callback if required. Since variables created within object methods are local to the function they are created in, and in all likelihood the cancellation will be invoked later, in a different function, it is reccomended that handles are stored in the object namespace, e.g. `self.handle`

#### Parameters
All parameters except `callback` are optional, and if `listen_state()` is called with no additiional parameters it will subscribe to any state change within Home Assistant.

##### callback

Function to be invoked when the requested state change occurs. It must conform to the standard State Callback format documented above.

##### entity

This is the name of an entity or device type. If just a device type is provided, e.g. `light` or `binary_sensor`, `listen_state()` will subscribe to state changes of all devices of that type. The callback will be provided with dictionaries containing the entire old and new state of the entity who's state changed.

If a fully qualified `entity_id` is provided, `listen_state()` will listen for state changes for just that entity and will supply the callback function, in old and new, the state attirbute for that entity, e.g. `on` or `off` for a light.

##### attribute

Name af an attribute within the entity state object. If this parameter is specified in addition to a fully qualified `entity_id`, `listen_state()` will subscribe to changes for just that attribute within that specific entity. The new and old parameters in the callback function will be provided with a single value representing the attribute.

The value `all` for attribute has special significance and will listen for any state change within the specified antity, and suppley the callback functions with the entire state dictionary for the specified entity rather than an individual attribute value.
#### Examples

```python
# Listen for any state change
self.handle = self.listen_state(self.all_state)

 # Listen for any state change involving a light
self.handle = self.listen_state(self.device, "light")

# Listen for a state change involving light.office1 and return the state attribute
self.handle = self.listen_state(self.entity, "light.office_1")

# Listen for a state change involving light.office1 and return the entire state
self.handle = self.listen_state(sself.attr, "light.office_1", "all")

# Listen for a state change involving the brightness attribute of light.office1
self.handle = self.listen_state(self.attr, "light.office_1", "brightness")
```

### cancel_listen_state()

Cancel a `listen_state() callback. This will mean that the App will no longer be notified for the specific state change that has been cancelled. Other state changes will continue to be monitored.

#### Synopsis

`listen_state(handle)`

#### Returns

Nothing

#### Parameters

##### handle

The handle returned when the `listen_state()` call was made.

#### Examples

`self.cancel_listen_state(self.office_light_handle)`

## Scheduler

Appdaemon contains a powerful scheduler that is able to run with 1 second resolution to fire off specific events at set times, or after set delays, or even relative to sunrise and sunset. In general, events should be fired less than a second after specified but under certain circumstances there may be short additional delays.

### About Schedule Callbacks

As with State Change callbacks, Scheduler Callbacks expect to call into functions with a known and specific signature and a class defined Scheduler callback funciton should look like this:

```python
  def my_callback(self, args, kwargs):
    <do some useful work here>
```

You can call the fucntion whatever you like - you will reference it in the Scheduler call, and you can create as many callback functions as you need.

The parameters have the following meanings:

#### self
A standard Python object reference

#### args

Zero or more positional arguments provided at the time the shcedule entry was added

#### kwargs

A dictionary containing Zero or more keyword arguments

The use of `args` and `kwargs` are an optional but powerful way of providing information to the callback function. 

### Creation of Scheduler Callbacks

Scheduler callbacks are created through use of a number of convenience functions which can be used to suit the situation.

#### run_in()

Run the callback in a defined number of seconds. This is used to add a delay, for instance a 60 second delay before a light is turned off after it has been triggered by a motion detector. This callback should always be used instead of `time.sleep()` as discussded previously.

#### Synopsis

`self.handle = self.run_in(callback, delay, *args, **kwargs)`

#### Returns

A handle that can be used to cancel the timer.

#### Parameters

##### callback
Function to be invoked when the requested state change occurs. It must conform to the standard Scheduler Callback format documented above.

##### delay

Delay, in seconds before the callback is invoked.

##### *args, **kwargs

Arbitary positional and keyword parameters to be provided to the callback function when it is invoked

#### Examples

```python
self.handle = self.run_in(self.run_in_c, 5)
self.handle = self.run_in(self.run_in_c, 5, 5, title = "run_in5")
```
#### run_once()
#### Synopsis

`self.handle = self.run_once(callback, time, *args, **kwargs)`

#### Returns

A handle that can be used to cancel the timer.

#### Parameters

##### callback
Function to be invoked when the requested state change occurs. It must conform to the standard Scheduler Callback format documented above.

##### time

A python `time` object that specifies when the callback will occur. If the time specified is in the past, the callback will occur the next day at the specified time.

##### *args, **kwargs

Arbitary positional and keyword parameters to be provided to the callback function when it is invoked

#### Examples

```python
# Run at 4pm today, or 4pm tomorrow if it isd already after 4pm
runtime = datetime.time(16, 0, 0)
handle = self.run_once(self.run_once_c, runtime)
```
#### run_daily()

Execute a callback at the same time every day. If the time has already passed, the function will not be invoked until the following day at the specified time.

#### Synopsis

`self.handle = self.run_daily(callback, time, *args, **kwargs)`

#### Returns

A handle that can be used to cancel the timer.

#### Parameters

##### callback
Function to be invoked when the requested state change occurs. It must conform to the standard Scheduler Callback format documented above.

##### time

A python `time` object that specifies when the callback will occur. If the time specified is in the past, the callback will occur the next day at the specified time.

##### *args, **kwargs

Arbitary positional and keyword parameters to be provided to the callback function when it is invoked

#### Examples

```python
# Run daily at 7pm
time = datetime.time(19, 0, 0)
self.run_daily(self.run_daily_c, runtime)
```
#### run_hourly()
Execute a callback at the same time every hour. If the time has already passed, the function will not be invoked until the following hour at the specified time.

#### Synopsis

`self.handle = self.run_hourly(callback, time = None, *args, **kwargs)`

#### Returns

A handle that can be used to cancel the timer.

#### Parameters

##### callback
Function to be invoked when the requested state change occurs. It must conform to the standard Scheduler Callback format documented above.

##### time

A python `time` object that specifies when the callback will occur, the hour copmponent of the time object is ignored. If the time specified is in the past, the callback will occur the next hour at the specified time. If time is not supplied, the callback will start an hour from the time that `run_hourly()` was executed.

##### *args, **kwargs

Arbitary positional and keyword parameters to be provided to the callback function when it is invoked

#### Examples

```python
# Run every hour, on the hour
time = datetime.time(0, 0, 0)
self.run_daily(self.run_daily_c, runtime)
```
#### run_minutely()
Execute a callback at the same time every minute. If the time has already passed, the function will not be invoked until the following minute at the specified time.

#### Synopsis

`self.handle = self.run_minutely(callback, time = None, *args, **kwargs)`

#### Returns

A handle that can be used to cancel the timer.

#### Parameters

##### callback
Function to be invoked when the requested state change occurs. It must conform to the standard Scheduler Callback format documented above.

##### time

A python `time` object that specifies when the callback will occur, the hour and minute copmponents of the time object are ignored. If the time specified is in the past, the callback will occur the next hour at the specified time. If time is not supplied, the callback will start a minute from the time that `run_minutely()` was executed.

##### *args, **kwargs

Arbitary positional and keyword parameters to be provided to the callback function when it is invoked

#### Examples

```python
# Run Every Minute on the minute
time = datetime.time(0, 0, 0)
self.run_minutely(self.run_minutely_c, time)
```
#### run_every()
Execute a repeating callback with a configurable delay starting at a specific time.

#### Synopsis

`self.handle = self.run_minutely(callback, time, repeat, *args, **kwargs)`

#### Returns

A handle that can be used to cancel the timer.

#### Parameters

##### callback
Function to be invoked when the requested state change occurs. It must conform to the standard Scheduler Callback format documented above.

##### time

A python `time` object that specifies when the initial callback will occur.

##### repeat

After the initial callback has occured, another will occur every `repeat` seconds.

##### *args, **kwargs

Arbitary positional and keyword parameters to be provided to the callback function when it is invoked

#### Examples

```python
# Run every 17 minutes starting in 2 hours time
time = datetime.datetime.now() + datetime.timedelta(hours=2)
repeat = datetime.timedelta(minutes=17)
self.run_every(self.run_every_c, time, repeat)
```
## Sunrise and Sunset

Appdaemon has a number of features to allow easy tracking of sunrise and sunset as well as a couple of scheduler functions.
### run_at_sunrise()
Run a callback at or around sunrise.
#### Synopsis

`self.handle = self.run_at_sunrise(callback, offset, *args, **kwargs)`

#### Returns

A handle that can be used to cancel the timer.

#### Parameters

##### callback
Function to be invoked when the requested state change occurs. It must conform to the standard Scheduler Callback format documented above.

##### offset

The time in seconds that the callback should be delayed after sunrise. A negative value will result in the callback occuring before sunrise.

##### *args, **kwargs

Arbitary positional and keyword parameters to be provided to the callback function when it is invoked

#### Examples

```python
# Example using timedelta
self.run_at_sunrise(self.sun, datetime.timedelta(minutes = -45).total_seconds(), "Sunrise -45 mins")
# or you can just do the math yourself
self.run_at_sunrise(self.sun, 30 * 60, "Sunrise +30 mins")
```

### run_at_sunset()
Run a callback at or around sunset.
#### Synopsis

`self.handle = self.run_at_sunset(callback, offset, *args, **kwargs)`

#### Returns

A handle that can be used to cancel the timer.

#### Parameters

##### callback
Function to be invoked when the requested state change occurs. It must conform to the standard Scheduler Callback format documented above.

##### offset

The time in seconds that the callback should be delayed after sunset. A negative value will result in the callback occuring before sunset.

##### *args, **kwargs

Arbitary positional and keyword parameters to be provided to the callback function when it is invoked

#### Examples

```python
# Example using timedelta
self.run_at_sunset(self.sun, datetime.timedelta(minutes = -45).total_seconds(), "Sunset -45 mins")
# or you can just do the math yourself
self.run_at_sunset(self.sun, 30 * 60, "Sunset +30 mins")
```
### sunrise()
Return the time that the next Sunrise will occur
#### Synopsis
`self.sunrise()`
#### Returns
A python datetime that represents the next time Sunrise will occur.
#### Examples
```python
rise_time = self.sunrise()
```
### sunset()
Return the time that the next Sunset will occur
#### Synopsis
`self.sunset()`
#### Returns
A python datetime that represents the next time Sunset will occur.
#### Examples
```python
set_time = self.sunset()
```
### sun_up()
A function that alows you to determine if the sun is currently up.
#### Synopsis
result = self.sun_up()`
#### Returns
`True` if the sun is up, False otherwise.
#### Examples
```python
if self.sun_up():
    do something

### sun_down()
A function that alows you to determine if the sun is currently down.
#### Synopsis
result = self.sun_down()`
#### Returns
`True` if the sun is down, False otherwise.
#### Examples
```python
if self.sun_down():
    do something
```
## Calling Services
### About Services
Services within Home Assistant are how changes are made to the system and its devices. Services can be used to tutn lights on and off, set thermostats and a whole number of other things. Home Assistant supplies a single interface to allk of these disparate services that take arbitary parameters. Appdaemon provides the `call_service()` function to call into Home Assistant and run a service. In addition, it also provides convenience finctions for some of the more common services making calling them a little easier.
### call_service()
Call service is the basic way of calling a service within appdaemon. It can call any service and provide any required parameters. Available services can be found using the developer tools in the UI. For listed services, the part before the first period is the domain, and the part after is the service name. For instance, `light.turn_on` has a domain of 1light1 and a service name of `turn_on`.
#### Synopsis
self.call_service(self, domain, service, **kwargs)
#### Returns
None
#### Parameters
##### domain
The domain of the service, e.g. `light` or `switch`. 
##### service
The service name, e.g. `turn_on`.
##### **kwargs
Each service has different parameter requirements. This argument allows you to specify a comma separated list of keyword value pairs, e,g, `entity_id = light.office_1`. These parameters will be different for every service and can be discovered using the developer tools. Most if not all service calls require an entity_id however, so use of the above example is very common with this call.
#### Examples
```python
self.call_service("light", "turn_on", entity_id = "light.office_lamp", color_name = "red")
self.call_service("notify", "notify", title = "Hello", message = "Hello World")
```
### turn_on()
This is a convenience function for the `homassistant.turn_on` function. It is able to turn on pretty much anything in Home Assistant that can be turned on or run:

- Lights
- Switches
- Scenes
- Scripts

And many more.

#### Synopsis
```python
self.turn_on(entity_id, **kwargs)
```
#### Returns
None
#### Parameters
##### entity_id
Fully qualified entity_id of the thing to be turned on, e.g. `light.office_lamp` or ```scene.downstairs_on```
##### **kwargs
A comma separated list of key value pairs to allow specification of parameters over and above ```entity_id```.
#### Examples
self.turn_on("switch.patio_lights")
self.turn_on("scene.bedrrom_on")
self.turn_on("light.office_1", color_name = "green")
### turn_off()
This is a convenience function for the `homassistant.turn_off` function. Like ```homeassistant.turn_on```it is able to turn off pretty much anything in Home Assistant that can be turned off.
#### Synopsis
```python
self.turn_off(entity_id)
```
#### Returns
None
#### Parameters
##### entity_id
Fully qualified entity_id of the thing to be turned off, e.g. `light.office_lamp` or ```scene.downstairs_on```
#### Examples
self.turn_off("switch.patio_lights")
self.turn_off("light.office_1")
### toggle()
This is a convenience function for the `homassistant.toggle` function. It is able to flip the state of pretty much anything in Home Assistant that can be turned on or off.

#### Synopsis
```python
self.toggle(entity_id)
```
#### Returns
None
#### Parameters
##### entity_id
Fully qualified entity_id of the thing to be toggled, e.g. `light.office_lamp` or ```scene.downstairs_on```

#### Examples
self.toggle("switch.patio_lights")
self.toggle("light.office_1", color_name = "green")
## Presence
Presence in Home Assistant is tracked using Device Trackers. The state of all device trackers can be found using the ```get_state()``` call, however appdaemon provides several convenience functions to make this easier.
### get_trackers()
Return a list of all device trackers. This is designed to be iterated over.
#### Synopsis
```tracker_list = get_trackers()```
#### Returns
An iterable list of all device trackers.
#### Examples
```python
trackers = self.get_trackers()
for tracker in trackers:
    do something
```
### get_tracker_state()
Get the state of a tracker. The values returned depend in part on the configuration and type of device trackers in the system. Simpler tracker types like `Locative` or `NMAP` will return one of 2 states:
- home
- not_home
Some types of device tracker are in addition able to supply locations that have been configured as Geofences, in which case the name of that location can be returned.
#### Synopsis
```python
location = self.get_tracker_state(tracker_id)
```
#### Returns
A string representing the location of the tracker.
#### Parameters
##### tracker_id
Fully qualified entity_id of the device tracker to query, e.g. `device_tracker.andrew`.
#### Examples
```python
trackers = self.get_trackers()
for tracker in trackers:
  self.log("{} is {}".format(tracker, self.get_tracker_state(tracker)))
```
### everyone_home()
A convenience function to determine if everyone is home. Use this in preference to getting the state of group.all_devices() as it avoids a race condition when using state change callbacks for device trackers.
#### Synopsis
```python
result = self.everyone_home()
```
#### Returns
Returns `True` if everyone is home, `False` otherwise.
#### Examples
```python
if self.everyone_home():
    do something
```
### anyone_home()
A convenience function to determine if one or more person is home. Use this in preference to getting the state of group.all_devices() as it avoids a race condition when using state change callbacks for device trackers.
#### Synopsis
```python
result = self.anyone_home()
```
#### Returns
Returns `True` if anyone is home, `False` otherwise.
#### Examples
```python
if self.anyone_home():
    do something
```
### noone_home()
A convenience function to determine if no people are home. Use this in preference to getting the state of group.all_devices() as it avoids a race condition when using state change callbacks for devioe trackers.
#### Synopsis
```python
result = self.noone_home()
```
#### Returns
Returns `True` if noone is home, `False` otherwise.
#### Examples
```python
if self.noone_home():
    do something
```

## Miscelaneous Helper Functions

### convert_utc()
Home Assistant provides timestamps of several different sorts that may be used to gain additional insight into state changes. These timestamps are in UTC and are coded as ISO 8601 Combined date and time strings. `convert_utc()` will accept one of these strings and convert it to a localised Python datetime object representing the timestamp
#### Synopsis

`convert_utc(utc_string)`

#### Returns

`convert_utc(utc_string)` returns a localised Python datetime object representing the timestamp.

#### Parameters

##### utc_string

An ISO 8601 encoded date and time string in the following format: `2016-07-13T14:24:02.040658-04:00`

#### Example

```python
time = self.convert_utc(self.get_state("sun.sun", "next_setting"))
```

### friendly_name()
```frindly_name()``` will return the Friendly Name of an entity if it has one.
#### Synopsis
```Name = self.friendly_name(entity_id)```
#### Returns
The friendly name of the entity if it exists or ```None```
#### Example
```python
tracker = "device_tracker.andrew"
self.log("{}  ({}) is {}".format(tracker, self.friendly_name(tracker), self.get_tracker_state(tracker)))
```

### Writing to Logfiles

Appdaemon uses 2 separate logs - the general log and the error log. An appdaemon App can write to either of these using the supplied convenience methods `log()` and `error()`, which are provided as part of parent `APPDaemon` class, and the call will automatically pre-pend the name of the App making the call. The `-D` option of appdaemon can be used to specify what level of logging is required and the logger objects will work as expected.

### log()
#### Synopsis

`log(message)`

#### Returns

Nothing

#### Parameters

##### Message

The message to log.

#### Examples

```python
self.log("Log Test: Parameter is {}".format(some_variable))
```

### error()
#### Synopsis
`error(message)`
#### Returns

Nothing

#### Parameters

##### Message

The message to log.

#### Examples

```python
self.error("Some Error string")
```