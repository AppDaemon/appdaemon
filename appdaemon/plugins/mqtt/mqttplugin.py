import asyncio
import copy
import json
import ssl
import traceback
from threading import Lock
from typing import Any

import paho.mqtt.client as mqtt

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.plugin_management import PluginBase

from ...models.config.plugin import MQTTConfig


class MqttPlugin(PluginBase):
    config: MQTTConfig
    initialized: bool
    mqtt_connected: bool
    state: dict[str, dict]
    mqtt_client: mqtt.Client
    mqtt_wildcards: list[str]
    mqtt_binary_topics: list[str]
    mqtt_lock: Lock
    name: str = "_mqtt"

    def __init__(self, ad: "AppDaemon", name: str, config: MQTTConfig):
        """Initialize MQTT Plugin."""
        super().__init__(ad, name, config)
        self.initialized = False
        self.mqtt_connected = False
        self.state = {}
        self.logger.info("MQTT Plugin Initializing")

        if self.config.birth_topic is not None:
            self.logger.info(
                f"Using '{self.config.birth_topic}' as birth topic with payload '{self.config.birth_payload}'"
            )

        if self.config.will_topic is not None:
            self.logger.info(
                f"Using '{self.config.will_topic}' as will topic with payload '{self.config.will_payload}'"
            )

        if self.config.tls_version == "1.2":
            self.config.tls_version = ssl.PROTOCOL_TLSv1_2
        elif self.config.tls_version == "1.1":
            self.config.tls_version = ssl.PROTOCOL_TLSv1_1
        elif self.config.tls_version == "1.0":
            self.config.tls_version = ssl.PROTOCOL_TLSv1
        else:
            import sys

            if sys.hexversion >= 0x03060000:
                self.config.tls_version = ssl.PROTOCOL_TLS
            else:
                self.config.tls_version = ssl.PROTOCOL_TLSv1

        self.logger.debug("Using %s as Client ID", self.config.client_id)
        self.mqtt_client = mqtt.Client(
            client_id=self.config.client_id,
            clean_session=self.config.clean_session,
            transport=self.config.transport,
        )
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_disconnect = self.mqtt_on_disconnect
        self.mqtt_client.on_message = self.mqtt_on_message

        self.mqtt_wildcards = list()
        self.mqtt_binary_topics = list()
        self.mqtt_connect_event = None
        self.mqtt_lock = Lock()

    @property
    def loop(self) -> asyncio.BaseEventLoop:
        return self.AD.loop

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True
        if self.mqtt_connected:
            self.logger.info(
                "Stopping MQTT Plugin and Unsubscribing from URL %s:%s",
                self.config.client_host,
                self.config.client_port,
            )
            client_topics = copy.deepcopy(self.config.client_topics)
            for topic in client_topics:
                self.mqtt_unsubscribe(topic)

            self.mqtt_client.publish(
                self.config.will_topic,
                self.config.shutdown_payload,
                self.config.client_qos,
                retain=self.config.will_retain,
            )
            self.mqtt_client.disconnect()  # disconnect cleanly

        self.mqtt_client.loop_stop()

    def mqtt_on_connect(self, client, userdata, flags, rc):
        try:
            err_msg = ""
            # means connection was successful
            if rc == 0:
                self.mqtt_client.publish(
                    self.config.birth_topic,
                    self.config.birth_payload,
                    self.config.client_qos,
                    retain=self.config.birth_retain,
                )

                self.logger.info(
                    "Connected to MQTT broker at URL %s:%s with paho-mqtt",
                    self.config.client_host,
                    self.config.client_port,
                )
                #
                # Register MQTT Services
                #
                self.AD.services.register_service(self.namespace, "mqtt", "subscribe", self.call_plugin_service)
                self.AD.services.register_service(self.namespace, "mqtt", "unsubscribe", self.call_plugin_service)
                self.AD.services.register_service(self.namespace, "mqtt", "publish", self.call_plugin_service)

                client_topics = copy.deepcopy(self.config.client_topics)

                for topic in client_topics:
                    self.mqtt_subscribe(topic, self.config.client_qos)

                self.mqtt_connected = True

                data = {
                    "event_type": self.config.event_name,
                    "data": {"state": "Connected", "topic": None, "wildcard": None},
                }
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

            # means there was an error
            if err_msg != "":
                self.logger.critical("Could not complete MQTT Plugin initialization, for %s", err_msg)

            # continue processing
            self.mqtt_connect_event.set()
        except Exception:
            self.logger.critical("There was an error while trying to setup the Mqtt Service")
            self.logger.debug(
                "There was an error while trying to setup the MQTT Service, with Traceback: %s",
                traceback.format_exc(),
            )

    def mqtt_on_disconnect(self, client, userdata, rc):
        try:
            # unexpected disconnection
            if rc != 0 and not self.stopping:
                self.initialized = False
                self.mqtt_connected = False
                self.logger.critical("MQTT Client Disconnected Abruptly. Will attempt reconnection")
                self.logger.debug("Return code: %s", rc)
                self.logger.debug("userdata: %s", userdata)

                data = {
                    "event_type": self.config.event_name,
                    "data": {"state": "Disconnected", "topic": None, "wildcard": None},
                }
                self.loop.create_task(self.send_ad_event(data))
            return
        except Exception:
            self.logger.critical("There was an error while disconnecting from the Mqtt Service")
            self.logger.debug(
                "There was an error while disconnecting from the MQTT Service, with Traceback: %s",
                traceback.format_exc(),
            )

    def mqtt_on_message(self, client, userdata, msg):
        try:
            self.update_perf(updates_recv=1, bytes_recv=utils.get_object_size(msg))
            self.logger.debug("Message Received: Topic = %s, Payload = %s", msg.topic, msg.payload)
            topic = msg.topic
            payload = msg.payload
            wildcard = None
            data = {"topic": topic}

            if self.mqtt_wildcards != []:
                # now check if the topic belongs to any of the wildcards
                for sub in self.mqtt_wildcards:
                    if mqtt.topic_matches_sub(sub, topic):
                        wildcard = sub
                        break

            if topic not in self.mqtt_binary_topics and wildcard not in self.mqtt_binary_topics:
                # the binary data is not required
                try:
                    payload = payload.decode()
                except UnicodeDecodeError as u:
                    self.logger.info(f"Unable to decode MQTT message from topic {topic}, ignoring message")
                    self.logger.error(f"Unable to decode MQTT message from topic {topic}, with error: {u}")
                    return

            data.update({"wildcard": wildcard, "payload": payload})

            event_data = {
                "event_type": self.config.event_name,
                "data": data,
            }

            self.loop.create_task(self.send_ad_event(event_data))
        except Exception as e:
            self.logger.critical(f"There was an error while processing MQTT message: {type(e)} {e}")
            self.logger.error(
                f"There was an error while processing MQTT message, with Traceback: {traceback.format_exc()}"
            )

    def mqtt_subscribe(self, topic, qos):
        self.logger.debug("Subscribing to Topic: %s, with Qos %s", topic, qos)

        result = None
        try:
            with self.mqtt_lock:
                self.update_perf(requests_sent=1, bytes_sent=len(json.dumps(topic)))

                result = self.mqtt_client.subscribe(topic, qos)
                if result[0] == 0:
                    self.logger.debug("Subscription to Topic %s Successful", topic)
                    if topic not in self.config.client_topics:
                        self.config.client_topics.append(topic)

                    if "#" in topic or "+" in topic:
                        # its a wildcard
                        self.add_mqtt_wildcard(topic)

                else:
                    if topic in self.config.client_topics:
                        self.config.client_topics.remove(topic)

                    self.logger.debug(
                        "Subscription to Topic %s Unsuccessful, as Client possibly not currently connected",
                        topic,
                    )

                self.update_perf(updates_recv=1, bytes_recv=len(json.dumps(result)))

        except Exception as e:
            self.logger.warning("There was an error while subscribing to topic %s, %s", topic, e)
            self.logger.debug(traceback.format_exc())

        return result

    def mqtt_unsubscribe(self, topic):
        self.logger.debug("Unsubscribing from Topic: %s", topic)

        result = None
        try:
            with self.mqtt_lock:
                self.update_perf(requests_sent=1, bytes_sent=len(json.dumps(topic)))
                result = self.mqtt_client.unsubscribe(topic)
                if result[0] == 0:
                    self.logger.debug("Unsubscription from Topic %s Successful", topic)
                    if topic in self.config.client_topics:
                        self.config.client_topics.remove(topic)

                    self.remove_mqtt_binary(topic)
                    self.remove_mqtt_wildcard(topic)

                else:
                    self.logger.warning("Unsubscription from Topic %s was not Successful", topic)

                self.update_perf(updates_recv=1, bytes_recv=len(json.dumps(result)))

        except Exception as e:
            self.logger.warning("There was an error while unsubscribing from topic %s, %s", topic, e)
            self.logger.debug(traceback.format_exc())

        return result

    async def call_plugin_service(self, namespace, domain, service, kwargs):
        result = None
        if "topic" in kwargs:
            if not self.mqtt_connected:  # ensure mqtt plugin is connected
                self.logger.warning("Attempt to call Mqtt Service while disconnected: %s", service)
                return None
            try:
                topic = kwargs["topic"]
                payload = kwargs.get("payload", None)
                retain = kwargs.get("retain", False)
                qos = int(kwargs.get("qos", self.config.client_qos))

                if service == "publish":
                    self.logger.debug("Publish Payload: %s to Topic: %s", payload, topic)

                    result = await utils.run_in_executor(self, self.mqtt_client.publish, topic, payload, qos, retain)

                    if result[0] == 0:
                        self.logger.debug(
                            "Publishing Payload %s to Topic %s Successful",
                            payload,
                            topic,
                        )
                    else:
                        self.logger.warning(
                            "Publishing Payload %s to Topic %s was not Successful",
                            payload,
                            topic,
                        )

                elif service == "subscribe":
                    if topic not in self.config.client_topics:
                        result = await utils.run_in_executor(self, self.mqtt_subscribe, topic, qos)

                    else:
                        self.logger.info("Topic %s already subscribed to", topic)

                elif service == "unsubscribe":
                    if topic in self.config.client_topics:
                        result = await utils.run_in_executor(self, self.mqtt_unsubscribe, topic)

                    else:
                        self.logger.info("Topic %s already unsubscribed from", topic)

                else:
                    self.logger.warning("Wrong Service Call %s for MQTT", service)
                    result = "ERR"

            except Exception as e:
                config = self.config
                if config["type"] == "mqtt":
                    self.logger.debug(
                        "Got the following Error %s, when trying to retrieve Mqtt Plugin",
                        e,
                    )
                    return str(e)
                else:
                    self.logger.critical(
                        "Wrong Namespace %s selected for MQTT Service. Please use proper namespace before trying again",
                        namespace,
                    )
                    return "ERR"
        else:
            self.logger.warning("Topic not provided for Service Call {!r}.".format(service))
            raise ValueError("Topic not provided, please provide Topic for Service Call")

        return result

    def add_mqtt_wildcard(self, wildcard):
        """Used to add to the plugin wildcard"""

        if wildcard not in self.mqtt_wildcards:
            self.mqtt_wildcards.append(wildcard)
            return True

        return False

    def remove_mqtt_wildcard(self, wildcard):
        """Used to remove remove from the plugin wildcard"""

        if wildcard in self.mqtt_wildcards:
            self.mqtt_wildcards.remove(wildcard)
            return True

        return False

    def add_mqtt_binary(self, topic):
        """Used to add to the plugin binary topic"""

        if topic not in self.mqtt_binary_topics:
            self.mqtt_binary_topics.append(topic)
            return True

        return False

    def remove_mqtt_binary(self, topic):
        """Used to remove from the plugin binary topic"""

        if topic in self.mqtt_binary_topics:
            self.mqtt_binary_topics.remove(topic)
            return True

        return False

    async def mqtt_client_state(self) -> bool:
        return self.mqtt_connected

    async def send_ad_event(self, data: dict[str, Any]):
        await self.AD.events.process_event(self.namespace, data)

    #
    # Get initial state
    #

    async def get_complete_state(self): # Needs to be async for plugins that need to send/receive something
        self.logger.debug("*** Sending Complete State: %s ***", self.state)
        return copy.deepcopy(self.state)

    def get_metadata(self) -> dict[str, Any]:
        return self.config.model_dump(by_alias=True, exclude_none=True)

    #
    # Utility gets called every second (or longer if configured
    # Allows plugin to do any housekeeping required
    #

    def utility(self):
        # self.logger.info("utility".format(self.state)
        return

    #
    # Handle state updates
    #

    async def get_updates(self):
        already_initialized = False
        already_notified = False
        first_time_service = True

        self.mqtt_connect_event = asyncio.Event()

        while not self.stopping:
            while (
                not self.initialized or not already_initialized
            ) and not self.stopping:  # continue until initialization is successful
                if (
                    not already_initialized and not already_notified
                ):  # if it had connected before, it need not run this. Run if just trying for the first time
                    try:
                        await asyncio.wait_for(
                            utils.run_in_executor(self, self.start_mqtt_service, first_time_service), 5.0
                        )
                        await asyncio.wait_for(
                            self.mqtt_connect_event.wait(), 5.0
                        )  # wait for it to return true for 5 seconds in case still processing connect
                    except asyncio.TimeoutError:
                        self.logger.critical(
                            "Could not Complete Connection to Broker, please Ensure Broker at URL %s:%s is correct and broker is not down and restart Appdaemon",
                            self.config.client_host,
                            self.config.client_port,
                        )

                        # meaning it should start anyway even if broker is down
                        if self.config.force_start:
                            self.mqtt_connected = True
                        else:
                            self.mqtt_client.loop_stop()
                            # disconnect so it won't attempt reconnection if the broker was to come up
                            self.mqtt_client.disconnect()

                    first_time_service = False

                state = await self.get_complete_state()
                meta = self.get_metadata()

                # meaning the client has connected to the broker
                if self.mqtt_connected:
                    await self.notify_plugin_started(meta, state)
                    already_notified = False
                    already_initialized = True
                    self.logger.info("MQTT Plugin initialization complete")
                    self.initialized = True
                    self.ready_event.set()
                else:
                    if not already_notified and already_initialized:
                        await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                        self.logger.critical("MQTT Plugin Stopped Unexpectedly")
                        already_notified = True
                        already_initialized = False
                    if not already_initialized and not already_notified:
                        self.logger.critical("Could not complete MQTT Plugin initialization, trying again in 5 seconds")
                        if self.stopping:
                            break
                    else:
                        self.logger.critical(
                            "Unable to reinitialize MQTT Plugin, will keep trying again until complete"
                        )
                    await asyncio.sleep(5)
            await asyncio.sleep(5)

    def start_mqtt_service(self, first_time: bool):
        try:
            # used to wait for connection
            self.mqtt_connect_event.clear()
            if first_time:
                if self.config.client_user is not None:
                    self.mqtt_client.username_pw_set(
                        self.config.client_user, password=self.config.client_password.get_secret_value()
                    )

                set_tls = False
                auth = {"tls_version": self.config.tls_version}
                if self.config.ca_cert is not None:
                    auth.update({"ca_certs": self.config.ca_cert})
                    set_tls = True

                if self.config.client_cert is not None:
                    auth.update({"certfile": self.config.client_cert})
                    set_tls = True

                if self.config.client_key is not None:
                    auth.update({"keyfile": self.config.client_key})
                    set_tls = True

                if set_tls is True:
                    self.mqtt_client.tls_set(**auth)

                    if not self.config.verify_cert:
                        self.mqtt_client.tls_insecure_set(not self.config.verify_cert)

                self.mqtt_client.will_set(
                    topic=self.config.will_topic,
                    payload=self.config.will_payload,
                    qos=self.config.client_qos,
                    retain=self.config.will_retain,
                )

            self.mqtt_client.connect_async(self.config.client_host, self.config.client_port, self.config.tls_version)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.logger.critical(
                "There was an error while trying to setup the Mqtt Service. Error was: %s",
                e,
            )
            self.logger.debug(
                "There was an error while trying to setup the MQTT Service. Error: %s, with Traceback: %s",
                e,
                traceback.format_exc(),
            )
            self.logger.debug(
                "There was an error while trying to setup the MQTT Service, with Traceback: %s",
                traceback.format_exc(),
            )

        return
