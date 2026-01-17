import asyncio
import concurrent.futures
import copy
import cProfile
import functools
import inspect
import io
import json
import logging
import os
import platform
import pstats
import random
import re
import shelve
import sys
import threading
import traceback
from collections.abc import Awaitable, Generator, Iterable, Mapping, Sequence
from datetime import datetime, time, timedelta, tzinfo
from enum import Enum
from functools import wraps
from logging import Logger
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Literal, ParamSpec, Protocol, TypeVar

import dateutil.parser
import tomli
import tomli_w
import yaml
from astral.location import Location
from pydantic import BaseModel, ValidationError
from pytz import BaseTzInfo

from appdaemon.parse import parse_datetime
from appdaemon.version import (
    __version__,  # noqa: F401
    __version_comments__,  # noqa: F401
)

from . import exceptions as ade
from .parse import parse_timedelta
from .types import TimeDeltaLike

logger = logging.getLogger("AppDaemon._utility")
file_log = logger.getChild("file")

if TYPE_CHECKING:
    from .adbase import ADBase
    from .appdaemon import AppDaemon


if platform.system() != "Windows":
    import pwd

secrets = None

ELEVATION_REGEX = re.compile(r"^(?P<N>\d+(?:\.\d+)?)\s+deg\s+(?P<dir>rising|setting)$", re.IGNORECASE)

OFFSET_SPLIT_REGEX = re.compile(r"\s*?[+-]\s*?")

T = TypeVar("T")


def has_offset(time_str: str) -> bool:
    """Check if a time string has an offset.

    Args:
        time_str (str): The time string to check.

    Returns:
        bool: True if the time string has an offset, False otherwise.
    """
    return bool(OFFSET_SPLIT_REGEX.search(time_str))


class Formatter(object):
    def __init__(self):
        self.types = {}
        self.htchar = "\t"
        self.lfchar = "\n"
        self.indent = 0
        self.set_formatter(object, self.__class__.format_object)
        self.set_formatter(dict, self.__class__.format_dict)
        self.set_formatter(list, self.__class__.format_list)
        self.set_formatter(tuple, self.__class__.format_tuple)

    def set_formatter(self, obj, callback):
        self.types[obj] = callback

    def __call__(self, value, **args):
        for key in args:
            setattr(self, key, args[key])
        formatter = self.types[type(value) if type(value) in self.types else object]
        return formatter(self, value, self.indent)

    @staticmethod
    def format_object(value, indent):
        return repr(value)

    def format_dict(self, value, indent):
        items = [
            self.lfchar + self.htchar * (indent + 1) + repr(key) + ": " + (self.types[type(value[key]) if type(value[key]) in self.types else object])(self, value[key], indent + 1) for key in value
        ]
        return "{%s}" % (",".join(items) + self.lfchar + self.htchar * indent)

    def format_list(self, value, indent):
        items = [self.lfchar + self.htchar * (indent + 1) + (self.types[type(item) if type(item) in self.types else object])(self, item, indent + 1) for item in value]
        return "[%s]" % (",".join(items) + self.lfchar + self.htchar * indent)

    def format_tuple(self, value, indent):
        items = [self.lfchar + self.htchar * (indent + 1) + (self.types[type(item) if type(item) in self.types else object])(self, item, indent + 1) for item in value]
        return "(%s)" % (",".join(items) + self.lfchar + self.htchar * indent)


class ADWritebackType(str, Enum):
    """Represents different strategies for AppDaemon to write persistent namespaces to disk.

    See :py:meth:`shelve.open` for more details about writeback modes for the underlying shelf object and
    `user Defined Namespaces <https://appdaemon.readthedocs.io/en/latest/APPGUIDE.html#user-defined-namespaces>`_
    """
    safe = "safe"
    """The namespace is written to disk every time a change is made so will be up to date even if a crash happens. The
    downside is that there is a possible performance impact for systems with slower disks, or that set state on many
    UDNS at a time."""
    hybrid = "hybrid"
    """A compromise setting in which the namespaces are saved periodically (once each time around the utility loop,
    usually once every second- with this setting a maximum of 1 second of data will be lost if AppDaemon crashes."""


