import asyncio
import json
import os
import re
import time
import traceback
import concurrent.futures
from urllib.parse import urlparse
import feedparser
from aiohttp import web
import ssl
import bcrypt
import threading
import uuid

import appdaemon.dashboard as addashboard
import appdaemon.utils as utils
import appdaemon.stream as stream

from appdaemon.appdaemon import AppDaemon

def securedata(myfunc):
    """
    Take care of streams and service calls
    """

    async def wrapper(*args):

        self = args[0]
        if self.password is None:
            return await myfunc(*args)
        else:
            if "adcreds" in args[1].cookies:
                match = await utils.run_in_executor(self.loop, self.executor, bcrypt.checkpw, str.encode(self.password), str.encode(args[1].cookies["adcreds"]))
                if match:
                    return await myfunc(*args)
                else:
                    return await self.error(args[1])
            else:
                return await self.error(args[1])

    return wrapper


def secure(myfunc):
    """
    Take care of screen based security
    """

    async def wrapper(*args):

        self = args[0]
        if self.password == None:
            return await myfunc(*args)
        else:
            if "adcreds" in args[1].cookies:
                match = await utils.run_in_executor(self.loop, self.executor, bcrypt.checkpw,
                                                    str.encode(self.password),
                                                    str.encode(args[1].cookies["adcreds"]))
                if match:
                    return await myfunc(*args)
                else:
                    return await self.forcelogon(args[1])
            elif "password" in args[1].query and args[1].query["password"] == self.password:
                return await myfunc(*args)
            else:
                return await self.forcelogon(args[1])

    return wrapper


