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
Download a copy of the ``dev`` branch. Run the following command to clone the ``dev`` branch of the official `AppDaemon repository <https://github.com/AppDaemon/appdaemon.git>`_:

.. code:: console

    $ git clone -b dev https://github.com/AppDaemon/appdaemon.git

This will create a directory called ``appdaemon``: this is your local Git repository, and all subsequent commands will need to be run from inside it.

Requirements
^^^^^^^^^^^^
Firstly, it is recommended to create a Python virtual environment (VE) and enable it. The best practice here is to use a VE specifically for the development version.
In some cases, it is possible that the ``dev`` branch may have updated dependencies that will be incompatible with the latest stable release, and may break it.

Make sure you are in the ``appdaemon`` project directory, then run the following commands:

1. Install the project dependencies, along with the development dependencies

.. code:: console

    $ pip install -r dev-requirements.txt

1. Setup `pre-commit hooks <https://pre-commit.com>`_. This will make sure that modified files are linted and formatted before every commit.

.. code:: console

    $ pre-commit install

Running the application
^^^^^^^^^^^^^^^^^^^^^^^
Now that you have a local copy of the source code, the next step is to run AppDaemon.

Copy the default configuration file (edit it if you need to tweak some settings):

.. code:: console

    $ cp conf/appdaemon.yaml.example conf/appdaemon.yaml

Start the application:

.. code:: console

    $ python -m appdaemon -c conf/

In most cases, it is possible to share configuration directories with other AppDaemon instances.
However, you must be aware of AppDaemon apps that use new features as they will likely cause errors for the other pre-existing version.
It is recommended to use an entirely separate configuration directory for your development environment.

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

Dependencies management
^^^^^^^^^^^^^^^^^^^^^^^

This project is published as a Python package, and following the `PEP 631 <https://peps.python.org/pep-0631/>`_ convention
the dependencies are declared as part of the ``pyproject.toml`` file.
However since this project is run as an application, as a `recommended practice in  Python development <https://caremad.io/posts/2013/07/setup-vs-requirement/>`_, its should clearly specify the version of dependencies the application has been built and tested with,
to ensure a consistent deployment environment across multiple systems.

For this reason, the ``requirements.txt`` files are used to **pin** all the dependencies (both direct and indirect ones) that the application needs, specifying their exact version.
There are multiple files, each specifying a subset of dependencies (as defined under the ``[project.optional-dependencies]`` key in ``pyproject.toml``)

requirements.txt
  The runtime dependencies needed at runtime for AppDaemon
dev-requirements.txt
  The dependencies needed for a local development environment
doc-requirements.txt
  The dependencies needed to build the documentation with Sphinx

These files are auto-generated using ``pip-compile``, provided by the `pip-tools <https://github.com/jazzband/pip-tools/>`_ package.
It uses the ``pyproject.toml`` as the source from which to read the project dependencies. The generated files should not be manually changed.
Each file has the ``pip-compile`` command used to generated them as a reference.

The runtime ``requirements.txt`` file is fundamental for efficiently building the ``Docker`` images: thanks to the Docker build cache,
the dependencies are only installed the first time in the build process, and are re-used from the Docker cache in subsequent builds.
This improves dramatically the build times, especially when there is the need to compile native dependencies.
See :ref:`Docker build` for more information.

Docker build
^^^^^^^^^^^^

To locally build the container, it is required to have installed at least *Docker Engine 23.0*, since it enables `Docker BuildKit <https://docs.docker.com/build/buildkit/>`_ by default,
with all its useful features used in this build process.

- First it is necessary to build the AppDaemon Python package in the project directory (it will then be used as part of the Docker build stage).

.. code:: console

    $ python -m build

- Then invoke the usual the docker build command:

.. code:: console

    $ docker build -t appdaemon .


The Docker build makes use of the `multi-stage build <https://docs.docker.com/build/building/multi-stage/>`_ capabilities of Docker.
This is necessary since the *arm/v6* and *arm/v7* architectures do not provide Python *wheels* for this architectures of the **orjson** and **uvloop** packages, required by this project.

For this reason the build is divided in multiple *stages*: a *builder* stage and a *runtime* stage:

- The **builder** stage is used to install compile-time dependencies such as ``gcc`` and ``rust`` (to compile C extensions of Python dependencies), in addition to all the dependencies defined in the ``requirements.txt``.

  By copying only the ``requirements.txt``, **only the dependencies** of AppDameon are installed, so if there is no change in them between two subsequent Docker builds, Docker caches this layer and skip this step.
- The **runtime stage** copies the built Python packages from the previous stage and install the AppDaemon package in the container, along with its startup scripts and files.

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

    $ pip install -r doc-requirements.txt

Then `cd` to the `docs` subdirectory, where all the `rst` files are found, and run the following command:

.. code:: console

    $ sphinx-autobuild --host=0.0.0.0 docs/ docs/_build/html

Sphinx will take a minute or so to build the current version of the docs, and it will then be available on local port 8000
(e.g., http://localhost:8000).
As you make changes, sphinx will automatically detects them and updates the browser page in real-time.
When you finish your edit, you can stop the server via ``Ctrl-C``.
