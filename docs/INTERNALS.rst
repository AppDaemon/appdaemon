Internal Documentation
======================

These notes are intended to assist anyone that wants to understand AppDaemon's internals better.

Structure
---------
The Python project follows the conventional `PEP 621 <https://peps.python.org/pep-0621/>`_, using a ``pyproject.toml`` file to define its metadata.
The repository is divided into various folder:

``./appdaemon``
    source code of the Python package
``./docs``
    source code from which this documentation is built
``./tests``
    tests written with ``pytest``
``./conf``
    configuration directory, containing some sample files

AppDaemon is organized into several subsystems managed by the central :class:`~appdaemon.appdaemon.AppDaemon` class. Each subsystem handles a specific aspect of functionality:

Core Subsystems
~~~~~~~~~~~~~~~

- **App Management** (:class:`~appdaemon.app_management.AppManagement`) - Provides the mechanics to manage the lifecycle of user apps, which includes tracking the user files for changes and reloading apps as needed.

- **Scheduler** (:class:`~appdaemon.scheduler.Scheduler`) - Provides time-based scheduling, sunrise/sunset calculations, and time travel functionality for testing.

- **State** (:class:`~appdaemon.state.State`) - Tracks and manages entity states across different namespaces,  provides state persistence between AppDaemon runs, and handles callbacks based on state changes.

- **Events** (:class:`~appdaemon.events.Events`) - Provides the mechanics to fire events, hand events off to relevant plugins (such as :doc:`HASS<HASS_API_REFERENCE>` for Home Assistant), and process event callbacks

- **Callbacks** (:class:`~appdaemon.callbacks.Callbacks`) - Container for storing and managing all registered callbacks from apps.

- **Services** (:class:`~appdaemon.services.Services`) - Provides the mechanics to register/deregister services and allows apps to call them with a ``<domain>/<service_name>`` string.

- **Plugin Management** (:class:`~appdaemon.plugin_management.PluginManagement`) - Manages external plugins that provide connectivity to external systems (Home Assistant, MQTT, etc.).

Threading & Async
~~~~~~~~~~~~~~~~~

- **Threading** (:class:`~appdaemon.threads.Threading`) - Manages worker threads for executing app callbacks and handles thread pinning.

- **Thread Async** (:class:`~appdaemon.thread_async.ThreadAsync`) - Bridges between threaded callback execution and the main async event loop using queues.

- **Utility Loop** (:class:`~appdaemon.utility_loop.Utility`) - Runs periodic maintenance tasks like file change detection, thread monitoring, and performance diagnostics.

Additional Subsystems
~~~~~~~~~~~~~~~~~~~~~

- **Sequences** (:class:`~appdaemon.sequences.Sequences`) - Manages configurable automation sequences with steps like service calls, waits, and conditionals.

- **Futures** (:class:`~appdaemon.futures.Futures`) - Handles asynchronous operations and provides mechanisms for cancelling long-running tasks.


Startup
-------

The top-level entrypoint is :py:func:`appdaemon.__main__.main`, which uses :py:mod:`argparse` to parse the launch
arguments.

The :py:class:`~appdaemon.__main__.ADMain` class primarily provides a :py:ref:`context manager<context-managers>` that
can be used with a :py:keyword:`with statement<with>`. This contains an :py:class:`~contextlib.ExitStack` instance that
gets closed when its context is exited. Several methods are wrapped with the :py:func:`~contextlib.contextmanager`
decorator and are added to the stack when AppDaemon is run. This guarantees that their respective cleanups are allowed
to run in the correct order, which is the reverse order that the contexts were entered.

Contexts
~~~~~~~~

The various context managers that get entered as AppDaemon starts include the logic for following steps. Some of these
are entered as part of the :py:class:`~appdaemon.__main__.ADMain` context, and some are entered in the
:py:class:`~appdaemon.__main__.ADMain.run` method. All of them are exited in reverse order as the
:py:class:`~contextlib.ExitStack` is closed, which happens when the :py:class:`~appdaemon.__main__.ADMain` context
exits.

   * Backstop logic to catch any exceptions and log them more prettily.
   * Creates a PID file for the duration of the context, if necessary/applicapable.
   * Creates a new async event loop and cleans it up afterwards.
   * Attaches/removes signal handlers to catch termination signals and stop gracefully
   * Startup/shutdown text in the logs about the versions and time it took to shut down
   * Creates the :py:class:`~appdaemon.appdaemon.AppDaemon` and :py:class:`~appdaemon.http.HTTP` objects.
   * Sets/unsets the default exception handler for the event loop to prettify any unhandled exceptions. The difference with the previous exception handler is that this one has access to the :py:class:`~appdaemon.appdaemon.AppDaemon` object

.. literalinclude:: ../appdaemon/__main__.py
   :language: python
   :lineno-match:
   :pyobject: main
   :caption: Top-level entrypoint in __main__.py
   :emphasize-lines: 16-17

