# Description

AppDaemon is a loosely coupled, multithreaded, sandboxed python execution environment for writing automation apps for [Home Assistant](https://home-assistant.io/) home automation software. As of release 2,0,0 it also provides a configurable dashboard (HADashboard) suitable for wall mounted tablets.

# Installation

Installation is either by pip3 or Docker.

## Clone the Repository

For either method you will need to clone the **AppDaemon** repository to the current local directory on your machine.

``` bash
$ git clone https://github.com/home-assistant/appdaemon.git
```

Change your working directory to the repository root. Moving forward, we will be working from this directory.

``` bash
$ cd appdaemon
```

## Install using Docker

To build the Docker image run the following:

``` bash
$ docker build -t appdaemon .
```

(Note the period at the end of the above command)

## Install Using PIP3

Before running `AppDaemon` you will need to install the package:

```bash
$ sudo pip3 install .
```

# Configuration

When you have appdaemon installed by either method, copy the `conf/appdaemon.yaml.example` file to `conf/appdaemon.yaml`, then edit the `AppDaemon` section to reflect your environment:

```yaml
AppDaemon:
  logfile: STDOUT
  errorfile: STDERR
  threads: 10
  cert_path: <path/to/root/CA/cert>
  cert_verify: True
HASS:
  ha_url: <some_url>
  ha_key: <some key>

# Apps
hello_world:
  module: hello
  class: HelloWorld
```

- `ha_url` is a reference to your home assistant installation and must include the correct port number and scheme (`http://` or `https://` as appropriate)
- `ha_key` should be set to your key if you have one, otherwise it can be removed.
- `logfile` (optional) is the path to where you want `AppDaemon` to keep its main log. When run from the command line this is not used - log messages come out on the terminal. When running as a daemon this is where the log information will go. In the example above I created a directory specifically for AppDaemon to run from, although there is no reason you can't keep it in the `appdaemon` directory of the cloned repository. If `logfile = STDOUT`, output will be sent to stdout instead of stderr when running in the foreground, if not specified, output will be sent to STDOUT.
- `errorfile` (optional) is the name of the logfile for errors - this will usually be errors during compilation and execution of the apps. If `errorfile = STDERR` errors will be sent to stderr instead of a file, if not specified, output will be sent to STDERR.
- `threads` - the number of dedicated worker threads to create for running the apps. Note, this will bear no resembelance to the number of apps you have, the threads are re-used and only active for as long as required to tun a particular callback or initialization, leave this set to 10 unless you experience thread starvation
- `cert_path` (optional) - path to root CA cert directory - use only if you are using self signed certs.
- `cert_verify` (optional) - flag for cert verification - set to `False` to disable verification on self signed certs.

Optionally, you can place your apps in a directory other than under the config directory using the `app_dir` directive.

e.g.:

```ini
app_dir = /etc/appdaemon/apps
```

The `#Apps` section is the configuration for the Hello World program and should be left in place for initial testing but can be removed later if desired, as other Apps are added, App configuration is described in the [API doc](API.md).

## Configuring the Dashboard

Configuration of the dashboard component (HADashboard) is described separately in the [Dashboard doc](DASHBOARD.md)

## Docker

For Docker Configuration you need to take a couple of extra things into consideration.

Our Docker image is designed to load your configuration and apps from a volume at `/conf` so that you can manage them in your own git repository, or place them anywhere else on the system and map them using the Docker command line.

For example, if you have a local repository in `/Users/foo/ha-config` containing the following files:

```bash
$ git ls-files
configuration.yaml
customize.yaml
known_devices.yaml
appdaemon.yaml
apps
apps/magic.py
```

You can run Docker and point the conf volume to that directory.

# Example Apps

There are a number of example apps under conf/examples, and the `conf/examples.yaml` file gives sample parameters for them.

# Running

As configured, AppDaemon comes with a single HelloWorld App that will send a greeting to the logfile to show that everything is working correctly.

## Docker

Assuming you have set the config up as described above for Docker, you can run it with the command:

```bash
$ docker run -d -v <Path to Config>/conf:/conf --name appdaemon appdaemon:latest
```

In the example above you would use:

```bash
$ docker run -d -v /Users/foo/ha-config:/conf --name appdaemon appdaemon:latest
```

Where you place the `conf` and `conf/apps` directory is up to you - it can be in downloaded repostory, or anywhere else on the host, as long as you use the correct mapping in the `docker run` command.

You can inspect the logs as follows:

```bash
$ docker logs appdaemon
2016-08-22 10:08:16,575 INFO Got initial state
2016-08-22 10:08:16,576 INFO Loading Module: /export/hass/appdaemon_test/conf/apps/hello.py
2016-08-22 10:08:16,578 INFO Loading Object hello_world using class HelloWorld from module hello
2016-08-22 10:08:16,580 INFO Hello from AppDaemon
2016-08-22 10:08:16,584 INFO You are now ready to run Apps!
```

Note that for Docker, the error and regular logs are combined.

## PIP3

You can then run AppDaemon from the command line as follows:

```bash
$ appdaemon -c conf
```

If all is well, you should see something like the following:

```
$ appdaemon -c conf
2016-08-22 10:08:16,575 INFO Got initial state
2016-08-22 10:08:16,576 INFO Loading Module: /export/hass/appdaemon_test/conf/apps/hello.py
2016-08-22 10:08:16,578 INFO Loading Object hello_world using class HelloWorld from module hello
2016-08-22 10:08:16,580 INFO Hello from AppDaemon
2016-08-22 10:08:16,584 INFO You are now ready to run Apps!
```

# AppDaemon arguments

usage: appdaemon [-h] [-c CONFIG] [-p PIDFILE] [-t TICK] [-s STARTTIME]
                 [-e ENDTIME] [-i INTERVAL]
                 [-D {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [-v] [-d]

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        full path to config diectory
  -p PIDFILE, --pidfile PIDFILE
                        full path to PID File
  -t TICK, --tick TICK  time in seconds that a tick in the schedular lasts
  -s STARTTIME, --starttime STARTTIME
                        start time for scheduler <YYYY-MM-DD HH:MM:SS>
  -e ENDTIME, --endtime ENDTIME
                        end time for scheduler <YYYY-MM-DD HH:MM:SS>
  -i INTERVAL, --interval INTERVAL
                        multiplier for scheduler tick
  -D {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --debug {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        debug level
  -v, --version         show program's version number and exit
  -d, --daemon          run as a background process

-c is the path to the configuration directory. If not specified, AppDaemon will look for a file named `appdaemon.cfg` first in `~/.homeassistant` then in `/etc/appdaemon`. If the directory is not specified and it is not found in either location, AppDaemon will raise an exception. In addition, AppDaemon expects to find a dir named `apps` immediately subordinate to the config directory.                    
                        
-d and -p are used by the init file to start the process as a daemon and are not required if running from the command line. 

-D can be used to increase the debug level for internal AppDaemon operations as well as apps using the logging function.

The -s, -i, -t and -s options are for the Time Travel feature and should only be used for testing. They are described in more detail in the API documentation. 

# Legacy Configuration

AppDaemon also currently supports a legacy `ini` style of configuration and it is shown here for backward compatibility. It is recommended that you move to the YAML format using the provided tool. When using the legacy configuration style, there are no `HASS` or `HADashboard` sections - the associated directives all go in the `AppDaemon` section.


```ini
[AppDaemon]
ha_url = <some_url>
ha_key = <some key>
logfile = STDOUT
errorfile = STDERR
threads = 10
cert_path = <path/to/root/CA/cert>
cert_verify = True
# Apps
[hello_world]
module = hello
class = HelloWorld
```

If you want to move from the legacy `ini` style of configuration to YAML, AppDaemon is able to do this for you. From the command line run:

```bash
$ appdaemon -c CONFIG --convertcfg
Converting /etc/appdaemon/appdaemon.cfg to /etc/appdaemon/appdaemon.yaml
$
```

AppDaemon should correctly figure out where the file is to convert form your existing configuration. After conversion, the new YAML file will be used in preference to the old ini file, which can then be removed if desired.

Note: any lines in the ini file that are commented out, whether actual comments of lines that are not active, will not be converted.
Note 2: Docker users will unfortunately need to perform the conversion manually.

# Starting At Reboot
To run `AppDaemon` at reboot, I have provided a sample init script in the `./scripts` directory. These have been tested on a Raspberry PI - your mileage may vary on other systems. There is also a sample Systemd script.

# Operation

Since AppDaemon under the covers uses the exact same APIs as the frontend UI, you typically see it react at about the same time to a given event. Calling back to Home Assistant is also pretty fast especially if they are running on the same machine. In action, observed latency above the built in automation component is usually sub-second.

# Updating AppDaemon
To update AppDaemon after I have released new code, just run the following command to update your copy:

```bash
$ git pull origin
```

If you are using pip3 for the install do this:

```bash
$ sudo pip3 uninstall appdaemon
$ sudo pip3 install .
```

If you are using docker, rerun the steps to create a new docker image.

# Windows Support

AppDaemon runs under windows and has been tested with the official 3.5.2 release. There are a couple of caveats however:

- The `-d` or `--daemonize` option is not supported owing to limitations in the Windows implementation of Python.
- Some internal diagnostics are disabled. This is not user visible but may hamper troubleshooting of internal issues if any crop up

AppDaemon can be installed exactlky as per the instructions for every other version using pip3.

# Windows Under the Linux Subsystem

Windows 10 now supports a full Linux bash environment that is capable of running Python. This is essentially an Ubuntu distribution and works extremely well. It is possible to run AppDaemon in exactly the same way as for Linux distributions, and none of the above Windows Caveats apply to this version. This is the reccomended way to run AppDaemon in a Windows 10 and later environment.