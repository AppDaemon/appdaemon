import appdaemon.conf as conf
import requests
import datetime
import re
import random
import uuid
import asyncio

from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

constraints = (
    "constrain_input_select", "constrain_presence",
    "constrain_start_time", "constrain_end_time"
)


__version__ = "2.5.0b1"


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


def _secret_yaml(loader, node):
    if conf.secrets is None:
        raise ValueError("!secret used but no secrets file found")

    if node.value not in conf.secrets:
        raise ValueError("{} not found in secrets file".format(node.value))

    return conf.secrets[node.value]


@asyncio.coroutine
def dispatch_app_by_name(name, args):
    with conf.endpoints_lock:
        callback = None
        for app in conf.endpoints:
            for handle in conf.endpoints[app]:
                if conf.endpoints[app][handle]["name"] == name:
                    callback = conf.endpoints[app][handle]["callback"]
    if callback is not None:
        return run_in_executor(conf.loop, conf.executor, callback, args)
    else:
        return '', 404


def sanitize_state_kwargs(kwargs):
    kwargs_copy = kwargs.copy()
    return _sanitize_kwargs(kwargs_copy, (
        "old", "new", "attribute", "duration", "state",
        "entity", "handle", "old_state", "new_state",
    ) + constraints)


def sanitize_timer_kwargs(kwargs):
    kwargs_copy = kwargs.copy()
    return _sanitize_kwargs(kwargs_copy, (
        "interval", "constrain_days", "constrain_input_boolean",
    ) + constraints)


def _sanitize_kwargs(kwargs, keys):
    for key in keys:
        if key in kwargs:
            del kwargs[key]
    return kwargs


def log(logger, level, msg, name=""):
    levels = {
        "CRITICAL": 50,
        "ERROR": 40,
        "WARNING": 30,
        "INFO": 20,
        "DEBUG": 10,
        "NOTSET": 0
    }
    if name != "":
        name = " {}:".format(name)

    # if conf.realtime:
    timestamp = datetime.datetime.now()
    # else:
    #    timestamp = get_now()
    # TODO: fix timestamps for timetravel
    logger.log(levels[level], "{} {}{} {}".format(timestamp, level, name, msg))


def day_of_week(day):
    nums = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    days = {day: idx for idx, day in enumerate(nums)}

    if type(day) == str:
        return days[day]
    if type(day) == int:
        return nums[day]
    raise ValueError("Incorrect type for 'day' in day_of_week()'")


def anyone_home():
    with conf.ha_state_lock:
        for entity_id in conf.ha_state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if conf.ha_state[entity_id]["state"] == "home":
                    return True
    return False


def everyone_home():
    with conf.ha_state_lock:
        for entity_id in conf.ha_state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if conf.ha_state[entity_id]["state"] != "home":
                    return False
    return True


def noone_home():
    with conf.ha_state_lock:
        for entity_id in conf.ha_state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if conf.ha_state[entity_id]["state"] == "home":
                    return False
    return True


def get_ha_state(entity_id=None):
    if conf.ha_key != "":
        headers = {'x-ha-access': conf.ha_key}
    else:
        headers = {}
    if entity_id is None:
        apiurl = "{}/api/states".format(conf.ha_url)
    else:
        apiurl = "{}/api/states/{}".format(conf.ha_url, entity_id)
    log(conf.logger, "DEBUG", "get_ha_state: url is {}".format(apiurl))
    r = requests.get(apiurl, headers=headers, verify=conf.certpath)
    r.raise_for_status()
    return r.json()


def get_ha_config():
    log(conf.logger, "DEBUG", "get_ha_config()")
    if conf.ha_key != "":
        headers = {'x-ha-access': conf.ha_key}
    else:
        headers = {}
    apiurl = "{}/api/config".format(conf.ha_url)
    log(conf.logger, "DEBUG", "get_ha_config: url is {}".format(apiurl))
    r = requests.get(apiurl, headers=headers, verify=conf.certpath)
    r.raise_for_status()
    return r.json()


def _check_service(service):
    if service.find("/") == -1:
        raise ValueError("Invalid Service Name: {}".format(service))


def call_service(service, **kwargs):
    _check_service(service)
    d, s = service.split("/")
    log(
        conf.logger, "DEBUG",
        "call_service: {}/{}, {}".format(d, s, kwargs)
    )
    if conf.ha_key != "":
        headers = {'x-ha-access': conf.ha_key}
    else:
        headers = {}
    apiurl = "{}/api/services/{}/{}".format(conf.ha_url, d, s)
    r = requests.post(
        apiurl, headers=headers, json=kwargs, verify=conf.certpath
    )
    r.raise_for_status()
    return r.json()


@asyncio.coroutine
def run_in_executor(loop, executor, fn, *args, **kwargs):
    completed, pending = yield from asyncio.wait([loop.run_in_executor(executor, fn, *args, **kwargs)])
    response = list(completed)[0].result()
    return response