Running
~~~~~~~

ADMain runs AppDaemon by calling its :py:meth:`~appdaemon.appdaemon.AppDaemon.start` method followed by the :py:meth:`~asyncio.loop.run_forever` method of the event loop.

.. literalinclude:: ../appdaemon/__main__.py
   :language: python
   :lineno-match:
   :pyobject: ADMain.run
   :caption: ADMain.run() method
   :emphasize-lines: 10

Shutdown
--------

Shutdown is initiated by the process running AppDaemon receiving either a :py:obj:`~signal.SIGINT` or :py:obj:`~signal.SIGTERM` signal.

.. literalinclude:: ../appdaemon/__main__.py
   :language: python
   :lineno-match:
   :pyobject: ADMain.handle_sig
   :caption: ADMain.handle_sig() method
   :emphasize-lines: 18-20

The :py:meth:`~appdaemon.appdaemon.AppDaemon.stop` method is called, which in turn calls the stop methods of the various
subsystems. It doesn't return until all the tasks that existed at the time of the call have finished. This usually
happens almost instantly, but this has a 3s timeout just to be safe.

.. literalinclude:: ../appdaemon/__main__.py
   :language: python
   :lineno-match:
   :pyobject: ADMain.stop
   :caption: ADMain.stop() method
   :emphasize-lines: 4

This will stop the event loop when all the tasks have finished, which breaks the :py:meth:`~asyncio.loop.run_forever`
call in :py:meth:`~appdaemon.__main__.ADMain.run` and causes the :py:class:`~contextlib.ExitStack` to close.

The :py:meth:`~appdaemon.appdaemon.AppDaemon.stop` method of the :py:class:`~appdaemon.appdaemon.AppDaemon` object is responsible for stopping all the subsystems in the correct order. It first sets a global stop event that all the subsystems check at the top of their respective loops. It then calls the stop methods of each subsystem in turn, waiting for each to finish before proceeding to the next one. Finally, it cancels any remaining tasks and waits for them to finish, with a timeout of 3 seconds.

Stop Event
~~~~~~~~~~

AppDaemon shutdown is globally indicated by the stop :py:class:`~asyncio.Event` getting set in the top-level :py:class:`~appdaemon.appdaemon.AppDaemon` object. All the subsystems check the status of this event using the :py:meth:`~asyncio.Event.is_set` method at the top of their respective loops, and exit if it is set. The general pattern is like this:

.. code-block:: python

      import asyncio
      import contextlib

      async def loop(self):
          while not self.AD.stop_event.is_set():
               ... # Do stuff
               with contextlib.suppress(asyncio.TimeoutError):
                   await asyncio.wait_for(self.AD.stop_event.wait(), timeout=1)

Rather than using :py:func:`~asyncio.sleep` to wait between iterations, they use :py:func:`~asyncio.wait_for` to wait for the stop event with a timeout. The timeout is suppressed with :py:func:`~contextlib.suppress` so that it doesn't raise an exception. Whenever
the event is set, :py:meth:`~asyncio.Event.wait` returns immediately, which causes :py:func:`~asyncio.wait_for` to return immediately rather than waiting for the timeout.

Reference
---------

.. autoclass:: appdaemon.__main__.ADMain
   :members:
   :no-index-entry:

.. autoclass:: appdaemon.appdaemon.AppDaemon
   :members:
   :no-index-entry:

.. automodule:: appdaemon.admin
   :members:

.. .. automodule:: appdaemon.admin_loop
..    :members:

.. automodule:: appdaemon.app_management
   :members:

.. automodule:: appdaemon.callbacks
   :members:

.. .. automodule:: appdaemon.dashboard
..    :members:

.. autoclass:: appdaemon.dependency_manager.DependencyManager
   :members:

.. automodule:: appdaemon.events
   :members:

.. automodule:: appdaemon.exceptions
   :members: exception_context

.. automodule:: appdaemon.futures
   :members:

.. autoclass:: appdaemon.http.HTTP
   :members:

.. automodule:: appdaemon.logging
   :members:

.. automodule:: appdaemon.plugin_management
   :members:

.. autoclass:: appdaemon.scheduler.Scheduler
   :members:

.. .. automodule:: appdaemon.services
..    :members:

.. autoclass:: appdaemon.services.ServiceCallback
   :private-members: __call__

.. autoclass:: appdaemon.services.Services

.. .. automodule:: appdaemon.sequences
..    :members:

.. autoclass:: appdaemon.state.State
   :members:

.. .. automodule:: appdaemon.stream
..    :members:

.. autoclass:: appdaemon.thread_async.ThreadAsync
   :members:

.. .. automodule:: appdaemon.threads
..    :members:

.. autoclass:: appdaemon.utility_loop.Utility
   :members:
   :private-members: _init_loop, _loop_iteration_context

.. .. automodule:: appdaemon.utils
..    :members:
