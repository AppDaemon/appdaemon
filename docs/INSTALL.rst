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


**Do not** install this in the same Python virtual environment as Home Assistant. If you do that then Home Assistant will stop working.

Install Using hass.io
---------------------

The official hass.io addon for AppDaemon is maintained by:

- `frenck <https://github.com/hassio-addons/repository>`__.


Running a Dev Version
---------------------

For the adventurous among you, it is possible to run the very latest dev code to get a preview of changes before they are released as part of a stable build. You do this at your own risk, and be aware that although I try to keep things consistent and functional, I can't guarantee that I won't break things in the dev version - if this happens you are on your own!

Also, note, that to run a dev version you should be using the PIP install method. Docker builds are created for dev too, but there is no hass.io support.

To run a PIP install method dev version follow these steps:

Clone the Repository
~~~~~~~~~~~~~~~~~~~~

First we need to get a clean copy of the dev branch. To do this, create a fresh directory, and change into it. Run the following command to clone the dev branch of the AppDaemon repository:

.. code:: bash

    $ git clone -b dev https://github.com/home-assistant/appdaemon.git

This will create a directory called ``appdaemon`` - this is your repository directory and all commands will need to be run from inside it.

Run AppDaemon from the command line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Now that you have a local copy of the code, the next step is to run AppDaemon using that code.

As a first step, if you are using a Virtual Environment enable it. The best practice here is to use a venv specifically for the dev version; it is possible that the dev branch may have updated dependencies that will be incompatible with the latest stable version, and may break it.

To run the cloned version of AppDaemon, make sure you are in the ``appdaemon`` subdirectory and run the following command:

.. code:: bash

    $ python3 -m appdaemon.admain -c <PATH To CONFIG DIRECTORY>

In most cases it is possible to share config directories with other AppDaemon instances, but beware of apps that use new features as they will likely cause errors for the stable version. If you prefer, you can create an entirely new conf directory for your dev environment.

Install AppDamon via PIP (Optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Although the reccomended way of running a dev build is to use the command line above, it is possible to install an appdaemon dev build as a pip package. If you do so, it will replace your stable version, so only do this if you are confident with packages and venvs - if you use a specific venv for the dev build this should not be an issue. Also, remember that if you do this you will need to reinstall the package as an extra step every time you refresh the dev repository (see below).

To install the dev build as a package, change to the ``appdaemon`` directory and run the following command:

.. code:: bash

    $ pip3 install .

Updating AppDaemon to the latest dev version
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the dev version has been updated and you want to pull over the latest changes, run the following command from the ``appdeamon`` directory:

.. code:: bash

    $ git pull

You can then immediately run the latest version with the command line above. If you are using pip, remember to run the install command again, using the ``--upgrade flag``:

.. code:: bash

    $ pip3 install --upgrade .


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
    User=%I
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
