import yaml
import asyncio
import copy
import string
import paho.mqtt.client as mqtt

import appdaemon.utils as utils

class MqttPlugin:

    def __init__(self, ad, name, logger, error, loglevel, args):
        """Initialize MQTT Plugin."""
        self.AD = ad
        self.logger = logger
        self.error = error
        self.stopping = False
        self.loglevel = loglevel
        self.config = args
        self.name = name
        self.state = None

        self.AD.log("INFO", "MQTT Plugin Initializing")

        self.name = name

        if 'namespace' in args:
            self.namespace = args['namespace']
        else:
            self.namespace = 'mqtt'

        if 'verbose' in args:
            self.verbose = args['verbose']
        else:
            self.verbose = False

        self.mqtt_client_host = args.get('mqtt_client_host', '127.0.0.1')
        self.mqtt_client_port = args.get('mqtt_client_port', 1883)
        self.mqtt_client_topics = args.get('mqtt_client_topics', ['#'])
        self.mqtt_client_user = args.get('mqtt_client_user')
        self.mqtt_client_password = args.get('mqtt_client_password')

        self.mqtt_client_tls_ca_certs = args.get('mqtt_ca_certs')
        self.mqtt_client_tls_client_cert = args.get('mqtt_client_cert')
        self.mqtt_client_tls_client_key = args.get('mqtt_client_key')

        self.mqtt_client_timeout = args.get('mqtt_client_timeout', 60)

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_message = self.mqtt_on_message
        self.mqtt_client.username_pw_set(self.mqtt_client_user,
                                         password=self.mqtt_client_password)

        if self.mqtt_client_tls_client_cert or self.mqtt_client_tls_ca_certs:
            self.mqtt_client.tls_set(self.mqtt_client_tls_ca_certs,
                                     certfile=self.mqtt_client_tls_client_cert,
                                     keyfile=self.mqtt_client_tls_client_key)
        if 'mqtt_verify_cert' in args:
            self.mqtt_client.tls_insecure_set(not args['mqtt_verify_cert'])

        self.mqtt_client.connect_async(self.mqtt_client_host, self.mqtt_client_port,
                                       self.mqtt_client_timeout)
        self.mqtt_client.loop_start()
        self.loop = asyncio.get_event_loop()
        self.AD.log('INFO', "MQTT Plugin initialization complete")

    def stop(self):
        self.log("stop")
        self.mqtt_client.loop_stop()
        self.stopping = True

    def log(self, text, level='INFO'):
        if self.verbose:
            self.AD.log(level, "{}: {}".format(self.name, text))

    def mqtt_on_connect(self, client, userdata, flags, rc):
        self.log("on_connect: connected: {}".format(rc), level='INFO')
        for topic in self.mqtt_client_topics:
            self.log("on_connect: subscribed: {}".format(topic))
            self.mqtt_client.subscribe(topic, 0)

    def mqtt_on_message(self, client, userdata, msg):
        self.log("on_message: {} {}".format(msg.topic, msg.payload), level='INFO')
        asyncio.run_coroutine_threadsafe(self.AD.state_update(self.namespace,
             {'event_type': 'MQTT_MESSAGE', 'data': {'topic': msg.topic,
              'payload': ''.join( chr(x) for x in msg.payload)}}), self.loop)

    #
    # Get initial state
    #

    async def get_complete_state(self):
        self.log("get_complete_state: {} ***".format(self.state),
                 level='DEBUG')
        return copy.deepcopy(self.state)

    async def get_metadata(self):
        return {
            "version": "0.1"
        }

    #
    # Utility gets called every second (or longer if configured
    # Allows plugin to do any housekeeping required
    #

    def utility(self):
        #self.AD.log('INFO',"utility".format(self.state))
        return

    def active(self):
        return True

    #
    # Handle state updates
    #

    async def get_updates(self):
        await self.AD.notify_plugin_started(self.namespace, True)

    #
    # Set State
    #

    def set_state(self, entity, state):
        self.log("set_state: {} = {} ***".format(entity, state))

    def get_namespace(self):
        return self.namespace
