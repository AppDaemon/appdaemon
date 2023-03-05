AppDaemon with Docker
=====================

A quick tutorial to AppDaemon with Docker

About Docker
------------

`Docker <https://www.docker.com>`_ is a popular application container technology. Application
containers allow an application to be built in a known-good state and
run totally independent of other applications. This makes it easier to
install complex software and removes concerns about application
dependency conflicts. Containers are powerful; however, they require
abstractions that can sometimes be confusing.

This guide will help you get the AppDaemon Docker image running and
hopefully help you become more comfortable with using Docker. There are
multiple ways of doing some of these steps which are removed for the
sake of keeping it simple. As your needs change, just remember there's
probably a way to do what you want!

Available Images
----------------

Starting with AppDaemon 4.1.0, we suport multi-arch images on Docker Hub.

Currently supported architectures: linux/arm64/v8,linux/amd64,linux/arm/v6,linux/arm/v7

Prereqs
-------

This guide assumes:

* You already have Docker installed. If you still need to do this, follow the `Docker Installation documentation <https://docs.docker.com/engine/installation/>`__
* You have Home Assistant up and running
* You are comfortable with some tinkering. This is a pre-req for AppDaemon too!

Testing your System
-------------------

Our first step will be to verify that we can get AppDaemon running on
our machine, which tests that we can successfully *pull* (download)
software from `Docker Hub <https://hub.docker.com/r/acockburn/appdaemon>`__, execute it and get output that AppDaemon is
working. We will worry about our persistent (normal) configuration
later.

Before you start, you need to know the following:

* HA\_URL: The URL of your running Home Assistant, in the form of ``http://[name]:[port]``. Port is usually 8123.
* TOKEN: If your Home Assistant is using Long-Lived Tokens you will need to use TOKEN

Now, on your Docker host, for Linux users, run the following command,
substituting the values above in the quotes below. (Note: to create a long-lived token, click your user icon in the HA front end and look for the Long-Lived Access Tokens card. If you do not
need a TOKEN, you can omit the entire -e TOKEN line)

::

    docker run --rm -it -p 5050:5050 \
      -e HA_URL="<your HA_URL value>" \
      -e TOKEN="<your TOKEN value>" \
      -e DASH_URL="http://$HOSTNAME:5050" \
      acockburn/appdaemon:latest

You may also need to add ``--network="host`` if you are running AppDaemon on the same host as HomeAssistant.

You should see some download activity the first time you run this as it
downloads the latest AppDaemon image. After that is downloaded, Docker
will create a container based on that image and run it. It will
automatically delete itself when it exits since right now we are just
testing.

You will see AppDaemon's output appear on your screen, and you should
look for lines like these being outputs:

HASS: Connected to Home Assistant 0.80.0

::

    2017-04-01 14:26:48.361140 INFO Connected to Home Assistant 0.80.0

The `apps` capability of AppDaemon is working, running the example Hello
World app

::

    2017-04-01 14:26:48.330084 INFO hello_world: Hello from AppDaemon
    2017-04-01 14:26:48.333040 INFO hello_world: You are now ready to run Apps!

The `dashboard` capability of AppDaemon has started.

::

    2018-10-25 16:53:09.105214 INFO Starting Dashboards

Now open up a web browser, and browse to http://<DASH_URL>:5050. You should see
the "Welcome to HADashboard for Home Assistant" screen and see the Hello
dashboard is available.

If all of these checks work, congratulations! Docker and AppDaemon are
working on your system! Hit Control-C to exit the container, and it will
clean up and return to the command line. It's almost as if nothing
happened... 😃

Persistent Configuration
------------------------

In Docker, containers (the running application) are considered
ephemeral. Any state that you want to be able to preserve must be stored
outside of the container so that the container can be disposed of and
recreated at any time. In the case of AppDaemon, this means you would be
concerned about your ``conf`` folder.

The first step is to create a location on your filesystem to store the
``conf`` folder. It does not matter where this is; some people like to
store it in the same location as Home Assistant. I like to keep a folder
structure under ``/docker`` on my systems, so we can do something
like:

::

    mkdir -p /docker/appdaemon/conf

Next, we will run a container again, omitting the ``--rm -it`` parameters
and adding ``-d`` so that it stays background and doesn't disappear when
it exits. We will also add ``--restart=always`` so that the container
will auto-start on system boot and restart on failures, and lastly
specify our ``conf`` folder location. Note that the folder path must be
fully qualified and not relative.

