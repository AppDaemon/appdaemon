# Description

AppDaemon is a loosely coupled, multithreaded, sandboxed python execution environment for writing automation apps for [Home Assistant](https://home-assistant.io/) home automation software.

# Installation

## Clone the Repository
Clone the **AppDaemon** repository to the current local directory on your machine.

``` bash
$ git clone https://github.com/acockburn/AppDaemon.git
```

Change your working directory to the repository root. Moving forward, we will be working from this directory.

``` bash
$ cd appdaemon
```

# Install Prereqs

Before running `AppDaemon` you will need to add some python prerequisites:

```bash
$ sudo pip3 install daemonize
$ sudo pip3 install sseclient
$ sudo pip3 install configparser
$ sudo pip3 install astral
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
$ sudo pip3 install --upgrade requests
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
latitude = <latitude>
longitude = <longitude>
elevation = <elevation
timezone = <timezone>
```

- `ha_url` is a reference to your home assistant installation and must include the correct port number and scheme (`http://` or `https://` as appropriate)
- `ha_key` should be set to your key if you have one, otherwise it can be removed.
- `logfile` is the path to where you want `AppDaemon` to keep its main log. When run from the command line this is not used - log messages come out on the terminal. When running as a daemon this is where the log information will go. In the example above I created a directory specifically for AppDaemon to run from, although there is no reason you can't keep it in the `appdaemon` directory of the cloned repository.
- `errorfile` is the name of the logfile for errors - this will usually be errors during compilation and execution of the apps
- `app_dir` is the directory the apps are placed in
- `threads` - the number of dedicated worker threads to create for running the apps. Note, this will bear no resembelance to the number of apps you have, the threads are re-used and only active for as long as required to tun a particular callback or initialization,
- `latitude`, `longitude`, `elevation`, `timezone` - should all be copied from your home assistant configuration file

The other sections of the file relate to App configuration and are described in the [API doc](API.md).

You can then run AppDaemon from the command line as follows:

```bash
$ ./bin/appdaemon.py conf/appdaemon.cfg
```

If all is well, you should start to see some log lines showing that various apps (if any are configured) are being initialized:

```
# bin/appdaemon.py conf/appdaemon.cfg 
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
