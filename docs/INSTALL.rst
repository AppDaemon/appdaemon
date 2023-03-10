***************
Getting started
***************

Installation
===============

The following installation methods are supported:

- :ref:`docker-install`
- :ref:`pip-install`
- :ref:`Home-Assistant-add-on`

.. _docker-install:

Docker
------

Supported architectures
^^^^^^^^^^^^^^^^^^^^^^^
Starting with AppDaemon 4.1.0, multi-arch images are published on the official `Docker Hub <https://hub.docker.com/r/acockburn/appdaemon>`_ repository.

Currently supported architectures:

- linux/arm/v6
- linux/arm/v7
- linux/arm64/v8
- linux/amd64

To start a container named ``appdaemon``, exposing the *HADashboard* on port ``5050``, use the following command:

.. code:: console

    $ docker run --name appdaemon \
        --detach \
        --restart=always \
        --network=host \
        -p 5050:5050 \
        -v <conf_folder>:/conf \
        -e HA_URL="http://homeassistant.local:8123" \
        -e TOKEN="my_long_liven_token" \
        acockburn/appdaemon

Configuration folder
^^^^^^^^^^^^^^^^^^^^

AppDaemon uses the ``/conf`` directory to store its configuration data.
To access this folder from the host system, you need to create a data directory outside the container and `mount this to the directory used inside the container <https://docs.docker.com/engine/tutorials/dockervolumes/#mount-a-host-directory-as-a-data-volume>`_.
This places the configuration files in a known location on the host system, and makes it easy for tools and applications on the host system to access the files.

The following steps illustrate the procedure;

1. Create a configuration directory on a suitable volume on your host system, e.g. ``/my/own/datadir``.
2. Start you ``AppDaemon`` container like this:

.. code:: console

    $ docker run --name appdaemon \
        --detach \
        --restart=always \
        --network=host \
        -p 5050:5050 \
        -v /my/own/datadir:/conf \
        -e HA_URL="http://homeassistant.local:8123" \
        -e TOKEN="my_long_liven_token" \
        acockburn/appdaemon

The ``-v /my/own/datadir:/conf`` part of the command mounts the ``/my/own/datadir`` directory from the underlying host system as ``/conf`` inside the container, where AppDaemon by default will write its data files.

The first you start the container, AppDaemon will write its own sample configuration files in this directory.

Environment variables
^^^^^^^^^^^^^^^^^^^^^

When you start the AppDaemon image, you can adjust some of its configuration variables by passing one or more environment variables on the ``docker run`` command:

======  ========================================================
Name    Description
======  ========================================================
HA_URL  The URL of your running Home Assistant instance
TOKEN   Long-Lived token to authenticates against Home Assistant
======  ========================================================

For a more in-depth guide to Docker, see the :ref:`Docker tutorial`.

.. _pip-install:

Pip
---

Linux
^^^^^

**Requirements**: Python version `3.8`, `3.9`, `3.10` or `3.11`.

**NOTE:** Do not install this in the same Python virtual environment as Home Assistant.
If you do that, then Home Assistant will stop working due to conflicting dependencies.


- Create a dedicated `Python virtual environment <https://docs.python.org/3/tutorial/venv.html>`_ for AppDaemon and activate it

- To install the latest version of AppDaemon:

.. code:: console

    $ pip install appdaemon

Note: There are some OS-specific instructions for :ref:`Windows` and :ref:`Raspberry Pi OS` users.

.. _Raspberry Pi OS:

Raspberry Pi OS
^^^^^^^^^^^^^^^

Some users have reported the need to install these additional requirements:

.. code:: console

    $ sudo apt install python-dev
    $ sudo apt install libffi-dev

.. _Windows:

Windows
^^^^^^^

AppDaemon under Windows has been tested with the official 3.8.1
release of Python.
There are a couple of caveats:

-  The ``-d`` or ``--daemonize`` option is not supported owing to
   limitations in the Windows implementation of Python.
-  Some internal diagnostics are disabled. This is not user-visible but
   may hamper troubleshooting of internal issues, if any crop up

AppDaemon can be installed exactly as per the instructions using pip.

WSL (Windows subsystem for Linux)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Windows 10+ now supports a full Linux Bash environment that is capable of
running Python. It allows to run a multitude of Linux distributions, virtualizing a full Linux OS.

It is possible to run AppDaemon in the same way
as in a standard Linux distributions, and none of the above Windows caveats apply
to this version.
This is the recommended way to run AppDaemon in a Windows 10 and later environment.


.. _Home-Assistant-add-on:

Home Assistant add-on
---------------------

The official AppDaemon add-on is available in the `Home Assistant Community Add-ons Repository <https://github.com/hassio-addons/repository>`_, maintained by `frenck <https://github.com/frenck>`_.
Please see their official documentation for installation and configuration instructions.

Running
=======

Pip
---

