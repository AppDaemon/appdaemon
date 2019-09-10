import asyncio
import json
import ssl
import websocket
import traceback
import aiohttp
import pytz
from deepdiff import DeepDiff
from urllib.parse import quote

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
        self.remote_namespaces = {}

        self.logger.info("AD Plugin Initializing")

        self.name = name

        if "namespace" in args:
            self.namespace = args["namespace"]
        else:
            self.namespace = "default"

        if "ad_url" in args:
            self.ad_url = args["ad_url"]
        else:
            self.ad_url = None
            self.logger.warning("ad_url not found in AD configuration - module not initialized")
        
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
            self.api_ssl_certificate = args["api_ssl_certificate"]
        else:
            self.api_ssl_certificate = None

        if "api_ssl_key" in args:
            self.api_ssl_key = args["api_ssl_key"]
        else:
            self.api_ssl_key = None

        if "timeout" in args:
            self.timeout = args["timeout"]
        else:
            self.timeout = None

        if "commtype" in args:
            self.commtype = args["commtype"]
        else:
            self.commtype = "WS"
        

        rn = self.config.get("remote_namespaces", {})

        if rn == {}:
            raise ValueError("AppDaemon requires remote namespace mapping and none provided in plugin config")

        for local, remote in rn.items():
            self.remote_namespaces[remote] = local

        self.session = None

        self.logger.info("AD Plugin initialization complete")

        self.metadata = {
            "version": "1.0"}

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

        for namespace in self.remote_namespaces:
            if namespace in ad_state["state"]:
                state = ad_state["state"][namespace]
            else:
                state = {}

            accept, ns = await self.process_namespace(namespace)
            
            if accept == False: #don't accept namespace
                continue

            states[ns] = state

        self.logger.debug("Got state")
        self.logger.debug("*** Sending Complete State: %s ***", states)
        return states

    async def process_namespace(self, namespace):
        accept= True
        ns = None

        if namespace in self.remote_namespaces:
            ns = self.remote_namespaces[namespace]
        
        else:
            accept = False

        return accept, ns

    #
    # Get AD Metadata
    #

    async def get_metadata(self):
        return self.metadata

    #
    # Handle state updates
    #

    async def get_updates(self):

        _id = 0

        already_notified = False
        first_time = True
        while not self.stopping:
            _id += 1
            try:
                #
                # Connect to websocket interface
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

                data = "{} ADPlugin".format(self.name)

                await utils.run_in_executor(self, self.ws.send, data)

                res = await utils.run_in_executor(self, self.ws.recv)
                #result = json.loads(res)
                result = {"type": res} #just to avoid breaking for now

                self.logger.info("Connected to AppDaemon %s", res)
                #
                # Check if auth required, if so send password
                #
                if result["type"] == "auth_required":
                    if self.api_key is not None:
                        auth = json.dumps({
                            "type": "auth",
                            "api_password": self.api_key
                        })
                    else:
                        raise ValueError("AppDaemon requires authentication and none provided in plugin config")

                    await utils.run_in_executor(self, self.ws.send, auth)
                    result = json.loads(self.ws.recv())
                    if result["type"] != "auth_ok":
                        self.logger.warning("Error in authentication")
                        raise ValueError("Error in authentication")
                #
                # Subscribe to event stream
                #
                sub = json.dumps({
                    "id": _id,
                    "type": "subscribe_events"
                })

                #await utils.run_in_executor(self, self.ws.send, sub)
                #result = json.loads(self.ws.recv())
                #if not (result["id"] == _id and result["type"] == "result" and
                #                result["success"] is True):
                #    self.logger.warning("Unable to subscribe to AppDaemon events, id = %s", _id)
                #    self.logger.warning(result)
                #    raise ValueError("Error subscribing to AppDaemon Events")

                #
                # Register Services
                #
                self.services = await self.get_ad_services()

                state_services = self.services["state"]
                namespaces = []

                for services in state_services:
                    namespace = services["namespace"]
                    domain = services["domain"]
                    service = services["service"]

                    accept, ns = await self.process_namespace(namespace)

                    if accept == False: #reject this namespace
                        continue

                    self.AD.services.register_service(ns, domain, service, self.call_plugin_service)

                # We are good to go
                self.reading_messages = True
                states = await self.get_complete_state()

                for ns in states:
                    namespaces.append(ns)

                namespace = {"namespace" : self.namespace, "remote_namespaces" : namespaces}

                await self.AD.plugins.notify_plugin_started(self.name, namespace, self.metadata, states, first_time)

                first_time = False
                already_notified = False

                #
                # Loop forever consuming events
                #
                while not self.stopping:
                    ret = await utils.run_in_executor(self, self.ws.recv)
                    result = json.loads(ret)

                    #if not (result["id"] == _id and result["event_type"] == "event"):
                    #    self.logger.warning("Unexpected result from AppDaemon, id = %s", _id)
                    #    self.logger.warning(result)
                    
                    namespace = result["namespace"]
                    del result["namespace"]

                    accept, ns = await self.process_namespace(namespace)

                    if accept == True: #accept data
                        await self.AD.events.process_event(ns, result)

                self.reading_messages = False

            except:
                self.reading_messages = False
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

        config = (await self.AD.plugins.get_plugin_object(self.namespace)).config
        
        if "api_key" in config:
            headers = {'x-ad-access': config["api_key"]}
        else:
            headers = {}

        if namespace not in list(self.remote_namespaces.values()):
            self.logger.warning("Unidentified namespace given as %s", namespace)
            return None

        else:
            ns = list(self.remote_namespaces.keys())[list(self.remote_namespaces.values()).index(namespace)]

        apiurl = "{}/api/appdaemon/service/{}/{}/{}".format(config["ad_url"], ns, domain, service)

        try:
            
            r = await self.session.post(apiurl, headers=headers, json=data, verify_ssl=self.cert_verify)
            
            if r.status == 200 or r.status == 201:
                result = await r.json()

                print(result)

            else:
                self.logger.warning("Error calling AppDaemon service %s/%s/%s", namespace, domain, service)
                txt = await r.text()
                self.logger.warning("Code: %s, error: %s", r.status, txt)
                result = None

            return result

        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning("Timeout in call_service(%s/%s/%s, %s)", namespace, domain, service, data)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("AD Disconnected unexpectedly during call_service()")
        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error during call_plugin_service()")
            self.logger.warning("Service: %s.%s.%s Arguments: %s", namespace, domain, service, data)
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)
            return None

    async def get_ad_state(self, entity_id=None):

        if self.api_key is not None:
            headers = {'x-ad-access': self.api_key}
        else:
            headers = {}

        if entity_id is None:
            apiurl = "{}/api/appdaemon/state".format(self.ad_url)
        else:
            apiurl = "{}/api/appdaemon/state/{}".format(self.ad_url, entity_id)

        self.logger.debug("get_ad_state: url is %s", apiurl)

        r = await self.session.get(apiurl, headers=headers, verify_ssl=self.cert_verify)

        if r.status == 200 or r.status == 201:
            state = await r.json()

        else:
            self.logger.warning("Error getting AppDaemon state for %s", entity_id)
            txt = await r.text()
            self.logger.warning("Code: %s, error: %s", r.status, txt)
            state = None

        return state

    async def get_ad_services(self):
        try:
            self.logger.debug("get_ad_services()")

            if self.session is None:
                #
                # Set up HTTP Client
                #
                conn = aiohttp.TCPConnector()
                self.session = aiohttp.ClientSession(connector=conn)

            if self.api_key is not None:
                headers = {'x-ad-access': self.api_key, "Content-Type" : "application/json"}
            else:
                headers = {}

            apiurl = "{}/api/appdaemon/service/".format(self.ad_url)

            self.logger.debug("get_ad_services: url is %s", apiurl)
            r = await self.session.get(apiurl, headers=headers, verify_ssl=self.cert_verify)

            r.raise_for_status()

            services = await r.json()

            return services
        except:
            self.logger.warning("Error getting services - retrying")
            raise

    @ad_check
    async def fire_plugin_event(self, event, namespace, **kwargs):
        self.logger.debug("fire_event: %s, %s %s", event, namespace, kwargs)

        config = (await self.AD.plugins.get_plugin_object(self.namespace)).config

        if "api_key" in config:
            headers = {'x-ad-access': config["api_key"]}
        else:
            headers = {}

        event_clean = quote(event, safe="")

        if namespace not in list(self.remote_namespaces.values()):
            self.logger.warning("Unidentified namespace given as %s", namespace)
            return None

        else:
            ns = list(self.remote_namespaces.keys())[list(self.remote_namespaces.values()).index(namespace)]

        apiurl = "{}/api/appdaemon/event/{}/{}".format(config["ad_url"], ns, event_clean)
        try:
            r = await self.session.post(apiurl, headers=headers, json=kwargs, verify_ssl=self.cert_verify)
            r.raise_for_status()
            state = await r.json(content_type="application/octet-stream")
            return state
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning("Timeout in fire_event(%s, %s, %s)", event, namespace, kwargs)
        except aiohttp.client_exceptions.ServerDisconnectedError:
            self.logger.warning("AD Disconnected unexpectedly during fire_event()")
        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error fire_plugin_event()")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)
            return None
