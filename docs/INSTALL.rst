Installation
============

Installation is either by pip3 or Docker. There is also an official
hass.io build.

Note: Windows and Raspbian users should check the environment specific section at the end of this doc for additional information.

Install and Run using Docker
----------------------------

Follow the instructions in the `Docker Tutorial <DOCKER_TUTORIAL.html>`__

Install Using pip3
------------------

Before running ``AppDaemon`` you will need to install the package:

.. code:: bash

    $ sudo pip3 install --pre appdaemon

Note: the ``--pre`` flag is required or you will install version 2.1.12. There are many breaking changes between 2.1.12 and this beta so ensure you have the correct version installed before proceeding.

Install Using hass.io
---------------------

There are a couple of hass.io addons for AppDaemon maintained by:

- `frenck <https://github.com/hassio-addons/repository>`__.
- `sparck75 <https://github.com/sparck75/hassio-addons>`__.


Configuration
-------------

When you have appdaemon installed by either method you are ready to
start working on the appdaemon.yaml file. For docker users, you will
already have a skeleton to work with. For pip users, you need to create
a configuration directory somewhere (e.g. ``/home/homeassistant/conf``)
and create a file in there called ``appdaemon.yaml``.

Your initial file should look something like this:

.. code:: yaml

     appdaemon:
       threads: 10
       plugins:
         HASS:
           type: hass
           ha_url: <some_url>
           ha_key: <some_key>

A more complete example could look like the following:

.. code:: yaml

    secrets: /some/path
    log:
      accessfile: /export/hass/appdaemon_test/logs/access.log
      errorfile: /export/hass/appdaemon_test/logs/error.log
      logfile: /export/hass/appdaemon_test/logs/appdaemon.log
      log_generations: 3
      log_size: 1000000
    appdaemon:
      threads: 10
      time_zone: <time zone>
      api_port: 5000
      api_key: !secret api_key
      api_ssl_certificate: <path/to/root/CA/cert>
      api_ssl_key: <path/to/root/CA/key>
      plugins:
        HASS:
          type: hass
          ha_url: <some_url>
          ha_key: <some key>
          cert_path: <path/to/root/CA/cert>
          cert_verify: True
          namespace: default

The top level consists of a number of sections:

secrets
~~~~~~~

AppDaemon supports the use of secrets in the configuration file, to allow separate storage of sensitive information such as passwords. For this to work, AppDaemon expects to find a file called ``secrets.yaml`` in the configuration directory, or a named file introduced by the top level ``secrets:`` section. The file should be a simple list of all the secrets. The secrets can be referred to using a !secret value in the configuration file.

The ``secret:`` section is optional. If it doesn't exist, AppDaemon looks for a file called ``secrets.yaml`` in the config directory.

An example ``secrets.yaml`` might look like this:

.. code:: yaml

    home_assistant_key: password123
    appdaemon_key: password456

The secrets can then be referred to as follows:

.. code:: yaml

    appdaemon:
      api_key: !secret appdaemon_key
      threads: '10'
      plugins:
        HASS:
          type: hass
          ha_key: !secret home_assistant_key
          ha_url: http://192.168.1.20:8123

log
~~~

The ``log:`` section is optional but if included, must have at least one directive in it. The directives are as follows:

-  ``logfile`` (optional) is the path to where you want ``AppDaemon`` to
   keep its main log. When run from the command line this is not used
   -log messages come out on the terminal. When running as a daemon this
   is where the log information will go. In the example above I created
   a directory specifically for AppDaemon to run from, although there is
   no reason you can't keep it in the ``appdaemon`` directory of the
   cloned repository. If ``logfile = STDOUT``, output will be sent to
   stdout instead of stderr when running in the foreground, if not
   specified, output will be sent to STDOUT.
-  ``errorfile`` (optional) is the name of the logfile for errors - this
   will usually be errors during compilation and execution of the apps.
   If ``errorfile = STDERR`` errors will be sent to stderr instead of a
   file, if not specified, output will be sent to STDERR.
-  ``diagfile`` (optional) is the name of the log files for diagnostic information. This will contain information form the ``log_thread_actions`` parameter, as well as information dumped from AppDaemon's internal state when the AppDaemon process is sent a ``SIGUSR1`` signal.
-  ``log_size`` (optional) is the maximum size a logfile will get to
   before it is rotated if not specified, this will default to 1000000
   bytes.
-  ``log_generations`` (optional) is the number of rotated logfiles that
   will be retained before they are overwritten if not specified, this
   will default to 3 files.

appdaemon
~~~~~~~~~

The ``appdaemon:`` section has a number of directives:

