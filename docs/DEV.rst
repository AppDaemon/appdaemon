Development
===========

If you want to help with the development of AppDaemon all assistance is gratefully received! Here are a few things you can do to help.

Running a Dev Version
---------------------

For the adventurous among you, it is possible to run the very latest dev code to get a preview of changes before they are released as part of a stable build. Be aware you use the ``dev`` branch at your own risk.  Although we try to keep things consistent and functional, we can't guarantee that things won't break. However, feedback from brave souls running the dev branch is always gratefully received!

Also, note, that to run a dev version you should be using the *PIP install method*. Docker builds are created for dev too, but there is no hass.io support.

There are 2 different ways of installing via PIP. If we are running a beta, we will have a number of specific milestone builds. These will not install by default using the standard pip command line but can be installed if their exact version is given to the pip command:

.. code:: bash

    $ pip3 install appdaemon==<specific beta version>

For non-beta builds, when the goal is just to run the latest dev code, or if you want a local version of the dev code without installing it over the top of the stable code, take the following steps:

Clone the Repository
~~~~~~~~~~~~~~~~~~~~

First, we need to get a clean copy of the dev branch. To do this, create a new directory, and change into it. Run the following command to clone the dev branch of the AppDaemon repository:

.. code:: bash

    $ git clone -b dev https://github.com/AppDaemon/appdaemon.git

This will create a directory called ``appdaemon`` - this is your repository directory, and all commands will need to be run from inside it.

Run AppDaemon from the command line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Now that you have a local copy of the code, the next step is to run AppDaemon using that code.

As a first step, if you are using a Virtual Environment (VE) enable it. The best practice here is to use a VE specifically for the dev version. In some cases, it is possible that the dev branch may have updated dependencies that will be incompatible with the latest stable release, and may break it. In this process, you can find dependency issues, review ``setup.py`` for a list of required dependencies.

To run the cloned version of AppDaemon, make sure you are in the ``appdaemon`` subdirectory and run the following command:

.. code:: bash

    $ python3 -m appdaemon -c <PATH To CONFIG DIRECTORY>

In most cases, it is possible to share config directories with other AppDaemon instances. However,  you must be aware of apps that use new features as they will likely cause errors for the stable version. If you prefer, you can create an entirely new conf directory for your dev environment.

Install AppDamon via PIP (Optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Although the recommended way of running a dev build is to use the command line above, it is possible to install an AppDaemon dev build as a pip package. If you do so, it will replace your stable version, so only do this if you are confident with packages and VEs. However,  if you use a specific VE for the dev build, this should not be an issue. Also, remember that if you do this, you will need to reinstall the package as an extra step every time you refresh the dev repository (see below).

To install the dev build as a package, change to the ``appdaemon`` directory and run the following command:

.. code:: bash

    $ pip3 install .

Updating AppDaemon to the latest dev version
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the dev version has been updated, and you want to pull over the latest changes, run the following command from the ``appdaemon`` directory:

.. code:: bash

    $ git pull

You can then immediately run the latest version with the command line above. If you are using pip, remember to rerun the ``install`` command using the ``--upgrade flag``:

.. code:: bash

    $ pip3 install --upgrade .

Pull Requests
-------------

If you see a way to improve on AppDaemon, We are pleased to receive Pull Requests. The official AppDaemon repository is here:

https://github.com/AppDaemon/appdaemon

Please note, if documentation is required to make sense of the PR, the PR will not be accepted without it.

Documentation
-------------

Assistance with the docs is always welcome, whether its fixing typos and incorrect information or reorganizing and
adding to the docs to make them more helpful. To work on the docs, submit a pull request with the changes, and I
will review and merge them in the usual way. I use `readthedocs` to build and host the docs, and you can easily
set up a preview of your edits as follows:

First, install sphinx.

.. code:: bash

    $ pip3 install sphinx

Then `cd` to the `docs` subdirectory, where all the `rst` files are found, and run the following command:

.. code:: bash

    $ sphinx-autobuild -H 0.0.0.0 . _build_html

Sphinx will take a minute or so to build the current version of the docs, and it will then be available on port 8000
(e.g., http://localhost:8080) of the machine hosting sphinx. As you make changes. Sphinx will automatically detect them
and update the browser page in real-time. When you finish your editing, stop sphinx by typing ctrl-c.
