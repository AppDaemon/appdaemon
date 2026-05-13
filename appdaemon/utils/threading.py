from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import inspect
import threading
from collections.abc import Awaitable, Callable, Coroutine
from logging import Logger
from typing import TYPE_CHECKING, Any, ParamSpec, Protocol, TypeVar

from .functools import unwrapped
from .parse import parse_timedelta
from .str import format_timedelta

if TYPE_CHECKING:
    from appdaemon.adbase import ADBase
    from appdaemon.appdaemon import AppDaemon
    from appdaemon.types import TimeDeltaLike


P = ParamSpec("P")
R = TypeVar("R")


class Subsystem(Protocol):
    """AppDaemon internal subsystem protocol."""

    AD: "AppDaemon"
    """Reference to the top-level AppDaemon object"""
    logger: Logger
    name: str
    """Used for registering futures, and maybe other things?"""


def executor_decorator(func: Callable[..., R]) -> Callable[..., Coroutine[Any, Any, R]]:
    """Decorate a sync function to turn it into an async function that runs in a separate thread."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> R:
        self: Subsystem = args[0]
        return await run_in_executor(self, func, *args, **kwargs)

    return wrapper


async def run_in_executor(self: Subsystem, fn: Callable[..., R], *args, **kwargs) -> R:
    """Runs the function with the given arguments in the instance of :class:`~concurrent.futures.ThreadPoolExecutor` in
    the top-level :class:`~appdaemon.appdaemon.AppDaemon` object.

    Args:
        self: Needs to have an ``AD`` attribute with the :class:`~appdaemon.appdaemon.AppDaemon` object
        fn (function): Function to run in the executor
        *args: Any positional arguments to use with the function
        **kwargs: Any keyword arguments to use with the function

    Returns:
        Whatever the function returns
    """
    function_name = unwrapped(fn).__qualname__
    executor_name = type(self.AD.executor).__name__
    self.AD.threading.logger.debug(f"Running {function_name} in the {executor_name}")

    preloaded_function = functools.partial(fn, *args, **kwargs)
    future = self.AD.loop.run_in_executor(executor=self.AD.executor, func=preloaded_function)
    self.AD.futures.add_future(self.name, future)
    return await future


def sync_decorator(coro_func: Callable[P, Awaitable[R]]) -> Callable[P, R]:
    """Wrap a coroutine function to ensure it gets run in the main thread.

    This allows users to run async ADAPI methods as if they were regular sync methods. It works by checking to see if
    the function is being run in the main thread, which has the async event loop in it. If it is the main loop, then it
    creates a task and returns it. If it isn't, then it runs the coroutine in the main thread using
    ``run_coroutine_threadsafe``.

    See
    `scheduling from other threads <https://docs.python.org/3/library/asyncio-task.html#scheduling-from-other-threads>`__
    for more details.
    """

    @functools.wraps(coro_func)
    def wrapper(self, *args, timeout: TimeDeltaLike | None = None, **kwargs) -> R:
        ad: "AppDaemon" = self.AD

        # Checks to see if it's being called from the main thread, which has the event loop in it
        in_main_thread = ad.main_thread_id == threading.current_thread().ident

        # pass through the timeout argument if the function accepts it
        if "timeout" in inspect.signature(coro_func).parameters:
            kwargs["timeout"] = timeout

        coro = coro_func(self, *args, **kwargs)
        if in_main_thread:
            task = asyncio.create_task(coro)
            ad.futures.add_future(self.name, task)
            return task
        else:
            return run_coroutine_threadsafe(self, coro, timeout=timeout)

    return wrapper


def run_coroutine_threadsafe(self: "ADBase", coro: Coroutine[Any, Any, R], timeout: TimeDeltaLike | None = None) -> R | None:
    """Run an instantiated coroutine (async) from sync code.

    This wraps the native python function ``asyncio.run_coroutine_threadsafe`` with logic to add a timeout. See
    `scheduling from other threads <https://docs.python.org/3/library/asyncio-task.html#scheduling-from-other-threads>`__
    for more details.

    Args:
        self (ADBase): Needs to have a ``self.AD`` attribute with a reference to the ``AppDaemon`` object.
        coro (Coroutine): An instantiated coroutine that hasn't been awaited.
        timeout (float | None, optional): Optional timeout to use. If no value is provided then the value set in
            ``appdaemon.internal_function_timeout`` in the ``appdaemon.yaml`` file will be used.

    Returns:
        Result from the coroutine
    """
    timeout = timeout or self.AD.config.internal_function_timeout
    timeout = parse_timedelta(timeout)

    if self.AD.loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, self.AD.loop)
        self.AD.futures.add_future(self.name, future)
        try:
            return future.result(timeout.total_seconds())
        except concurrent.futures.CancelledError:
            self.logger.warning(f"Future cancelled while waiting for coroutine: {coro}")
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
            if hasattr(self, "logger"):
                self.logger.warning(
                    "Coroutine (%s) took too long (%s), cancelling the task...",
                    coro,
                    format_timedelta(timeout),
                )
            else:
                print(f"Coroutine ({coro}) took too long, cancelling the task...")
            future.cancel()
    else:
        self.logger.warning("LOOP NOT RUNNING. Returning NONE.")


async def run_async_sync_func(self, method, *args, **kwargs):
    if inspect.iscoroutinefunction(method):
        result = await method(*args, **kwargs)
    else:
        result = await run_in_executor(self, method, *args, **kwargs)
    return result
