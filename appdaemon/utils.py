import appdaemon.conf as conf
import requests
import datetime
import re
import random
import uuid
import asyncio

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
            self.lfchar + self.htchar * (indent + 1) + (self.types[type(item) if type(item) in self.types else object])(self, item, indent + 1)
            for item in value
        ]
        return '[%s]' % (','.join(items) + self.lfchar + self.htchar * indent)

    def format_tuple(self, value, indent):
        items = [
            self.lfchar + self.htchar * (indent + 1) + (self.types[type(item) if type(item) in self.types else object])(self, item, indent + 1)
            for item in value
        ]
        return '(%s)' % (','.join(items) + self.lfchar + self.htchar * indent)


from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

constraints = (
    "constrain_input_select", "constrain_presence",
    "constrain_start_time", "constrain_end_time"
)


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

    if conf.realtime:
        timestamp = datetime.datetime.now()
    else:
        timestamp = get_now()

    logger.log(levels[level], "{} {}{} {}".format(timestamp, level, name, msg))


def get_now():
    return datetime.datetime.fromtimestamp(conf.now)


def get_now_ts():
    return conf.now

  
def day_of_week(day):
    nums = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    days = {day: idx for idx, day in enumerate(nums)}

    if type(day) == str:
        return days[day]
    if type(day) == int:
        return nums[day]
    raise ValueError("Incorrect type for 'day' in day_of_week()'")


def parse_time(time_str, name=None):
    time = None
    parts = re.search('^(\d+):(\d+):(\d+)', time_str)
    if parts:
        time = datetime.time(
            int(parts.group(1)), int(parts.group(2)), int(parts.group(3))
        )
    else:
        if time_str == "sunrise":
            time = sunrise().time()
        elif time_str == "sunset":
            time = sunset().time()
        else:
            parts = re.search(
                '^sunrise\s*([+-])\s*(\d+):(\d+):(\d+)', time_str
            )
            if parts:
                if parts.group(1) == "+":
                    time = (sunrise() + datetime.timedelta(
                        hours=int(parts.group(2)), minutes=int(parts.group(3)),
                        seconds=int(parts.group(4))
                    )).time()
                else:
                    time = (sunrise() - datetime.timedelta(
                        hours=int(parts.group(2)), minutes=int(parts.group(3)),
                        seconds=int(parts.group(4))
                    )).time()
            else:
                parts = re.search(
                    '^sunset\s*([+-])\s*(\d+):(\d+):(\d+)', time_str
                )
                if parts:
                    if parts.group(1) == "+":
                        time = (sunset() + datetime.timedelta(
                            hours=int(parts.group(2)),
                            minutes=int(parts.group(3)),
                            seconds=int(parts.group(4))
                        )).time()
                    else:
                        time = (sunset() - datetime.timedelta(
                            hours=int(parts.group(2)),
                            minutes=int(parts.group(3)),
                            seconds=int(parts.group(4))
                        )).time()
    if time is None:
        if name is not None:
            raise ValueError(
                "{}: invalid time string: {}".format(name, time_str))
        else:
            raise ValueError("invalid time string: {}".format(time_str))
    return time


def now_is_between(start_time_str, end_time_str, name=None):
    start_time = parse_time(start_time_str, name)
    end_time = parse_time(end_time_str, name)
    now = get_now()
    start_date = now.replace(
        hour=start_time.hour, minute=start_time.minute,
        second=start_time.second
    )
    end_date = now.replace(
        hour=end_time.hour, minute=end_time.minute, second=end_time.second
    )
    if end_date < start_date:
        # Spans midnight
        if now < start_date and now < end_date:
            now = now + datetime.timedelta(days=1)
        end_date = end_date + datetime.timedelta(days=1)
    return start_date <= now <= end_date


def sunrise():
    return datetime.datetime.fromtimestamp(calc_sun("next_rising"))


def sunset():
    return datetime.datetime.fromtimestamp(calc_sun("next_setting"))


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


def calc_sun(type_):
    # convert to a localized timestamp
    return conf.sun[type_].timestamp()


def parse_utc_string(s):
    return datetime.datetime(*map(
        int, re.split('[^\d]', s)[:-1]
    )).timestamp() + get_tz_offset() * 60


def get_tz_offset():
    utc_offset_min = int(round(
        (datetime.datetime.now()
         - datetime.datetime.utcnow()).total_seconds())
    ) / 60   # round for taking time twice
    utc_offset_h = utc_offset_min / 60

    # we do not handle 1/2 h timezone offsets
    assert utc_offset_min == utc_offset_h * 60
    return utc_offset_min


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


def get_offset(kwargs):
    if "offset" in kwargs["kwargs"]:
        if "random_start" in kwargs["kwargs"]\
                or "random_end" in kwargs["kwargs"]:
            raise ValueError(
                "Can't specify offset as well as 'random_start' or "
                "'random_end' in 'run_at_sunrise()' or 'run_at_sunset()'"
            )
        else:
            offset = kwargs["kwargs"]["offset"]
    else:
        rbefore = kwargs["kwargs"].get("random_start", 0)
        rafter = kwargs["kwargs"].get("random_end", 0)
        offset = random.randint(rbefore, rafter)
    # log(conf.logger, "INFO", "sun: offset = {}".format(offset))
    return offset


def insert_schedule(name, utc, callback, repeat, type_, **kwargs):
    with conf.schedule_lock:
        if name not in conf.schedule:
            conf.schedule[name] = {}
        handle = uuid.uuid4()
        utc = int(utc)
        c_offset = get_offset({"kwargs": kwargs})
        ts = utc + c_offset
        interval = kwargs.get("interval", 0)

        conf.schedule[name][handle] = {
            "name": name,
            "id": conf.objects[name]["id"],
            "callback": callback,
            "timestamp": ts,
            "interval": interval,
            "basetime": utc,
            "repeat": repeat,
            "offset": c_offset,
            "type": type_,
            "kwargs": kwargs
        }
        # log(conf.logger, "INFO", conf.schedule[name][handle])
    return handle


def cancel_timer(name, handle):
    log(conf.logger, "DEBUG", "Canceling timer for {}".format(name))
    with conf.schedule_lock:
        if name in conf.schedule and handle in conf.schedule[name]:
            del conf.schedule[name][handle]
        if name in conf.schedule and conf.schedule[name] == {}:
            del conf.schedule[name]


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
