Internals
=========

.. admonition:: Subject to Change
    :class: warning

    These are just notes over how the internals of AppDaemon work, but the implementation details are subject to change.

.. toctree::
   :maxdepth: 1

   threading
   scheduler
   lifecycle

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

- **Events** (:class:`~appdaemon.events.Events`) - Provides the mechanics to fire events, hand events off to relevant plugins (such as :doc:`HASS<../HASS_API_REFERENCE>` for Home Assistant), and process event callbacks

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


Reference
---------

.. .. autoclass:: appdaemon.__main__.ADMain
..    :members:
..    :no-index-entry:

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

.. .. autoclass:: appdaemon.scheduler.Scheduler
..    :members:

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
