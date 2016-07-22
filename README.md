# Description

AppDaemon is a loosely coupled, multithreaded, sandboxed python execution environment for writing automation apps for [Home Assistant](https://home-assistant.io/) home automation software.

# Architecture

AppDaemon is a python daemon that consumes events from Home Assistant and feeds them to snippets of python code called "Apps". An App is a Python class that is instantiated possibly multiple times from AppDaemon and registers callbacks for various system events. It is also able to inspect and set state and call services. [The API](API.md) provides a rich environment suited to home automation tasks that can also leverage all the power of Python.

# What it actually does

The best way to show what AppDaemon does is through a few simple examples.

## Turn on a Light

Lets start with a simple App to turn a light on at a specific time - this app will turn on the porch light at 7:00pm. every night. It does so by registering a callback for AppDaemons's scheduler for a specific time. When the time occurs, the `run_daily()` function is called which then makes a call to Home Assistant to turn the porch light on.

```python
import appapi
import datetime

class NightLight(appapi.AppDaemon):

  def initialize(self):
    time = datetime.time(19, 00, 0)
    self.run_daily(self.run_daily_callback, time)
    
  def run_daily_callback(self, args, kwargs):
    self.turn_on("light.porch")
```

Doing this via an automation is also fairly simple:

```yaml
automation:
    - alias: 'Night Light On'
      trigger:
        platform: time
        after: '19:00:00'
      action:
        service: light.turn_on
        entity_id: light.porch
```

## Motion Light

Our next example is to turn on a light when motion is detected and it is dark, and turn it off after a period of time. This is still pretty simple using AppDaemon:

```python
import appapi

class MotionLights(appapi.AppDaemon):

  def initialize(self):
    self.listen_state(self.motion, "binary_sensor.drive")
  
  def motion(self, entity, attribute, old, new):
    if new == "on" and self.sun_down():
      self.turn_on("light.drive")
      self.run_in(self.light_off, 60)
  
  def light_off(self, args, kwargs):
    self.turn_off("light.drive")
```

But it's starting to look more complicated using automations:

```yaml
automation:
    - alias: 'Drive Motion After Dark'
      trigger:
        platform: state
        entity_id: binary_sensor.drive
        to: 'on'
      condition:
      - condition: sun
        after: sunset
      action:
        service: script.turn_on
        entity_id: script.drive_motion_night_on

script:
    - alias: Drive Motion Night On
        sequence:
          # Cancel ev. old timers
        - service: script.turn_off
          data:
             entity_id: script.drive_motion_night_off
        - service: light.turn_on
          data:
            entity_id: light.drive
        # Set new timer
        - service: script.turn_on
          data:
            entity_id: script.drive_motion_night_off
    - alias: Drive Motion Night Off
        sequence:
        - delay:
            minutes: 5
        - service: light.turn_off
          data:
            entity_id: light.drive     
```

Now lets extend this with a somewhat artificial example to show something that is simple in AppDaemon but very difficult if not impossible using automations. Lets warn someone inside the house that there has been motion outside by flashing a lamp on and off 10 times:

```python
import appapi

class MotionLights(appapi.AppDaemon):

  def initialize(self):
    self.listen_state(self.motion, "binary_sensor.drive")
  
  def motion(self, entity, attribute, old, new):
    if new == "on" and self.self.sun_down():
      self.turn_on("light.drive")
      self.run_in(self.light_off, 60)
      self.flashcount = 0
      self.run_in(self.flash_warning, 1)
  
  def light_off(self, args, kwargs):
    self.turn_off("light.drive")
    
  def flash_warning(self, args, kwargs):
    self.toggle("light.living_room")
    self.flashcount += 1
    if self.flashcount < 10:
      self.run_in(self.flash_warning, 1)
```

I will insert a better example here when I use the system a little more, but in the example above, AppDaemon was only just getting started and can handle way more complex tasks. Addition of more logic to for instance only flash the light when someone is home, and start a siren otherwise would be very simple. 

# AppDaemon Advantages

AppDaemon is not meant to replace Home Assistant Automations and Scripts, rather complement them. For a lot of things, automations work well and can be very succinct. However, there is a class of more complex automations for which they become harder to use, and appdeamon then comes into its own.

- New paradigm - some problems require a procedural and/or iterative approach, and Home Assistant automations are not a natural fit for this. Recent script enhancements have made huge strides, but for the most complex scenarios, Apps can do things that Automations can't
- Ease of use - AppDaemon's API is full of helper functions that make programming as easy and natural as possible. The fucntions and their operation are as "Pythonic" as possible, experienced Python programmers should feel right at home.
- Reuse - write a piece of code once and instantiate it as an app as many times as you need with different parameters e.g. a motion light program that you can use in 5 different places around your home. The code stays the same, you just dynamically add new instances of it in the config file
- Dynamic - AppDaemon has been designed from the start to enable the user to make changes without requiring a restart of Home Assistant, thanks to it's loose coupling. However, it is better than that - the user can make changes to code and AppDaemon will automatically reload the code, figure out which Apps were using it and restart them to use the new code. It is also possible to change parameters for an individual or multiple apps and have them picked up dynamically, and for a final trick, removing or adding apps is also picked up dynamically. Testing cycles become a lot more efficient as a result.
- Complex logic - Python's If/Else constructs are clearer and easier to code for arbitrarily complex nested logic
- All the power of Python - use any of Python's libraries, create your own modules, share variables, refactor and re-use code, create a single app to do everything, or multiple apps for individual tasks - nothing is off limits!

If you want to give AppDaemon a try, start with the following section.

# Installation

## 1. Clone the Repository
Clone the **AppDaemon** repository to the current local directory on your machine.

``` bash
$ git clone https://github.com/acockburn/AppDaemon.git
```

Change your working directory to the repository root. Moving forward, we will be working from this directory.

``` bash
$ cd AppDaemon
```

# Install Prereqs

Before running `AppDaemon` you will need to add some python prerequisites:

```bash
$ sudo pip3 install daemonize
$ sudo pip3 install sseclient
$ sudo pip3 install configparser
```

Some users are reporting errors with `InsecureRequestWarning`:
```
Traceback (most recent call last):
  File "./hapush.py", line 21, in <module>
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
ImportError: cannot import name 'InsecureRequestWarning'
```
This can be fixed with:
```
$ sudo pip3 install requests==2.6.0
```

When you have all the prereqs in place, edit the `[AppDaemon]` section of the conf/AppDaemon.cfg file to reflect your environment:

```
[AppDaemon]
ha_url = <some_url>
ha_key = <some key>
logfile = /etc/AppDaemon/AppDaemon.log
errorfile = /etc/AppDaemon/error.log
app_dir = /srv/hass/src/AppDaemon/apps
threads = 10
```

- `ha_url` is a reference to your home assistant installation and must include the correct port number and scheme (`http://` or `https://` as appropriate)
- `ha_key` should be set to your key if you have one, otherwise it can be removed.
- `logfile` is the path to where you want `AppDaemon` to keep its main log. When run from the command line this is not used - log messages come out on the terminal. When running as a daemon this is where the log information will go. In the example above I created a directory specifically for AppDaemon to run from, although there is no reason you can't keep it in the `AppDaemon` directory of the cloned repository.
- `errorfile` is the name of the logfile for errors - this will usually be errors during compilation and execution of the apps
- `app_dir` is the directory the apps are placed in
- `threads` - the number of dedicated worker threads to create for running the apps. Note, this will bear no resembelance to the number of apps you have, the threads are re-used and only active for as long as required to tun a particular callback or initialization,

The other sections of the file relate to App configuration and are described in the [API doc](API.md).

You can then run AppDaemon from the command line as follows:

```bash
$ ./bin/AppDaemon.py conf/AppDaemon.cfg
```

If all is well, you should start to see some log lines showing that various apps (if any are configured) are being initialized:

```
# bin/AppDaemon.py conf/AppDaemon.cfg 
2016-07-12 13:45:07,844 INFO Loading Module: /srv/hass/AppDaemon_test/conf/apps/log.py
2016-07-12 13:45:07,851 INFO Loading Object log using class Log from module log
2016-07-12 13:45:07,853 INFO Loading Module: /srv/hass/AppDaemon_test/conf/apps/sun.py
2016-07-12 13:45:07,857 INFO Loading Object sun using class Sun from module sun
2016-07-12 13:45:07,858 INFO Loading Module: /srv/hass/AppDaemon_test/conf/apps/service.py
2016-07-12 13:45:07,862 INFO Loading Object service using class Service from module service
2016-07-12 13:45:07,863 INFO Loading Module: /srv/hass/AppDaemon_test/conf/apps/mirror_light.py
2016-07-12 13:45:07,867 INFO Loading Object mirror_light using class MirrorLight from module mirror_light
2016-07-12 13:45:07,868 INFO Loading Module: /srv/hass/AppDaemon_test/conf/apps/schedule.py
2016-07-12 13:45:07,872 INFO Loading Object schedule using class Schedule from module schedule
2016-07-12 13:45:07,874 INFO Loading Module: /srv/hass/AppDaemon_test/conf/apps/state.py
2016-07-12 13:45:07,877 INFO Loading Object state using class State from module state
```

# AppDaemon arguments

usage: AppDaemon.py [-h] [-d] [-p PIDFILE]
                    [-D {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                    config

positional arguments:
  config                full path to config file

optional arguments:
  -h, --help            show this help message and exit
  -d, --daemon          run as a background process
  -p PIDFILE, --pidfile PIDFILE
                        full path to PID File
  -D {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --debug {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        debug level

-d and -p are used by the init file to start the process as a daemon and are not required if running from the command line. 

-D can be used to increase the debug level for internal AppDaemon operations as well as apps using the logging function.

# Starting At Reboot
To run `AppDaemon` at reboot, I have provided a sample init script in the `./init` directory. These have been tested on a Raspberry PI - your mileage may vary on other systems.

# Operation

Since AppDaemon under the covers uses the exact same APIs as the frontend UI, you typically see it react at about the same time to a given event. Calling back to Home Assistant is also pretty fast especially if they are running on the same machine. In action, observed latency above the built in automation component is usually sub-second.

# Updating AppDaemon
To update AppDaemon after I have released new code, just run the following command to update your copy:

```bash
$ git pull origin
```

# Release Notes

***Version 1.0***

Initial Release

## Known Issues

- There is a race condition that prevents sunrise() and sunset() from being updated to their new values for a few seconds after Sunrise and Sunset respectively