::

    docker run --name=appdaemon -d -p 5050:5050 \
      --restart=always \
      -e HA_URL="<your HA_URL value>" \
      -e TOKEN="<your TOKEN value>" \
      -e DASH_URL="http://$HOSTNAME:5050" \
      -v <your_conf_folder>:/conf \
      acockburn/appdaemon:latest

I would suggest documenting the command line above in your notes, so
that you have it as a reference in the future for rebuilding and
upgrading. If you back up your command line, as well as your ``conf``
folder, you can trivially restore AppDaemon on another machine or on a
rebuild!

If your ``conf`` folder is brand new, the AppDaemon Docker will copy the
default configuration files into this folder. If there are already
configuration files, it will not overwrite them. Double-check that the
files are there now.

You are now ready to start working on your AppDaemon configurations!

At this point forward, you can edit configurations on your ``conf``
folder and AppDaemon will load them see the `AppDaemon Installation
page <INSTALL.html>`__ for full instructions on AppDaemon configuration.
Have fun!

Viewing AppDaemon Log Output
----------------------------

You can view the output of your AppDaemon with this command:

::

    docker logs appdaemon

If you'd like to tail the latest output, try this:

::

    docker logs -f --tail 20 appdaemon

Upgrading AppDaemon
-------------------

Upgrading with Docker really doesn't exist in the same way as with
non-containerized apps. Containers are considered ephemeral and are an
instance of a base, known-good application image. Therefore the process
of upgrading is simply disposing of the old version, grabbing a newer
version of the application image and starting up a new container with
the new version's image. Since the persistent state (``conf``) was
kept, it is effectively an upgrade.

(It is possible to get into downgrades and multiple versions, however in
this guide we are keeping it simple!)

Run the following commands:

::

    docker stop appdaemon
    docker rm appdaemon
    docker pull acockburn/appdaemon:latest
    docker run --name=appdaemon -d -p 5050:5050 \
      --restart=always \
      -e HA_URL="<your HA_URL value>" \
      -e TOKEN="<your TOKEN value>" \
      -e DASH_URL="http://$HOSTNAME:5050" \
      -v <your_conf_folder>:/conf \
      acockburn/appdaemon:latest

Controlling the AppDaemon Container
-----------------------------------

To restart AppDaemon:

::

    docker restart appdaemon

To stop AppDaemon:

::

    docker stop appdaemon

To start AppDaemon back up after stopping:

::

    docker start appdaemon

To check the running state, run the following and look at the 'STATUS'
column:

::

    docker ps -a

Running with AppDaemon Debug
----------------------------

If you need to run AppDaemon with Debug, it may be easiest to stop your
normal AppDaemon and run a temporary container with the debug flag set.
This presumes you already have a configured ``conf`` folder you are
debugging, so we don't need to pass the HA/DASH variables into the
container.

Run the following commands:

::

    docker stop appdaemon
    docker run --rm -it -p 5050:5050 \
      -v <your_conf_folder>:/conf \
      acockburn/appdaemon:latest -D DEBUG

Once you are done with the debugging, start the non-debug container back up:

::

    docker start appdaemon

You can also append any other AppDaemon flags to the end of the command line if desired, e.g. to use time travel.

Timezones
---------

Some users have reported issues with the Docker container running in different timezones to the host OS - this is obviously problematic for any of the scheduler functions.
Adding the following to the Docker command line has helped some users:

::

     -v /etc/localtime:/etc/localtime:ro

Home Assistant SSL
------------------

If your Home Assistant is running with self-signed certificates, you
will want to point to the location of the certificate files as part of
the container creation process. Add ``-v <your_cert_path>:/certs`` to
the ``docker run`` command line

Removing AppDaemon
------------------

If you no longer want to use AppDaemon ``confused``, use the following commands:

::

    docker kill appdaemon
    docker rm appdaemon
    docker rmi acockburn/appdaemon:latest

You can delete the ``conf`` folder if you wish at this time too.
AppDaemon is now completely removed.

Adding Dependencies
-------------------

Sometimes it can be helpful to install additional Python dependencies into the Docker container before AppDaemon starts, to allow additional libraries to be used from Apps. The Docker script will recursively search the CONF directory for any files named ``requirements.txt``. All the found requirements will be used as input to pip3 to install any packages that they describe.

It's also often helpful to add system packages to the Docker container before AppDaemon starts, to allow any custom python packages that depend on other `system packages <https://pkgs.alpinelinux.org/packages>`_ to install without issue. The Docker script will recursively search the CONF directory for any files named ``system_packages.txt``. Packages should be listed either space delimited or newline delimited. These packages will be used as input to ``apk add`` to install any packages that they describe.
