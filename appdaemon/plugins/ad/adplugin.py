import asyncio
import json
import ssl
import websocket
import traceback
from urllib.parse import quote
import uuid

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
from appdaemon.plugin_management import PluginBase


async def no_func():
    pass


def ad_check(func):
    def func_wrapper(*args, **kwargs):
        self = args[0]
        if not self.reading_messages:
            self.logger.warning("Attempt to call remote AD while disconnected: %s", func.__name__)
            return no_func()
        else:
            return func(*args, **kwargs)

    return func_wrapper


class AdPlugin(PluginBase):
    def __init__(self, ad: AppDaemon, name, args):
        super().__init__(ad, name, args)

        # Store args
        self.AD = ad
        self.config = args
        self.name = name

        self.stopping = False
        self.ws = None
        self.reading_messages = False
        self.stream_results = {}
        self.remote_namespaces = {}
        self.is_booting = True

        self.logger.info("AD Plugin Initializing")

        if "namespace" in args:
            self.namespace = args["namespace"]
        else:
            self.namespace = "default"

        if "url" in args:
            self.ad_url = args["url"]
        else:
            self.ad_url = None
            self.logger.warning("ad_url not found in AD configuration - module not initialized")
            raise ValueError("AppDaemon requires remote AD's URL, and none provided in plugin config")

        self.password = args.get("password")
        self.timeout = args.get("timeout")
        self.cert_verify = args.get("cert_verify", True)
        self.ca_certs = args.get("ca_certs")
        self.ca_cert_path = args.get("ca_cert_path")
        self.ssl_certificate = args.get("ssl_certificate")
        self.ssl_key = args.get("ssl_key")

        if "client_name" in args:
            self.client_name = args["client_name"]
        else:
            self.client_name = "{}_{}".format(self.name.lower(), uuid.uuid4().hex)

        self.proxy = args.get("proxy")
        self.check_hostname = args.get("check_hostname", True)
        self.subscriptions = args.get("subscriptions")
        self.forward_namespaces = args.get("forward_namespaces", {})
        self.forward_namespaces["forwarded_namespaces"] = {}

        if "enabled" not in self.forward_namespaces:
            self.forward_namespaces["enabled"] = False

        self.tls_version = args.get("tls_version", "auto")

        if self.tls_version == "1.2":
            self.tls_version = ssl.PROTOCOL_TLSv1_2
        elif self.tls_version == "1.1":
            self.tls_version = ssl.PROTOCOL_TLSv1_1
        elif self.tls_version == "1.0":
            self.tls_version = ssl.PROTOCOL_TLSv1
        else:
            import sys

            if sys.hexversion >= 0x03060000:
                self.tls_version = ssl.PROTOCOL_TLS
            else:
                self.tls_version = ssl.PROTOCOL_TLSv1

        self.ssl_certificate = args.get("ssl_certificate")
        self.host_proxy = {}

        if "http_proxy_host" in args:
            self.host_proxy["http_proxy_host"] = args["http_proxy_host"]

        if "http_proxy_port" in args:
            self.host_proxy["http_proxy_port"] = args["http_proxy_port"]

        rn = args.get("remote_namespaces", {})

        if rn == {}:
            raise ValueError("AppDaemon requires remote namespace mapping and none provided in plugin config")

        for local, remote in rn.items():
            self.remote_namespaces[remote] = local

        self.logger.info("AD Plugin initialization complete")
        self.metadata = {"version": "1.0"}

    async def am_reading_messages(self):
        return self.reading_messages

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True
        self.reading_messages = False

        if self.ws is not None:
            self.ws.close()

    #
    # Placeholder for constraints
    #
    def list_constraints(self):
        return []

    #
    # Get initial state
    #

    async def get_complete_state(self):
        ad_state = await self.get_ad_state()

        states = {}

        for namespace in self.remote_namespaces:
            if namespace in ad_state:
                state = ad_state[namespace]
            else:
                continue

            accept, ns = self.process_namespace(namespace)

            if accept is False:  # don't accept namespace
                continue

            states[ns] = state

        # now add local AD plugin state
        states[self.namespace] = {}

        self.logger.debug("*** Sending Complete State: %s ***", states)
        return states

    #
    # Get AD Metadata
    #

    async def get_metadata(self):
        return self.metadata

    #
    # Handle state updates
    #

    async def get_updates(self):
        already_notified = False
        first_time = True
        self.lock = asyncio.Lock()

        while not self.stopping:
            try:
                #
                # First Connect to websocket interface
                #
                url = self.ad_url
                if url.startswith("https://"):
                    url = url.replace("https", "wss", 1)
                elif url.startswith("http://"):
                    url = url.replace("http", "ws", 1)

                sslopt = {}
                options = {"enable_multithread": False}

                if self.timeout is not None:
                    options.update({"timeout": self.timeout})

                options.update(self.host_proxy)

                # setup SSL

                if self.cert_verify is False:
                    sslopt = {"cert_reqs": ssl.CERT_NONE}

                sslopt["ca_certs"] = self.ca_certs
                sslopt["ca_cert_path"] = self.ca_cert_path
                sslopt["check_hostname"] = self.check_hostname
                sslopt["certfile"] = self.ssl_certificate
                sslopt["keyfile"] = self.ssl_key
                sslopt["ssl_version"] = self.tls_version

                self.ws = await utils.run_in_executor(
                    self, websocket.create_connection, "{}/stream".format(url), sslopt=sslopt, **options,
                )

                #
                # Setup Initial authorizations
                #

                self.logger.info("Using client_name %r to subscribe", self.client_name)

                data = {
                    "request_type": "hello",
                    "request_id": uuid.uuid4().hex,
                    "data": {"client_name": self.client_name, "password": self.password},
                }

                await utils.run_in_executor(self, self.ws.send, json.dumps(data))

                res = await utils.run_in_executor(self, self.ws.recv)
                result = json.loads(res)

                self.logger.debug(result)

                if result["response_success"] is True:
                    # We are good to go
                    self.logger.info(
                        "Connected to AppDaemon with Version %s", result["data"]["version"],
                    )

                else:
                    self.logger.warning(
                        "Unable to Authenticate to AppDaemon with Error %s", result["response_error"],
                    )
                    self.logger.debug("%s", result)
                    raise ValueError(
                        "Error Connecting to AppDaemon Instance using URL %s", self.ad_url,
                    )

                #
                # Register Services with Local Services registeration first
                #

                self.AD.services.register_service(self.namespace, "stream", "subscribe", self.call_plugin_service)
                self.AD.services.register_service(self.namespace, "stream", "unsubscribe", self.call_plugin_service)
                self.AD.services.register_service(self.namespace, "stream", "send_bytes", self.call_plugin_service)

                services = await self.get_ad_services()
                namespaces = []

                for serv in services:
                    namespace = serv["namespace"]
                    domain = serv["domain"]
                    service = serv["service"]

                    accept, ns = self.process_namespace(namespace)

                    if accept is False:  # reject this namespace
                        continue

                    self.AD.services.register_service(ns, domain, service, self.call_plugin_service)

                states = await self.get_complete_state()
                namespaces.extend(list(states.keys()))

                #
                # Subscribe to event stream
                #

                self.subscription_event_stream()
                namespace = {"namespace": self.namespace, "namespaces": namespaces}

                await self.AD.plugins.notify_plugin_started(self.name, namespace, self.metadata, states, first_time)

                #
                # Finally Loop forever consuming events
                #

                first_time = False
                already_notified = False
                self.is_booting = False
                self.reading_messages = True

                while not self.stopping:
                    res = await utils.run_in_executor(self, self.ws.recv)

                    result = json.loads(res)
                    self.logger.debug("%s", result)

                    if result.get("response_type") in ("event", "state_changed",):  # an event happened
                        remote_namespace = result["data"].pop("namespace")

                        data = result["data"]
                        accept, local_namespace = self.process_namespace(remote_namespace)

                        if accept is True:  # accept data

                            # asyncio.ensure_future(self.process_data_from_remote_ad(local_namespace, remote_namespace, data))
                            await self.process_data_from_remote_ad(local_namespace, remote_namespace, data)

                    else:  # not an event stream but a specific required response
                        response_id = result.get("response_id")  # its for a message with expected result if not None

                        if response_id in self.stream_results:  # if to be picked up
                            self.stream_results[response_id]["response"] = result
                            self.stream_results[response_id]["event"].set()  # time for pickup

            except Exception:
                if self.forward_namespaces["enabled"] is True:
                    # remove callback from getting local events
                    await self.AD.callbacks.clear_callbacks(self.name)

                self.reading_messages = False
                self.is_booting = True
                self.ws = None

                if not already_notified:
                    await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                    already_notified = True
                if not self.stopping:
                    self.logger.warning("Disconnected from AppDaemon, retrying in 5 seconds")
                    self.logger.debug("-" * 60)
                    self.logger.debug("Unexpected error:")
                    self.logger.debug("-" * 60)
                    self.logger.debug(traceback.format_exc())
                    self.logger.debug("-" * 60)
                    await asyncio.sleep(5)

        self.logger.info("Disconnecting from AppDaemon")
        self.reading_messages = False

    def subscription_event_stream(self):
        if self.subscriptions is not None:
            if "state" in self.subscriptions:
                for subscription in self.subscriptions["state"]:
                    asyncio.ensure_future(self.run_subscription("state", subscription))

            if "event" in self.subscriptions:
                for subscription in self.subscriptions["event"]:
                    asyncio.ensure_future(self.run_subscription("event", subscription))

        if self.forward_namespaces["enabled"] is True:
            # meaning it is to forward the stream
            # so setup to receive instructions for this local instance from the remote one
            # self.client_name* is used, to make it easy for the far-end to use namespace just
            # using the client's name
            subscription = {"namespace": f"{self.client_name}*", "event": "*"}
            asyncio.ensure_future(self.run_subscription("event", subscription))

    async def process_data_from_remote_ad(self, local_namespace, remote_namespace, data):

        # for any service requesting data, it should only send forwarded namespaces
        res = None
        response = None

        if data["data"].get("__AD_ORIGIN") == self.client_name:
            pass  # it originated from this instance so disregard it

        elif data["event_type"] == "service_registered":  # a service was registered
            domain = data["data"]["domain"]
            service = data["data"]["service"]
            self.AD.services.register_service(local_namespace, domain, service, self.call_plugin_service)

        elif data["event_type"] == "__AD_ENTITY_REMOVED":  # an entity was deleted
            entity_id = data["data"]["entity_id"]
            await self.AD.state.remove_entity(local_namespace, entity_id)

        elif self.forward_namespaces["enabled"] is True and data["event_type"] in (
            "get_state",
            "get_services",
            "call_service",
            "listen_event",
            "cancel_listen_event",
        ):
            res, response = await self.process_forward_event(local_namespace, remote_namespace, data)

        else:
            data["data"]["__AD_ORIGIN"] = self.client_name
            await self.AD.events.process_event(local_namespace, data)

        if res is not None:  # a response should be sent back
            request_id = data.pop("request_id", uuid.uuid4().hex)

            data = {}
            data["response"] = res
            data["response_type"] = response
            data["response_id"] = request_id

            if local_namespace is None:
                remote_namespace = self.client_name

            else:
                remote_namespace = f"{self.client_name}_{local_namespace}"

            await self.fire_plugin_event(response, remote_namespace, **data)

    async def process_forward_event(self, local_namespace, remote_namespace, data):
        res = None
        response = None

        if data["event_type"] == "get_state":  # get state
            forwarded_namespaces = list(self.forward_namespaces["forwarded_namespaces"].keys())
            entity_id = data["data"].get("entity_id")

            requested_namespace = data["data"].get("requested_namespace", local_namespace)

            if requested_namespace is None:
                requested_namespace = forwarded_namespaces

            elif not isinstance(remote_namespace, list):
                requested_namespace = [requested_namespace]

            states = {}
            for namespace in requested_namespace:
                if namespace in forwarded_namespaces:
                    state = self.AD.state.get_entity(namespace, entity_id, self.client_name)

                    states[namespace] = {}
                    states[namespace].update(state)

            res = states
            response = "get_state_response"

        elif data["event_type"] == "get_services":  # get services
            forwarded_namespaces = list(self.forward_namespaces["forwarded_namespaces"].keys())
            res = []

            for namespace in forwarded_namespaces:
                res.extend(self.AD.services.list_services(namespace))

            # now get the local namespace services
            # res.extend(self.AD.services.list_services(self.namespace))

            response = "get_services_response"

        elif data["event_type"] == "call_service":  # a service call is being made by remote device

            service = data["data"]["service"]
            if "domain" not in data["data"]:
                d, s = service.split("/")
                if d and s:
                    domain = d
                    service = s
            else:
                domain = data["data"]["domain"]

            service_data = data["data"].get("data", {})
            res = await self.AD.services.call_service(local_namespace, domain, service, service_data)
            response = "call_service_response"

        elif data["event_type"] == "listen_event":  # instruct AD to listen then forward these events

            namespaces = await self.get_requested_namespace(data)

            res = await self.setup_forward_events(namespaces)
            response = "listen_event_response"

        elif (
            data["event_type"] == "cancel_listen_event"
        ):  # instruct AD to cancel listen then don't forward these events

            namespaces = await self.get_requested_namespace(data)

            for namespace in namespaces:
                if namespace in self.forward_namespaces["forwarded_namespaces"]:
                    handle = self.forward_namespaces["forwarded_namespaces"].pop(namespace)
                    await self.AD.events.cancel_event_callback(self.name, handle)

        return res, response

    async def get_requested_namespaces(self, data):
        """Uused to get the requested namespace"""

        requested_namespace = data["data"]["requested_namespace"]

        if not isinstance(requested_namespace, list):
            namespaces = [requested_namespace]

        elif requested_namespace == "global":  # get events from all namespaces
            namespaces = await self.AD.state.list_namespaces()

        else:
            namespaces = requested_namespace

        return namespaces

    async def setup_forward_events(self, namespaces):
        handles = {}
        if self.forward_namespaces.get("allow") is True:

            restricted_namespaces = self.forward_namespaces.get("restricted_namespaces", [])

            if not isinstance(restricted_namespaces, list):
                restricted_namespaces = [restricted_namespaces]

            non_restricted_namespaces = self.forward_namespaces.get("non_restricted_namespaces", [])

            if not isinstance(non_restricted_namespaces, list):
                non_restricted_namespaces = [non_restricted_namespaces]

            # register callback to get local stream

            for namespace in namespaces:
                # first check if it hasn't subcribed to the namespace before
                if (
                    namespace not in self.forward_namespaces["forwarded_namespaces"]
                    and (
                        non_restricted_namespaces == []
                        or (non_restricted_namespaces != [] and namespace in non_restricted_namespaces)
                    )
                    and (
                        restricted_namespaces == []
                        or (restricted_namespaces != [] and namespace not in restricted_namespaces)
                    )
                    and namespace != "global"
                ):
                    handle = await self.AD.events.add_event_callback(
                        self.name, namespace, self.forward_events, None, __silent=True, __namespace=namespace,
                    )

                    handles[namespace] = handle
                    self.forward_namespaces["forwarded_namespaces"][namespace] = handle

        return handles

    def get_namespace(self):
        return self.namespace

    #
    # Utility functions
    #

    def utility(self):
        # self.logger.debug("Utility")
        return None

    #
    # AppDaemon Interactions
    #

    @ad_check
    async def call_plugin_service(self, namespace, domain, service, data):
        self.logger.debug(
            "call_plugin_service() namespace=%s domain=%s service=%s data=%s", namespace, domain, service, data,
        )
        res = None

        if namespace == self.namespace and domain == "stream":  # its a service to the stream
            if service == "subscribe":
                if "type" in data:
                    subscribe_type = data["type"]

                    if "subscription" in data:
                        res = await self.stream_subscribe(subscribe_type, data["subscription"])

                else:
                    self.logger.warning("Stream Type not given in data %s", data)

            elif service == "unsubscribe":
                if "type" in data:
                    unsubscribe_type = data["type"]

                    if "handle" in data:
                        res = await self.stream_unsubscribe(unsubscribe_type, data["handle"])

                    else:
                        self.logger.warning("No handle provided in service call, please provide handle")
                else:
                    self.logger.warning("Cancel Type not given in data %s", data)

            elif service == "send_bytes":  # used to send bytes based data, doesn't get response
                if "bytes_data" in data:
                    bytes_data = data["bytes_data"]
                    try:
                        async with self.lock:
                            await utils.run_in_executor(self, self.ws.send_binary, bytes_data)

                    except websocket._exceptions.WebSocketConnectionClosedException:
                        self.logger.warning("Attempt to call remote AD while disconnected: send_bytes")

                    except Exception:
                        self.logger.error("-" * 60)
                        self.logger.error("Unexpected error during send_bytes call_plugin_service()")
                        self.logger.error(
                            "Service: %s.%s.%s Arguments: %s", namespace, domain, service, data,
                        )
                        self.logger.error("-" * 60)
                        self.logger.error(traceback.format_exc())
                        self.logger.error("-" * 60)

                else:
                    self.logger.warning("No bytes_data provided in service call, please provide bytes to be sent")

            else:
                self.logger.warning("Unrecognised service given %s", service)

            return res

        if namespace not in list(self.remote_namespaces.values()):
            self.logger.warning("Unidentified namespace given as %s", namespace)
            return res

        else:
            ns = list(self.remote_namespaces.keys())[list(self.remote_namespaces.values()).index(namespace)]

        request_id = uuid.uuid4().hex
        kwargs = {
            "request_type": "call_service",
            "request_id": request_id,
            "data": {"namespace": ns, "service": service, "domain": domain, "data": data},
        }

        res = await self.process_request(request_id, kwargs)

        if res is not None:
            if res["response_success"] is True:
                res = res["data"]
            else:
                response_error = res["response_error"]
                request_data = res["request"]
                self.logger.warning(
                    "Could not execute service call, as there was an error from the remote AD %s", response_error,
                )
                self.logger.debug(request_data)

        return res

    @ad_check
    async def set_plugin_state(self, namespace, entity_id, **data):
        self.logger.debug("set_plugin_state() %s %s %s", namespace, entity_id, data)
        res = None

        try:
            data["entity_id"] = entity_id
            res = await self.call_plugin_service(namespace, "state", "set", data)

        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error during set_plugin_state()")
            self.logger.error("Arguments: %s = %s", entity_id, data)
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)

        return res

    @ad_check
    async def fire_plugin_event(self, event, namespace, **data):

        if event != "__AD_LOG_EVENT":  # this is to avoid a potential loop
            self.logger.debug("fire_event: %s, %s %s", event, namespace, data)

        event_clean = quote(event, safe="")

        if namespace.startswith(f"{self.client_name}_"):  # its for local and sent to remote
            ns = namespace

        elif namespace not in list(self.remote_namespaces.values()):
            if not namespace.startswith(self.client_name):
                self.logger.warning("Unidentified namespace given as %s", namespace)

            return None

        else:
            ns = list(self.remote_namespaces.keys())[list(self.remote_namespaces.values()).index(namespace)]

        data["__AD_ORIGIN"] = self.client_name

        kwargs = {
            "request_type": "fire_event",
            "data": {"namespace": ns, "event": event_clean, "data": data},
        }

        try:
            async with self.lock:
                await utils.run_in_executor(self, self.ws.send, json.dumps(kwargs))

        except websocket._exceptions.WebSocketConnectionClosedException:
            self.logger.warning("Attempt to call remote AD while disconnected: fire_event")

        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error during fire_event()")
            self.logger.error("Arguments: %s = %s", event_clean, data)
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)

        return None

    async def stream_subscribe(self, subscribe_type, data):
        self.logger.debug("stream_subscribe() subscribe_type=%s data=%s", subscribe_type, data)
        request_id = uuid.uuid4().hex
        result = None

        if subscribe_type == "state":
            kwargs = {"request_type": "listen_state", "request_id": request_id}

            kwargs["data"] = {}
            kwargs["data"].update(data)

            res = await self.process_request(request_id, kwargs)

            if res is not None:
                result = res["data"]

        if subscribe_type == "event":
            kwargs = {"request_type": "listen_event", "request_id": request_id}

            kwargs["data"] = {}
            kwargs["data"].update(data)

            res = await self.process_request(request_id, kwargs)

            if res is not None:
                result = res["data"]

        return result

    async def stream_unsubscribe(self, unsubscribe_type, handle):
        self.logger.debug(
            "stream_unsubscribe() unsubscribe_type=%s handle=%s", unsubscribe_type, handle,
        )
        request_id = uuid.uuid4().hexs
        result = None

        if unsubscribe_type == "state":
            request_type = "cancel_listen_state"

        elif unsubscribe_type == "event":
            request_type = "cancel_listen_event"

        else:
            self.logger.warning("Unidentified unsubscribe type given as %s", unsubscribe_type)

        kwargs = {
            "request_type": request_type,
            "request_id": request_id,
            "data": {"handle": handle},
        }

        res = await self.process_request(request_id, kwargs)

        if res is not None:
            result = res["data"]

        return result

    async def forward_events(self, event, data, kwargs):
        """Callback for event forwarding"""
        try:
            if data.get("__AD_ORIGIN") == self.client_name:
                return  # meaning it should be ignored

            namespace = kwargs.get("__namespace")
            if "namespace" in data:
                del data["namespace"]

            if event != "__AD_LOG_EVENT":  # this is to avoid a potential loop
                self.logger.debug(
                    "forward_events() event=%s namespace=%s data=%s", event, namespace, data,
                )

            if event == "__AD_ENTITY_ADDED":
                event = "state_changed"
                new_state = data["state"]
                old_state = {}
                entity_id = data["entity_id"]

                data = {
                    "entity_id": entity_id,
                    "new_state": new_state,
                    "old_state": old_state,
                }

            forward = True

            if namespace not in list(
                self.forward_namespaces["forwarded_namespaces"].keys()
            ):  # meaning it was gotten from remote AD
                forward = False

            if forward is True:  # it is good to go
                namespace = f"{self.client_name}_{namespace}"

                await self.fire_plugin_event(event, namespace, **data)

        except Exception:
            self.logger.debug("-" * 60)
            self.logger.error("Unexpected error during forward_event()")
            self.logger.debug("-" * 60)
            self.logger.debug(traceback.format_exc())
            self.logger.debug("-" * 60)

    async def get_ad_state(self):
        self.logger.debug("get_ad_state()")

        state = {}

        for namespace in list(self.remote_namespaces.keys()):
            request_id = uuid.uuid4().hex
            kwargs = {
                "request_type": "get_state",
                "request_id": request_id,
                "data": {"namespace": namespace},
            }

            result = await self.process_request(request_id, kwargs)

            if result is not None:
                if result["data"] is not None:
                    state[namespace] = result["data"]

                else:
                    state[namespace] = {}
                    if self.is_booting is True:  # only report at boot up
                        self.logger.warning(
                            "No state data available for Namespace %r", self.remote_namespaces[namespace],
                        )
                    else:
                        self.logger.debug(
                            "No state data available for Namespace %r", self.remote_namespaces[namespace],
                        )
            else:
                state[namespace] = {}
                if self.is_booting is True:  # only report at boot up
                    self.logger.warning(
                        "There was an error while processing data for Namespace %r, so no state data",
                        self.remote_namespaces[namespace],
                    )
                else:
                    self.logger.debug(
                        "There was an error while processing data for Namespace %r, so no state data",
                        self.remote_namespaces[namespace],
                    )

        return state

    async def get_ad_services(self):
        self.logger.debug("get_ad_services()")

        services = []
        request_id = uuid.uuid4().hex
        kwargs = {"request_type": "get_services", "request_id": request_id}

        result = await self.process_request(request_id, kwargs)

        if result is not None:
            for res in result["data"]:
                if res["namespace"] in list(self.remote_namespaces.keys()):
                    services.append(res)

        return services

    async def process_request(self, request_id, data, wait=5.0):
        res = None
        result = None

        if self.is_booting is True:
            await utils.run_in_executor(self, self.ws.send, json.dumps(data))
            res = await utils.run_in_executor(self, self.ws.recv)

        elif request_id is not None:
            self.stream_results[request_id] = {}
            self.stream_results[request_id]["event"] = asyncio.Event()
            self.stream_results[request_id]["response"] = None

            async with self.lock:
                await utils.run_in_executor(self, self.ws.send, json.dumps(data))

            try:
                await asyncio.wait_for(self.stream_results[request_id]["event"].wait(), wait)
                res = self.stream_results[request_id].pop("response")

            except asyncio.TimeoutError:
                self.logger.warning("Timeout Error occured while processing %s", data["request_type"])
                self.logger.debug("Timeout Error occured while trying to process data %s", data)

            except Exception:
                self.logger.error("-" * 60)
                self.logger.error("Unexpected error during process_request()")
                self.logger.error("Request_id: %s Arguments: %s", request_id, data)
                self.logger.error("-" * 60)
                self.logger.error(traceback.format_exc())
                self.logger.error("-" * 60)

            finally:
                del self.stream_results[request_id]

        if res is not None:
            try:
                result = json.loads(res)
            except Exception:
                result = res

        return result

    def process_namespace(self, namespace):
        accept = True
        local_namespace = None

        if namespace in self.remote_namespaces:
            local_namespace = self.remote_namespaces[namespace]

        elif namespace.startswith("{}".format(self.client_name)):
            # it is for a local namespace, fired by the remote one
            local_namespace = namespace.replace(self.client_name, "")

            # if it is empty
            if local_namespace in ("", "_"):
                local_namespace = None

            # if it is starting with an underscore like _default
            elif local_namespace[:1] == "_":
                local_namespace = local_namespace[1:]

        else:
            accept = False

        return accept, local_namespace

    def check_namespace(self, namespace, namespaces):
        """Used to check if a namespace should be accepted to be processed"""
        accept = False
        if namespace.endswith("*"):
            for ns in namespaces:
                if ns.startswith(namespace[:-1]):
                    accept = True
                    break
        else:
            if namespace in namespaces:
                accept = True

        return accept

    async def run_subscription(self, sub_type, subscription):
        await asyncio.sleep(1)
        namespace = subscription["namespace"]

        if namespace.startswith(self.client_name):  # for local instance remote subscription
            accept = True
        else:
            accept = self.check_namespace(namespace, self.remote_namespaces)

        if accept is True:
            result = await self.stream_subscribe(sub_type, subscription)
            self.logger.info("Handle for Subscription %r is %r", subscription, result)
        else:
            self.logger.warning(
                "Cannot Subscribe to Namespace %r, as not defined in remote namespaces", namespace,
            )
