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

In most cases, the sttribute `state` has the most important value in it, e.g. for a light or switch this will be `on` or `off`, for a sensor it will be the value of that sensor.

### get_state()

#### Synopsis

`get_state(entity_id = None, attribute = None)`

`get_state()` is used to query the state of any component within Home Assistant. State updates are continuously tracked so this call runs locally and does not require appdaemon to call back to Home Assistant and as such is very efficient.

#### Returns

`get_state()` returns a `dictionary` or string object, the structure of which varies according to the parameters used.

#### Parameters

All parameters are optional, and if `get_state()` is called with no parameters it will return the entire state of Home Assistant at that given time. This will consist of a dictionary with a key for each entity. Under that key will be the standard entity state information.

##### entity_id

Fully qualified entity id to get state for, e.g. `light.office` or `sensor.lightlevel`. To find the correct entity id, use the developer tools in the Home Assistant UI. Specifying just an entity id will return the state attribute for that entity, (e.g. "on" or "off" for a light), or `None` if it doesn't exist.

##### attribute

Name af an attribute within the entity state object. If this parameter is specified, a single value representing the attribute will be returned, or `None` if it is not present.

The value `all` for attribute has special significance and will return the entire state dictionary for the specified entity rather than an individual attribute value.

### set_state()

### About State Callbacks

### Creation of State Callbacks

### listen_state()

### cancel_listen_state()

## Scheduler

### About Schedule Callbacks

### Creation of Scheduler Callbacks

#### run_in()

#### run_once()

#### run_daily()

#### run_hourly()

#### run_minutely()

#### run_every()

## Sunrise/Sunset

#### run_at_sunrise()

### run_at_sunset()

### sunrise()

### sunset()

### sun_state()

## Calling Services

### About Services

### call_service()

### turn_on()

### turn_off()

### toggle()

## Presence

### get_trackers()

### get_tracker_state()

### everyone_home()

## Introspection

### get_all_device_types()

### get_all_devices()

## Miscelaneous Helper Functions

### convert_utc()
