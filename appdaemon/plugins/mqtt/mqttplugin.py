import asyncio
import copy
import logging
import traceback
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any, Literal

import paho.mqtt.client as mqtt
from paho.mqtt.enums import MQTTErrorCode
from pydantic import SecretBytes

from appdaemon import utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.models.config.plugin import MQTTConfig
from appdaemon.plugin_management import PluginBase


ERROR_MSGS = {
    MQTTErrorCode.MQTT_ERR_AGAIN: "Try again",
    MQTTErrorCode.MQTT_ERR_NOMEM: "out of memory",
    MQTTErrorCode.MQTT_ERR_PROTOCOL: "protocol error",
    MQTTErrorCode.MQTT_ERR_INVAL: "invalid input",
    MQTTErrorCode.MQTT_ERR_NO_CONN: "no connection",
    MQTTErrorCode.MQTT_ERR_CONN_REFUSED: "connection refused",
    MQTTErrorCode.MQTT_ERR_NOT_FOUND: "not found",
    MQTTErrorCode.MQTT_ERR_CONN_LOST: "connection lost",
    MQTTErrorCode.MQTT_ERR_TLS: "TLS error",
    MQTTErrorCode.MQTT_ERR_PAYLOAD_SIZE: "payload too large",
    MQTTErrorCode.MQTT_ERR_NOT_SUPPORTED: "not supported",
    MQTTErrorCode.MQTT_ERR_AUTH: "authentication error",
    MQTTErrorCode.MQTT_ERR_ACL_DENIED: "ACL denied",
    MQTTErrorCode.MQTT_ERR_UNKNOWN: "unknown error",
    MQTTErrorCode.MQTT_ERR_ERRNO: "system call error (check errno)",
    MQTTErrorCode.MQTT_ERR_QUEUE_SIZE: "message queue full",
    MQTTErrorCode.MQTT_ERR_KEEPALIVE: "keepalive timeout",
}


class AppDaemonMQTTClient(mqtt.Client):
    """Wrapper for the paho MQTT client to integrate with the asyncio loop

    Based on: `paho-mqtt asyncio example <https://github.com/eclipse-paho/paho.mqtt.python/blob/master/examples/loop_asyncio.py>`_
    """

    loop: asyncio.AbstractEventLoop
    logger: logging.Logger

    def __init__(self, *args, loop: asyncio.AbstractEventLoop, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.loop = loop

    async def _internal_loop(self):
        self.logger.debug("socket loop started")
        while self.loop_misc() == mqtt.MQTT_ERR_SUCCESS:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
        self.logger.debug("socket loop finished")

    def on_socket_open(self, client: mqtt.Client, userdata, sock):
        self.logger.debug("Socket opened")

        def cb():
            self.logger.debug("Socket is readable, calling loop_read")
            client.loop_read()

        self.loop.add_reader(sock, cb)
        self.misc = self.loop.create_task(self._internal_loop())

    def on_socket_close(self, client, userdata, sock):
        self.logger.debug("Socket closed")
        self.loop.remove_reader(sock)
        self.misc.cancel()

    def on_socket_register_write(self, client: mqtt.Client, userdata, sock):
        self.logger.debug("Watching socket for writability.")

        def cb():
            self.logger.debug("Socket is writable, calling loop_write")
            client.loop_write()

        self.loop.add_writer(sock, cb)

    def on_socket_unregister_write(self, client, userdata, sock):
        self.logger.debug("Stop watching socket for writability.")
        self.loop.remove_writer(sock)

    def reconnect(self) -> MQTTErrorCode:
        try:
            return super().reconnect()
        except Exception as e:
            self.logger.error("Error connecting MQTT client: %s", e)
            return MQTTErrorCode.MQTT_ERR_UNKNOWN


class MqttPlugin(PluginBase):
    config: MQTTConfig
    state: dict[str, dict]
    mqtt_binary_topics: set[str]
    mqtt_json_topics: set[str]
    mqtt_client: AppDaemonMQTTClient
    name: str = "_mqtt"

    disconnect_event: asyncio.Event

    _mid: dict[int, str | list[str]]
    _mid_futures: dict[int, asyncio.Future]

    def __init__(self, ad: "AppDaemon", name: str, config: MQTTConfig):
        """Initialize MQTT Plugin."""
        super().__init__(ad, name, config)
        self.disconnect_event = asyncio.Event()
        self.state = {}
        self.mqtt_binary_topics = set()
        self.mqtt_json_topics = set()
        self._mid = {}
        self._mid_futures = {}
        self.logger.debug("Using client ID '%s'", self.config.client_id)
        self.logger.debug(
            "Using '%s' as birth topic with payload '%s'",
            self.config.birth_topic,
            self.config.birth_payload
        )
        self.logger.debug(
            "Using '%s' as will topic with payload '%s'",
            self.config.will_topic,
            self.config.will_payload
        )
        self.logger.info("MQTT plugin loaded")

    def _setup_mqtt_client(self):
        # self.mqtt_client = mqtt.Client(
        self.mqtt_client = AppDaemonMQTTClient(
            client_id=self.config.client_id,
            clean_session=self.config.clean_session,
            transport=self.config.transport,
            loop=self.AD.loop,
        )
        self.mqtt_client.enable_logger(self.logger.getChild("mqtt-socket"))
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_connect_fail = self.mqtt_on_connect_fail
        self.mqtt_client.on_disconnect = self.mqtt_on_disconnect
        self.mqtt_client.on_message = self.mqtt_on_message
        self.mqtt_client.on_subscribe = self.mqtt_on_subscribe
        self.mqtt_client.on_unsubscribe = self.mqtt_on_unsubscribe

        match self.config:
            case MQTTConfig(client_user=str(client), client_password=SecretBytes() as password):
                pw = password.get_secret_value().decode("utf-8")
                self.mqtt_client.username_pw_set(client, password=pw)

        set_tls = False
        auth: dict[str, str | int] = {"tls_version": self.config.tls_version.value}

        match self.config:
            case MQTTConfig(ca_cert=str(ca_cert)):
                auth["ca_certs"] = ca_cert
                set_tls = True

        match self.config:
            case MQTTConfig(client_cert=str(client_cert)):
                auth["certfile"] = client_cert
                set_tls = True

        match self.config:
            case MQTTConfig(client_key=str(client_key)):
                auth["keyfile"] = client_key
                set_tls = True

        if set_tls is True:
            self.mqtt_client.tls_set(**auth)  # pyright: ignore[reportArgumentType]

            if not self.config.verify_cert:
                self.mqtt_client.tls_insecure_set(not self.config.verify_cert)

        self.mqtt_client.will_set(
            topic=self.config.will_topic,
            payload=self.config.will_payload,
            qos=self.config.client_qos,
            retain=self.config.will_retain,
        )

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self.AD.loop

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        if self.connect_event.is_set():
            self.logger.info(
                "Stopping MQTT plugin and disconnecting from %s:%s",
                self.config.client_host,
                self.config.client_port,
            )
            self.mqtt_unsubscribe(list(self.config.client_topics))

            self.mqtt_client.publish(
                self.config.will_topic,
                self.config.shutdown_payload,
                self.config.client_qos,
                retain=self.config.will_retain,
            )

        self._stop_client()

    def mqtt_on_connect(self, _: mqtt.Client, __: dict[str, Any], ___, rc: int) -> None:
        try:
            match rc:
                case mqtt.MQTT_ERR_SUCCESS:
                    self.connect_event.set()
                    self.mqtt_client.publish(
                        self.config.birth_topic,
                        self.config.birth_payload,
                        self.config.client_qos,
                        retain=self.config.birth_retain,
                    )

                    self.logger.info(
                        "Connected to MQTT broker at %s:%s with paho-mqtt",
                        self.config.client_host,
                        self.config.client_port,
                    )

                    # Register MQTT Services
                    self.AD.services.register_service(self.namespace, "mqtt", "subscribe", self.call_plugin_service)
                    self.AD.services.register_service(self.namespace, "mqtt", "unsubscribe", self.call_plugin_service)
                    self.AD.services.register_service(self.namespace, "mqtt", "publish", self.call_plugin_service)

                    self.mqtt_subscribe(list(self.config.client_topics), self.config.client_qos)

                    data = {
                        "event_type": self.config.event_name,
                        "data": {"state": "Connected", "topic": None, "wildcard": None},
                    }
                    self.AD.loop.create_task(self.send_ad_event(data), name="internal connection event")
                    self.AD.loop.create_task(self.__post_conn__(), name=f"post_connect for '{self.name}'")
                case _:
                    err_msg = ERROR_MSGS.get(MQTTErrorCode(rc), "unknown error")
                    self.logger.critical("Could not complete MQTT plugin initialization, because %s", err_msg)
        except Exception:
            self.logger.critical("There was an error while trying to setup the MQTT plugin")
            self.logger.debug(
                "There was an error while trying to setup the MQTT plugin, with traceback: %s",
                traceback.format_exc(),
            )

    async def __post_conn__(self) -> None:
        state = await self.get_complete_state()
        meta = self.get_metadata()
        await self.notify_plugin_started(meta, state)
        self.ready_event.set()
        self.logger.info(
            "MQTT plugin initialization completed in %s",
            utils.format_timedelta(perf_counter() - self.start)
        )

    def mqtt_on_connect_fail(self, _: mqtt.Client, __: dict[str, Any]) -> None:
        self.logger.debug("MQTT client connection failure")

    def mqtt_on_disconnect(self, _: mqtt.Client, userdata: dict[str, Any], rc: int) -> None:
        if not self.AD.stopping:
            self.ready_event.clear()
            self.connect_event.clear()
            self.disconnect_event.set()
            self._stop_client()
        match rc:
            case mqtt.MQTT_ERR_SUCCESS:
                self.logger.info("MQTT client disconnected cleanly")
            case _:
                self.logger.critical(
                    "MQTT client disconnected unexpectedly: %s. Attempting to reconnect in %s",
                    ERROR_MSGS.get(MQTTErrorCode(rc), "unknown error"),
                    utils.format_timedelta(self.config.retry_secs)
                )

                if not self.AD.stopping:
                    self.disconnect_event.set()
                    data = {
                        "event_type": self.config.event_name,
                        "data": {"state": "Disconnected", "topic": None, "wildcard": None},
                    }
                    self.AD.loop.create_task(self.send_ad_event(data), name="internal disconnection event")
                    self.AD.loop.create_task(
                        self.AD.plugins.notify_plugin_stopped(self.name, self.namespace),
                        name=f"notify_plugin_stopped for '{self.name}'",
                    )

    def _match_topic(self, topic: str) -> str | None:
        for sub in self.config.client_topics:
            if mqtt.topic_matches_sub(sub, topic):
                return sub
        return None

    def mqtt_on_message(self, _: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        try:
            match msg:
                case mqtt.MQTTMessage(topic=str(topic), payload=bytes() as payload):
                    self.updates_recv += 1
                    self.bytes_recv += len(payload)
                    matched_topic = self._match_topic(topic)
                    if topic not in self.mqtt_binary_topics and matched_topic not in self.mqtt_binary_topics:
                        # the binary data is not required
                        try:
                            payload = payload.decode()
                            # try:
                            #     match json.loads(payload):
                            #         case {"state": str()} as full_state:
                            #             self.state[topic] = full_state
                            # except Exception:
                            #     pass
                        except UnicodeDecodeError as u:
                            self.logger.info(f"Unable to decode MQTT message from topic {topic}, ignoring message")
                            self.logger.error(f"Unable to decode MQTT message from topic {topic}, with error: {u}")
                            return

                    data = {"topic": topic, "wildcard": matched_topic, "payload": payload}
                    event_data = {"event_type": self.config.event_name, "data": data}
                    self.AD.loop.create_task(self.send_ad_event(event_data), name="internal mqtt message event")
                case _:
                    raise TypeError("Invalid MQTT message received")
        except Exception as e:
            self.logger.critical(f"There was an error while processing MQTT message: {type(e)} {e}")
            self.logger.error(
                f"There was an error while processing MQTT message, with Traceback: {traceback.format_exc()}"
            )

    def mqtt_subscribe(self, topic: list[str], qos: Literal[0, 1, 2]) -> MQTTErrorCode | None:
        if not self.connect_event.is_set():  # ensure mqtt plugin is connected
            self.logger.warning("Attempt to subscribe to topic while disconnected: %s", topic)
            return None
        try:
            zipped = list(zip(topic, [qos] * len(topic), strict=False))
            result, mid = self.mqtt_client.subscribe(zipped)
            self.requests_sent += 1
            self.bytes_sent += sum(map(len, topic)) + len(topic)
            if mid is not None:
                self._mid[mid] = topic
            match result:
                case MQTTErrorCode.MQTT_ERR_SUCCESS:
                    self.logger.debug("Subscription to topic %s sent to MQTT broker", topic)
                case _:
                    self.logger.debug("Subscription to topic %s was unsuccessful", topic)
        except Exception as e:
            self.logger.warning("There was an error while subscribing to topic %s, %s", topic, e)
            self.logger.debug(traceback.format_exc())
        else:
            return result

    def mqtt_on_subscribe(self, client: mqtt.Client, _, mid: int, granted_qos: tuple[int, ...]) -> None:
        self.updates_recv += 1
        self.bytes_recv += 1
        match self._mid.pop(mid, None):
            case(list() | tuple() | set()) as topics:
                self.config.client_topics |= set(topics)
                for topic, qos in zip(topics, granted_qos):
                    self.logger.info("Subscription to %s acknowledged by MQTT broker with QoS %d", topic, qos)
            case None:
                self.logger.warning("Subscription with mid %s not found in unresolved subscriptions", mid)

    def mqtt_unsubscribe(self, topic: list[str]) -> MQTTErrorCode | None:
        if not self.connect_event.is_set():  # ensure mqtt plugin is connected
            self.logger.warning("Attempt to unsubscribe to topic while disconnected: %s", topic)
            return None
        elif len(topic) == 0:
            return None
        try:
            result, mid = self.mqtt_client.unsubscribe(topic)
            self.requests_sent += 1
            self.bytes_sent += sum(map(len, topic)) + len(topic)
            if mid is not None:
                self._mid[mid] = topic
                future = self.AD.loop.create_future()
                self._mid_futures[mid] = future
                self._last_mid = mid
            match result:
                case MQTTErrorCode.MQTT_ERR_SUCCESS:
                    self.logger.debug("Unsubscription to topic %s sent to MQTT broker", topic)
                case _:
                    self.logger.debug("Unsubscription to topic %s was unsuccessful", topic)
        except Exception as e:
            self.logger.warning("There was an error while unsubscribing from topic %s, %s", topic, e)
            self.logger.debug(traceback.format_exc())
        else:
            return result

    def mqtt_on_unsubscribe(self, client: mqtt.Client, _, mid: int) -> None:
        self.updates_recv += 1
        self.bytes_recv += 1
        match self._mid.pop(mid, None):
            case list(topics):
                self.config.client_topics -= set(topics)
                self.logger.info("Unsubscription from %s acknowledged by MQTT broker", topics)
            case None:
                self.logger.warning("Subscription with mid %s not found in unresolved subscriptions", mid)

    async def call_plugin_service(self, namespace, domain, service, kwargs):
        result = None
        if "topic" in kwargs:
            if not self.connect_event.is_set():  # ensure mqtt plugin is connected
                self.logger.warning("Attempt to call MQTT Service while disconnected: %s", service)
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
                    self.logger.debug("Got the following Error %s, when trying to retrieve Mqtt Plugin", e)
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

    async def send_ad_event(self, data: dict[str, Any]):
        await self.AD.events.process_event(self.namespace, data)

    #
    # Get initial state
    #

    async def get_complete_state(self):
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

    def _start_client(self) -> None:
        self.start = perf_counter()
        self.connect_event.clear()
        self.disconnect_event.clear()
        self.ready_event.clear()
        self.mqtt_client.connect_async(self.config.client_host, self.config.client_port, keepalive=60)
        self.AD.executor.submit(self.mqtt_client.reconnect)

    def _stop_client(self):
        if self.connect_event.is_set():
            self.mqtt_unsubscribe(list(self.config.client_topics))
            self.connect_event.clear()
            self.disconnect_event.clear()
            self.mqtt_client.disconnect()  # disconnect cleanly

        self.ready_event.clear()

    @asynccontextmanager
    async def _run_context(self):
        try:
            self._setup_mqtt_client()
            self._start_client()
            yield
        finally:
            self._stop_client()

    async def get_updates(self):
        while not self.AD.stopping:
            async with self._run_context():
                try:
                    await asyncio.wait_for(self.connect_event.wait(), self.config.connect_timeout.total_seconds())
                except asyncio.TimeoutError:
                    self.logger.critical(
                        "Failed to start MQTT plugin. Please ensure broker is not down and restart Appdaemon. Retrying in %s",
                        utils.format_timedelta(self.config.retry_secs)
                    )
                    if not self.config.force_start:
                        await self.AD.utility.sleep(self.config.retry_secs.total_seconds(), timeout_ok=True)
                        continue

                except Exception:
                    self.error.exception("Unhandled exception while starting MQTT plugin")
                    if not self.config.force_start:
                        await self.AD.utility.sleep(self.config.retry_secs.total_seconds(), timeout_ok=True)
                        continue

                try:
                    self.ready_event.set()

                    waits = {
                        "mqtt disconnect_event": self.disconnect_event.wait(),
                        "appdaemon stopping mqtt": self.AD.stop_event.wait(),
                    }
                    tasks = [
                        self.AD.loop.create_task(coro, name=name)
                        for name, coro in waits.items()
                    ]
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    # Shutdown will hang until both of these events are set if we don't cancel the ongoing one.
                    for task in tasks:
                        if not task.done() and not task.cancelled():
                            task.cancel()
