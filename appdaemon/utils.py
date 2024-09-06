import asyncio
import concurrent.futures
import copy
import cProfile
import datetime
import functools
import inspect
import io
import json
import os
import platform
import pstats
import re
import shelve
import sys
import threading
import time
import traceback
from collections.abc import Iterable
from datetime import timedelta
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict

import dateutil.parser
import tomli
import tomli_w
import yaml
from pydantic import ValidationError

from appdaemon.futures import Futures
from appdaemon.version import __version__  # noqa: F401

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


if platform.system() != "Windows":
    import pwd

secrets = None


class Formatter(object):
    def __init__(self):
        self.types = {}
        self.htchar = "\t"
        self.lfchar = "\n"
        self.indent = 0
        self.set_formater(object, self.__class__.format_object)
        self.set_formater(dict, self.__class__.format_dict)
        self.set_formater(list, self.__class__.format_list)
        self.set_formater(tuple, self.__class__.format_tuple)

    def set_formater(self, obj, callback):
        self.types[obj] = callback

    def __call__(self, value, **args):
        for key in args:
            setattr(self, key, args[key])
        formater = self.types[type(value) if type(value) in self.types else object]
        return formater(self, value, self.indent)

    @staticmethod
    def format_object(value, indent):
        return repr(value)

    def format_dict(self, value, indent):
        items = [
            self.lfchar
            + self.htchar * (indent + 1)
            + repr(key)
            + ": "
            + (self.types[type(value[key]) if type(value[key]) in self.types else object])(self, value[key], indent + 1)
            for key in value
        ]
        return "{%s}" % (",".join(items) + self.lfchar + self.htchar * indent)

    def format_list(self, value, indent):
        items = [
            self.lfchar
            + self.htchar * (indent + 1)
            + (self.types[type(item) if type(item) in self.types else object])(self, item, indent + 1)
            for item in value
        ]
        return "[%s]" % (",".join(items) + self.lfchar + self.htchar * indent)

    def format_tuple(self, value, indent):
        items = [
            self.lfchar
            + self.htchar * (indent + 1)
            + (self.types[type(item) if type(item) in self.types else object])(self, item, indent + 1)
            for item in value
        ]
        return "(%s)" % (",".join(items) + self.lfchar + self.htchar * indent)


class PersistentDict(shelve.DbfilenameShelf):
    """
    Dict-like object that uses a Shelf to persist its contents.
    """

    def __init__(self, filename, safe: bool, *args, **kwargs):
        # writeback=True allows for mutating objects in place, like with a dict.
        super().__init__(filename, writeback=True)
        self.safe = safe
        self.rlock = threading.RLock()
        self.update(*args, **kwargs)

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

    def update(self, save=True, *args, **kwargs):
        with self.rlock:
            for key, value in dict(*args, **kwargs).items():
                # use super().__setitem__() to prevent multiple save() calls
                super().__setitem__(key, value)
                if self.safe and save:
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


class EntityStateAttrs(dict):
    def __init__(self, dict):
        self.__dict__ = AttrDict.from_nested_dict(dict)


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


def sync_decorator(coro):  # no type hints here, so that @wraps(func) works properly
    @wraps(coro)
    def wrapper(self, *args, **kwargs):
        try:
            asyncio.get_running_loop()
            task = asyncio.create_task(coro(self, *args, **kwargs))
            futures: Futures = self.AD.futures
            futures.add_future(self.name, task)
            return task
        except RuntimeError:
            # Maybe the async loop is not running yet
            result = run_coroutine_threadsafe(self, coro(self, *args, **kwargs))
            return result

    return wrapper


