import appdaemon.appapi as appapi
import appdaemon.utils as utils
import asyncio
import inspect
import traceback


class Entities:

    def __get__(self, instance, owner):
        state = utils.StateAttrs(instance.ad.get_state(instance.namespace, None, None, None))
        return state


class Mqtt(appapi.AppDaemon):

    entities = Entities()

    def __init__(self, ad, name, logger, error, args, config, app_config, global_vars,):

        super(Mqtt, self).__init__(ad, name, logger, error, args, config, app_config, global_vars)

        self.namespace = "default"
        self.AD = ad
        self.name = name
        self._logger = logger
        self._error = error
        self.args = args
        self.config = config
        self.app_config = app_config
        self.global_vars = global_vars
        self.loop = self.AD.loop
        
    def _sub_stack(self, msg):
        # If msg is a data structure of some type, don't sub
        if type(msg) is str:
            stack = inspect.stack()
            if msg.find("__module__") != -1:
                msg = msg.replace("__module__", stack[2][1])
            if msg.find("__line__") != -1:
                msg = msg.replace("__line__", str(stack[2][2]))
            if msg.find("__function__") != -1:
                msg = msg.replace("__function__", stack[2][3])
        return msg

    def set_namespace(self, namespace):
        self.namespace = namespace

    def _get_namespace(self, **kwargs):
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]
            del kwargs["namespace"]
        else:
            namespace = self.namespace

        return namespace

    #
    # Listen state stub here as super class doesn't know the namespace
    #

    def listen_state(self, cb, entity=None, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
        return super(Mqtt, self).listen_state(namespace, cb, entity, **kwargs)

    def listen_event(self, cb, event=None, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
        return super(Mqtt, self).listen_event(namespace, cb, event, **kwargs)

    #
    # Likewise with get and set state
    #

    def get_state(self, entity=None, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
        return super(Mqtt, self).get_state(namespace, entity, **kwargs)

    def set_app_state(self, entity_id, **kwargs):
        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]
        self._check_entity(namespace, entity_id)
        self.AD.log(
            "DEBUG",
            "set_app_state: {}, {}".format(entity_id, kwargs)
        )

        if entity_id in self.get_state(namespace = namespace):
            new_state = self.get_state(namespace = namespace)[entity_id]
        else:
            # Its a new state entry
            new_state = {}
            new_state["attributes"] = {}

        if "state" in kwargs:
            new_state["state"] = kwargs["state"]

        if "attributes" in kwargs and kwargs.get('replace', False):
            new_state["attributes"] = kwargs["attributes"]
        else:
            if "attributes" in kwargs:
                new_state["attributes"].update(kwargs["attributes"])



        # Update AppDaemon's copy

        self.AD.set_app_state(namespace, entity_id, new_state)

        return new_state

    #
    # Utility
    #
    def entity_exists(self, entity_id, **kwargs):
        namespace = self._get_namespace(**kwargs)
        return self.AD.entity_exists(namespace, entity_id)

    def split_entity(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(**kwargs), entity_id)
        return entity_id.split(".")
        
    def split_device_list(self, list_):
        return list_.split(",")

    def log(self, msg, level="INFO"):
        msg = self._sub_stack(msg)
        self.AD.log(level, msg, self.name)

    def error(self, msg, level="WARNING"):
        msg = self._sub_stack(msg)
        self.AD.err(level, msg, self.name)

    def get_plugin_config(self, **kwargs):
        namespace = self._get_namespace(**kwargs)
        return self.AD.get_plugin_meta(namespace)
        
    #
    # service calls
    #
    def mqtt_publish(self, topic, payload = None, **kwargs):
        kwargs['topic'] = topic
        kwargs['payload'] = payload
        service = 'publish'
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_subscribe(self, topic, **kwargs):
        kwargs['topic'] = topic
        service = 'subscribe'
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_unsubscribe(self, topic, **kwargs):
        kwargs['topic'] = topic
        service = 'unsubscribe'
        result = self.call_service(service, **kwargs)
        return result

    def call_service(self, service, **kwargs):
        self.AD.log(
            "DEBUG",
            "call_service: {}, {}".format(service, kwargs)
        )
        
        namespace = self._get_namespace(**kwargs)

        if 'topic' in kwargs:
            try:
                result = self.AD.get_plugin(namespace).mqtt_service(service, **kwargs)
                
            except Exception as e:
                config = self.AD.get_plugin(namespace).config
                if config['type'] == 'mqtt':
                    self.AD.log('DEBUG', 'Got the following Error {}, when trying to retrieve Mqtt Plugin'.format(e))
                    self.error('Got error with the following {}'.format(e))
                    return str(e)
                else:
                    self.AD.log('CRITICAL', 'Wrong Namespace {!r} selected for MQTT Service. Please use proper namespace before trying again'.format(namespace))
                    self.error('Could not execute Service Call, as wrong Namespace {!r} used'.format(namespace))
                    return 'ERR'
        else:
            self.AD.log('DEBUG', 'Topic not provided for Service Call {!r}.'.format(service))
            raise ValueError("Topic not provided, please provide Topic for Service Call")
            return 'ERR'

        return result
