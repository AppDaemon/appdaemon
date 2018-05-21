import appdaemon.appapi as appapi
import appdaemon.utils as utils
import asyncio
import inspect
import traceback
import paho.mqtt.publish as publish


class Entities:

    def __get__(self, instance, owner):
        state = utils.StateAttrs(instance.ad.get_state(instance.namespace, None, None, None))
        return state


class Mqtt(appapi.AppDaemon):

    entities = Entities()

    def __init__(self, ad, name, logger, error, args, config, app_config, global_vars,):

        super(Mqtt, self).__init__(ad, name, logger, error, args, config, app_config, global_vars)

        self.namespace = "mqtt"
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
        return super(Mqtt, self).listen_event(self.namespace, cb, event, **kwargs)

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

        if "attributes" in kwargs:
            new_state["attributes"].update(kwargs["attributes"])

        # Update AppDaemon's copy

        self.AD.set_app_state(namespace, entity_id, new_state)

        return new_state

    #
    # Utility
    #

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
        
    #
    # Publishing
    #
    
    def mqtt_send(self, topic, payload, qos = 0, retain = False, **kwargs):
        if 'retain' in kwargs:
            retain = kwargs['retain']
        if 'qos' in kwargs:
            qos = int(kwargs['qos'])
            
        config = self.AD.get_plugin(self._get_namespace(**kwargs)).config
        try:
            mqtt_client_host = config.get('mqtt_client_host', '127.0.0.1')
            mqtt_client_port = config.get('mqtt_client_port', 1883)
            mqtt_client_user = config.get('mqtt_client_user', None)
            mqtt_client_password = config.get('mqtt_client_password', None)
            mqtt_client_tls_insecure = config.get('mqtt_verify_cert', False)

            mqtt_client_tls_ca_certs = config.get('mqtt_ca_certs', None)
            mqtt_client_tls_client_cert = config.get('mqtt_client_cert', None)
            mqtt_client_tls_client_key = config.get('mqtt_client_key', None)

            mqtt_client_timeout = config.get('mqtt_client_timeout', 60)

            if mqtt_client_tls_ca_certs != None and mqtt_client_tls_insecure != False:
                mqtt_client_tls = {'ca_certs':mqtt_client_tls_ca_certs, 'certfile':mqtt_client_tls_client_cert, 'keyfile':mqtt_client_tls_client_key}
            else:
                mqtt_client_tls = None
            
            if mqtt_client_user != None:
                auth = {'username':mqtt_client_user, 'password':mqtt_client_password}
            else:
                auth = None
        except Exception as e:
            self.AD.log('CRITICAL', 'Got the following Error {}, when trying to retrieve Mqtt Server Values'.format(e))
            self.error('Got error with the following {}'.format(e))
            return str(e)
            
        result = publish.single(topic, payload = payload, qos = qos, hostname = mqtt_client_host, port = mqtt_client_port, auth = auth, 
                        tls = mqtt_client_tls, retain = retain, keepalive = mqtt_client_timeout)
        return result
    