class PersistentDict(shelve.DbfilenameShelf):
    """
    Dict-like object that uses a shelf to persist its contents.

    A “shelf” is a persistent, dictionary-like object. The difference with “dbm” databases is that the values (not the
    keys!) in a shelf can be essentially arbitrary Python objects — anything that the pickle module can handle. This
    includes most class instances, recursive data types, and objects containing lots of shared sub-objects. The keys are
    ordinary strings.
    """

    writeback_type: ADWritebackType
    safe: bool
    rlock: threading.RLock
    filepath: Path

    def __init__(self, filename: str | Path, writeback_type: ADWritebackType = ADWritebackType.safe) -> None:
        match writeback_type:
            case ADWritebackType.safe:
                # This is the default condition for shelf objects, which saves all assignments to the dict to disk.
                writeback = False
            case ADWritebackType.hybrid:
                # From the Python docs:
                # If the optional writeback parameter is set to True, all entries accessed are also cached in memory,
                # and written back on sync() and close(); this can make it handier to mutate mutable entries in the
                # persistent dictionary, but, if many entries are accessed, it can consume vast amounts of memory for
                # the cache, and it can make the close operation very slow since all accessed entries are written back
                # (there is no way to determine which accessed entries are mutable, nor which ones were actually mutated).
                writeback = True

        filepath = Path(filename).resolve()
        if sys.version_info.minor < 13:
            filepath = filepath.with_suffix("")
        else:
            filepath = filepath.with_suffix(".db")

        super().__init__(str(filepath), writeback=writeback)
        self.writeback_type = writeback_type
        self.safe = writeback_type == ADWritebackType.safe
        self.rlock = threading.RLock()
        self.filepath = filepath
        # print(f'PersistentDict using writeback mode: {self.writeback_type}, writeback={writeback}')

    @property
    def is_safe(self) -> bool:
        return self.writeback_type == ADWritebackType.safe

    def __contains__(self, key):
        with self.rlock:
            return super().__contains__(key)

    def __copy__(self):
        return dict(self)

    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self), memo=memo)

    def __delitem__(self, key):
        with self.rlock:
            super().__delitem__(key)

    def __getitem__(self, key):
        with self.rlock:
            return super().__getitem__(key)

    def __iter__(self):
        with self.rlock:
            for item in super().__iter__():
                yield item

    def __len__(self):
        with self.rlock:
            return super().__len__()

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, dict(self))

    def __setitem__(self, key, val):
        with self.rlock:
            super().__setitem__(key, val)
            if self.safe:
                self.sync()

    def sync(self):
        with self.rlock:
            super().sync()

    def update(self, new: dict[str, Any], save: bool = False) -> None:
        with self.rlock:
            for key, val in new.items():
                super().__setitem__(key, val)
            if self.is_safe or save:
                self.sync()


class AttrDict(dict):
    """Dictionary subclass whose entries can be accessed by attributes
    (as well as normally).
    """

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

    @staticmethod
    def from_nested_dict(data):
        """Construct nested AttrDicts from nested dictionaries."""
        if not isinstance(data, dict):
            return data
        else:
            return AttrDict({key: AttrDict.from_nested_dict(data[key]) for key in data})


class StateAttrs(dict):
    def __init__(self, dict):
        device_dict = {}
        devices = set()
        for entity in dict:
            if "." in entity:
                device, name = entity.split(".")
                devices.add(device)
        for device in devices:
            entity_dict = {}
            for entity in dict:
                if "." in entity:
                    thisdevice, name = entity.split(".")
                    if device == thisdevice:
                        entity_dict[name] = dict[entity]
            device_dict[device] = AttrDict.from_nested_dict(entity_dict)

        self.__dict__ = device_dict


def check_state(logger, new_state, callback_state, name) -> bool:
    passed = False

    try:
        if isinstance(callback_state, (str, int, float)):
            passed = new_state == callback_state

        elif isinstance(callback_state, Iterable):
            passed = new_state in callback_state

        elif callback_state.__name__ == "<lambda>":  # lambda function
            passed = callback_state(new_state)

    except Exception as e:
        logger.warning("Could not evaluate state check due to %s, from %s", e, name)
        passed = False

    return passed


