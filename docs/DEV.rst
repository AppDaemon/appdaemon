Development
===========

If you want to help with the development of AppDaemon all assistance is gratefully received! Here are a few things you can do to help.

Running a Dev Version
---------------------

For the adventurous among you, it is possible to run the very latest dev code to get a preview of changes before they are released as part of a stable build. You do this at your own risk, and be aware that although I try to keep things consistent and functional, I can't guarantee that I won't break things in the dev version, however, feedback from brave souls running the dev branch is always gratefully received!

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

As a first step, if you are using a Virtual Environment enable it. The best practice here is to use a venv specifically for the dev version; it is possible that the dev branch may have updated dependencies that will be incompatible with the latest stable version, and may break it. If there are dependency issues, review ``setup.py`` for a list of required dependencies.

To run the cloned version of AppDaemon, make sure you are in the ``appdaemon`` subdirectory and run the following command:

.. code:: bash

    $ python3 -m appdaemon.main -c <PATH To CONFIG DIRECTORY>

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

Pull Requests
-------------

If you see a way to imporve on AppDaemon, I am very happy to recieve Pull Requests. The official AppDaemon reposotory is here:

https://github.com/home-assistant/appdaemon

Documentation
-------------

Assistance with the docs is always welcome, whether its fixing typos and incorrect information, or reorganixing and adding to the docs to make them more helpful. To work on the docs, just subit a pull request with the changes and I will review and merge them in the ususal way. I use readthedocs to build and host the docs, and you can easily set up a preview of your edits as follows:

First, install sphinx:

.. code:: bash

    $ pip3 install sphinx

Then cd to the docs subdircetory, where all the    `rst` files are found, and run the following command:

.. code:: bash

    $ sphinx-autobuild -H 0.0.0.0 . _build_html

Sphinx will take a minute or so to build the current version of the docs, and it will then be available by browser on port 8000 of the machine hosting sphinx. As you make changes, sphinx will automatically detect them and update the browser page in real time. When you are finished editing, simply stop sphinx by typing ctrl-c.