You can run AppDaemon from the command line as follows.
Note: make sure first to create a directory to contain all AppDaemon configuration files!

.. code:: console

    $ appdaemon -c <patch_to_config_folder>

You should see something like the following:

.. code:: console

    $ appdaemon -c <patch_to_config_folder>
    2016-08-22 10:08:16,575 INFO Got initial state
    2016-08-22 10:08:16,576 INFO Loading Module: /home/homeassistant/conf/apps/hello.py
    2016-08-22 10:08:16,578 INFO Loading Object hello_world using class HelloWorld from module hello
    2016-08-22 10:08:16,580 INFO Hello from AppDaemon
    2016-08-22 10:08:16,584 INFO You are now ready to run Apps!

CLI arguments
-------------
The following CLI arguments are available:

.. code:: console

    $ usage: appdaemon [-h] [-c CONFIG] [-p PIDFILE] [-t TIMEWARP] [-s STARTTIME] [-e ENDTIME] [-C CONFIGFILE] [-D {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [-m MODULEDEBUG MODULEDEBUG] [-v]

    options:
    -h, --help            show this help message and exit
    -c CONFIG, --config CONFIG
                            full path to config directory
    -p PIDFILE, --pidfile PIDFILE
                            full path to PID File
    -t TIMEWARP, --timewarp TIMEWARP
                            speed that the scheduler will work at for time travel
    -s STARTTIME, --starttime STARTTIME
                            start time for scheduler <YYYY-MM-DD HH:MM:SS|YYYY-MM-DD#HH:MM:SS>
    -e ENDTIME, --endtime ENDTIME
                            end time for scheduler <YYYY-MM-DD HH:MM:SS|YYYY-MM-DD#HH:MM:SS>
    -C CONFIGFILE, --configfile CONFIGFILE
                            name for config file
    -D {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --debug {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                            global debug level
    -m MODULEDEBUG MODULEDEBUG, --moduledebug MODULEDEBUG MODULEDEBUG
    -v, --version         show program's version number and exit

A brief description of them follows:

``-c`` path to the configuration directory
    If not specified, AppDaemon will look for a file named ``appdaemon.yaml`` under the following default locations:

    - ``~/.homeassistant/``
    - ``/etc/appdaemon``

    If no file is found in either location, AppDaemon will raise an exception. In addition, AppDaemon expects to find a dir named ``apps`` immediately subordinate to the config directory.

``-C`` name of the configuration file (default: ``appdaemon.yaml``)

.. TODO: document -d in appdaemon help text

``-d``, ``-p`` used by the init file to start the process as a daemon
    Not required if running from the command line.

``-D`` increase the debug level for internal AppDaemon operations, and configure debug logs for the apps.

``-s``, ``-i``, ``-t``, ``-e`` time travel options
    Useful only for testing. Described in more detail in the API documentation.

Automatically starting on boot
------------------------------

To run ``AppDaemon`` every time you restart your machine, you can set it up to run as a ``systemd service`` as follows.

Systemd service file
^^^^^^^^^^^^^^^^^^^^

Create a Systemd service file ``/etc/systemd/system/appdaemon@appdaemon.service`` and add the following content.
Make sure to use the correct full path for your configuration directory and that you edit the ``User`` field to a valid user that can run AppDaemon, usually the same user that is running the Home Assistant process is a good choice.

.. code:: console

    [Unit]
    Description=AppDaemon
    After=home-assistant@homeassistant.service
    [Service]
    Type=simple
    User=%I
    ExecStart=/usr/local/bin/appdaemon -c <full path to config directory>
    [Install]
    WantedBy=multi-user.target

The above should work for Raspberry Pi OS, but if your ``homeassistant`` service is
named something different you may need to change the ``After=`` lines to
reflect the actual name.

Activate the service
~~~~~~~~~~~~~~~~~~~~

.. code:: console

    $ sudo systemctl daemon-reload
    $ sudo systemctl enable appdaemon@appdaemon.service --now

Now AppDaemon should be up and running and good to go.

Upgrading
=========

To update AppDaemon after a new release has been published, run the
following command to update your local installation:

.. code:: console

    $ pip install --upgrade appdaemon

If you are using Docker, refer to the steps in the `tutorial <Docker-Upgrading>`_.

Versioning Strategy
-------------------

AppDaemon follows a simple 3 point versioning strategy in the format ``x.y.z``:

x: major version number
    Incremented when very significant changes have been made to the platform, or sizeable new functionality has been added.

y: minor version number
    Incremented when incremental new features have been added, or breaking changes have occurred

z: point version number
    Point releases will typically contain bugfixes, and package upgrades

Users should be able to expect point release upgrades to be seamless, but should check release notes for breaking changes and
new functionality for minor or major releases.

Next steps
==========

Now that you have a working setup for AppDaemon, learn how to configure it in the next section: :doc:`CONFIGURE`.
