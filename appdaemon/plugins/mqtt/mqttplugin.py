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
        self.initialized = False

        self.AD.log("INFO", "MQTT Plugin Initializing")

        self.name = name

        if 'namespace' in self.config:
            self.namespace = self.config['namespace']
        else:
            self.namespace = 'mqtt'

        if 'verbose' in self.config:
            self.verbose = self.config['verbose']
        else:
            self.verbose = False

        self.mqtt_client_host = self.config.get('mqtt_client_host', '127.0.0.1')
        self.mqtt_client_port = self.config.get('mqtt_client_port', 1883)
        self.mqtt_client_topics = self.config.get('mqtt_client_topics', ['#'])
        self.mqtt_client_user = self.config.get('mqtt_client_user', None)
        self.mqtt_client_password = self.config.get('mqtt_client_password', None)

        self.mqtt_client_tls_ca_certs = self.config.get('mqtt_ca_certs', None)
        self.mqtt_client_tls_client_cert = self.config.get('mqtt_client_cert', None)
        self.mqtt_client_tls_client_key = self.config.get('mqtt_client_key', None)
        self.mqtt_client_tls_insecure = self.config.get('mqtt_verify_cert', None)

        self.mqtt_client_timeout = self.config.get('mqtt_client_timeout', 60)

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_message = self.mqtt_on_message
        
        if self.mqtt_client_user != None:
            self.mqtt_client.username_pw_set(self.mqtt_client_user,
                                         password=self.mqtt_client_password)

        if self.mqtt_client_tls_ca_certs != None:
            self.mqtt_client.tls_set(self.mqtt_client_tls_ca_certs,
                                     certfile=self.mqtt_client_tls_client_cert,
                                     keyfile=self.mqtt_client_tls_client_key)
        if self.mqtt_client_tls_insecure != None:
            self.mqtt_client.tls_insecure_set(not self.mqtt_client_tls_insecure)

        self.mqtt_client.connect_async(self.mqtt_client_host, self.mqtt_client_port,
                                       self.mqtt_client_timeout)
        self.mqtt_client.loop_start()
        self.loop = self.AD.loop # get AD loop

    def stop(self):
        self.log("Stoping MQTT and Unsubcribing from URL {}:{}".format(self.mqtt_client_host, self.mqtt_client_port))
        for topic in self.mqtt_client_topics:
            self.log("Unsubscribing from Topic: {}".format(topic))
            result = self.mqtt_client.unsubscribe(topic)
            if result[0] == 'MQTT_ERR_SUCCESS':
                self.log("Unsubscription from Topic {} Sucessful".format(topic))
        self.mqtt_client.loop_stop()
        self.stopping = True

    def log(self, text, **kwargs):
        level = kwargs.get('level', 'INFO')
        if self.verbose:
            self.AD.log(level, "{}: {}".format(self.name, text))

    def mqtt_on_connect(self, client, userdata, flags, rc):
        err_msg = ""
        if int(rc) == 0: #means connection was successful
            self.AD.log("INFO", "Connected to Broker at URL {}:{}".format(self.mqtt_client_host, self.mqtt_client_port))
            for topic in self.mqtt_client_topics:
                self.log("Subscribing to Topic: {}".format(topic))
                result = self.mqtt_client.subscribe(topic)
                if result[0] == 0:
                    self.log("Subscription to Topic {} Sucessful".format(topic))
                else:
                    self.log("Subscription to Topic {} Unsucessful, as Client not currently connected".format(topic))
            self.initialized = True
            self.AD.log("INFO", "MQTT Plugin initialization complete")
        elif int(rc) == 1:
            err_msg = "Connection was refused due to Incorrect Protocol Version"
        elif int(rc) == 2:
            err_msg = "Connection was refused due to Invalid Client Identifier"
        elif int(rc) == 3:
            err_msg = "Connection was refused due to Server Unavailable"
        elif int(rc) == 4:
            err_msg = "Connection was refused due to Bad Username or Password"
        elif int(rc) == 5:
            err_msg = "Connection was refused due to Not Authorised"
        else:
            err_msg = "Connection was refused. Please check configuration settings"
        
        if err_msg != "": #means there was an error
            self.AD.log("CRITICAL", "Could not complete MQTT Plugin initialization, for {}".format(err_msg))

    def mqtt_on_message(self, client, userdata, msg):
        self.log("Message Received: Topic = {}, Payload = {}".format(msg.topic, msg.payload), level='INFO')
        data = {'event_type': 'MQTT_MESSAGE', 'data': {'topic': msg.topic, 'payload': ''.join( chr(x) for x in msg.payload)}}
        self.loop.create_task(self.send_ad_event(data))
              
    async def send_ad_event(self, data):
        await self.AD.state_update(self.namespace, data)

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
        await self.AD.notify_plugin_started(self.namespace, self.initialized)

    def get_namespace(self):
        return self.namespace