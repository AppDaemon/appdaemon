Testing AppDaemon
=================

AppDaemon uses `pytest <https://docs.pytest.org/en/stable/>`_ and `pytest-asyncio <https://pytest-asyncio.readthedocs.io/en/stable/>`_.

- Pytest is configured in the this section in the `pyproject.toml <https://docs.pytest.org/en/stable/reference/customize.html#pyproject-toml>`_ file.

  .. literalinclude:: ../pyproject.toml
    :language: toml
    :lines: 88-96
    :caption: Pytest configuration options

- Pytest-asyncio manages creating the event loop, which is normally handled by :py:class:`~appdaemon.__main__.ADMain`.
  The event loop persists throughout the test session and is reused many times by different instantiations of the
  top-level :py:class:`~appdaemon.appdaemon.AppDaemon` class.
- Instantiating the :py:class:`~appdaemon.appdaemon.AppDaemon` class can now be done without any side effects. This will
  also instantiate the necessary subsystem classes, but nothing will really start happening until the :py:meth:`~appdaemon.appdaemon.AppDaemon.start` method is called.
- The :py:class:`~appdaemon.appdaemon.AppDaemon` object is provided as a `pytest fixture <https://docs.pytest.org/en/stable/how-to/fixtures.html#>`_ (``ad``)
  with the ``function`` scope, which means it will be recreated fresh for each test function. The fixture handles starting
  and stopping the :py:class:`~appdaemon.appdaemon.AppDaemon` instance before/after each test. It also disables all apps,
  so they can be selectively run by the tests.
- Apps can be modified before they're run by the :py:class:`~appdaemon.app_management.AppManagement` object.
- The ``run_app_for_time`` fixture combines the functionality of the ``ad`` fixture with the
  :py:meth:`~appdaemon.app_management.AppManagement.app_run_context` so that apps can be temporarily modified and run
  for short periods.

Running Tests
-------------
Use the `uv run <https://docs.astral.sh/uv/reference/cli/#uv-run>`_ command to ensure uv handles the environment. It will make sure the dependencies are all satisfied.

.. code-block:: console
  :caption: Run all tests

    $ uv run pytest

CI Tests
~~~~~~~~
The CI tests get run as part of the GitHub action on PRs to the ``dev`` branch. They're intended to each run more or less instantly and collectively only take a few seconds.

.. code-block:: console
  :caption: Run CI tests

    $ uv run pytest -m ci

Functional
~~~~~~~~~~
Functional tests cover various end-to-end interactions between components, so they require AppDaemon to be running. An example would be starting an app, having it register a callback for an event, firing that event, and checking that the callback was called. These should cover as many corner cases as possible

.. code-block:: console
  :caption: Run functional tests

    $ uv run pytest -m functional

Unit Tests
~~~~~~~~~~
Unit tests don't require AppDaemon to be running and should be run frequently during development. Currently the only unit tests are ones that cover datetime and timedelta parsing.

.. code-block:: console
  :caption: Run unit tests

    $ uv run pytest -m unit

Plugin Tests
~~~~~~~~~~~~
Testing plugins involves either connecting to or mocking external systems, so aren't yet covered.

Reference
---------

Startup Tests
~~~~~~~~~~~~~

.. autofunction:: tests.functional.test_startup.test_hello_world

Event Tests
~~~~~~~~~~~

.. autoclass:: tests.functional.test_event.TestEventCallback
   :members:

State Tests
~~~~~~~~~~~

.. autoclass:: tests.functional.test_state.TestStateCallback
   :members:
