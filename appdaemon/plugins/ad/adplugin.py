import asyncio
import json
import ssl
import websocket
import traceback
import aiohttp
from urllib.parse import quote
import uuid
import copy

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

    return (func_wrapper)


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
        self.rm_ns = {}
        self.is_booting = True

        self.logger.info("AD Plugin Initializing")

        if "namespace" in args:
            self.namespace = args["namespace"]
        else:
            self.namespace = "default"

        if "ad_url" in args:
            self.ad_url = args["ad_url"]
        else:
            self.ad_url = None
            self.logger.warning("ad_url not found in AD configuration - module not initialized")
            raise ValueError("AppDaemon requires remote AD's URL, and none provided in plugin config")

        
        if "api_key" in args:
            self.api_key = args["api_key"]
        else:
            self.api_key = None

        if "cert_path" in args:
            self.cert_path = args["cert_path"]
        else:
            self.cert_path = None

        if "cert_verify" in args:
            self.cert_verify = args["cert_verify"]
        else:
            self.cert_verify = True

        if "api_ssl_certificate" in args:
            api_ssl_certificate = args["api_ssl_certificate"]
        else:
            api_ssl_certificate = None

        if "api_ssl_key" in args:
            api_ssl_key = args["api_ssl_key"]
        else:
            api_ssl_key = None

        if "client_name" in args:
            self.client_name = args["client_name"]
        else:
            self.client_name = "{}_{}".format(self.name.lower(), uuid.uuid4().hex)
        
        check_hostname = args.get("check_hostname", False)

        #
        # Setup SSL
        #

        if api_ssl_certificate != None:
            try:
                self.ssl_context = ssl.create_default_context()
                self.ssl_context.check_hostname = check_hostname

                cert = {}

                if api_ssl_certificate != None:
                    cert.update({"certfile":api_ssl_certificate})
                
                if api_ssl_key != None:
                    cert.update({"keyfile":api_ssl_key})

                if cert != {}:
                    self.ssl_context.load_cert_chain(**cert)

            except ssl.SSLError as s:
                self.logger.debug("Could not initialize AD Client SSL Context because %s", s)
                self.logger.critical("Could not initialize AD Client SSL Context. Will not be using SSL for CLient Authentication")
                self.ssl_context = None
        else:
            self.ssl_context = None

        if "subscriptions" in args:
            self.subscriptions = args["subscriptions"]
        else:
            self.subscriptions = None

        rn = self.config.get("remote_namespaces", {})

        if rn == {}:
            raise ValueError("AppDaemon requires remote namespace mapping and none provided in plugin config")

        for local, remote in rn.items():
            self.rm_ns[remote] = local

        if "forward_stream" in args:
            self.forward_stream = args["forward_stream"]
        else:
            self.forward_stream = None

        self.session = None

        self.logger.info("AD Plugin initialization complete")

        self.metadata = {
            "version": "1.0"
            }

    async def am_reading_messages(self):
        return(self.reading_messages)

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True

        if self.ws is not None:
            self.ws.close()

    #
    # Get initial state
    #

    async def get_complete_state(self):
        ad_state = await self.get_ad_state()

        states = {}

        for namespace in self.rm_ns:
            if namespace in ad_state:
                state = ad_state[namespace]
            else:
                continue

            accept, ns = await self.process_namespace(namespace)
            
            if accept == False: #don't accept namespace
                continue

            states[ns] = state

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
        while not self.stopping:
            try:
                #
                # First Connect to websocket interface
                #
                url = self.ad_url
                if url.startswith('https://'):
                    url = url.replace('https', 'wss', 1)
                elif url.startswith('http://'):
                    url = url.replace('http', 'ws', 1)

                sslopt = {}
                if self.cert_verify is False:
                    sslopt = {'cert_reqs': ssl.CERT_NONE}

                if self.cert_path:
                    sslopt['ca_certs'] = self.cert_path

                self.ws = websocket.create_connection(
                    "{}/stream".format(url), sslopt=sslopt
                )

                #
                # Setup Initial authorizations
                #

                self.logger.info("Using client_name %r to subscribe", self.client_name)

                data = {"request_type" : "hello", 
                        "data" : { 
                            "client_name" : self.client_name,
                                "password" : self.api_key
                                    }
                        }

                await utils.run_in_executor(self, self.ws.send, json.dumps(data))

                res = await utils.run_in_executor(self, self.ws.recv)
                result = json.loads(res)

                self.logger.debug(result)

                if result["response_success"] == True:
                    # We are good to go
                    self.logger.info("Connected to AppDaemon with Version %s", result["data"]["version"])

                else:
                    self.logger.warning("Unable to Authenticate to AppDaemon with Error %s", result["response_error"])
                    self.logger.debug("%s", result)
                    raise ValueError("Error Connecting to AppDaemon Instance using URL %s", self.ad_url)

                #
                # Register Services with Local Services registeration first
                #

                self.AD.services.register_service(self.namespace, "stream", "subscribe", self.call_plugin_service)
                self.AD.services.register_service(self.namespace, "stream", "unsubscribe", self.call_plugin_service)

                services = await self.get_ad_services()

                namespaces = []

                count = 0
                for serv in services:
                    namespace = serv["namespace"]
                    domain = serv["domain"]
                    service = serv["service"]

                    accept, ns = await self.process_namespace(namespace)

                    if accept == False: #reject this namespace
                        continue
                
                    self.AD.services.register_service(ns, domain, service, self.call_plugin_service)

                states = await self.get_complete_state()

                namespaces.extend(list(states.keys()))

                #
                # Subscribe to event stream
                #
                
                if self.subscriptions != None:
                    if "state" in self.subscriptions:
                        for subscription in self.subscriptions["state"]:
                            asyncio.ensure_future(self.run_subscription("state", subscription))

                    if "event" in self.subscriptions:
                        for subscription in self.subscriptions["event"]:
                            asyncio.ensure_future(self.run_subscription("event", subscription))

                namespace = {"namespace" : self.namespace, "namespaces" : namespaces}

                await self.AD.plugins.notify_plugin_started(self.name, namespace, self.metadata, states, first_time)

                #
                # check if Local event upload is required and subscribe
                #

                if self.forward_stream != None:

                    self.restricted_namespaces = self.forward_stream.get("restricted_namespaces", [])

                    if not isinstance(self.restricted_namespaces, list):
                        self.restricted_namespaces = [self.restricted_namespaces]

                    self.non_restricted_namespaces = self.forward_stream.get("non_restricted_namespaces", [])

                    if not isinstance(self.non_restricted_namespaces, list):
                        self.non_restricted_namespaces = [self.non_restricted_namespaces]

                    # register callback to get local stream

                    allowed_namespaces = []
                    if self.non_restricted_namespaces != []: #only allowed namespaces
                        allowed_namespaces.extend(self.non_restricted_namespaces)

                    if allowed_namespaces != []:
                        for namespace in allowed_namespaces:
                            self.AD.http.stream.local_register_stream(self.client_name, self.forward_local_stream, namespace)
                    
                    else: #subscribe to all events
                        self.AD.http.stream.local_register_stream(self.client_name, self.forward_local_stream, "*")

                    #setup to receive instructions for this local instance from the remote one
                    subscription = {"namespace" : "{}*".format(self.client_name),
                                    "event" : "*"
                                }
                    asyncio.ensure_future(self.run_subscription("event", subscription))

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

                    if "response_type" in result: #not an event stream but a response type
                        if "response_id" in result: #its for a message with expected result
                            response_id = result.get("response_id")

                            if response_id in self.stream_results: #if to be picked up
                                self.stream_results[response_id]["response"] = result
                                self.stream_results[response_id]["event"].set() #time for pickup

                    else:
                        namespace = result.pop("namespace")

                        accept, ns = await self.process_namespace(namespace)

                        if accept == True: #accept data
                            res = None
                            response = None
                            if result["data"].get("__AD_ORIGIN", None) == self.client_name:
                                pass #it originated from this instance so disregard it

                            elif result["event_type"] == "service_registered": #a service was registered
                                domain = result["data"]["domain"]
                                service = result["data"]["service"]
                                self.AD.services.register_service(ns, domain, service, self.call_plugin_service)
                            
                            elif result["event_type"] == "get_state": #get state
                                entity_id = result["data"].get("entity_id", None)
                                res = self.AD.state.get_entity(ns, entity_id, self.client_name)  
                                response = "get_state_response"
                            
                            elif result["event_type"] == "get_services": #get services
                                services = self.AD.services.list_services()
                                res = {}

                                if ns == None:
                                    res = services
                                else:
                                    for service in services:
                                        if service["namespace"] == ns:
                                            res.update(service)

                                response = "get_services_response"
                            
                            elif result["event_type"] == "call_service": #a service call is being made by remote device
                                domain = result["data"]["domain"]
                                service = result["data"]["service"]
                                service_data = result["data"]["data"]
                                res = await self.AD.services.call_service(ns, domain, service, service_data)
                                response = "call_service_response"

                            else:
                                result["data"]["__AD_ORIGIN"] = self.client_name
                                await self.AD.events.process_event(ns, result)

                            if res != None:
                                data = {}
                                data["__AD_ORIGIN"] = self.client_name
                                data["response"] = res

                                request_id = result.pop("request_id", uuid.uuid4().hex)

                                if ns == None:
                                    ns = self.client_name

                                kwargs = {
                                    "request_type": "forwarded_stream",
                                    "data" : {
                                    "namespace" : ns,
                                    "response_type" : response,
                                    "response_id" : request_id,
                                    "data" : data
                                    }
                                }

                                await utils.run_in_executor(self, self.ws.send, json.dumps(kwargs))

            except:
                if self.forward_stream != None:
                    # unregister callback from getting local stream
                    self.AD.http.stream.unregister_stream(self.client_name)

                self.reading_messages = False
                self.is_booting = True
                self.ws = None

                if not already_notified:
                    await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                    already_notified = True
                if not self.stopping:
                    self.logger.warning("Disconnected from AppDaemon, retrying in 5 seconds")
                    self.logger.debug('-' * 60)
                    self.logger.debug("Unexpected error:")
                    self.logger.debug('-' * 60)
                    self.logger.debug(traceback.format_exc())
                    self.logger.debug('-' * 60)
                    await asyncio.sleep(5)

        self.logger.info("Disconnecting from AppDaemon")
    
    def get_namespace(self):
        return self.namespace

    #
    # Utility functions
    #

    def utility(self):
        #self.logger.debug("Utility")
        return None

    #
    # AppDaemon Interactions
    #

    @ad_check
    async def call_plugin_service(self, namespace, domain, service, data):
        self.logger.debug("call_plugin_service() namespace=%s domain=%s service=%s data=%s", namespace, domain, service, data)
        res = None

        if namespace == self.namespace and domain == "stream": #its a service to the stream
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
                        self.logger.warning("No handle provided, please provide handle")
                else:
                    self.logger.warning("Cancel Type not given in data %s", data)
            
            else:
                self.logger.warning("Unrecognised service given %s", service)

            return res

        if namespace not in list(self.rm_ns.values()):
            self.logger.warning("Unidentified namespace given as %s", namespace)
            return res

        else:
            ns = list(self.rm_ns.keys())[list(self.rm_ns.values()).index(namespace)]

        request_id = uuid.uuid4().hex
        kwargs = {
            "request_type": "call_service",
            "request_id" : request_id,
            "data" : {
            "namespace" : ns,
            "service" : service,
            "domain" : domain,
            "data" : data
            }
        }

        res = await self.process_request(request_id, kwargs)

        if res != None:
            res = res["data"]
        
        return res
    
    async def stream_subscribe(self, subscribe_type, data):
        self.logger.debug("stream_subscribe() subscribe_type=%s data=%s", subscribe_type, data)
        request_id = uuid.uuid4().hex
        result = None

        if subscribe_type == "state":
            kwargs = {
                "request_type": "listen_state", 
                "request_id" : request_id
            }

            kwargs["data"] = {}
            kwargs["data"].update(data)

            res = await self.process_request(request_id, kwargs)
            
            if res != None:
                result = res["data"]

        if subscribe_type == "event":
            kwargs = {
                "request_type": "listen_event",
                "request_id" : request_id
            }

            kwargs["data"] = {}
            kwargs["data"].update(data)

            res = await self.process_request(request_id, kwargs)
            
            if res != None:
                result = res["data"]
        
        return result
    
    async def stream_unsubscribe(self, unsubscribe_type, handle):
        self.logger.debug("stream_unsubscribe() unsubscribe_type=%s handle=%s", unsubscribe_type, handle)
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
                "request_id" : request_id,
                "data" : {
                    "handle" : handle
                }
            }

        res = await self.process_request(request_id, kwargs)
            
        if res != None:
            result = res["data"]

        return result

    @ad_check
    async def forward_local_stream(self, data):
        namespace = data.pop("namespace")
        forward = True

        if self.ws == None:
            forward = False

        elif namespace in list(self.rm_ns.values()): #meaning it was gotten from remote AD
            forward = False
        
        elif self.restricted_namespaces != [] and await self.check_namespace(namespace, self.restricted_namespaces): #don't pass these ones
            forward = False
        
        elif self.non_restricted_namespaces != [] and not await self.check_namespace(namespace, self.non_restricted_namespaces): #pass these ones
            forward = False

        if forward == True: #it is good to go
            namespace = "{}_{}".format(self.client_name, namespace)
            data["namespace"] = namespace
            data["data"]["__AD_ORIGIN"] = self.client_name #indicate where it came from

            kwargs = {
                    "request_type": "forwarded_stream",
                    "data" : data
                }

            #
            # first log event needs to be formatted to use the right signature
            #

            if data["event_type"] == "__AD_LOG_EVENT":
                if "asctime" in data["data"]:
                    ts = copy.deepcopy(data["data"]["asctime"])
                    data["data"]["ts"] = ts

            if data["event_type"] == "state_changed":# for test
                return

            await utils.run_in_executor(self, self.ws.send, json.dumps(kwargs))

    async def get_ad_state(self, entity_id=None):
        self.logger.debug("get_ad_state()")

        state = {}

        for namespace in list(self.rm_ns.keys()):
            request_id = uuid.uuid4().hex
            kwargs = {
                "request_type": "get_state",
                "request_id" : request_id,
                "data" : {
                    "namespace" : namespace
                }
            }

            result = await self.process_request(request_id, kwargs)

            if result != None:
                if result["data"] != None:
                    state[namespace] = result["data"]
                
                else:
                    state[namespace] = None
                    self.logger.warning("No state data available for Namespace %r", self.rm_ns[namespace])

            else:
                state[namespace] = None
                self.logger.warning("There was an error while processing data for Namespace %r", self.rm_ns[namespace])
            
        return state

    async def get_ad_services(self):
        self.logger.debug("get_ad_services()")

        services = {}
        request_id = uuid.uuid4().hex
        kwargs = {
            "request_type": "get_services",
            "request_id" : request_id
        }

        result = await self.process_request(request_id, kwargs)

        if result != None:
            services = result["data"]
        
        return services

    @ad_check
    async def fire_plugin_event(self, event, namespace, **data):
        self.logger.debug("fire_event: %s, %s %s", event, namespace, data)

        event_clean = quote(event, safe="")

        if namespace not in list(self.rm_ns.values()):
            self.logger.warning("Unidentified namespace given as %s", namespace)
            return None

        else:
            ns = list(self.rm_ns.keys())[list(self.rm_ns.values()).index(namespace)]

        data["__AD_ORIGIN"] = self.client_name

        request_id = uuid.uuid4().hex
        kwargs = {
            "request_type": "fire_event", 
            "data" : { 
            "namespace" : ns,
            "event" : event,
            "data" : data
            }
        }
        await utils.run_in_executor(self, self.ws.send, json.dumps(kwargs))
        
        return None
    
    async def process_request(self, request_id, data):
        res = None
        result = None

        if self.is_booting == True:
            await utils.run_in_executor(self, self.ws.send, json.dumps(data))
            res = await utils.run_in_executor(self, self.ws.recv)
        else:
            self.stream_results[request_id] = {}
            self.stream_results[request_id]["event"] = asyncio.Event()
            await utils.run_in_executor(self, self.ws.send, json.dumps(data))

            try:
                await asyncio.wait_for(self.stream_results[request_id]["event"].wait(), 5.0)
                res = self.stream_results[request_id]["response"]
                del self.stream_results[request_id]
            except asyncio.TimeoutError:
                self.logger.warning("Timeout Error occured while processing %s", data["request_type"])
                self.logger.debug("Timeout Error occured while trying to process data %s", data)

        if res != None:
            try:
                result = json.loads(res)
            except:
                result = res

        return result
    
    async def process_namespace(self, namespace):
        accept = True
        ns = None

        if namespace in self.rm_ns:
            ns = self.rm_ns[namespace]
        
        elif namespace.startswith("{}".format(self.client_name)):
            # it is for a local namespace, fired by the remote one
            ns = namespace.replace("{}".format(self.client_name), "")

            if ns == "":
                ns = None

            elif ns == "_":
                accept = False
        
        else:
            accept = False

        return accept, ns

    async def check_namespace(self, namespace, namespaces):
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

        if namespace.startswith(self.client_name): #for local instance remote subscription
            accept = True
        else:
            accept = await self.check_namespace(namespace, self.rm_ns)

        if accept is True:
            result = await self.stream_subscribe(sub_type, subscription)
            self.logger.info("Handle for Subscription %r is %r", subscription, result)
        else:
            self.logger.warning("Cannot Subscribe to Namespace %r, as not defined in remote namespaces", namespace)
