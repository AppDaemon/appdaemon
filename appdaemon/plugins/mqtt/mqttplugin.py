import copy
import string
import paho.mqtt.client as mqtt
import asyncio
import traceback

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
        self.initialized = False

        self.AD.log("INFO", "{}: MQTT Plugin Initializing".format(self.name))

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
        mqtt_client_id = self.config.get('mqtt_client_id', '')
        self.mqtt_client_topics = self.config.get('mqtt_client_topics', ['#'])
        self.mqtt_client_user = self.config.get('mqtt_client_user', None)
        self.mqtt_client_password = self.config.get('mqtt_client_password', None)
        self.mqtt_event_name = self.config.get('mqtt_event_name', 'MQTT_MESSAGE')

        self.mqtt_client_tls_ca_certs = self.config.get('mqtt_ca_certs', None)
        self.mqtt_client_tls_client_cert = self.config.get('mqtt_client_cert', None)
        self.mqtt_client_tls_client_key = self.config.get('mqtt_client_key', None)
        self.mqtt_client_tls_insecure = self.config.get('mqtt_verify_cert', None)

        self.mqtt_client_timeout = self.config.get('mqtt_client_timeout', 60)

        self.mqtt_client = mqtt.Client(client_id=mqtt_client_id)
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_disconnect = self.mqtt_on_disconnect
        self.mqtt_client.on_message = self.mqtt_on_message

        self.loop = self.AD.loop # get AD loop
        self.mqtt_connect_event = asyncio.Event(loop = self.loop)

    def stop(self):
        self.stopping = True
        if self.initialized:
            self.log("{}: Stoping MQTT Plugin and Unsubcribing from URL {}:{}".format(self.name, self.mqtt_client_host, self.mqtt_client_port))
            for topic in self.mqtt_client_topics:
                self.log("{}: Unsubscribing from Topic: {}".format(self.name, topic))
                result = self.mqtt_client.unsubscribe(topic)
                if result[0] == 0:
                    self.log("{}: Unsubscription from Topic {} Successful".format(self.name, topic))
                    
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect() #disconnect cleanly

    def log(self, text, **kwargs):
        level = kwargs.get('level', 'INFO')
        if self.verbose:
            self.AD.log(level, "{}".format(text))

    def mqtt_on_connect(self, client, userdata, flags, rc):
        err_msg = ""
        if rc == 0: #means connection was successful
            self.AD.log("INFO", "{}: Connected to Broker at URL {}:{}".format(self.name, self.mqtt_client_host, self.mqtt_client_port))
            for topic in self.mqtt_client_topics:
                self.log("{}: Subscribing to Topic: {}".format(self.name, topic))
                result = self.mqtt_client.subscribe(topic)
                if result[0] == 0:
                    self.log("{}: Subscription to Topic {} Sucessful".format(self.name, topic))
                else:
                    self.log("{}: Subscription to Topic {} Unsucessful, as Client not currently connected".format(self.name, topic))
            self.initialized = True
            self.mqtt_connect_event.set() # continue processing

        elif rc == 1:
            err_msg = "Connection was refused due to Incorrect Protocol Version"
        elif rc == 2:
            err_msg = "Connection was refused due to Invalid Client Identifier"
        elif rc == 3:
            err_msg = "Connection was refused due to Server Unavailable"
        elif rc == 4:
            err_msg = "Connection was refused due to Bad Username or Password"
        elif rc == 5:
            err_msg = "Connection was refused due to Not Authorised"
        else:
            err_msg = "Connection was refused. Please check configuration settings"
        
        if err_msg != "": #means there was an error
            self.AD.log("CRITICAL", "{}: Could not complete MQTT Plugin initialization, for {}".format(self.name, err_msg))

    def mqtt_on_disconnect(self,  client, userdata, rc):
        if rc != 0 and not self.stopping: #unexpected disconnection
            self.initialized = False

    def mqtt_on_message(self, client, userdata, msg):
        self.log("{}: Message Received: Topic = {}, Payload = {}".format(self.name, msg.topic, msg.payload), level='INFO')
        data = {'event_type': self.mqtt_event_name, 'data': {'topic': msg.topic, 'payload': msg.payload.decode()}}
        self.loop.create_task(self.send_ad_event(data))
              
    async def send_ad_event(self, data):
        await self.AD.state_update(self.namespace, data)

    #
    # Get initial state
    #

    async def get_complete_state(self):
        states = {}
        entity_id = '{}.none'.format(self.name.lower())
        states[entity_id] = {'state': 'None', 'attributes' : {}}
        self.log("{}: *** Sending Complete State: {} ***".format(self.name, states))
        return states

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
        return self.initialized

    #
    # Handle state updates
    #

    async def get_updates(self):
        already_notified = False
        first_time = True

        while not self.stopping and not self.initialized: #continue until initialization is successful
            await asyncio.wait_for(utils.run_in_executor(self.AD.loop, self.AD.executor, self.start_mqtt_service), 5.0)

            await asyncio.wait_for(self.mqtt_connect_event.wait(), 2.0) # wait for it to return in case still processing connect 

            if self.initialized: #meaning the plugin started as expected
                await self.AD.notify_plugin_started(self.namespace, first_time)
                already_notified = False
                self.AD.log("INFO", "{}: MQTT Plugin initialization complete".format(self.name))
            else:
                if not already_notified:
                    self.AD.notify_plugin_stopped(self.namespace)
                    self.AD.log("CRITICAL", "{}: MQTT Plugin Stopped Unexpectedly".format(self.name))
                    already_notified = True
                    first_time = False

                self.AD.log("CRITICAL", "{}: Could not complete MQTT Plugin initialization, trying again in 5 seconds".format(self.name))
                await asyncio.sleep(5)

    def get_namespace(self):
        return self.namespace

    def start_mqtt_service(self):
        try:
            self.mqtt_connect_event.clear() # used to wait for connection
            if self.mqtt_client_user != None:
                self.mqtt_client.username_pw_set(self.mqtt_client_user, password=self.mqtt_client_password)

            if self.mqtt_client_tls_ca_certs != None:
                self.mqtt_client.tls_set(self.mqtt_client_tls_ca_certs, certfile=self.mqtt_client_tls_client_cert,
                                        keyfile=self.mqtt_client_tls_client_key)
            if self.mqtt_client_tls_insecure != None:
                self.mqtt_client.tls_insecure_set(not self.mqtt_client_tls_insecure)

            self.mqtt_client.connect_async(self.mqtt_client_host, self.mqtt_client_port,
                                        self.mqtt_client_timeout)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.AD.log("CRITICAL", "{}: There was an error while trying to setup the Mqtt Service. Error was: {}".format(self.name, e))
            self.AD.log("DEBUG", "{}: There was an error while trying to setup the MQTT Service. Error: {}, with Traceback: {}".format(self.name, e, traceback.format_exc()))
            self.log('{}: There was an error while trying to setup the MQTT Service, with Traceback: {}'.format(self.name, traceback.format_exc()), level = 'CRITICAL')
        except:
            self.AD.log("CRITICAL", "{}: There was an error while trying to setup the Mqtt Service".format(self.name))
            self.log('{}: There was an error while trying to setup the MQTT Service, with Traceback: {}'.format(self.name, traceback.format_exc()), level = 'CRITICAL')
        
        return
