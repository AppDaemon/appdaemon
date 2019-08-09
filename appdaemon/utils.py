import os
from datetime import timedelta
import asyncio
import platform
import functools
import time
import cProfile
import io
import pstats
import json
import threading
import datetime
import dateutil.parser
import copy


if platform.system() != "Windows":
    import pwd

__version__ = "4.0.0b1"
secrets = None

class Formatter(object):
    def __init__(self):
        self.types = {}
        self.htchar = '\t'
        self.lfchar = '\n'
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

    def format_object(self, value, indent):
        return repr(value)

    def format_dict(self, value, indent):
        items = [
            self.lfchar + self.htchar * (indent + 1) + repr(key) + ': ' +
            (self.types[type(value[key]) if type(value[key]) in self.types else object])(self, value[key], indent + 1)
            for key in value
        ]
        return '{%s}' % (','.join(items) + self.lfchar + self.htchar * indent)

    def format_list(self, value, indent):
        items = [
            self.lfchar + self.htchar * (indent + 1) + (self.types[type(item) if type(item) in self.types else object])(
                self, item, indent + 1)
            for item in value
        ]
        return '[%s]' % (','.join(items) + self.lfchar + self.htchar * indent)

    def format_tuple(self, value, indent):
        items = [
            self.lfchar + self.htchar * (indent + 1) + (self.types[type(item) if type(item) in self.types else object])(
                self, item, indent + 1)
            for item in value
        ]
        return '(%s)' % (','.join(items) + self.lfchar + self.htchar * indent)


class PersistentDict(dict):

    """
    Persistent Dictionary subclass that uses JSON to persist its contents
    """

    #TODO - this all runs in the loop at the moment ...

    def __init__(self, filename, safe, *args, **kwargs):
        super().__init__(**kwargs)
        self.filename = filename
        self.safe = safe
        self.lock = threading.RLock()
        self._load()

    def _load(self):
        with self.lock:
            if os.path.isfile(self.filename) and os.path.getsize(self.filename) > 0:
                with open(self.filename, 'r') as fh:
                    self.update(False, json.load(fh))

    def save(self):
        with self.lock:
            with open(self.filename, 'w') as fh:
                json.dump(self, fh)

    def __getitem__(self, key):
        return dict.__getitem__(self, key)

    def __setitem__(self, key, val):
        dict.__setitem__(self, key, val)
        if self.safe is True:
            self.save()

    def __repr__(self):
        dictrepr = dict.__repr__(self)
        return '%s(%s)' % (type(self).__name__, dictrepr)

    def __deepcopy__(self, memo):
        result = {}
        for key in self.keys():
            result[key] = self.__getitem__(key)

        return copy.deepcopy(result)

    def update(self, save=True, *args, **kwargs):
        for k, v in dict(*args, **kwargs).items():
            self[k] = v
            if self.safe is True and save is True:
                self.save()


class AttrDict(dict):
    """ Dictionary subclass whose entries can be accessed by attributes
        (as well as normally).
    """

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

    @staticmethod
    def from_nested_dict(data):
        """ Construct nested AttrDicts from nested dictionaries. """
        if not isinstance(data, dict):
            return data
        else:
            return AttrDict({key: AttrDict.from_nested_dict(data[key])
                             for key in data})


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


def _timeit(func):
    @functools.wraps(func)
    def newfunc(*args, **kwargs):
        self = args[0]
        start_time = time.time()
        result = func(self, *args, **kwargs)
        elapsed_time = time.time() - start_time
        self.logger.info('function [%s] finished in %s ms', func.__name__, int(elapsed_time * 1000))
        return result

    return newfunc


def _profile_this(fn):
    def profiled_fn(*args, **kwargs):
        self = args[0]
        self.pr = cProfile.Profile()
        self.pr.enable()

        result = fn(self, *args, **kwargs)

        self.pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
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


def _dummy_secret(loader, node):
    pass


def _secret_yaml(loader, node):
    if secrets is None:
        raise ValueError("!secret used but no secrets file found")

    if node.value not in secrets:
        raise ValueError("{} not found in secrets file".format(node.value))

    return secrets[node.value]


def rreplace(s, old, new, occurrence):
    li = s.rsplit(old, occurrence)
    return new.join(li)


def day_of_week(day):
    nums = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    days = {day: idx for idx, day in enumerate(nums)}

    if type(day) == str:
        return days[day]
    if type(day) == int:
        return nums[day]
    raise ValueError("Incorrect type for 'day' in day_of_week()'")


async def run_in_executor(self, fn, *args, **kwargs):
    completed, pending = await asyncio.wait([self.AD.loop.run_in_executor(self.AD.executor, functools.partial(fn, *args, **kwargs))])
    future = list(completed)[0]
    response = future.result()
    return response


def run_coroutine_threadsafe(self, coro):
    result = None
    if self.AD.loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, self.AD.loop)
        try:
            result = future.result(self.AD.internal_function_timeout)
        except asyncio.TimeoutError:
            if hasattr(self, "logger"):
                self.logger.warning("Coroutine (%s) took too long (%s seconds), cancelling the task...", coro, self.AD.internal_function_timeout)
            else:
                print("Coroutine ({}) took too long, cancelling the task...".format(coro))
            future.cancel()

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

def find_path(name):
    for path in [os.path.join(os.path.expanduser("~"), ".homeassistant"),
                 os.path.join(os.path.sep, "etc", "appdaemon")]:
        _file = os.path.join(path, name)
        if os.path.isfile(_file) or os.path.isdir(_file):
            return _file
    return None


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
                    self.logger.warning("Invalid value for %s: %s, using default(%s)", value, getattr(self, arg))
            if "float" in kwargs and kwargs["float"] is True:
                try:
                    value = float(value)
                    setattr(self, arg, value)
                except ValueError:
                    self.logger.warning("Invalid value for %s: %s, using default(%s)", arg, value, getattr(self, arg))
            else:
                setattr(self, arg, value)

def find_owner(filename):
    return pwd.getpwuid(os.stat(filename).st_uid).pw_name

def check_path(type, logger, inpath, pathtype="directory", permissions=None):
    #disable checks for windows platform
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
                    logger.warning("%s: %s exists, but is a file instead of a directory", type,
    directory)
                    fullpath = False
            else:
                owner = find_owner(directory)
                if "r" in perms and not os.access(directory, os.R_OK):
                    logger.warning("%s: %s exists, but is not readable, owner: %s", type, directory, owner)
                    fullpath = False
                if "w" in perms and not os.access(directory, os.W_OK):
                    logger.warning("%s: %s exists, but is not writeable, owner: %s", type, directory, owner)
                    fullpath = False
                if "x" in perms and not os.access(directory, os.X_OK):
                    logger.warning("%s: %s exists, but is not executable, owner: %s", type, directory, owner)
                    fullpath = False
        if fullpath is True:
            owner = find_owner(path)
            user = pwd.getpwuid(os.getuid()).pw_name
            if owner != user:
                logger.warning("%s: %s is owned by %s but appdaemon is running as %s", type, path, owner, user)

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