P = ParamSpec("P")
R = TypeVar("R")


def parse_timedelta_or_none(input_: str | int | float | timedelta | None) -> timedelta | None:
    """Parse to timedelta, but return None if input is None."""
    return parse_timedelta(input_) if input_ is not None else None


def resolve_offset(
    offset: timedelta,
    random_start: timedelta | None = None,
    random_end: timedelta | None = None,
) -> timedelta:
    """Resolves a given offset with some randomization into a timedelta object.

    Args:
        offset: Base offset as a timedelta
        random_start: Start of random range as a timedelta (can be negative)
        random_end: End of random range as a timedelta

    Returns:
        The offset plus a random value in [random_start, random_end]
    """
    if random_start is not None or random_end is not None:
        r_start = random_start if random_start is not None else timedelta()
        r_end = random_end if random_end is not None else timedelta()

        span = r_end - r_start
        assert span >= timedelta(), "Random end must be greater than or equal to random start"

        random_offset = span * random.random() + r_start
        offset += random_offset
    return offset


# Maximum allowed offset for sun events (sunrise/sunset repeat daily)
SUN_EVENT_INTERVAL = timedelta(days=1)


def validate_offset_within_interval(
    offset: timedelta,
    interval: timedelta,
    event_type: str,
    random_start: timedelta | None = None,
    random_end: timedelta | None = None,
) -> None:
    """Validate that the offset (including random range) doesn't exceed the event interval.

    For repeating schedules, an offset that exceeds the interval between events would cause
    confusing behavior where the callback fires at unpredictable times relative to the intended
    base time.

    Args:
        offset: The base offset as a timedelta
        interval: The interval between events as a timedelta
        event_type: Human-readable description of the event type (e.g., "sunrise", "daily")
        random_start: Optional random range start as a timedelta
        random_end: Optional random range end as a timedelta

    Raises:
        OffsetExceedsIntervalError: If the maximum possible offset exceeds the interval
    """
    if interval <= timedelta():
        return  # Non-repeating event or invalid interval, skip validation

    r_start = random_start if random_start is not None else timedelta()
    r_end = random_end if random_end is not None else timedelta()

    # Calculate the extreme possible offsets
    min_offset = offset + r_start
    max_offset = offset + r_end

    # Check if any possible offset would exceed the interval
    if abs(min_offset) >= interval or abs(max_offset) >= interval:
        raise ade.OffsetExceedsIntervalError(
            offset=offset,
            interval=interval,
            event_type=event_type,
            random_start=random_start,
            random_end=random_end,
        )


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

    @wraps(coro_func)
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