-  ``threads`` (required) - the number of dedicated worker threads to create for
   running the apps. Note, this will bear no resembelance to the number
   of apps you have, the threads are re-used and only active for as long
   as required to run a particular callback or initialization, leave
   this set to 10 unless you experience thread starvation
-  ``filters`` (optional) - see below
-  ``plugins`` (required) - see below
-  ``latitude`` (optional) - latitude for AppDaemon to use. If not
   specified, AppDaemon will query the latitude from Home Assistant
-  ``longitude`` (optional) - longitude for AppDaemon to use. If not
   specified, AppDaemon will query the longitude from Home Assistant
-  ``elevation`` (optional) - elevation for AppDaemon to use. If not
   specified, AppDaemon will query the elevation from Home Assistant
-  ``time_zone`` (optional) - timezone for AppDaemon to use. If not
   specified, AppDaemon will query the timezone from Home Assistant
-  ``api_key`` (optional) - adds the requirement for AppDaemon API calls
   to provide a key in the header of a request
-  ``api_ssl_certificate`` (optional) - certificate to use when running
   the API over SSL
-  ``api_ssl_key`` (optional) - key to use when running the API over SSL
-  ``exclude_dirs`` (optional) - a list of subdirectories to ignore under the apps directory when looking for apps
- ``missing_app_warnings`` (optional) - by default, AppDaemon will log a warning if it finds a python file that has no associated configuration in an apps.yaml file. If this parameter is set to ``1`` the warning will be suppressed. This allows non-appdaemon python files to be distributed along with apps.
- ``invalid_yaml_warnings`` (optional) - by default, AppDaemon will log a warning if it finds an apps.yaml file that doesn't include "class" and "module" for an app. If this parameter is set to ``1`` the warning will be suppressed. This is intended to ease the distribution of additional yaml files along with apps.
- ``production_mode`` (optional) - If set to true, AppDaemon will only check for changes in Apps and apps.yaml files when AppDaemon is restarted, as opposed to every second. This can save some processing power on busy systems. Defaults to ``False``
- ``log_thread_actions`` (optional) - if set to 1, AppDaemon will log all callbacks on entry and exit for the scheduler, events and state changes - this can be useful for troubleshooting thread starvation issues
When using the ``exclude_dirs`` directive you should supply a list of directory names that should be ignored, e.g.

.. code:: yaml

    exclude_dirs:
        - dir1
        - dir2
        - dir3

AppDaemon will search for matching directory names at any level of the folder hierarchy under appdir and will exclude that directory and any beneath it. It is not possible to match multiple level directory names e.g. ``somedir/dir1``. In that case the match should be on ``dir1``, with the caveat that if you have dir1 anywhere else in the hierarchy it will also be excluded.

In the required ``plugins:`` sub-section, there will usually be one or more plugins with a number of directives introduced by a top level name:

-  ``type`` (required) The type of the plugin. For Home Assistant this will always be ``hass``
-  ``ha_url`` (required for the ``hass`` plugin) is a reference to your home assistant installation and
   must include the correct port number and scheme (``http://`` or ``https://`` as appropriate)
-  ``ha_key`` (required for the ``hass`` plugin) should be set to your home assistant password if you have one, otherwise it can be removed.
-  ``cert_verify`` (optional) - flag for cert verification for HASS -
   set to ``False`` to disable verification on self signed certs, or certs for which the address used doesn;tmatch the cert address (e.g. using an internal IP address)
-  ``api_port`` (optional) - Port the AppDaemon RESTFul API will listen
   on. If not specified, the RESTFul API will be turned off.
-  ``namespace`` (optional) - which namespace to use. This can safely be left out unless you are planning to use multiple plugins (see below)
-  ``app_init_delay`` (optional) - If sepcified, when AppDaemon connects to HASS each time, it will wait for this number of seconds before initializing apps and listening for events. This is useful for HASS instances that have subsystems that take time to initialize (e.g. zwave).
Optionally, you can place your apps in a directory other than under the
config directory using the ``app_dir`` directive.

e.g.:

.. code:: yaml

    app_dir: /etc/appdaemon/apps

A Note About Plugins
~~~~~~~~~~~~~~~~~~~~

In the example above, you will see that home assistant is configured as a plugin.
For most applications there is little significance to this - just configure a single plugin for HASS exactly as above. However, for power users this is a way to allow AppDaemon to work with more than one installation of Home Assistant.
The plugin architecture also allows the creation of plugins for other purposes, e.g.
different home automation systems.

To configure more than one plugin, simply add a new section to the plugins list and configure it appropriately.
Before you do this, make sure to review the section on namespaces to fully understand what this entails, and if you are using more than one plugin, make sure you use the namespace directive to create a unique namespace for each plugin.
(One of the plugins may be safely allowed to use the default value, however any more than that will require the namespace directive. There is also no harm in giving them all namespaces, since the default namespace is literally ``default``
and has no particular significance, it's just a different name, but if you use namespaces other than default you will need to change your Apps to understand which namespaces are in use.).

Filters
~~~~~~~

The use of filters allows you to run an arbitary command against a file with a specific extenstion to generate a new .py file. The usecases for this are varied, but this can be used to run a preprocessor on an app, or perhaps some kind of global substitute or any of a number of other commands. AppDaemon, when made aware of the filter via configurtion, will look for files in the appdir with the specified extension, and run the specified command on them writing the output to a new file with the specified extension. The output extension would usually be a .py file whcih would then be picked up by normal app processing, meaning that if you edit the original input file, the result will be a new .py file that is part of an app whcih will then be restarted.

In addition, it is possible to chain multiple filters, as the filter list is processed in order - just ensure you end with a .py file.

A simple filter would look like this:

    .. code:: yaml

        filters:
          - command_line: /bin/cat $1 > $2
            input_ext: cat
            output_ext: py

This would result in AppDaemon looking for any files with the extension ``.cat`` and running the ``/bin/cat`` command and creating a file with an extension of ``.py``. In the ``command_line``, ``$1`` and ``$2`` are replaced by the correctly named input and output files. In this example the output is just a copy of the input but this technique could be used with commands such as sed and awk, or even m4 for more complex manipulations.

A chained set of filters might look like this:

    .. code:: yaml

        filters:
          - command_line: /bin/cat $1 > $2
            input_ext: mat
            output_ext: cat
          - command_line: /bin/cat $1 > $2
            input_ext: cat
            output_ext: py

These will run in order resulting in edits to a ``.mat`` file running through the 2 filters and resulting in a new .py file which will run as the app in the usual way.

Finally, it is possible to have multiple unconnected fiters like so:

    .. code:: yaml

        filters:
          - command_line: /bin/cat $1 > $2
            input_ext: mat
            output_ext: .py
          - command_line: /bin/cat $1 > $2
            input_ext: cat
            output_ext: py

Here we have defined ``.mat`` and ``.cat`` files as both creating new apps. In a real world example the ``command_line`` would be different.

Configuring a Test App
~~~~~~~~~~~~~~~~~~~~~~

To add an initial test app to match the configuration above, we need to
first create an ``apps`` subdirectory under the conf directory. Then
create a file in the apps directory called ``hello.py``, and paste the
following into it using your favorite text editor:

.. code:: python

    import appdaemon.plugins.hass.hassapi as hass

    #
    # Hello World App
    #
    # Args:
    #

    class HelloWorld(hass.Hass):

      def initialize(self):
         self.log("Hello from AppDaemon")
         self.log("You are now ready to run Apps!")

Then, we can create a file called apps.yaml in the apps directory and add an entry for the Hello World App like this:

.. code:: yaml

    hello_world:
      module: hello
      class: HelloWorld

App configuration is fully described in the `API doc <API.md>`__.

With this app in place we will be able to test the App part of AppDaemon
when we first run it.

Configuring the Dashboard
~~~~~~~~~~~~~~~~~~~~~~~~~

Configuration of the dashboard component (HADashboard) is described
separately in the `Dashboard doc <DASHBOARD_INSTALL.html>`__

Example Apps
------------

There are a number of example apps under ``conf/examples`` in the git
repository, and the ``conf/examples.yaml`` file gives sample parameters
for them.

Running
-------

Docker
~~~~~~

Assuming you have set the config up as described in the tutotial for
Docker, you should see the logs output as follows:

.. code:: bash

    $ docker logs appdaemon
    2016-08-22 10:08:16,575 INFO Got initial state
    2016-08-22 10:08:16,576 INFO Loading Module: /export/hass/appdaemon_test/conf/apps/hello.py
    2016-08-22 10:08:16,578 INFO Loading Object hello_world using class HelloWorld from module hello
    2016-08-22 10:08:16,580 INFO Hello from AppDaemon
    2016-08-22 10:08:16,584 INFO You are now ready to run Apps!

Note that for Docker, the error and regular logs are combined.

PIP3
~~~~

You can run AppDaemon from the command line as follows:

.. code:: bash

    $ appdaemon -c /home/homeassistant/conf

If all is well, you should see something like the following:

::

    $ appdaemon -c /home/homeassistant/conf
    2016-08-22 10:08:16,575 INFO Got initial state
    2016-08-22 10:08:16,576 INFO Loading Module: /home/homeassistant/conf/apps/hello.py
    2016-08-22 10:08:16,578 INFO Loading Object hello_world using class HelloWorld from module hello
    2016-08-22 10:08:16,580 INFO Hello from AppDaemon
    2016-08-22 10:08:16,584 INFO You are now ready to run Apps!

AppDaemon arguments
-------------------

::

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

-c is the path to the configuration directory. If not specified,
AppDaemon will look for a file named ``appdaemon.cfg`` first in
``~/.homeassistant`` then in ``/etc/appdaemon``. If the directory is not
specified and it is not found in either location, AppDaemon will raise
an exception. In addition, AppDaemon expects to find a dir named
``apps`` immediately subordinate to the config directory.

-d and -p are used by the init file to start the process as a daemon and
are not required if running from the command line.

-D can be used to increase the debug level for internal AppDaemon
operations as well as apps using the logging function.

The -s, -i, -t and -e options are for the Time Travel feature and should
only be used for testing. They are described in more detail in the API
documentation.

Starting At Reboot
------------------

To run ``AppDaemon`` at reboot, you can set it up to run as a systemd
service as follows.

Add Systemd Service (appdaemon@appdaemon.service)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First, create a new file using vi:

.. code:: bash

    $ sudo vi /etc/systemd/system/appdaemon@appdaemon.service

Add the following, making sure to use the correct full path for your
config directory. Also make sure you edit the ``User`` to a valid user
to run AppDaemon, usually the same user as you are running Home
Assistant with is a good choice.

::

    [Unit]
    Description=AppDaemon
    After=home-assistant@homeassistant.service
    [Service]
    Type=simple
    User=%1
    ExecStart=/usr/local/bin/appdaemon -c <full path to config directory>
    [Install]
    WantedBy=multi-user.target

The above should work for hasbian, but if your homeassistant service is
named something different you may need to change the ``After=`` lines to
reflect the actual name.

Activate Systemd Service
~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    $ sudo systemctl daemon-reload
    $ sudo systemctl enable appdaemon@appdaemon.service --now

Now AppDaemon should be up and running and good to go.

Operation
---------

Since AppDaemon under the covers uses the exact same APIs as the
frontend UI, you typically see it react at about the same time to a
given event. Calling back to Home Assistant is also pretty fast
especially if they are running on the same machine. In action, observed
latency above the built in automation component is usually sub-second.

Updating AppDaemon
------------------

To update AppDaemon after new code has been released, just run the
following command to update your copy:

.. code:: bash

    $ sudo pip3 install --upgrade appdaemon

If you are using docker, refer to the steps in the tutorial.

Windows Support
---------------

AppDaemon runs under windows and has been tested with the official 3.5.2
release of python. There are a couple of caveats however:

-  The ``-d`` or ``--daemonize`` option is not supported owing to
   limitations in the Windows implementation of Python.
-  Some internal diagnostics are disabled. This is not user visible but
   may hamper troubleshooting of internal issues if any crop up

AppDaemon can be installed exactly as per the instructions for every
other version using pip3.

Windows Under the Linux Subsystem
---------------------------------

Windows 10 now supports a full Linux bash environment that is capable of
running Python. This is essentially an Ubuntu distribution and works
extremely well. It is possible to run AppDaemon in exactly the same way
as for Linux distributions, and none of the above Windows Caveats apply
to this version. This is the recommended way to run AppDaemon in a
Windows 10 and later environment.

Raspbian
--------

Some users have reported a requirement to install a couple of packages
prior to installing AppDaemon with the pip3 method:

.. code:: bash

    $ sudo apt-get install python-dev
    $ sudo apt-get install libffi-dev

Raspberry Pi Docker
-------------------

Since the official Docker image isn't compatible with raspberry Pi, you will need to build your own docker image
from the downloaded repository. The Dockerfile also needs a couple of changes:

1. Change the image line to use a Resin image:

``FROM arm32v7/python:3.6``

2. Change the ``RUN`` line to the following:

``RUN pip3 install requests && pip3 install .``

You can then build and run a docker image locally as follows:

.. code:: bash
    $ git clone https://github.com/home-assistant/appdaemon.git
    $ cd appdaemon
    $ docker build -t appdaemon .
    $ docker run -t -i --name=appdaemon -p 5050:5050 \
      -e HA_URL="<Your HA URL>" \
      -e HA_KEY="<your HA Key>" \
      -e DASH_URL="<Your DASH URL>" \
      -v <Your AppDaemon conf dir>:/conf \
      appdaemon:latest

For more information on running AppDaemon under Docker, see the Docker Tutorial. The key difference is that
you will be running a locally built instance of AppDaemon rather than one from Docker Hub, so for run commands,
make usre yo uspecify "appdaemon:latest" as the image, as above, rather than "acockburn/appdaemon:latest" as the tutorial states.

At the time of writing, @torkildr is maintaining a linked Raspberry Pi image here:

https://hub.docker.com/r/torkildr/rpi-appdaemon/