class HTTP:

    def __init__(self, ad: AppDaemon, loop, logging, appdaemon, dashboard, admin, api, http):

        self.AD = ad
        self.logging = logging
        self.logger = ad.logging.get_child("_http")
        self.access = ad.logging.get_access()

        self.appdaemon = appdaemon
        self.dasboard = dashboard
        self.admin = admin
        self.http = http
        self.api = api

        self.password = None
        self._process_arg("password", http)

        self.url = None
        self._process_arg("url", http)

        self.work_factor = 8
        self._process_arg("work_factor", http)

        self.ssl_certificate = None
        self._process_arg("ssl_certificate", http)

        self.ssl_key = None
        self._process_arg("ssl_key", http)

        self.transport = "ws"
        self._process_arg("transport", http)
        self.logger.info("Using %s for event stream", self.transport)

        self.stopping = False

        self.endpoints = {}
        self.endpoints_lock = threading.RLock()

        try:
            url = urlparse(self.url)

            net = url.netloc.split(":")
            self.host = net[0]
            try:
                self.port = net[1]
            except IndexError:
                self.port = 80

            if self.host == "":
                raise ValueError("Invalid host for 'url'")

            self.app = web.Application()

            # Setup event stream

            self.stream = stream.ADStream(self.AD, self.app, self.transport, self.on_connect, self.on_message)

            self.loop = loop
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

            if self.ssl_certificate is not None and self.ssl_key is not None:
                context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
                context.load_cert_chain(self.ssl_certificate, self.ssl_key)
            else:
                context = None

            # Start Dashboards

            if dashboard is not None:
                self.logger.info("Starting Dashboards")

                self.dashboard_dir = None
                self._process_arg("dashboard_dir", dashboard)

                self.compile_on_start = True
                self._process_arg("compile_on_start", dashboard)

                self.force_compile = False
                self._process_arg("force_compile", dashboard)

                self.profile_dashboard = False
                self._process_arg("profile_dashboard", dashboard)

                self.rss_feeds = None
                self._process_arg("rss_feeds", dashboard)

                self.fa4compatibility = False
                self._process_arg("fa4compatibility", dashboard)

                self.config_dir = None
                self._process_arg("config_dir", dashboard)

                if "rss_feeds" in dashboard:
                    self.rss_feeds = []
                    for feed in dashboard["rss_feeds"]:
                        if feed["target"].count('.') != 1:
                            self.logger.warning("Invalid RSS feed target: %s", feed["target"])
                        else:
                            self.rss_feeds.append(feed)

                self.rss_update = None
                self._process_arg("rss_update", dashboard)

                self.rss_last_update = None

                # find dashboard dir

                if self.dashboard_dir is None:
                    if self.config_dir is None:
                        self.dashboard_dir = utils.find_path("dashboards")
                    else:
                        self.dashboard_dir = os.path.join(self.config_dir, "dashboards")


                #
                # Setup compile directories
                #
                if self.config_dir is None:
                    self.compile_dir = utils.find_path("compiled")
                else:
                    self.compile_dir = os.path.join(self.config_dir, "compiled")

                self.dashboard_obj = addashboard.Dashboard(self.config_dir, self.logging,
                                                 dash_compile_on_start=self.compile_on_start,
                                                 dash_force_compile=self.force_compile,
                                                 profile_dashboard=self.profile_dashboard,
                                                 dashboard_dir=self.dashboard_dir,
                                                 fa4compatibility=self.fa4compatibility,
                                                 transport=self.transport
                                                 )
                self.setup_dashboard_routes()

            else:
                self.logger.info("Dashboards Disabled")

            if api is not None:
                self.logger.info("Starting API")
                self.setup_api()
            else:
                self.logger.info("API is disabled")

            #if "admin" in appdaemon and "port" in appdaemon["admin"]:
            #    self.logger.info("Starting Admin Interface on port %s", appdaemon["admin"]["port"])
            #else:
            #    self.logger.info("Admin Interface is disabled")

            handler = self.app.make_handler()

            f = loop.create_server(handler, "0.0.0.0", int(self.port), ssl=context)
            loop.create_task(f)
            loop.create_task(self.update_rss())

        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error in HTTP module")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)

    def stop(self):
        self.stopping = True

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    @staticmethod
    def check_password(password, hash):
        return bcrypt.checkpw, str.encode(password), str.encode(hash)

    async def forcelogon(self, request):
        response = await utils.run_in_executor(self.loop, self.executor, self.dashboard_obj.get_dashboard_list,
                                                    {"logon": 1})
        return web.Response(text=response, content_type="text/html")

    async def logon(self, request):
        data = await request.post()
        password = data["password"]

        if password == self.password:
            self.access.info("Succesful logon from %s", request.host)
            hashed = bcrypt.hashpw(str.encode(self.password), bcrypt.gensalt(self.work_factor))

            # utils.verbose_log(conf.dash, "INFO", hashed)

            response = await self.list_dash_no_secure(request)
            response.set_cookie("adcreds", hashed.decode("utf-8"))

        else:
            self.access.warning("Unsuccessful logon from {}", request.host)
            response = await self.list_dash(request)

        return response


    # Views


    # noinspection PyUnusedLocal
    @secure
    async def list_dash(self, request):
        return await self._list_dash(request)

    async def list_dash_no_secure(self, request):
        return await self._list_dash(request)

    async def _list_dash(self, request):
        response = await utils.run_in_executor(self.loop, self.executor, self.dashboard_obj.get_dashboard_list)
        return web.Response(text=response, content_type="text/html")

    @secure
    async def load_dash(self, request):
        name = request.match_info.get('name', "Anonymous")
        params = request.query
        skin = params.get("skin", "default")
        recompile = params.get("recompile", False)
        if recompile == '1':
            recompile = True

        response = await utils.run_in_executor(self.loop, self.executor, self.dashboard_obj.get_dashboard, name, skin, recompile)

        return web.Response(text=response, content_type="text/html")

    async def update_rss(self):
        # Grab RSS Feeds

        if self.rss_feeds is not None and self.rss_update is not None:
            while not self.stopping:
                try:
                    if self.rss_last_update == None or (self.rss_last_update + self.rss_update) <= time.time():
                        self.rss_last_update = time.time()

                        for feed_data in self.rss_feeds:
                            feed = await utils.run_in_executor(self.loop, self.executor, feedparser.parse, feed_data["feed"])

                            if "bozo_exception" in feed:
                                self.logger.warning("Error in RSS feed %s: %s", feed_data["feed"], feed["bozo_exception"])
                            else:
                                new_state = {"feed": feed}

                                # RSS Feeds always live in the default namespace
                                self.AD.state.set_state("default", feed_data["target"], new_state)

                                data = {"event_type": "state_changed",
                                        "data": {"entity_id": feed_data["target"], "new_state": new_state}}

                                await self.ws_update("default", data)

                    await asyncio.sleep(1)
                except:
                    self.logger.warning('-' * 60)
                    self.logger.warning("Unexpected error in dashboard thread")
                    self.logger.warning('-' * 60)
                    self.logger.warning(traceback.format_exc())
                    self.logger.warning('-' * 60)



    @securedata
    async def get_state(self, request):

        entity_id = request.match_info.get('entity')
        namespace = request.match_info.get('namespace')

        state = self.AD.state.get_entity(namespace, entity_id)

        return web.json_response({"state": state})

    # noinspection PyUnusedLocal
    @securedata
    async def call_service(self, request):
        try:
            data = await request.post()
            args = {}
            service = data["service"]
            namespace = data["namespace"]
            for key in data:
                if key == "service" or key == "namespace":
                    pass
                elif key == "rgb_color":
                    m = re.search('\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', data[key])
                    if m:
                        r = m.group(1)
                        g = m.group(2)
                        b = m.group(3)
                        args["rgb_color"] = [r, g, b]
                elif key == "xy_color":
                    m = re.search('\s*(\d+\.\d+)\s*,\s*(\d+\.\d+)', data[key])
                    if m:
                        x = m.group(1)
                        y = m.group(2)
                        args["xy_color"] = [x, y]
                elif key == "json_args":
                      json_args = json.loads(data[key])
                      for k in json_args.keys():
                         args[k] = json_args[k]
                else:
                    args[key] = data[key]

            plugin = self.AD.plugins.get_plugin_object(namespace)
            await plugin.call_service(service, **args)
            return web.Response(status=200)

        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error in call_service()")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)
            return web.Response(status=500)

    # noinspection PyUnusedLocal
    @staticmethod
    async def not_found(request):
        return web.Response(status=404)

    # noinspection PyUnusedLocal
    @staticmethod
    async def error(request):
        return web.Response(status=401)

    # Stream Handling

    async def ws_update(self, namespace, data):

        if data["event_type"] == "state_changed" or data["event_type"] == "hadashboard":
            data["namespace"] = namespace

            await self.stream.send_update(data)


    async def on_message(self, data):
        self.access.info("New dashboard connected: %s", data)

    async def on_connect(self):
        pass

    # Routes, Status and Templates

    def setup_dashboard_routes(self):
        self.app.router.add_get('/favicon.ico', self.not_found)
        self.app.router.add_get('/{gfx}.png', self.not_found)
        self.app.router.add_post('/logon', self.logon)
        self.app.router.add_post('/call_service', self.call_service)
        self.app.router.add_get('/state/{namespace}/{entity}', self.get_state)
        self.app.router.add_get('/', self.list_dash)
        self.app.router.add_get('/{name}', self.load_dash)

        # Setup Templates

        # Add static path for JavaScript

        self.app.router.add_static('/javascript', self.dashboard_obj.javascript_dir)
        self.app.router.add_static('/compiled_javascript', self.dashboard_obj.compiled_javascript_dir)

        # Add static path for css
        self.app.router.add_static('/css', self.dashboard_obj.css_dir)
        self.app.router.add_static('/compiled_css', self.dashboard_obj.compiled_css_dir)

        # Add path for custom_css if it exists

        custom_css = os.path.join(self.dashboard_obj.config_dir, "custom_css")
        if os.path.isdir(custom_css):
            self.app.router.add_static('/custom_css', custom_css)

        # Add static path for fonts
        self.app.router.add_static('/fonts', self.dashboard_obj.fonts_dir)

        # Add static path for webfonts
        self.app.router.add_static('/webfonts', self.dashboard_obj.webfonts_dir)

        # Add static path for images
        self.app.router.add_static('/images', self.dashboard_obj.images_dir)

    # API

    def term_object(self, name):
        with self.endpoints_lock:
            if name in self.endpoints:
                del self.endpoints[name]

    @staticmethod
    def get_response(code, error):
        res = "<html><head><title>{} {}</title></head><body><h1>{} {}</h1>Error in API Call</body></html>".format(code, error, code, error)
        return res

    async def call_api(self, request):

        code = 200
        ret = ""

        app = request.match_info.get('app')

        if self.password is not None:
            if (("x-ad-access" not in request.headers) or (request.headers["x-ad-access"] != self.password)) \
                    and (("api_password" not in request.query) or (request.query["api_password"] != self.password)):

                code = 401
                response = "Unauthorized"
                res = self.get_response(code, response)
                self.access.info("API Call to %s: status: %s %s", app, code, response)
                return web.Response(body=res, status=code)

        try:
            args = await request.json()
        except json.decoder.JSONDecodeError:
            code = 400
            response = "JSON Decode Error"
            res = self.get_response(code, response)
            self.logger.warning("API Call to %s: status: %s %s", app, code, response)
            return web.Response(body = res, status = code)

        try:
            ret, code = await self.dispatch_app_by_name(app, args)
        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error during API call")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)

        if code == 404:
            response = "App Not Found"
            res = self.get_response(code, response)
            self.access.info("API Call to %s: status: %s %s", app, code, response)
            return web.Response(body = res, status = code)

        response = "OK"
        res = self.get_response(code, response)
        self.access.info("API Call to %s: status: %s %s", app, code, response)

        return web.json_response(ret, status = code)

    # Routes, Status and Templates

    def setup_api(self):
        self.app.router.add_post('/api/appdaemon/{app}', self.call_api)

    def register_endpoint(self, cb, name):

        handle = uuid.uuid4()

        with self.endpoints_lock:
            if name not in self.endpoints:
                self.endpoints[name] = {}
            self.endpoints[name][handle] = {"callback": cb, "name": name}

        return handle

    def unregister_endpoint(self, handle, name):
        with self.endpoints_lock:
            if name in self.endpoints and handle in self.endpoints[name]:
                del self.endpoints[name][handle]

    async def dispatch_app_by_name(self, name, args):
        with self.endpoints_lock:
            callback = None
            for app in self.endpoints:
                for handle in self.endpoints[app]:
                    if self.endpoints[app][handle]["name"] == name:
                        callback = self.endpoints[app][handle]["callback"]
        if callback is not None:
            return await utils.run_in_executor(self.AD.loop, self.AD.executor, callback, args)
        else:
            return '', 404

