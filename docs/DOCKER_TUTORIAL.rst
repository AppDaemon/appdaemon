Appdaemon with Docker
=====================

A quick tutorial to Appdaemon with Docker

About Docker
------------

Docker is a popular application container technology. Application
containers allow an application to be built in a known-good state and
run totally independant of other applications. This makes it easier to
install complex software and removes concerns about application
dependency conflicts. Containers are powerful, however they require
abstractions that can sometimes be confusing.

This guide will help you get the Appdaemon Docker image running and
hopefully help you become more comfortable with using Docker. There are
multiple ways of doing some of these steps which are removed for the
sake of keeping it simple. As your needs change, just remember there's
probably a way to do what you want!

Prereqs
-------

This guide assumes:

* You already have Docker installed. If you still need to do this, follow the `Docker Installation documentation <https://docs.docker.com/engine/installation/>`__
* You have Home Assistant up and running
* You are comfortable with some tinkering. This is a pre-req for Appdaemon too!

Testing your System
-------------------

Our first step will be to verify that we can get Appdaemon running on
our machine, which tests that we can successfully "pull" (download)
software from Docker Hub, execute it, and get output that Appdaemon is
working. We will worry about our persistent (normal) configuration
later.

Before you start, you need to know the following:

* HA\_URL: The URL of your running Home Assistant, in the form of ``http://[name]:[port]``. Port is usually 8123.
* HA\_KEY: If your Home Assistant requires an API key, you'll need that

Now, on your Docker host, for linux users, run the following command,
substituting the values above in the quotes below. (Note, if you do not
need an HA\_KEY, you can omit the entire -e HA\_KEY line)

::

    docker run --rm -it -p 5050:5050 \
      -e HA_URL="<your HA_URL value>" \
      -e HA_KEY="<your HA_KEY value>" \
      -e DASH_URL="http://$HOSTNAME:5050" \
      acockburn/appdaemon:latest

You should see some download activity the first time you run this as it
downloads the latest Appdaemon image. After that is downloaded, Docker
will create a container based on that image and run it. It will
automatically delete itself when it exits, since right now we are just
testing.

You will see Appdaemon's output appear on your screen, and you should
look for lines like these being output:

Appdaemon successfully connected to Home Assistant

::

    2017-04-01 14:26:48.361140 INFO Connected to Home Assistant 0.40.0

The 'apps' capability of Appdaemon is working, running the example Hello
World app

::

    2017-04-01 14:26:48.330084 INFO hello_world: Hello from AppDaemon
    2017-04-01 14:26:48.333040 INFO hello_world: You are now ready to run Apps!

The 'dashboard' capability of Appdaemon has started.

::

    2017-04-01 14:26:48.348260 INFO HADashboard Started
    2017-04-01 14:26:48.349135 INFO Listening on ('0.0.0.0', 5050)

Now open up a web browser, and browse to http://:5050. You should see
the "Welcome to HADashboard for Home Assistant" screen and see the Hello
dashboard is available.

If all of these checks work, congratulations! Docker and Appdaemon are
working on your system! Hit Control-C to exit the container, and it will
clean up and return to the command line. It's almost as if nothing
happened... :)

Persistent Configuration
------------------------

In Docker, containers (the running application) are considered
ephemeral. Any state that you want to be able to preserve must be stored
outside of the container so that the container can be disposed and
recreated at any time. In the case of Appdaemon, this means you would be
concerned about your ``conf`` folder.

The first step is to create a location on your filesystem to store the
``conf`` folder. It does not matter where this is, some people like to
store it in the same location as Home Assistant. I like to keep a folder
structure under ``/docker`` on my systems, so we can simply do something
like:

::

    mkdir -p /docker/appdaemon/conf

Next, we will run a container again, omiting the ``--rm -it`` parameters
and adding ``-d`` so that it stays background and doesn't disappear when
it exits. We will also add ``--restart=always`` so that the container
will auto-start on system boot and restart on failures, and lastly
specify our ``conf`` folder location. Note that the folder path must be
fully qualified and not relative.

::

    docker run --name=appdaemon -d -p 5050:5050 \
      --restart=always \
      -e HA_URL="<your HA_URL value>" \
      -e HA_KEY="<your HA_KEY value>" \
      -e DASH_URL="http://$HOSTNAME:5050" \
      -v <your_conf_folder>:/conf \
      acockburn/appdaemon:latest

I would suggest documenting the command line above in your notes, so
that you have it as a reference in the future for rebuilding and
upgrading. If you back up your command line, as well as your ``conf``
folder, you can trivially restore Appdaemon on another machine or on a
rebuild!

If your ``conf`` folder is brand new, the Appdaemon Docker will copy the
default configuration files into this folder. If there are already
configuration files, it will not overwrite them. Double check that the
files are there now.

You are now ready to start working on your Appdaemon configurations!

At this point forward, you can edit configurations on your ``conf``
folder and Appdaemon will load them see the `AppDaemon Installation
page <INSTALL.html>`__ for full instrctions on AppDaemon configuration.
Have fun!

Viewing Appdaemon Log Output
----------------------------

You can view the output of your Appdaemon with this command:

::

    docker logs appdaemon

If you'd like to tail the latest output, try this:

::

    docker logs -f --tail 20 appdaemon

Upgrading Appdaemon
-------------------

Upgrading with Docker really doesn't exist in the same way as with
non-containerized apps. Containers are considered ephemeral and are an
instance of a base, known-good application image. Therefore the process
of upgrading is simply disposing of the old version, grabbing a newer
version of the application image and starting up a new container with
the new version's image. Since the the persistent state (``conf``) was
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
      -e HA_KEY="<your HA_KEY value>" \
      -e DASH_URL="http://$HOSTNAME:5050" \
      -v <your_conf_folder>:/conf \
      acockburn/appdaemon:latest

Controlling the Appdaemon Conter
--------------------------------

To restart Appdaemon:

::

    docker restart appdaemon

To stop Appdaemon:

::

    docker stop appdaemon

To start Appdaemon back up after stopping:

::

    docker start appdaemon

To check the running state, run the following and look at the 'STATUS'
column:

::

    docker ps -a

Running with Appdaemon Debug
----------------------------

If you need to run Appdaemon with Debug, it may be easiest to stop your
normal appdaemon and run a temporary container with the debug flag set.
This presumes you already have a configured ``conf`` folder you are
debugging, so we don't need to pass the HA/DASH variables into the
container.

Run the following commands:

::

    docker stop appdaemon
    docker run --rm -it -p 5050:5050 \
      -v <your_conf_folder>:/conf \
      -e EXTRA_CMD="-D DEBUG" \
      acockburn/appdaemon:latest

Once you are done with the debug, start the non-debug container back up:

::

    docker start appdaemon

Timezones
---------

Some users have reported issues with the Docker container running in different timezones to the host OS - this is obviously problematic for any of the scheduler functions.
Adding the following to the Docker command line has helped for some users:

::

     -v /etc/localtime:/etc/localtime:ro

Home Assistant SSL
------------------

If your Home Assistant is running with self-signed certificates, you
will want to point to the location of the certificate files as part of
the container creation process. Add ``-v <your_cert_path>:/certs`` to
the ``docker run`` command line

Removing Appdaemon
------------------

If you no longer want to use Appdaemon :(, use the following commands:

::

    docker kill appdaemon
    docker rm appdaemon
    docker rmi acockburn/appdaemon:latest

You can delete the ``conf`` folder if you wish at this time too.
Appdaemon is now completely removed.
