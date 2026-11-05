# Lifecycle

"Lifecycle" refers to AppDaemon itself starting, running, and stopping.

## Contexts

AppDaemon makes heavy use of {ref}`context managers <python:context-managers>` to ensure safe and efficient startup and shutdown. Each context guarantees certain things happen as it enters and exits. The logic for the AppDaemon lifecycle consists of the following contexts, all of which get added to an {py:class}`~contextlib.ExitStack`.

* Backstop logic to catch any exceptions and log them more prettily.
* Creates a PID file for the duration of the context, if necessary/applicable.
* Creates a new async event loop and cleans it up afterwards.
* Attaches/removes signal handlers to catch termination signals and stop gracefully
* Startup/shutdown text in the logs about the versions and time it took to shut down
* Creates the `AppDaemon` and `HTTP` objects.
* Sets/unsets the default exception handler for the event loop to prettify any unhandled exceptions. The difference with the previous exception handler is that this one has access to the `AppDaemon` object

Some of these are entered as part of the `ADMain` context, and some are entered in the `ADMain.run` method. All of them are exited in reverse order as the {py:class}`~contextlib.ExitStack` is closed at shutdown.

## Startup

The top-level entrypoint is {py:func}`appdaemon.__main__.main`, which uses {py:mod}`argparse` to parse the launch arguments.

The {py:class}`~appdaemon.__main__.ADMain` class primarily provides a context manager that allows it to be used with a with statement to smoothly control AppDaemon's lifecycle. Internally it uses an instance of {py:class}`~contextlib.ExitStack`. Several methods are wrapped with the {py:func}`~contextlib.contextmanager` decorator to create context managers that get entered as part of AppDaemon starting.

```{literalinclude} ../../appdaemon/__main__.py
:language: python
:lineno-match:
:pyobject: main
:caption: main() function
:emphasize-lines: 16-17
```

## Running

ADMain runs AppDaemon by calling the {py:meth}`~appdaemon.appdaemon.AppDaemon.start` method on the top-level AppDaemon object, followed by the {py:meth}`~asyncio.loop.run_forever` method of the event loop.

```{literalinclude} ../../appdaemon/__main__.py
:language: python
:lineno-match:
:pyobject: ADMain.run
:caption: ADMain.run() method
:emphasize-lines: 10
```

## Shutdown

Shutdown is initiated by the process running AppDaemon receiving either a {py:obj}`~signal.SIGINT` or {py:obj}`~signal.SIGTERM` signal.

```{literalinclude} ../../appdaemon/__main__.py
:language: python
:lineno-match:
:pyobject: ADMain.handle_sig
:caption: ADMain.handle_sig() method
:emphasize-lines: 21-23
```

The {py:meth}`~appdaemon.appdaemon.AppDaemon.stop` method is called, which in turn calls the stop methods of the various subsystems. It doesn't return until all the tasks that existed at the time of the call have finished. This usually happens almost instantly, but this has a 3s timeout just to be safe.

```{literalinclude} ../../appdaemon/__main__.py
:language: python
:lineno-match:
:pyobject: ADMain.stop
:caption: ADMain.stop() method
:emphasize-lines: 4
```

This will stop the event loop when all the tasks have finished, which breaks the {py:meth}`~asyncio.loop.run_forever` call in {py:meth}`~appdaemon.__main__.ADMain.run` and causes the {py:class}`~contextlib.ExitStack` to close.

The {py:meth}`~appdaemon.appdaemon.AppDaemon.stop` method of the {py:class}`~appdaemon.appdaemon.AppDaemon` object is responsible for stopping all the subsystems in the correct order. It first sets a global stop event that all the subsystems check at the top of their respective loops. It then calls the stop methods of each subsystem in turn, waiting for each to finish before proceeding to the next one. Finally, it cancels any remaining tasks and waits for them to finish, with a timeout of 3 seconds.

### Stop Event

AppDaemon shutdown is globally indicated by the stop {py:class}`~asyncio.Event` getting set in the top-level {py:class}`~appdaemon.appdaemon.AppDaemon` object. All the subsystems check the status of this event using the {py:meth}`~asyncio.Event.is_set` method at the top of their respective loops, and exit if it is set. The general pattern is like this:

```python
import asyncio
import contextlib

async def loop(self):
    while not self.AD.stop_event.is_set():
         ... # Do stuff
         with contextlib.suppress(asyncio.TimeoutError):
             await asyncio.wait_for(self.AD.stop_event.wait(), timeout=1)
```

Rather than using {py:func}`~asyncio.sleep` to wait between iterations, they use {py:func}`~asyncio.wait_for` to wait for the stop event with a timeout. The timeout is suppressed with {py:func}`~contextlib.suppress` so that it doesn't raise an exception. Whenever the event is set, {py:meth}`~asyncio.Event.wait` returns immediately, which causes {py:func}`~asyncio.wait_for` to return immediately rather than waiting for the timeout.

## Reference

```{eval-rst}
.. autoclass:: appdaemon.__main__.ADMain
   :members:
   :undoc-members:
   :show-inheritance:
```