def timeit(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        start_time = perf_counter()
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            self.logger.exception(e)
        finally:
            elapsed_time = perf_counter() - start_time
            self.logger.debug(f"Finished [{func.__name__}] in {elapsed_time * 10**3:.0f} ms")

    return wrapper


def _profile_this(fn):
    def profiled_fn(*args, **kwargs):
        self = args[0]
        self.pr = cProfile.Profile()
        self.pr.enable()

        result = fn(self, *args, **kwargs)

        self.pr.disable()
        s = io.StringIO()
        sortby = "cumulative"
        ps = pstats.Stats(self.pr, stream=s).sort_stats(sortby)
        ps.print_stats()
        self.profile = fn + s.getvalue()

        return result

    return profiled_fn


def format_seconds(secs: TimeDeltaLike) -> str:
    return str(parse_timedelta(secs))


def format_timedelta(td: TimeDeltaLike | None) -> str:
    """Format a timedelta object into a human-readable string.

    There are different brackets for lengths of time that will format the strings differently.

    Uses ``parse_timedelta`` to convert the input into a timedelta object before formatting the string.

    Examples:
        >>> format_timedelta(0.025374)
        '25.374ms'

        >>> format_timedelta(0.687)
        '687ms'

        >>> format_timedelta(2.5)
        '2.5s'

        >>> format_timedelta(25)
        '25s'

        >>> format_timedelta(None)
        'never'

        >>> format_timedelta(0)
        'No time'

    """
    match td:
        case None:
            return "never"
        case _:
            td = parse_timedelta(td)
            seconds = td.total_seconds()
            if seconds == 0:
                return "No time"
            elif seconds < 0.1:
                return f"{seconds * 10**3:.3f}ms"
            elif seconds < 1:
                return f"{seconds * 10**3:.0f}ms"
            elif seconds < 25:
                return f"{seconds:.1f}s"
            else:
                td = timedelta(seconds=round(seconds, 0))  # Round off the seconds for longer durations
                res = str(td)
                hours = int(seconds / 3600)
                if hours == 0:  # Remove the hours portion if it's 0
                    res = res.split(":", 1)[1]
                return res


def now_is_between(
    now: datetime,
    start_time: str | time | datetime,
    end_time: str | time | datetime,
    location: Location | None = None,
) -> bool:
    assert now.tzinfo is not None, "Now must be a timezone-aware datetime"
    parse = functools.partial(
        parse_datetime,
        now=now,
        location=location,
        today=True,
    )

    aware_start = parse(start_time)
    aware_end = parse(end_time)

    if aware_start > aware_end and (now < aware_start or now < aware_end):
        aware_start = parse(start_time, days_offset=-1)
        if aware_start > aware_end:
            aware_start -= timedelta(days=1)

    if aware_start > aware_end and now > aware_start and now > aware_end:
        aware_end = parse(end_time, days_offset=1)
        if aware_start > aware_end:
            aware_end += timedelta(days=1)

    return aware_start <= now <= aware_end


def ensure_timezone(input_: datetime, timezone: BaseTzInfo | None) -> datetime:
    if timezone is not None:
        if input_.tzinfo is None:
            result = timezone.localize(input_)
        else:
            result = input_.astimezone(timezone)
    else:
        result = input_

    assert result.tzinfo is not None, "Resulting datetime must be timezone-aware"
    return result


def deep_compare(check: dict, data: dict) -> bool:
    """Compares 2 nested dictionaries of values"""
    data = data or {}  # Replaces a None value with an empty dict

    for k, v in tuple(check.items()):
        if isinstance(v, dict) and isinstance(data[k], dict):
            if deep_compare(v, data[k]):
                continue
            else:
                return False
        elif v != data.get(k):
            return False
    else:
        return True


def get_kwargs(kwargs):
    result = ""
    for kwarg in kwargs:
        if kwarg[:2] != "__":
            result += "{}={} ".format(kwarg, kwargs[kwarg])
    return result


def rreplace(s, old, new, occurrence):
    li = s.rsplit(old, occurrence)
    return new.join(li)


def day_of_week(day):
    nums = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    days = {day: idx for idx, day in enumerate(nums)}

    if isinstance(day, str):
        return days[day]
    if isinstance(day, int):
        return nums[day]
    raise ValueError("Incorrect type for 'day' in day_of_week()'")


def format_exception(e):
    # return "\n\n" + "".join(traceback.format_exception_only(e))
    return traceback.format_exc()


def log_warning_block(logger: Logger, exception_text: str, header: str | None = None, width: int = 60) -> None:
    logger.warning("-" * width)
    logger.warning(header or "Unexpe")
    exception_text = ("-" * 60) + "\n" + exception_text
    logger.warning(exception_text)
    logger.warning("-" * 60)


def warning_decorator(
    start_text: str | None = None,
    success_text: str | None = None,
    error_text: str | None = None,
    finally_text: str | None = None,
    reraise: bool = False,
) -> Callable[[Callable[..., Coroutine[Any, Any, R]]], Callable[..., Coroutine[Any, Any, R]]]:
    """Decorate an async function to log messages at various stages around it running.

    By default this does not reraise any exceptions that occur during the execution of the wrapped function.

    Only works on methods of AppDaemon subsystems because it uses the attributes:
        - self.logger
        - self.AD

    Raises:
        By default, only ever re-raises an AppDaemonException

    """

    def decorator(func: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., Coroutine[Any, Any, R]]:
        @wraps(func)
        async def wrapper(self, *args: Any, **kwargs: Any) -> R:
            logger: Logger = self.logger
            error_logger: Logger = self.error
            nonlocal error_text
            error_text = error_text or f"Unexpected error running {func.__qualname__}"
            try:
                nonlocal start_text
                if start_text is not None:
                    logger.debug(start_text)

                result = await func(self, *args, **kwargs)
            except SyntaxError as e:
                logger.warning(error_text)
                log_warning_block(error_logger, header=error_text, exception_text="".join(traceback.format_exception(e, limit=-1)))
            except ade.AppDaemonException as e:
                raise e
            except ValidationError as e:
                log_warning_block(error_logger, header=error_text, exception_text=str(e))
            except Exception as e:
                log_warning_block(
                    error_logger,
                    exception_text=format_exception(e),
                    header=error_text,
                )

                if self.AD.logging.separate_error_log():
                    logger.warning(
                        "Logged an error to %s",
                        self.AD.logging.get_filename("error_log"),
                    )
                if reraise:
                    raise e
            else:
                nonlocal success_text
                if success_text:
                    logger.debug(success_text)
                return result
            finally:
                nonlocal finally_text
                if finally_text:
                    logger.debug(finally_text)

        return wrapper

    return decorator


class Subsystem(Protocol):
    """AppDaemon internal subsystem protocol."""

    AD: "AppDaemon"
    """Reference to the top-level AppDaemon object"""
    logger: Logger
    name: str
    """Used for registering futures, and maybe other things?"""


def executor_decorator(func: Callable[..., R]) -> Callable[..., Coroutine[Any, Any, R]]:
    """Decorate a sync function to turn it into an async function that runs in a separate thread."""

    @wraps(func)
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


def run_coroutine_threadsafe(self: "ADBase", coro: Coroutine[Any, Any, R], timeout: TimeDeltaLike | None = None) -> R:
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


def deepcopy(data):
    result = None

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = deepcopy(value)

        assert id(result) != id(data)

    elif isinstance(data, list):
        result = []
        for item in data:
            result.append(deepcopy(item))

        assert id(result) != id(data)

    elif isinstance(data, tuple):
        aux = []
        for item in data:
            aux.append(deepcopy(item))
        result = tuple(aux)

        assert id(result) != id(data)

    else:
        result = data

    return result


def find_path(name: str) -> Path:
    search_paths = [Path("~/.homeassistant").expanduser(), Path("/etc/appdaemon")]
    for path in search_paths:
        if (file := (path / name)).exists():
            return file
    else:
        raise FileNotFoundError(f"Did not find {name} in {search_paths}")


def _sanitize_kwargs(kwargs, keys):
    for key in keys:
        if key in kwargs:
            del kwargs[key]
    return kwargs


def find_owner(filename):
    return pwd.getpwuid(os.stat(filename).st_uid).pw_name


def check_path(type, logger, inpath, pathtype="directory", permissions=None):  # noqa: C901
    # disable checks for windows platform

    # Some root directories are expected to be owned by people other than the user so skip some checks
    skip_owner_checks = ["/Users", "/home"]

    if platform.system() == "Windows":
        return

    try:
        path = os.path.abspath(inpath)

        perms = permissions
        if pathtype == "file":
            dir = os.path.dirname(path)
            file = path
            if perms is None:
                perms = "r"
        else:
            dir = path
            file = None
            if perms is None:
                perms = "rx"

        dirs = []
        while not os.path.ismount(dir):
            dirs.append(dir)
            d, F = os.path.split(dir)
            dir = d

        fullpath = True
        for directory in reversed(dirs):
            if not os.access(directory, os.F_OK):
                logger.warning("%s: %s does not exist exist", type, directory)
                fullpath = False
            elif not os.path.isdir(directory):
                if os.path.isfile(directory):
                    logger.warning(
                        "%s: %s exists, but is a file instead of a directory",
                        type,
                        directory,
                    )
                    fullpath = False
            else:
                owner = find_owner(directory)
                if "r" in perms and not os.access(directory, os.R_OK):
                    logger.warning(
                        "%s: %s exists, but is not readable, owner: %s",
                        type,
                        directory,
                        owner,
                    )
                    fullpath = False
                if "w" in perms and not os.access(directory, os.W_OK) and directory not in skip_owner_checks:
                    logger.warning(
                        "%s: %s exists, but is not writeable, owner: %s",
                        type,
                        directory,
                        owner,
                    )
                    fullpath = False
                if "x" in perms and not os.access(directory, os.X_OK):
                    logger.warning(
                        "%s: %s exists, but is not executable, owner: %s",
                        type,
                        directory,
                        owner,
                    )
                    fullpath = False
        if fullpath is True:
            owner = find_owner(path)
            user = pwd.getpwuid(os.getuid()).pw_name
            if owner != user:
                logger.warning(
                    "%s: %s is owned by %s but appdaemon is running as %s",
                    type,
                    path,
                    owner,
                    user,
                )

        if file is not None:
            owner = find_owner(file)
            if "r" in perms and not os.access(file, os.R_OK):
                logger.warning("%s: %s exists, but is not readable, owner: %s", type, file, owner)
            if "w" in perms and not os.access(file, os.W_OK):
                logger.warning("%s: %s exists, but is not writeable, owner: %s", type, file, owner)
            if "x" in perms and not os.access(file, os.X_OK):
                logger.warning("%s: %s exists, but is not executable, owner: %s", type, file, owner)
    except KeyError:
        #
        # User ID is not properly set up with a username in docker variants
        # getpwuid() errors out with a KeyError
        # We just have to skip most of these tests
        pass


def str_to_dt(time):
    if time == "never":
        return time
    return dateutil.parser.parse(time)


def dt_to_str(dt: datetime, tz: tzinfo | None = None, *, round: bool = False) -> str | Literal["never"]:
    """Convert a datetime object to a string.

    This function provides a single place for standardizing the conversion of datetimes to strings.

    Args:
        dt (datetime): The datetime object to convert.
        tz (tzinfo, optional): Optional timezone to apply. Defaults to None.
        round (bool, optional): Whether to round the datetime to the nearest second. Defaults to False.
    """
    if round:
        dt = dt.replace(microsecond=0)

    if dt == datetime(1970, 1, 1, 0, 0, 0, 0):
        return "never"
    else:
        if tz is not None:
            return dt.astimezone(tz).isoformat()
        else:
            return dt.isoformat()


def convert_json(data, **kwargs):
    def fallback_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    return json.dumps(data, default=fallback_serializer, **kwargs)


def get_object_size(obj, seen=None):
    """Recursively finds size of objects"""
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    # Important mark as seen *before* entering recursion to gracefully handle
    # self-referential objects
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum([get_object_size(v, seen) for v in obj.values()])
        size += sum([get_object_size(k, seen) for k in obj.keys()])
    elif hasattr(obj, "__dict__"):
        size += get_object_size(obj.__dict__, seen)
    elif hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_object_size(i, seen) for i in obj])
    return size


