Development
===========

If you want to help with the development of AppDaemon all assistance is gratefully received! Here are a few things you can do to help.

Installing a beta version
-------------------------

For the adventurous among you, it is possible to run a pre-release version to get a preview of changes before they are released as part of a stable build. 
**Please be aware**: use it at your own risk.  Although we try to keep things consistent and functional, we can't guarantee that things won't break.
However, feedback from brave souls running this pre-release version is always gratefully received!

Also, note, that to run a development version you should be using the *Pip install method*. Docker builds are created for dev too, but there is no hass.io support.

There are 2 different ways of installing via Pip. If we are running a beta, we will have a number of specific milestone builds. 
The beta version will not install by default using the standard ``pip`` command but can be installed if its exact version is specified to `pip``:

.. code:: console

    $ pip install appdaemon==<beta version>

Setting up a development environment
------------------------------------

If you want to run the latest code available in the ``dev`` branch, or if you want to run a local version of the application separate from your existing installation, take the following steps:

Clone the repository
^^^^^^^^^^^^^^^^^^^^

First, we need to get a clean copy of the ``dev`` branch. Run the following command to clone the ``dev`` branch of the official `AppDaemon repository <https://github.com/AppDaemon/appdaemon.git>`_:

.. code:: console

    $ git clone -b dev https://github.com/AppDaemon/appdaemon.git

This will create a directory called ``appdaemon``: this is your local Git repository, and all subsequent commands will need to be run from inside it.

Requirements
^^^^^^^^^^^^

Now that you have a local copy of the code, the next step is to run AppDaemon using this code.

Firstly, it is recommended to create a Python virtual environment (VE) and enable it. The best practice here is to use a VE specifically for the development version.
In some cases, it is possible that the ``dev`` branch may have updated dependencies that will be incompatible with the latest stable release, and may break it.

Make sure you are in the ``appdaemon`` project directory, then run the following commands:

1. Install the project dependencies, along with the development dependencies

.. code:: console

    $ pip install -e .[dev]

2. Setup `pre-commit hooks <https://pre-commit.com>`_

.. code:: console

    $ pre-commit install

Running the application
^^^^^^^^^^^^^^^^^^^^^^^
To start the application:

.. code:: console

    $ python -m appdaemon -c <PATH TO CONFIG DIRECTORY>

In most cases, it is possible to share configuration directories with other AppDaemon instances. However, you must be aware of apps that use new features as they will likely cause errors for the stable version.
If you prefer, you can create an entirely new configuration directory for your dev environment.

Getting the latest changes
^^^^^^^^^^^^^^^^^^^^^^^^^^

When there are updates on the ``dev`` branch and you want to pull over the latest changes, run the following command from the ``appdaemon`` directory:

.. code:: console

    $ git pull

You can then immediately run the latest version with the commands previously detailed.

Building a distribution package
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To build a Python distribution package (*wheel*), run the following command:

.. code:: console

    $ python -m build

It will output the result of the build inside a ``dist/`` folder.

The package can be installed directly via pip:

.. code:: console

    $ pip install dist/appdaemon*.whl

Project structure
-----------------

The Python project follows the conventional PEP 621, using a ``pyproject.toml`` to define its metadata. 
The repository is divided into various folder:

appdaemon
    source code of the Python package
docs 
    source code from which this documentation is built
tests
    unit tests written with ``pytest``
conf
    configuration directory, containing some sample files


Pull Requests
-------------

If you would like to improve AppDaemon, we are pleased to receive Pull Requests in `the official AppDaemon repository <https://github.com/AppDaemon/appdaemon>`_.

Please note, if some documentation is required to make sense of the PR, the PR will not be accepted without it.

Working on the documentation
----------------------------

Assistance with the docs is always welcome, whether its fixing typos and incorrect information or reorganizing and adding to the docs to make them more helpful.
To work on the docs, submit a pull request with the changes, and I
will review and merge them in the usual way.
I use `Read the Docs <https://readthedocs.org/>`_ to build and host the documentation pages.
You can easily preview your edits locally, by running the following command:

If not already done, install the development dependencies locally.
The following command downloads and install the optional dependencies, as defined in the `pyproject.toml` file:

.. code:: console

    $ pip install .[dev]

Then `cd` to the `docs` subdirectory, where all the `rst` files are found, and run the following command:

.. code:: console

    $ sphinx-autobuild --host=0.0.0.0 docs/ docs/_build/html

Sphinx will take a minute or so to build the current version of the docs, and it will then be available on local port 8000
(e.g., http://localhost:8000).
As you make changes, sphinx will automatically detects them and updates the browser page in real-time. 
When you finish your edit, you can stop the server via ``Ctrl-C``.
