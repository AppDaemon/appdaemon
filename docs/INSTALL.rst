Installation
============

AppDaemon runs on Python versions 3.8, 3.9, 3.10 and 3.11. Installation is either by pip3 or Docker. There is also an official
hass.io build.

Note: Windows and Raspbian users should check the environment-specific section at the end of this doc for additional information.

Install and Run using Docker
----------------------------

Follow the instructions in the `Docker Tutorial <DOCKER_TUTORIAL.html>`__

Install Using pip3
------------------

Before running ``AppDaemon`` you will need to install the package:

.. code:: bash

    $ sudo pip3 install appdaemon


**Do not** install this in the same Python virtual environment as Home Assistant. If you do that, then Home Assistant will stop working.

Install Using hass.io
---------------------

The official hass.io addon for AppDaemon is maintained by:

- `frenck <https://github.com/hassio-addons/repository>`__.

Running
-------

Docker
~~~~~~

Assuming you have set the config up as described in `the tutorial <DOCKER_TUTORIAL.html>`_ for
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

    usage: appdaemon [-h] [-c CONFIG] [-p PIDFILE] [-t TIMEWARP] [-s STARTTIME]
                       [-e ENDTIME] [-C CONFIGFILE]
                       [-D {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                       [-m MODULEDEBUG MODULEDEBUG] [-v]

    options:
      -h, --help            show this help message and exit
      -c CONFIG, --config CONFIG
                            full path to config directory
      -p PIDFILE, --pidfile PIDFILE
                            full path to PID File
      -t TIMEWARP, --timewarp TIMEWARP
                            speed that the scheduler will work at for time travel
      -s STARTTIME, --starttime STARTTIME
                            start time for scheduler <YYYY-MM-DD HH:MM:SS|YYYY-MM-
                            DD#HH:MM:SS>
      -e ENDTIME, --endtime ENDTIME
                            end time for scheduler <YYYY-MM-DD HH:MM:SS|YYYY-MM-
                            DD#HH:MM:SS>
      -C CONFIGFILE, --configfile CONFIGFILE
                            name for config file
      -D {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --debug {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                            global debug level
      -m MODULEDEBUG MODULEDEBUG, --moduledebug MODULEDEBUG MODULEDEBUG
      -v, --version         show program's version number and exit

-c is the path to the configuration directory. If not specified,
AppDaemon will look for a file named ``appdaemon.yaml`` first in
``~/.homeassistant`` then in ``/etc/appdaemon``. If the directory is not
specified and it is not found in either location, AppDaemon will raise
an exception. In addition, AppDaemon expects to find a dir named
``apps`` immediately subordinate to the config directory.

-C allows the user to override the name of the appdaemon config file and set it to soemthing other than
``appdaemon.yaml``

-d and -p are used by the init file to start the process as a daemon and
are not required if running from the command line.

-D can be used to increase the debug level for internal AppDaemon
operations as well as apps using the logging function.

The -s, -i, -t and -e options are for the Time Travel feature and should
only be used for testing. They are described in more detail in the API
documentation.

Starting At Reboot (Systemd)
----------------------------

To run ``AppDaemon`` at reboot, you can set it up to run as a ``systemd
service``. To run it with ``init.d`` instead, see the next section.

Add Systemd Service (appdaemon@appdaemon.service)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First, create a new file using vi:

.. code:: bash

    $ sudo vi /etc/systemd/system/appdaemon@appdaemon.service

Add the following, making sure to use the correct full path for your
config directory. Also, make sure you edit the ``User`` to a valid user
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

The above should work for hasbian, but if your ``homeassistant`` service is
named something different you may need to change the ``After=`` lines to
reflect the actual name.

Activate Systemd Service
~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    $ sudo systemctl daemon-reload
    $ sudo systemctl enable appdaemon@appdaemon.service --now

Now AppDaemon should be up and running and good to go.

Starting At Reboot (Init.d)
----------------------------

To run ``AppDaemon`` at reboot, you can set it up to run as an ``init.d
service``. To run it with ``systemd`` instead, see the previous section.

Add Init.d Service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First, create a new file using vi:

.. code:: bash

    $ sudo vi /etc/init.d/appdaemon-daemon 

Copy and paste the following script into the new file, making sure that the following variables 
are set according to your setup.

- APPDAEMON_INSTALL_DIR
   - Location of appdaemon installation.
- PRE_EXEC
   - Command for starting the python venv for appdaemon.
- APPDAEMON_BIN
   - Location of appdaemon binary.
- RUN_AS
   - Usually the same user you are using to run Home Assistant.
- CONFIG_DIR
   - Location of Home Assistant config.

::

    #!/bin/sh
    ### BEGIN INIT INFO
    # Provides:          appdaemon
    # Required-Start:    $local_fs $network $named $time $syslog
    # Required-Stop:     $local_fs $network $named $time $syslog
    # Default-Start:     2 3 4 5
    # Default-Stop:      0 1 6
    # Description:       AppDaemon
    ### END INIT INFO

    # /etc/init.d Service Script for AppDaemon
    APPDAEMON_INSTALL_DIR="/srv/appdaemon"
    PRE_EXEC="cd $APPDAEMON_INSTALL_DIR; python3.9 -m venv .; source bin/activate;"
    APPDAEMON_BIN="/srv/appdaemon/bin/appdaemon"
    RUN_AS="homeassistant"
    PID_DIR="/var/run/appdaemon"
    PID_FILE="$PID_DIR/appdaemon.pid"
    CONFIG_DIR="/home/$RUN_AS/.homeassistant"
    LOG_DIR="/var/log/appdaemon"
    LOG_FILE="$LOG_DIR/appdaemon.log"
    FLAGS="-c $CONFIG_DIR"
    DAEMONIZE="daemonize -c $APPDAEMON_INSTALL_DIR -e $LOG_FILE.stderr -o $LOG_FILE.stdout -p $PID_FILE -l $PID_FILE -v"

    start() {
    create_piddir
    if [ -f $PID_FILE ] && kill -0 $(cat $PID_FILE) 2> /dev/null; then
        echo 'Service already running' >&2
        return 1
    fi
    echo -n 'Starting service' >&2
    local CMD="$PRE_EXEC $DAEMONIZE $APPDAEMON_BIN $FLAGS"
    su -s /bin/bash -c "$CMD" $RUN_AS
    if [ $? -ne 0 ]; then
        echo "Failed" >&2
    else
        echo 'Done' >&2
    fi
    }

    stop() {
    if [ ! -f "$PID_FILE" ] || ! kill -0 $(cat "$PID_FILE") 2> /dev/null; then
        echo 'Service not running' >&2
        return 1
    fi
    echo -n 'Stopping service' >&2
    kill $(cat "$PID_FILE")
    while ps -p $(cat "$PID_FILE") > /dev/null 2>&1; do sleep 1;done;
    rm -f $PID_FILE
    echo 'Done' >&2
    }

    install() {
    echo "Installing AppDaemon Daemon (appdaemon-daemon)"
    update-rc.d appdaemon-daemon defaults
    create_piddir
    mkdir -p $CONFIG_DIR
    chown $RUN_AS $CONFIG_DIR
    mkdir -p $LOG_DIR
    chown $RUN_AS $LOG_DIR
    }

    uninstall() {
    echo "Are you really sure you want to uninstall this service? The INIT script will"
    echo -n "also be deleted! That cannot be undone. [yes|No] "
    local SURE
    read SURE
    if [ "$SURE" = "yes" ]; then
        stop
        remove_piddir
        echo "Notice: The config directory has not been removed"
        echo $CONFIG_DIR
        echo "Notice: The log directory has not been removed"
        echo $LOG_DIR
        update-rc.d -f appdaemon-daemon remove
        rm -fv "$0"
        echo "AppDaemon Daemon has been removed. AppDaemon is still installed."
    fi
    }

    create_piddir() {
    if [ ! -d "$PID_DIR" ]; then
        mkdir -p $PID_DIR
        chown $RUN_AS "$PID_DIR"
    fi
    }

    remove_piddir() {
    if [ -d "$PID_DIR" ]; then
        if [ -e "$PID_FILE" ]; then
        rm -fv "$PID_FILE"
        fi
        rmdir -v "$PID_DIR"
    fi
    }

    case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    install)
        install
        ;;
    uninstall)
        uninstall
        ;;
    restart)
        stop
        start
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|install|uninstall}"
    esac