def timeit(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        start_time = time.perf_counter()
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            self.logger.exception(e)
        finally:
            elapsed_time = time.perf_counter() - start_time
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


def format_seconds(secs):
    return str(timedelta(seconds=secs))


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


# don't use any type hints here, so that @wraps will work properly
def executor_decorator(func):
    """Use this decorator on synchronous class methods to have them run in the AD executor asynchronously"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        ad: "AppDaemon" = self.AD
        preloaded_function = functools.partial(func, self, *args, **kwargs)
        ad.threading.logger.debug(f"Running {func.__qualname__} in the {type(ad.executor).__name__}")
        # self.logger.debug(f"Running {func.__qualname__} in the {type(ad.executor).__name__}")
        future = ad.loop.run_in_executor(executor=ad.executor, func=preloaded_function)
        return await future

    return wrapper


def format_exception(e):
    # return "\n\n" + "".join(traceback.format_exception_only(e))
    return traceback.format_exc()


def warning_decorator(
    start_text: str = None, success_text: str = None, error_text: str = None, finally_text: str = None
):
    """Creates a decorator for a function that logs custom text before and after."""

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                nonlocal start_text
                if start_text is not None:
                    self.logger.debug(start_text)

                if asyncio.iscoroutinefunction(func):
                    result = await func(self, *args, **kwargs)
                else:
                    result = func(self, *args, **kwargs)
            except Exception as e:
                error_logger = self.error
                error_logger.warning("-" * 60)
                nonlocal error_text
                error_text = error_text or f"Unexpected error running {func.__qualname__}"
                error_logger.warning(error_text)
                error_logger.warning("-" * 60)
                if isinstance(e, ValidationError):
                    error_logger.warning(e)
                else:
                    error_logger.warning(format_exception(e))
                error_logger.warning("-" * 60)

                if self.AD.logging.separate_error_log():
                    self.logger.warning(
                        "Logged an error to %s",
                        self.AD.logging.get_filename("error_log"),
                    )
            else:
                if success_text:
                    self.logger.debug(success_text)
                return result
            finally:
                nonlocal finally_text
                if finally_text:
                    self.logger.debug(finally_text)

        return wrapper

    return decorator


async def run_in_executor(self, fn, *args, **kwargs) -> Any:
    """Runs the function with the given arguments in the instance of :class:`~concurrent.futures.ThreadPoolExecutor` in the top-level :class:`~appdaemon.appdaemon.AppDaemon` object.

    Args:
        self: Needs to have an ``AD`` attribute with the :class:`~appdaemon.appdaemon.AppDaemon` object
        fn (function): Function to run in the executor
        *args: Any positional arguments to use with the function
        **kwargs: Any keyword arguments to use with the function

    Returns:
        Whatever the function returns
    """
    ad: "AppDaemon" = self.AD
    preloaded_function = functools.partial(fn, *args, **kwargs)
    future = ad.loop.run_in_executor(executor=ad.executor, func=preloaded_function)
    return await future


def run_coroutine_threadsafe(self, coro, timeout=0):
    result = None
    if timeout == 0:
        t = self.AD.internal_function_timeout
    else:
        t = timeout

    if self.AD.loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, self.AD.loop)
        try:
            result = future.result(t)
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
            if hasattr(self, "logger"):
                self.logger.warning(
                    "Coroutine (%s) took too long (%s seconds), cancelling the task...",
                    coro,
                    t,
                )
            else:
                print("Coroutine ({}) took too long, cancelling the task...".format(coro))
            future.cancel()
    else:
        self.logger.warning("LOOP NOT RUNNING. Returning NONE.")

    return result


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


def single_or_list(field):
    if isinstance(field, list):
        return field
    else:
        return [field]


def _sanitize_kwargs(kwargs, keys):
    for key in keys:
        if key in kwargs:
            del kwargs[key]
    return kwargs


def process_arg(self, arg, args, **kwargs):
    if args:
        if arg in args:
            value = args[arg]
            if "int" in kwargs and kwargs["int"] is True:
                try:
                    value = int(value)
                    setattr(self, arg, value)
                except ValueError:
                    self.logger.warning(
                        "Invalid value for %s: %s, using default(%s)",
                        value,
                        getattr(self, arg),
                    )
            if "float" in kwargs and kwargs["float"] is True:
                try:
                    value = float(value)
                    setattr(self, arg, value)
                except ValueError:
                    self.logger.warning(
                        "Invalid value for %s: %s, using default(%s)",
                        arg,
                        value,
                        getattr(self, arg),
                    )
            else:
                setattr(self, arg, value)


def find_owner(filename):
    return pwd.getpwuid(os.stat(filename).st_uid).pw_name


def is_valid_root_path(root: str) -> bool:
    root = os.path.basename(root)
    return root != "__pycache__" and not root.startswith(".")


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
    return dateutil.parser.parse(time)


def dt_to_str(dt, tz=None):
    if dt == datetime.datetime(1970, 1, 1, 0, 0, 0, 0):
        return "never"
    else:
        if tz is not None:
            return dt.astimezone(tz).isoformat()
        else:
            return dt.isoformat()


def convert_json(data, **kwargs):
    return json.dumps(data, default=str, **kwargs)


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
    if file.suffix == ".yaml":
        write_yaml_config(file, **kwargs)
    elif file.suffix == ".toml":
        write_toml_config(file, **kwargs)
    else:
        raise ValueError(f"ERROR: unknown file extension: {file.suffix}")


def write_yaml_config(path, **kwargs):
    with open(path, "w") as stream:
        yaml.dump(kwargs, stream, Dumper=yaml.SafeDumper)


def write_toml_config(path, **kwargs):
    with open(path, "wb") as stream:
        tomli_w.dump(kwargs, stream)


def read_config_file(file: Path) -> Dict[str, Dict]:
    # raise ValueError
    """Reads a single YAML or TOML file.

    This includes all the mechanics for including secrets and environment variables.
    """
    file = Path(file) if not isinstance(file, Path) else file
    if file.suffix == ".yaml":
        return read_yaml_config(file)
    elif file.suffix == ".toml":
        return read_toml_config(file)
    else:
        raise ValueError(f"ERROR: unknown file extension: {file.suffix}")


def read_toml_config(path: Path):
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
        raise ValueError("{} not found in as environment varibale".format(env_var))

    return os.environ[env_var]


def _include_yaml(loader, node):
    filename = node.value
    if not os.path.isfile(filename) or filename.split(".")[-1] != "yaml":
        raise ValueError("{} is not a valid yaml file".format(filename))

    with open(filename, "r") as f:
        return yaml.load(f, Loader=yaml.SafeLoader)


def read_yaml_config(file: Path) -> Dict[str, Dict]:
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
    return len(
        [
            p
            for p in inspect.signature(callable).parameters.values()
            if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD or p.kind == inspect.Parameter.VAR_POSITIONAL
        ]
    )


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
