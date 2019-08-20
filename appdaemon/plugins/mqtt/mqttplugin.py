import copy
import paho.mqtt.client as mqtt
import asyncio
import traceback
import ssl

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.plugin_management import PluginBase

class MqttPlugin(PluginBase):

    def __init__(self, ad: AppDaemon, name, args):
        super().__init__(ad, name, args)

        """Initialize MQTT Plugin."""
        self.AD = ad
        self.stopping = False
        self.config = args
        self.name = name
        self.initialized = False
        self.mqtt_connected = False
        self.state = {}

        self.logger.info("MQTT Plugin Initializing")

        self.name = name

        if 'namespace' in self.config:
            self.namespace = self.config['namespace']
        else:
            self.namespace = 'default'

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
        self.mqtt_client_force_start = self.config.get('force_start', False)

        status_topic = '{}/status'.format(self.config.get('client_id', self.name + '-client').lower())
        
        self.mqtt_will_topic = self.config.get('will_topic', None)
        self.mqtt_on_connect_topic = self.config.get('birth_topic', None)
        self.mqtt_will_retain = self.config.get('will_retain', True)
        self.mqtt_on_connect_retain = self.config.get('birth_retain', True)
        
        if self.mqtt_client_topics == "NONE":
            self.mqtt_client_topics = []

        if self.mqtt_will_topic == None:
            self.mqtt_will_topic = status_topic
            self.logger.info("Using %r as Will Topic", status_topic)
        
        if self.mqtt_on_connect_topic == None:
            self.mqtt_on_connect_topic = status_topic
            self.logger.info("Using %r as Birth Topic", status_topic)

        self.mqtt_will_payload = self.config.get('will_payload', 'offline')
        self.mqtt_on_connect_payload = self.config.get('birth_payload', 'online')
        self.mqtt_shutdown_payload = self.config.get('shutdown_payload', self.mqtt_will_payload)

        self.mqtt_client_tls_ca_cert = self.config.get('ca_cert', None)
        self.mqtt_client_tls_client_cert = self.config.get('client_cert', None)
        self.mqtt_client_tls_client_key = self.config.get('client_key', None)
        self.mqtt_verify_cert = self.config.get('verify_cert', True)
        self.mqtt_tls_version = self.config.get('tls_version', 'auto')

        if self.mqtt_tls_version == '1.2':
            self.mqtt_tls_version = ssl.PROTOCOL_TLSv1_2
        elif self.mqtt_tls_version == '1.1':
            self.mqtt_tls_version = ssl.PROTOCOL_TLSv1_1
        elif self.mqtt_tls_version == '1.0':
            self.mqtt_tls_version = ssl.PROTOCOL_TLSv1
        else:
            import sys
            if sys.hexversion >= 0x03060000:
                self.mqtt_tls_version = ssl.PROTOCOL_TLS
            else:
                self.mqtt_tls_version = ssl.PROTOCOL_TLSv1


        self.mqtt_client_timeout = self.config.get('client_timeout', 60)

        if mqtt_client_id == None:
            mqtt_client_id = 'appdaemon_{}_client'.format(self.name.lower())
            self.logger.info("Using %s as Client ID", mqtt_client_id)

        self.mqtt_client = mqtt.Client(client_id=mqtt_client_id, clean_session=mqtt_session, transport= mqtt_transport)
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_disconnect = self.mqtt_on_disconnect
        self.mqtt_client.on_message = self.mqtt_on_message

        self.loop = self.AD.loop # get AD loop
        self.mqtt_connect_event = asyncio.Event(loop = self.loop)
        self.mqtt_wildcards = list()
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
            "will_retain" : self.mqtt_will_retain,
            "birth_topic" : self.mqtt_on_connect_topic,
            "birth_payload" : self.mqtt_on_connect_payload,
            "birth_retain" : self.mqtt_on_connect_retain,
            "shutdown_payload" : self.mqtt_shutdown_payload,
            "ca_cert" : self.mqtt_client_tls_ca_cert,
            "client_cert" : self.mqtt_client_tls_client_cert,
            "client_key" : self.mqtt_client_tls_client_key,
            "verify_cert" : self.mqtt_verify_cert,
            "tls_version" : self.mqtt_tls_version,
            "timeout" : self.mqtt_client_timeout,
            "force_state" : self.mqtt_client_force_start
                            }

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True
        if self.mqtt_connected:
            self.logger.info("Stopping MQTT Plugin and Unsubcribing from URL %s:%s", self.mqtt_client_host, self.mqtt_client_port)
            for topic in self.mqtt_client_topics:
                self.logger.debug("Unsubscribing from Topic: %s", topic)
                result = self.mqtt_client.unsubscribe(topic)
                if result[0] == 0:
                    self.logger.debug("Unsubscription from Topic %s Successful", topic)
                    
            self.mqtt_client.publish(self.mqtt_will_topic, self.mqtt_shutdown_payload, self.mqtt_qos, retain=self.mqtt_will_retain)
            self.mqtt_client.disconnect() #disconnect cleanly
            
        self.mqtt_client.loop_stop()

    def mqtt_on_connect(self, client, userdata, flags, rc):
        try:
            err_msg = ""
            if rc == 0: #means connection was successful
                self.mqtt_client.publish(self.mqtt_on_connect_topic, self.mqtt_on_connect_payload, self.mqtt_qos, retain=self.mqtt_on_connect_retain)

                self.logger.info("Connected to Broker at URL %s:%s", self.mqtt_client_host, self.mqtt_client_port)
                #
                # Register MQTT Services
                #
                self.AD.services.register_service(self.namespace, "mqtt", "subscribe", self.call_plugin_service)
                self.AD.services.register_service(self.namespace, "mqtt", "unsubscribe", self.call_plugin_service)
                self.AD.services.register_service(self.namespace, "mqtt", "publish", self.call_plugin_service)

                for topic in self.mqtt_client_topics:
                    self.logger.debug("Subscribing to Topic: %s", topic)
                    result = self.mqtt_client.subscribe(topic, self.mqtt_qos)
                    if result[0] == 0:
                        self.logger.debug("Subscription to Topic %s Sucessful", topic)
                    else:
                        self.mqtt_client_topics.remove(topic)
                        self.logger.debug("Subscription to Topic %s Unsucessful, as Client possibly not currently connected", topic)

                self.mqtt_connected = True

                data = {'event_type': self.mqtt_event_name, 'data': {'state': 'Connected', 'topic' : None, 'wildcard' : None}}
                self.loop.create_task(self.send_ad_event(data))

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

            if err_msg != "": #means there was an err
                self.logger.critical("Could not complete MQTT Plugin initialization, for %s", err_msg)

            self.mqtt_connect_event.set() # continue processing
        except:
            self.logger.critical("There was an error while trying to setup the Mqtt Service")
            self.logger.debug('There was an error while trying to setup the MQTT Service, with Traceback: %s', traceback.format_exc())

    def mqtt_on_disconnect(self,  client, userdata, rc):
        try:
            if rc != 0 and not self.stopping: #unexpected disconnection
                self.initialized = False
                self.mqtt_connected = False
                self.logger.critical("MQTT Client Disconnected Abruptly. Will attempt reconnection")
                self.logger.debug("Return code: %s", rc)
                self.logger.debug("userdata: %s", userdata)

                data = {'event_type': self.mqtt_event_name, 'data': {'state': 'Disconnected', 'topic' : None, 'wildcard' : None}}
                self.loop.create_task(self.send_ad_event(data))
            return
        except:
            self.logger.critical("There was an error while disconnecting from the Mqtt Service")
            self.logger.debug('There was an error while disconnecting from the MQTT Service, with Traceback: %s', traceback.format_exc())

    def mqtt_on_message(self, client, userdata, msg):
        try:
            self.logger.debug("Message Received: Topic = %s, Payload = %s", msg.topic, msg.payload)
            topic = msg.topic

            if self.mqtt_wildcards != [] and list(filter(lambda x: x in topic, self.mqtt_wildcards)) != []: #check if any of the wildcards belong
                wildcard = list(filter(lambda x: topic.startswith(x), self.mqtt_wildcards))[0] + '#'

                data = {'event_type': self.mqtt_event_name, 'data': {'topic': topic, 'payload': msg.payload.decode(), 'wildcard': wildcard}}

            else:
                data = {'event_type': self.mqtt_event_name, 'data': {'topic': topic, 'payload': msg.payload.decode(), 'wildcard': None}}

            self.loop.create_task(self.send_ad_event(data))
        except:
            self.logger.critical("There was an error while processing an MQTT message")
            self.logger.debug('There was an error while processing an MQTT message, with Traceback: %s', traceback.format_exc())


    async def call_plugin_service(self, namespace, domain, service, kwargs):

        result = None
        if 'topic' in kwargs:
            if not self.mqtt_connected:  # ensure mqtt plugin is connected
                self.logger.warning("Attempt to call Mqtt Service while disconnected: %s", service)
                return None
            try:
                topic = kwargs['topic']
                payload = kwargs.get('payload', None)
                retain = kwargs.get('retain', False)
                qos = int(kwargs.get('qos', self.mqtt_qos))

                if service == 'publish':
                    self.logger.debug("Publish Payload: %s to Topic: %s", payload, topic)

                    result = await utils.run_in_executor(self, self.mqtt_client.publish, topic, payload, qos, retain)

                    if result[0] == 0:
                        self.logger.debug("Publishing Payload %s to Topic %s Successful", payload, topic)
                    else:
                        self.logger.warning("Publishing Payload %s to Topic %s was not Successful", payload, topic)

                elif service == 'subscribe':
                    self.logger.debug("Subscribe to Topic: %s", topic)

                    if topic not in self.mqtt_client_topics:
                        result = await utils.run_in_executor(self, self.mqtt_client.subscribe, topic, qos)

                        if result[0] == 0:
                            self.logger.debug("Subscription to Topic %s Successful", topic)
                            self.mqtt_client_topics.append(topic)
                        else:
                            self.logger.warning("Subscription to Topic %s was not Successful", topic)
                    else:
                        self.logger.info("Topic %s already subscribed to", topic)

                elif service == 'unsubscribe':
                    self.logger.debug("Unsubscribe from Topic: %s", topic)

                    result = await utils.run_in_executor(self, self.mqtt_client.unsubscribe, topic)
                    if result[0] == 0:
                        self.logger.debug("Unsubscription from Topic %s Successful", topic)
                        if topic in self.mqtt_client_topics:
                            self.mqtt_client_topics.remove(topic)
                    else:
                        self.logger.warning("Unsubscription from Topic %s was not Sucessful", topic)

                else:
                    self.logger.warning("Wrong Service Call %s for MQTT", service)
                    result = 'ERR'

            except Exception as e:
                config = self.config
                if config['type'] == 'mqtt':
                    self.logger.debug('Got the following Error %s, when trying to retrieve Mqtt Plugin', e)
                    return str(e)
                else:
                    self.logger.critical(
                        'Wrong Namespace %s selected for MQTT Service. Please use proper namespace before trying again',
                        namespace)
                    return 'ERR'
        else:
            self.logger.warning('Topic not provided for Service Call {!r}.'.format(service))
            raise ValueError("Topic not provided, please provide Topic for Service Call")

        return result

    async def process_mqtt_wildcard(self, wildcard):
        if wildcard.rstrip('#') not in self.mqtt_wildcards:
            self.mqtt_wildcards.append(wildcard.rstrip('#'))

    async def mqtt_client_state(self):
        return self.mqtt_connected
    
    async def send_ad_event(self, data):
        await self.AD.events.process_event(self.namespace, data)

    #
    # Get initial state
    #

    async def get_complete_state(self):
        self.logger.debug("*** Sending Complete State: %s ***", self.state)
        return copy.deepcopy(self.state)

    async def get_metadata(self):
        return self.mqtt_metadata

    #
    # Utility gets called every second (or longer if configured
    # Allows plugin to do any housekeeping required
    #

    def utility(self):
        #self.logger.info("utility".format(self.state)
        return

    #
    # Handle state updates
    #

    async def get_updates(self):
        already_initialized = False
        already_notified = False
        first_time = True
        first_time_service = True

        while not self.stopping: 
            while (not self.initialized or not already_initialized) and not self.stopping: #continue until initialization is successful
                if not already_initialized and not already_notified: #if it had connected before, it need not run this. Run if just trying for the first time
                    try:
                        await asyncio.wait_for(utils.run_in_executor(self, self.start_mqtt_service, first_time_service), 5.0, loop=self.loop)
                        await asyncio.wait_for(self.mqtt_connect_event.wait(), 5.0, loop=self.loop) # wait for it to return true for 5 seconds in case still processing connect
                    except asyncio.TimeoutError:
                        self.logger.critical("Could not Complete Connection to Broker, please Ensure Broker at URL %s:%s is correct and broker is not down and restart Appdaemon", self.mqtt_client_host, self.mqtt_client_port)

                        if self.mqtt_client_force_start: #meaning it should start anyway even if broker is down
                            self.mqtt_connected = True
                        else:
                            self.mqtt_client.loop_stop()
                            self.mqtt_client.disconnect() #disconnect so it won't attempt reconnection if the broker was to come up

                    first_time_service = False

                state = await self.get_complete_state()
                meta = await self.get_metadata()

                if self.mqtt_connected : #meaning the client has connected to the broker
                    await self.AD.plugins.notify_plugin_started(self.name, self.namespace, meta, state, first_time)
                    already_notified = False
                    already_initialized = True
                    self.logger.info("MQTT Plugin initialization complete")
                    self.initialized = True
                else:
                    if not already_notified and already_initialized:
                        await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                        self.logger.critical("MQTT Plugin Stopped Unexpectedly")
                        already_notified = True
                        already_initialized = False
                        first_time = False
                    if not already_initialized and not already_notified:
                        self.logger.critical("Could not complete MQTT Plugin initialization, trying again in 5 seconds")
                        if self.stopping:
                            break
                    else:
                        self.logger.critical("Unable to reinitialize MQTT Plugin, will keep trying again until complete")
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

                set_tls = False
                auth = {"tls_version" : self.mqtt_tls_version}
                if self.mqtt_client_tls_ca_cert != None:
                    auth.update({"ca_certs" : self.mqtt_client_tls_ca_cert})
                    set_tls = True
                
                if self.mqtt_client_tls_client_cert != None:
                    auth.update({"certfile" : self.mqtt_client_tls_client_cert})
                    set_tls = True
                  
                if self.mqtt_client_tls_client_key != None:
                    auth.update({"keyfile" : self.mqtt_client_tls_client_key})
                    set_tls = True
                   
                if set_tls == True:                    
                    self.mqtt_client.tls_set(**auth)

                    if not self.mqtt_verify_cert:
                        self.mqtt_client.tls_insecure_set(not self.mqtt_verify_cert)

                self.mqtt_client.will_set(self.mqtt_will_topic, self.mqtt_will_payload, self.mqtt_qos, retain=self.mqtt_will_retain)

            self.mqtt_client.connect_async(self.mqtt_client_host, self.mqtt_client_port,
                                        self.mqtt_client_timeout)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.logger.critical("There was an error while trying to setup the Mqtt Service. Error was: %s", e)
            self.logger.debug("There was an error while trying to setup the MQTT Service. Error: %s, with Traceback: %s", e, traceback.format_exc())
            self.logger.debug('There was an error while trying to setup the MQTT Service, with Traceback: %s',traceback.format_exc())

        return