Save the file and then make it executable:

.. code:: bash

    $ sudo chmod +x /etc/init.d/appdaemon-daemon

Activate Init.d Service
~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    $ sudo service appdaemon-daemon install

That's it. After a restart, AppDaemon will start automatically. 

If ``AppDaemon`` doesn't start, check the log file output for errors at ``/var/log/appdaemon/appdaemon.log``.

If you want to start/stop ``AppDaemon`` manually, use:

.. code:: bash

    $ sudo service appdaemon-daemon <start|stop>

Updating AppDaemon
------------------

To update AppDaemon after new code has been released, just run the
following command to update your copy:

.. code:: bash

    $ sudo pip3 install --upgrade appdaemon

If you are using docker, refer to the steps in the tutorial.

AppDaemon Versioning Strategy
-----------------------------

AppDaemon uses a simple 3 point versioning strategy of the form x.y.z

- x = Major Version Number
- y = Minor Version Number
- z = Point Version Number

Major versions will be released when very significant changes have been made to the platform, or
sizeable new functionality has been added.

Minor versions will be released when incremental new features have been added, or breaking changes have occured

Point releases will typically contain bugfixes, and package upgrades

Users should be able to expect point release upgrades to be seamless, but should check release notes for breaking changes and
new functionality for minor or major releases.

Windows Support
---------------

AppDaemon runs under windows and has been tested with the official 3.8.1
release of python. However, there are a couple of caveats:

-  The ``-d`` or ``--daemonize`` option is not supported owing to
   limitations in the Windows implementation of Python.
-  Some internal diagnostics are disabled. This is not user-visible but
   may hamper troubleshooting of internal issues if any crop up

AppDaemon can be installed exactly as per the instructions for every
other version using pip3.

Windows Under the Linux Subsystem
---------------------------------

Windows 10+ now supports a full Linux bash environment that is capable of
running Python. This is essentially an Ubuntu distribution and works
extremely well. It is possible to run AppDaemon in the same way
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