def write_config_file(file: Path, **kwargs):
    """Writes a single YAML or TOML file."""
    file = Path(file) if not isinstance(file, Path) else file
    match file.suffix:
        case ".yaml":
            return write_yaml_config(file, **kwargs)
        case ".toml":
            return write_toml_config(file, **kwargs)
        case _:
            raise ValueError(f"ERROR: unknown file extension: {file.suffix}")


def write_yaml_config(path, **kwargs):
    with open(path, "w") as stream:
        yaml.dump(kwargs, stream, Dumper=yaml.SafeDumper)


def write_toml_config(path, **kwargs):
    with open(path, "wb") as stream:
        tomli_w.dump(kwargs, stream)


def read_config_file(file: Path, app_config: bool = False) -> dict[str, dict[str, Any]]:
    # raise ValueError
    """Reads a single YAML or TOML file.

    This includes all the mechanics for including secrets and environment variables.

    Args:
        file: Path to the configuration file to read.
        app_config: Flag for whether to add the config_path key to the loaded dictionaries
    """
    try:
        file = Path(file) if not isinstance(file, Path) else file
        match file.suffix.lower():
            case ".yaml" | ".yml":
                full_cfg = read_yaml_config(file)
            case ".toml":
                full_cfg = read_toml_config(file)
            case _:
                raise ValueError(f"ERROR: unknown file extension: {file.suffix}")

        if app_config:
            for key, cfg in full_cfg.items():
                if key == "sequence":
                    for seq_cfg in cfg.values():
                        seq_cfg["config_path"] = file
                elif cfg is not None and isinstance(cfg, dict):
                    cfg["config_path"] = file

        return full_cfg
    except Exception as exc:
        raise ade.ConfigReadFailure(file) from exc


