import copy
import string
import paho.mqtt.client as mqtt
import asyncio
import traceback
import json

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
        self.state = {}

        self.AD.log("INFO", "{}: MQTT Plugin Initializing".format(self.name))

        self.name = name

        if 'namespace' in self.config:
            self.namespace = self.config['namespace']
        else:
            self.namespace = 'default'

        if 'verbose' in self.config:
            self.verbose = self.config['verbose']
        else:
            self.verbose = False

        self.mqtt_client_host = self.config.get('client_host', '127.0.0.1')
        self.mqtt_client_port = self.config.get('client_port', 1883)
        self.mqtt_qos = self.config.get('client_qos', 0)
        mqtt_client_id = self.config.get('client_id', None)
        mqtt_transport = self.config.get('client_transport', 'tcp')
        mqtt_session = self.config.get('client_clean_session', True)
        self.mqtt_client_topics = self.config.get('client_topics', ['#'])
        self.mqtt_client_user = self.config.get('client_user', None)
        self.mqtt_client_password = self.config.get('client_password', None)
        self.mqtt_event_name = self.config.get('event_name', 'MQTT_MESSAGE')

        status_topic = '{} status'.format(self.config.get('client_id', self.name + ' client').lower())
        
        self.mqtt_will_topic = self.config.get('will_topic', None)
        self.mqtt_on_connect_topic = self.config.get('birth_topic', None)

        if self.mqtt_will_topic == None:
            self.mqtt_will_topic = status_topic
            self.AD.log("INFO", "{}: Using {!r} as Will Topic".format(self.name, status_topic))
        
        if self.mqtt_on_connect_topic == None:
            self.mqtt_on_connect_topic = status_topic
            self.AD.log("INFO", "{}: Using {!r} as Birth Topic".format(self.name, status_topic))

        self.mqtt_will_payload = self.config.get('will_payload', 'offline')
        self.mqtt_on_connect_payload = self.config.get('birth_payload', 'online')

        self.mqtt_client_tls_ca_cert = self.config.get('ca_cert', None)
        self.mqtt_client_tls_client_cert = self.config.get('client_cert', None)
        self.mqtt_client_tls_client_key = self.config.get('client_key', None)
        self.mqtt_verify_cert = self.config.get('verify_cert', True)

        self.mqtt_client_timeout = self.config.get('client_timeout', 60)

        if mqtt_client_id == None:
            mqtt_client_id = 'appdaemon_{}_client'.format(self.name.lower())
            self.AD.log("INFO", "{}: Using {!r} as Client ID".format(self.name, mqtt_client_id))

        self.mqtt_client = mqtt.Client(client_id=mqtt_client_id, clean_session=mqtt_session, transport= mqtt_transport)
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_disconnect = self.mqtt_on_disconnect
        self.mqtt_client.on_message = self.mqtt_on_message

        self.loop = self.AD.loop # get AD loop
        self.mqtt_connect_event = asyncio.Event(loop = self.loop)
        self.mqtt_metadata = {
            "version": "1.0",
            "host" : self.mqtt_client_host,
            "port" : self.mqtt_client_port,
            "client_id" : mqtt_client_id,
            "transport" : mqtt_transport,
            "clean_session": mqtt_session,
            "qos" : self.mqtt_qos,
            "topics" : self.mqtt_client_topics,
            "username" : self.mqtt_client_user,
            "password" : self.mqtt_client_password,
            "event_name" : self.mqtt_event_name,
            "status_topic" : status_topic,
            "will_topic" : self.mqtt_will_topic,
            "will_payload" : self.mqtt_will_payload,
            "birth_topic" : self.mqtt_on_connect_topic,
            "birth_payload" : self.mqtt_on_connect_payload,
            "ca_cert" : self.mqtt_client_tls_ca_cert,
            "client_cert" : self.mqtt_client_tls_client_cert,
            "client_key" : self.mqtt_client_tls_client_key,
            "verify_cert" : self.mqtt_verify_cert,
            "timeout" : self.mqtt_client_timeout
                            }

    def stop(self):
        self.stopping = True
        if self.initialized:
            self.AD.log("INFO", "{}: Stoping MQTT Plugin and Unsubcribing from URL {}:{}".format(self.name, self.mqtt_client_host, self.mqtt_client_port))
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
            self.mqtt_client.publish(self.mqtt_on_connect_topic, self.mqtt_on_connect_payload, self.mqtt_qos)
                
            self.AD.log("INFO", "{}: Connected to Broker at URL {}:{}".format(self.name, self.mqtt_client_host, self.mqtt_client_port))
            for topic in self.mqtt_client_topics:
                self.log("{}: Subscribing to Topic: {}".format(self.name, topic))
                result = self.mqtt_client.subscribe(topic, self.mqtt_qos)
                if result[0] == 0:
                    self.log("{}: Subscription to Topic {} Sucessful".format(self.name, topic))
                else:
                    if topic == self.mqtt_metadata['plugin_topic']:
                        self.AD.log("CRITICAL", 
                                "{}: Subscription to Plugin Internal Topic Unsucessful. Please check Broker and Restart AD".format(self.name))
                    else:
                        self.log("{}: Subscription to Topic {} Unsucessful, as Client not currently connected".format(self.name, topic))

            self.initialized = True

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

        self.mqtt_connect_event.set() # continue processing

    def mqtt_on_disconnect(self,  client, userdata, rc):
        if rc != 0 and not self.stopping: #unexpected disconnection
            self.initialized = False
            self.AD.log("CRITICAL", "{}: MQTT Client Disconnected Abruptly. Will attempt reconnection".format(self.name))
        return

    def mqtt_on_message(self, client, userdata, msg):
        self.log("{}: Message Received: Topic = {}, Payload = {}".format(self.name, msg.topic, msg.payload), level='INFO')

        data = {'event_type': self.mqtt_event_name, 'data': {'topic': msg.topic, 'payload': msg.payload.decode()}}
        self.loop.create_task(self.send_ad_event(data))

    def mqtt_service(self, service, **kwargs):
        if not self.initialized:
            self.AD.log("WARNING", "{}: Attempt to call Mqtt Service while disconnected: {!r}".format(self.name, service))
            return None
        
        topic = kwargs['topic']
        payload = kwargs.get('payload', None)
        retain = kwargs.get('retain', False)
        qos = int(kwargs.get('qos', self.mqtt_qos))

        if service == 'publish':
            self.AD.log("DEBUG", 
                "{}: Publish Payload: {} to Topic: {}".format(self.name, payload, topic))

            result = self.mqtt_client.publish(topic, payload, qos, retain)

            if result[0] == 0:
                self.log("{}: Publishing Payload {} to Topic {} Successful".format(self.name, payload, topic))

        elif service == 'subscribe':
            self.AD.log("DEBUG", 
                "{}: Subscribe to Topic: {}".format(self.name, topic))

            result = self.mqtt_client.subscribe(topic, qos)

            if result[0] == 0:
                self.log("{}: Subscription to Topic {} Sucessful".format(self.name, topic))
                if topic not in self.mqtt_client_topics:
                    self.mqtt_client_topics.append(topic)

        elif service == 'unsubscribe':
            self.AD.log("DEBUG", 
                "{}: Unsubscribe from Topic: {}".format(self.name, topic))

            result = self.mqtt_client.unsubscribe(topic)
            if result[0] == 0:
                self.log("{}: Unsubscription from Topic {} Successful".format(self.name, topic))
                if topic in self.mqtt_client_topics:
                    self.mqtt_client_topics.remove(topic)
        
        else:
            self.error("{}: Wrong Service Call {} for MQTT".format(self.name, service))
            result = 'ERR'

        return result
    
    async def send_ad_event(self, data):
        await self.AD.state_update(self.namespace, data)

    #
    # Get initial state
    #

    async def get_complete_state(self):
        entity_id = '{}.none'.format(self.name.lower())
        self.state[entity_id] = {'state': 'None', 'attributes' : {}}
        self.log("{}: *** Sending Complete State: {} ***".format(self.name, self.state))
        return copy.deepcopy(self.state)

    async def get_metadata(self):
        return self.mqtt_metadata

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
        already_initialized = False
        already_notified = False
        first_time = True
        first_time_service = True

        while not self.stopping: 
            while not self.initialized or not already_initialized: #continue until initialization is successful
                if not already_initialized and not already_notified: #if it had connected before, it need not run this. Run if just trying for the first time 
                    try:
                        await asyncio.wait_for(utils.run_in_executor(self.AD.loop, self.AD.executor, self.start_mqtt_service, first_time_service), 5.0, loop=self.loop)
                        await asyncio.wait_for(self.mqtt_connect_event.wait(), 5.0, loop=self.loop) # wait for it to return true for 5 seconds in case still processing connect
                    except asyncio.TimeoutError:
                        self.AD.log(
                            "CRITICAL", 
                                "{}: Could not Complete Connection to Broker, please Ensure Broker at URL {}:{} is correct or broker not down and restart Appdaemon".format(self.name, self.mqtt_client_host, self.mqtt_client_port))
                        self.mqtt_client.loop_stop()
                        self.mqtt_client.disconnect() #disconnect so it won't attempt reconnection if the broker was to come up

                    first_time_service = False

                if self.initialized : #meaning the plugin started as expected
                    await self.AD.notify_plugin_started(self.namespace, first_time)
                    already_notified = False
                    already_initialized = True
                    self.AD.log("INFO", "{}: MQTT Plugin initialization complete".format(self.name))
                else:
                    if not already_notified and already_initialized:
                        self.AD.notify_plugin_stopped(self.namespace)
                        self.AD.log("CRITICAL", "{}: MQTT Plugin Stopped Unexpectedly".format(self.name))
                        already_notified = True
                        already_initialized = False
                        first_time = False
                    if not already_initialized and not already_notified:
                        self.AD.log("CRITICAL", "{}: Could not complete MQTT Plugin initialization, trying again in 5 seconds".format(self.name))
                    else:
                        self.AD.log("CRITICAL", "{}: Unable to reinitialize MQTT Plugin, will keep trying again until complete".format(self.name))
                    await asyncio.sleep(5)
            await asyncio.sleep(5)

    def get_namespace(self):
        return self.namespace

    def start_mqtt_service(self, first_time):
        try:
            self.mqtt_connect_event.clear() # used to wait for connection
            if first_time:
                if self.mqtt_client_user != None:
                    self.mqtt_client.username_pw_set(self.mqtt_client_user, password=self.mqtt_client_password)

                if self.mqtt_client_tls_ca_cert != None:
                    self.mqtt_client.tls_set(self.mqtt_client_tls_ca_cert, certfile=self.mqtt_client_tls_client_cert,
                                            keyfile=self.mqtt_client_tls_client_key)

                if not self.mqtt_verify_cert:
                    self.mqtt_client.tls_insecure_set(not self.mqtt_verify_cert)

                self.mqtt_client.will_set(self.mqtt_will_topic, self.mqtt_will_payload, self.mqtt_qos)

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
