import requests
import inspect

import appdaemon.adbase as appapi
import appdaemon.utils as utils


from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

#
# Define an entities class as a descriptor to enable read only access of HASS state
#

def hass_check(func):
    def func_wrapper(*args, **kwargs):
        self = args[0]
        if not self.AD.get_plugin(self._get_namespace(**kwargs)).reading_messages:
            self.AD.log("WARNING", "Attempt to call Home Assistant while disconnected: {}".format(func))
            return lambda *args: None
        else:
            return func(*args, **kwargs)

    return (func_wrapper)


class Hass(appapi.ADBase):
    #
    # Internal
    #

    def __init__(self, ad, name, logger, error, args, config, app_config, global_vars):

        # Call Super Class
        super(Hass, self).__init__(ad, name, logger, error, args, config, app_config, global_vars)

        #
        # Register specific constraints
        #
        self.register_constraint("constrain_presence")
        self.register_constraint("constrain_input_boolean")
        self.register_constraint("constrain_input_select")
        self.register_constraint("constrain_days")

    #
    # State
    #

    def set_state(self, entity_id, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        new_state = super(Hass, self).parse_state(entity_id, namespace, **kwargs)

        config = self.AD.get_plugin(namespace).config
        if "cert_path" in config:
            cert_path = config["cert_path"]
        else:
            cert_path = False

        if "token" in config:
            headers = {'Authorization': "Bearer {}".format(config["token"])}
        elif "ha_key"  in config:
            headers = {'x-ha-access': config["ha_key"]}
        else:
            headers = {}

        apiurl = "{}/api/states/{}".format(config["ha_url"], entity_id)

        r = requests.post(
            apiurl, headers=headers, json=new_state, verify=cert_path
        )
        r.raise_for_status()
        state = r.json()

        # Update AppDaemon's copy

        self.AD.set_state(namespace, entity_id, state)

        return state

    #
    # Device Trackers
    #

    def get_trackers(self, **kwargs):
        return (key for key, value in self.get_state("device_tracker", **kwargs).items())

    def get_tracker_details(self, **kwargs):
        return self.get_state("device_tracker", **kwargs)

    def get_tracker_state(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(**kwargs), entity_id)
        return self.get_state(entity_id, **kwargs)

    def anyone_home(self, **kwargs):
        state = self.get_state(**kwargs)
        for entity_id in state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if state[entity_id]["state"] == "home":
                    return True
        return False

    def everyone_home(self, **kwargs):
        state = self.get_state(**kwargs)
        for entity_id in state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if state[entity_id]["state"] != "home":
                    return False
        return True

    def noone_home(self, **kwargs):
        state = self.get_state(**kwargs)
        for entity_id in state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if state[entity_id]["state"] == "home":
                    return False
        return True

    #
    # Built in constraints
    #

    def constrain_presence(self, value):
        unconstrained = True
        if value == "everyone" and not self.everyone_home():
            unconstrained = False
        elif value == "anyone" and not self.anyone_home():
            unconstrained = False
        elif value == "noone" and not self.noone_home():
            unconstrained = False

        return unconstrained

    def constrain_input_boolean(self, value):
        unconstrained = True
        state = self.get_state()

        values = value.split(",")
        if len(values) == 2:
            entity = values[0]
            desired_state = values[1]
        else:
            entity = value
            desired_state = "on"
        if entity in state and state[entity]["state"] != desired_state:
            unconstrained = False

        return unconstrained

    def constrain_input_select(self, value):
        unconstrained = True
        state = self.get_state()

        values = value.split(",")
        entity = values.pop(0)
        if entity in state and state[entity]["state"] not in values:
            unconstrained = False

        return unconstrained

    def constrain_days(self, value):
        day = self.get_now().weekday()
        daylist = [utils.day_of_week(day) for day in value.split(",")]
        if day in daylist:
            return True
        return False

    #
    # Helper functions for services
    #

    @hass_check
    def turn_on(self, entity_id, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
            
        self._check_entity(namespace, entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
            
        rargs["namespace"] = namespace
        self.call_service("homeassistant/turn_on", **rargs)

    @hass_check
    def turn_off(self, entity_id, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
            
        self._check_entity(namespace, entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id

        rargs["namespace"] = namespace
        device, entity = self.split_entity(entity_id)
        if device == "scene":
            self.call_service("homeassistant/turn_on", **rargs)
        else:
            self.call_service("homeassistant/turn_off", **rargs)

    @hass_check
    def toggle(self, entity_id, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
            
        self._check_entity(namespace, entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
            
        rargs["namespace"] = namespace
        self.call_service("homeassistant/toggle", **rargs)

    @hass_check
    def set_value(self, entity_id, value, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
            
        self._check_entity(namespace, entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id, "value": value}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
            rargs["value"] = value
        rargs["namespace"] = namespace
        self.call_service("input_number/set_value", **rargs)

    @hass_check
    def set_textvalue(self, entity_id, value, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
            
        self._check_entity(namespace, entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id, "value": value}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
            rargs["value"] = value
            
        rargs["namespace"] = namespace
        self.call_service("input_text/set_value", **rargs)

    @hass_check
    def select_option(self, entity_id, option, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
            
        self._check_entity(namespace, entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id, "option": option}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
            rargs["option"] = option
            
        rargs["namespace"] = namespace
        self.call_service("input_select/select_option", **rargs)

    @hass_check
    def notify(self, message, **kwargs):
        kwargs["message"] = message
        if "name" in kwargs:
            service = "notify/{}".format(kwargs["name"])
            del kwargs["name"]
        else:
            service = "notify/notify"

        self.call_service(service, **kwargs)

    @hass_check
    def persistent_notification(self, message, title=None, id=None):
        kwargs = {}
        kwargs["message"] = message
        if title is not None:
            kwargs["title"] = title
        if id is not None:
            kwargs["notification_id"] = id
        self.call_service("persistent_notification/create", **kwargs)

    #
    # Event
    #

    @hass_check
    def fire_event(self, event, **kwargs):
        self.AD.log("DEBUG",
                  "fire_event: {}, {}".format(event, kwargs))
        
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
            
        config = self.AD.get_plugin(namespace).config        
        if "cert_path" in config:
            cert_path = config["cert_path"]
        else:
            cert_path = False

        if "token" in config:
            headers = {'Authorization': "Bearer {}".format(config["token"])}
        elif "ha_key"  in config:
            headers = {'x-ha-access': config["ha_key"]}
        else:
            headers = {}


        apiurl = "{}/api/events/{}".format(config["ha_url"], event)
        r = requests.post(
            apiurl, headers=headers, json=kwargs, verify=cert_path
        )
        r.raise_for_status()
        return r.json()

    #
    # Service
    #
    @staticmethod
    def _check_service(service):
        if service.find("/") == -1:
            raise ValueError("Invalid Service Name: {}".format(service))

    @hass_check
    def call_service(self, service, **kwargs):
        self._check_service(service)
        d, s = service.split("/")
        self.AD.log(
            "DEBUG",
            "call_service: {}/{}, {}".format(d, s, kwargs)
        )
        
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        config = self.AD.get_plugin(namespace).config
        if "cert_path" in config:
            cert_path = config["cert_path"]
        else:
            cert_path = False

        if "token" in config:
            headers = {'Authorization': "Bearer {}".format(config["token"])}
        elif "ha_key"  in config:
            headers = {'x-ha-access': config["ha_key"]}
        else:
            headers = {}

        apiurl = "{}/api/services/{}/{}".format(config["ha_url"], d, s)
        r = requests.post(
            apiurl, headers=headers, json=kwargs, verify=cert_path
        )
        r.raise_for_status()
        return r.json()