def read_toml_config(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("rb") as f:
        config = tomli.load(f)

    # now figure out secrets file

    if "secrets" in config:
        secrets_file = Path(config["secrets"])
    else:
        secrets_file = path.with_name("secrets.toml")

    try:
        with secrets_file.open("rb") as f:
            secrets = tomli.load(f)
    except FileNotFoundError:
        # We have no secrets
        secrets = None

    # traverse config looking for !secret and !env

    final_config = toml_sub(config, secrets, os.environ)

    return final_config


def toml_sub(data, secrets, env):
    result = None

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = toml_sub(value, secrets, env)

        assert id(result) != id(data)

    elif isinstance(data, list):
        result = []
        for item in data:
            result.append(toml_sub(item, secrets, env))

        assert id(result) != id(data)

    elif isinstance(data, tuple):
        aux = []
        for item in data:
            aux.append(toml_sub(item, secrets, env))
        result = tuple(aux)

        assert id(result) != id(data)

    else:
        result = data
        if isinstance(data, str):
            r = re.match(r"^!secret\s+(\w+)$", data)
            if r is not None:
                key = r.group(1)
                if secrets is None:
                    print(f"ERROR: !secret used and no secrets file: '{data}'")
                elif key in secrets:
                    result = secrets[key]
                else:
                    print(f"ERROR: !secret ({key}) not found in secrets file")

            r = re.search(r"^!env\s+(\w+)$", data)
            if r is not None:
                key = r.group(1)
                if key in env:
                    result = env[key]
                else:
                    print(f"ERROR: !env ({key}) not found in environment")

    return result


def _dummy_secret(loader, node):
    pass


def _secret_yaml(loader, node):
    if secrets is None:
        raise ValueError("!secret used but no secrets file found")

    if node.value not in secrets:
        raise ValueError("{} not found in secrets file".format(node.value))

    return secrets[node.value]


def _env_var_yaml(loader, node):
    env_var = node.value
    if env_var not in os.environ:
        raise ValueError("{} not found in as environment variable".format(env_var))

    return os.environ[env_var]


def _include_yaml(loader, node):
    filename = node.value
    if not os.path.isfile(filename) or filename.split(".")[-1] != "yaml":
        raise ValueError("{} is not a valid yaml file".format(filename))

    with open(filename, "r") as f:
        return yaml.load(f, Loader=yaml.SafeLoader)


def read_yaml_config(file: Path) -> dict[str, dict[str, Any]]:
    #
    # First locate secrets file
    #
    #    try:
    #
    # Read config file using include directory
    #

    yaml.add_constructor("!include", _include_yaml, Loader=yaml.SafeLoader)

    #
    # Read config file using environment variables
    #

    yaml.add_constructor("!env_var", _env_var_yaml, Loader=yaml.SafeLoader)

    #
    # Initially load file to see if secret directive is present
    #
    yaml.add_constructor("!secret", _dummy_secret, Loader=yaml.SafeLoader)
    with file.open("r") as yamlfd:
        file_log.debug("Reading config file: %s", file)
        config = yaml.safe_load(yamlfd)

    # No need to keep processing if the file is empty
    if not bool(config):
        return {}

    if "secrets" in config:
        secrets_file = Path(config["secrets"])
    else:
        secrets_file = file.with_name("secrets.yaml")

    #
    # Read Secrets
    #
    try:
        if secrets_file.exists():
            with secrets_file.open("r") as yamlfd:
                global secrets
                secrets = yaml.safe_load(yamlfd)
    except Exception:
        print(
            "ERROR",
            f"Error loading secrets file: {secrets_file}",
        )
        return None

    #
    # Read config file again, this time with secrets
    #

    yaml.add_constructor("!secret", _secret_yaml, Loader=yaml.SafeLoader)

    with file.open("r") as yamlfd:
        return yaml.safe_load(yamlfd)


def count_positional_arguments(callable: Callable) -> int:
    return len([p for p in inspect.signature(callable).parameters.values() if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD or p.kind == inspect.Parameter.VAR_POSITIONAL])


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def time_str(start: float, now: float | None = None) -> str:
    return format_timedelta((now or perf_counter()) - start)


def clean_kwargs(val: Any, *, http: bool = False) -> Any:
    """Recursively clean a dict of kwargs.

    Conversions:
        - datetime values are converted to ISO format strings
        - Mapping values (like dicts) are converted to dicts of cleaned key-value pairs
        - Iterable values (like lists and tuples) are converted to lists of cleaned values
        - Other values are converted to strings
    """

    match val:
        case True if http:
            return "true"
        case str() | int() | float() | bool() | None:
            return val
        case datetime():
            return val.isoformat()
        case Mapping():
            return {k: clean_kwargs(v, http=http) for k, v in val.items()}
        case Iterable():
            return [clean_kwargs(v, http=http) for v in val]
        case _:
            return str(val)


def remove_literals(val: Any, literal: Sequence[Any]) -> Any:
    """Remove instances of literals from a nested data structure."""
    match val:
        case str():
            return val
        case Mapping():
            return {k: remove_literals(v, literal) for k, v in val.items() if v not in literal}
        case Iterable():
            return [remove_literals(v, literal) for v in val if v not in literal]
        case _:
            return val


def clean_http_kwargs(val: Any) -> Any:
    """Recursively cleans the kwarg dict to prepare it for use in HTTP requests."""
    cleaned = clean_kwargs(val, http=True)
    pruned = remove_literals(cleaned, (None, False))
    return pruned


def unwrapped(func: Callable) -> Callable:
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    if isinstance(func, functools.partial):
        func = func.func
    return func


def has_expanded_kwargs(func):
    """Determines whether or not to use keyword argument expansion on this function by
    finding if there's a ``**kwargs`` expansion somewhere.

    Handles unwrapping (removing decorators) if necessary.
    """
    func = unwrapped(func)

    if isinstance(func, functools.partial):
        func = func.func

    return any(param.kind == param.VAR_KEYWORD for param in inspect.signature(func).parameters.values())


def has_collapsed_kwargs(func):
    func = unwrapped(func)
    params = inspect.signature(func).parameters
    p = list(params.values())[-1]
    return p.kind == p.POSITIONAL_OR_KEYWORD


def deprecation_warnings(model: BaseModel, logger: Logger):
    for field in model.model_fields_set:
        if model.__pydantic_extra__ is not None and field in model.__pydantic_extra__:
            logger.warning(f"Extra config field '{field}'. This will be ignored")
        elif (info := model.model_fields.get(field)) and info.deprecated:
            logger.warning(f"Deprecated field '{field}': {info.deprecation_message}")

        match attr := getattr(model, field):
            case dict():
                for val in attr.values():
                    if isinstance(val, BaseModel):
                        deprecation_warnings(val, logger)
            case BaseModel():
                deprecation_warnings(attr, logger)


def recursive_get_files(base: Path, suffix: str | set[str], exclude: set[str] | None = None) -> Generator[Path, None, None]:
    """Recursively generate file paths.

    Args:
        base (Path): The base directory to start searching from.
        suffix (str): The file extension to filter by.
        exclude (set[str]): A set of directory names to exclude from the search.

    Yields:
        Path objects to files that have the matching extension and are readable.
    """
    suffix = {suffix} if isinstance(suffix, str) else suffix
    exclude = set() if exclude is None else exclude
    for item in base.iterdir():
        if item.name.startswith(".") or (exclude is None or item.name in exclude):
            continue
        elif item.is_file() and item.suffix in suffix and os.access(item, os.R_OK):
            yield item
        elif item.is_dir() and os.access(item, os.R_OK):
            yield from recursive_get_files(item, suffix, exclude)
