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

    $ sudo pip3 install appdaemon

Install Using hass.io
---------------------

There is an official hass.io addon for AppDaemon maintained by
`vkorn <https://community.home-assistant.io/u/vkorn/summary>`__.
Instructions to install AppDaemon this way can be found
`here <https://community.home-assistant.io/t/repository-few-addons/20659>`__

Configuration
-------------

When you have appdaemon installed by either method you are ready to
start working on the appdaemon.yaml file. For docker users, you will
already have a skeleton to work with. For pip users, you need to create
a configuration directory somewhere (e.g. ``/home/homeassistant/conf``)
and create a file in there called ``appdaemon.yaml``.

Your initial file should look something like this:

.. code:: yaml

    AppDaemon:
      logfile: STDOUT
      errorfile: STDERR
      logsize: 100000
      log_generations: 3
      threads: 10
      cert_path: <path/to/root/CA/cert>
      cert_verify: True
      time_zone: <time zone>
      api_port: 5000
      api_key: !secret api_key
      api_ssl_certificate: <path/to/root/CA/cert>
      api_ssl_key: <path/to/root/CA/key>
    HASS:
      ha_url: <some_url>
      ha_key: <some key>

-  ``ha_url`` is a reference to your home assistant installation and
   must include the correct port number and scheme (``http://`` or
   ``https://`` as appropriate)
-  ``ha_key`` should be set to your key if you have one, otherwise it
   can be removed.
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
-  ``log_size`` (optional) is the maximum size a logfile will get to
   before it is rotated if not specified, this will default to 1000000
   bytes.
-  ``log_generations`` (optional) is the number of rotated logfiles that
   will be retained before they are overwritten if not specified, this
   will default to 3 files.
-  ``threads`` - the number of dedicated worker threads to create for
   running the apps. Note, this will bear no resembelance to the number
   of apps you have, the threads are re-used and only active for as long
   as required to tun a particular callback or initialization, leave
   this set to 10 unless you experience thread starvation
-  ``cert_path`` (optional) - path to root CA cert directory for HASS -
   use only if you are using self signed certs.
-  ``cert_verify`` (optional) - flag for cert verification for HASS -
   set to ``False`` to disable verification on self signed certs.
-  ``time_zone`` (optional) - timezone for AppDaemon to use. If not
   specified, AppDaemon will query the timezone from Home Assistant
-  ``api_port`` (optional) - Port the AppDaemon RESTFul API will liten
   on. If not specified, the RESTFul API will be turned off
-  ``api_key`` (optional) - adds the requirement for AppDaemon API calls
   to provide a key in the header of a request
-  ``api_ssl_certificate`` (optional) - certificate to use when running
   the API over SSL
-  ``api_ssl_key`` (optional) - key to use when running the API over SSL

Optionally, you can place your apps in a directory other than under the
config directory using the ``app_dir`` directive.

e.g.:

.. code:: yaml

    app_dir: /etc/appdaemon/apps

Secrets
~~~~~~~

AppDaemon supports the use of secrets in the configuration file (YAML
only), to allow separate storage of sensitive information such as
passwords. For this to work, AppDaemon expects to find a file called
secrets.yaml in the configuration directory with a simple list of all
the secrets. The secrets can be referred to using a !secret value in the
configuration file.

An example secrets.yaml might look like this:

.. code:: yaml

    home_assistant_key_key: password123
    appdaemon_key: password456

The secrets can then be referred to as follows:

.. code:: yaml

    AppDaemon:
      api_key: !secret appdaemon_key
      threads: '10'
    HASS:
      ha_key: !secret home_assistant_key
      ha_url: http://192.168.1.20:8123

Configuring a Test App
~~~~~~~~~~~~~~~~~~~~~~

To start configuring Apps, we need to create a new `apps.yaml` file in the same directory as appdaemon.yaml.
To start, we can add an entry for the Hello World App like this:

.. code:: yaml

    hello_world:
      module: hello
      class: HelloWorld

App configuration is fully described in the `API doc <API.md>`__.

To add an initial test app to match the configuration above, we need to
first create an ``apps`` subdirectory under the conf directory. Then
create a file in the apps directory called ``hello.py``, and paste the
following into it using your favorite text editor:

.. code:: python

    import appdaemon.appapi as appapi

    #
    # Hello World App
    #
    # Args:
    #

    class HelloWorld(appapi.AppDaemon):

      def initialize(self):
         self.log("Hello from AppDaemon")
         self.log("You are now ready to run Apps!")

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

The -s, -i, -t and -s options are for the Time Travel feature and should
only be used for testing. They are described in more detail in the API
documentation.

Legacy Configuration
--------------------

AppDaemon also currently supports a legacy ``ini`` style of
configuration and it is shown here for backward compatibility. It is
recommended that you move to the YAML format using the provided tool.
When using the legacy configuration style, there are no ``HASS`` or
``HADashboard`` sections - the associated directives all go in the
``AppDaemon`` section.

.. code:: ini

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

If you want to move from the legacy ``ini`` style of configuration to
YAML, AppDaemon is able to do this for you. Just run AppDaemon providing
the configuration directory using the -c option as usual and specify the
--convertcfg flag. From the command line run:

.. code:: bash

    $ appdaemon -c YOUR_CONFIG_DIR --convertcfg
    Converting /etc/appdaemon/appdaemon.cfg to /etc/appdaemon/appdaemon.yaml
    $

AppDaemon should correctly figure out where the file is to convert form
your existing configuration. After conversion, the new YAML file will be
used in preference to the old ini file, which can then be removed if
desired.

Note: any lines in the ini file that are commented out, whether actual
comments of lines that are not active, will not be converted. Note 2:
Docker users will unfortunately need to perform the conversion manually.

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
    User=hass
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
to this version. This is the reccomended way to run AppDaemon in a
Windows 10 and later environment.

Raspbian
--------

Some users have reported a requirement to install a couple of packages
prior to installing AppDaemon with the pip3 method:

.. code:: bash

    $ sudo apt-get install python dev
    $ sudo apt-get install libffi-dev

