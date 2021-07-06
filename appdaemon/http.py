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
import uuid
from jinja2 import Environment, FileSystemLoader, select_autoescape

import appdaemon.dashboard as addashboard
import appdaemon.utils as utils
import appdaemon.stream.adstream as stream
import appdaemon.admin as adadmin

from appdaemon.appdaemon import AppDaemon


def securedata(myfunc):
    """
    Take care of streams and service calls
    """

    async def wrapper(*args):

        self = args[0]
        request = args[1]
        if self.password is None:
            return await myfunc(*args)
        elif "adcreds" in request.cookies:
            match = await utils.run_in_executor(
                self, bcrypt.checkpw, str.encode(self.password), str.encode(request.cookies["adcreds"]),
            )
            if match:
                return await myfunc(*args)
        elif ("x-ad-access" in request.headers) and (request.headers["x-ad-access"] == self.password):
            return await myfunc(*args)
        elif "api_password" in request.query and request.query["api_password"] == self.password:
            return await myfunc(*args)
        else:
            return self.get_response(request, "401", "Unauthorized")

    return wrapper


def secure(myfunc):
    """
    Take care of screen based security
    """

    async def wrapper(*args):

        self = args[0]
        request = args[1]
        if self.password is None:
            return await myfunc(*args)
        else:
            if "adcreds" in request.cookies:
                match = await utils.run_in_executor(
                    self, bcrypt.checkpw, str.encode(self.password), str.encode(request.cookies["adcreds"]),
                )
                if match:
                    return await myfunc(*args)
                else:
                    return await self.forcelogon(request)
            else:
                return await self.forcelogon(request)

    return wrapper


def route_secure(myfunc):
    """
    Take care of streams and service calls
    """

    async def wrapper(*args):

        self = args[0]
        request = args[1]
        if self.password is None or self.valid_tokens == []:
            return await myfunc(*args)

        elif "adcreds" in request.cookies:
            match = await utils.run_in_executor(
                self, bcrypt.checkpw, str.encode(self.password), str.encode(request.cookies["adcreds"])
            )
            if match:
                return await myfunc(*args)

        elif "token" in request.query and request.query["token"] in self.valid_tokens:
            return await myfunc(*args)

        else:
            return self.get_response(request, "401", "Unauthorized")

    return wrapper


class HTTP:
    def __init__(self, ad: AppDaemon, loop, logging, appdaemon, dashboard, admin, aui, api, http):

        self.AD = ad
        self.logging = logging
        self.logger = ad.logging.get_child("_http")
        self.access = ad.logging.get_access()

        self.appdaemon = appdaemon
        self.dashboard = dashboard
        self.dashboard_dir = None
        self.admin = admin
        self.aui = aui
        self.http = http
        self.api = api
        self.runner = None

        self.template_dir = os.path.join(os.path.dirname(__file__), "assets", "templates")

        self.password = None
        self.valid_tokens = []
        self.url = None
        self.work_factor = 12
        self.ssl_certificate = None
        self.ssl_key = None
        self.transport = "ws"

        self.config_dir = None
        self._process_arg("config_dir", dashboard)

        self.static_dirs = {}

        self._process_http(http)

        self.stopping = False

        self.endpoints = {}
        self.app_routes = {}

        self.dashboard_obj = None
        self.admin_obj = None

        self.install_dir = os.path.dirname(__file__)

        self.javascript_dir = os.path.join(self.install_dir, "assets", "javascript")
        self.template_dir = os.path.join(self.install_dir, "assets", "templates")
        self.css_dir = os.path.join(self.install_dir, "assets", "css")
        self.fonts_dir = os.path.join(self.install_dir, "assets", "fonts")
        self.webfonts_dir = os.path.join(self.install_dir, "assets", "webfonts")
        self.images_dir = os.path.join(self.install_dir, "assets", "images")

        # AUI
        self.aui_dir = os.path.join(self.install_dir, "assets", "aui")
        self.aui_css_dir = os.path.join(self.install_dir, "assets", "aui/css")
        self.aui_js_dir = os.path.join(self.install_dir, "assets", "aui/js")

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

            if "headers" in self.http:
                self.app.on_response_prepare.append(self.add_response_headers)

            # Setup event stream

            self.stream = stream.ADStream(self.AD, self.app, self.transport)

            self.loop = loop
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

            if self.ssl_certificate is not None and self.ssl_key is not None:
                self.context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
                self.context.load_cert_chain(self.ssl_certificate, self.ssl_key)
            else:
                self.context = None

            self.setup_http_routes()

            #
            # API
            #

            if api is not None:
                self.logger.info("Starting API")
                self.setup_api_routes()
            else:
                self.logger.info("API is disabled")

            #
            # Admin
            #

            if aui is not None:
                self.logger.info("Starting Admin Interface")

                self.stats_update = "realtime"
                self._process_arg("stats_update", aui)

            if admin is not None:
                self.logger.info("Starting Old Admin Interface")

                self.stats_update = "realtime"
                self._process_arg("stats_update", admin)

            if admin is not None or aui is not None:

                self.admin_obj = adadmin.Admin(
                    self.config_dir,
                    logging,
                    self.AD,
                    javascript_dir=self.javascript_dir,
                    template_dir=self.template_dir,
                    css_dir=self.css_dir,
                    fonts_dir=self.fonts_dir,
                    webfonts_dir=self.webfonts_dir,
                    images_dir=self.images_dir,
                    transport=self.transport,
                    **admin
                )

            if admin is None and aui is None:
                self.logger.info("Admin Interface is disabled")
            #
            # Dashboards
            #

            if dashboard is not None:
                self._process_dashboard(dashboard)

            else:
                self.logger.info("Dashboards Disabled")

            #
            # Finish up and start the server
            #

            # handler = self.app.make_handler()

            # f = loop.create_server(handler, "0.0.0.0", int(self.port), ssl=context)
            # loop.create_task(f)

            if self.dashboard_obj is not None:
                loop.create_task(self.update_rss())

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in HTTP module")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

    def _process_dashboard(self, dashboard):
        self.logger.info("Starting Dashboards")

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

        if "rss_feeds" in dashboard:
            self.rss_feeds = []
            for feed in dashboard["rss_feeds"]:
                if feed["target"].count(".") != 1:
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

        self.javascript_dir = os.path.join(self.install_dir, "assets", "javascript")
        self.template_dir = os.path.join(self.install_dir, "assets", "templates")
        self.css_dir = os.path.join(self.install_dir, "assets", "css")
        self.fonts_dir = os.path.join(self.install_dir, "assets", "fonts")
        self.webfonts_dir = os.path.join(self.install_dir, "assets", "webfonts")
        self.images_dir = os.path.join(self.install_dir, "assets", "images")

        #
        # Setup compile directories
        #
        if self.config_dir is None:
            self.compile_dir = utils.find_path("compiled")
        else:
            self.compile_dir = os.path.join(self.config_dir, "compiled")

        self.dashboard_obj = addashboard.Dashboard(
            self.config_dir,
            self.logging,
            dash_compile_on_start=self.compile_on_start,
            dash_force_compile=self.force_compile,
            profile_dashboard=self.profile_dashboard,
            dashboard_dir=self.dashboard_dir,
            fa4compatibility=self.fa4compatibility,
            transport=self.transport,
            javascript_dir=self.javascript_dir,
            template_dir=self.template_dir,
            css_dir=self.css_dir,
            fonts_dir=self.fonts_dir,
            webfonts_dir=self.webfonts_dir,
            images_dir=self.images_dir,
        )
        self.setup_dashboard_routes()

    def _process_http(self, http):
        self._process_arg("password", http)
        self._process_arg("tokens", http)
        self._process_arg("work_factor", http)
        self._process_arg("ssl_certificate", http)
        self._process_arg("ssl_key", http)

        self._process_arg("url", http)
        if not self.url:
            self.logger.warning(
                "'{arg}' is '{value}'. Please configure appdaemon.yaml".format(arg="url", value=self.url)
            )
            exit(0)

        self._process_arg("transport", http)
        self.logger.info("Using '%s' for event stream", self.transport)

        self._process_arg("static_dirs", http)

    async def start_server(self):

        self.logger.info("Running on port %s", self.port)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", int(self.port), ssl_context=self.context)
        await site.start()

    async def stop_server(self):
        self.logger.info("Shutting down webserver")
        #
        # We should do this but it makes AD hang so ...
        #
        # await self.runner.cleanup()

    async def add_response_headers(self, request, response):
        for header, value in self.http["headers"].items():
            response.headers[header] = value

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
        response = await self.logon_page(request)
        return response

    async def logon_response(self, request):
        try:
            data = await request.post()
            password = data["password"]

            if password == self.password:
                self.access.info("Successful logon from %s", request.host)
                hashed = bcrypt.hashpw(str.encode(self.password), bcrypt.gensalt(self.work_factor))
                if self.admin is not None:
                    response = await self._admin_page(request)
                else:
                    response = await self._list_dash(request)

                self.logger.debug("hashed=%s", hashed)
                # Set cookie to last for 1 year
                response.set_cookie("adcreds", hashed.decode("utf-8"), max_age=31536000)

            else:
                self.access.warning("Unsuccessful logon from %s", request.host)
                response = await self.logon_page(request)

            return response
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in logon_response()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.get_response(request, 500, "Server error in logon_response()")

    # noinspection PyUnusedLocal
    @secure
    async def list_dash(self, request):
        return await self._list_dash(request)

    async def _list_dash(self, request):
        response = await utils.run_in_executor(self, self.dashboard_obj.get_dashboard_list)
        return web.Response(text=response, content_type="text/html")

    @secure
    async def load_dash(self, request):
        name = request.match_info.get("name", "Anonymous")
        params = request.query
        skin = params.get("skin", "default")
        recompile = params.get("recompile", False)
        if recompile == "1":
            recompile = True

        response = await utils.run_in_executor(self, self.dashboard_obj.get_dashboard, name, skin, recompile)

        return web.Response(text=response, content_type="text/html")

    async def update_rss(self):
        # Grab RSS Feeds
        if self.rss_feeds is not None and self.rss_update is not None:
            while not self.stopping:
                try:
                    if self.rss_last_update is None or (self.rss_last_update + self.rss_update) <= time.time():
                        self.rss_last_update = time.time()

                        for feed_data in self.rss_feeds:
                            feed = await utils.run_in_executor(self, feedparser.parse, feed_data["feed"])
                            if "bozo_exception" in feed:
                                self.logger.warning(
                                    "Error in RSS feed %s: %s", feed_data["feed"], feed["bozo_exception"],
                                )
                            else:
                                new_state = {"feed": feed}

                                # RSS Feeds always live in the admin namespace
                                await self.AD.state.set_state("rss", "admin", feed_data["target"], state=new_state)

                    await asyncio.sleep(1)
                except Exception:
                    self.logger.warning("-" * 60)
                    self.logger.warning("Unexpected error in update_rss()")
                    self.logger.warning("-" * 60)
                    self.logger.warning(traceback.format_exc())
                    self.logger.warning("-" * 60)

    #
    # REST API
    #

    @securedata
    async def get_ad(self, request):
        return web.json_response({"state": {"status": "active"}}, dumps=utils.convert_json)

    @securedata
    async def get_entity(self, request):
        namespace = None
        entity_id = None
        try:
            entity_id = request.match_info.get("entity")
            namespace = request.match_info.get("namespace")

            self.logger.debug("get_state() called, ns=%s, entity=%s", namespace, entity_id)
            state = self.AD.state.get_entity(namespace, entity_id)

            self.logger.debug("result = %s", state)

            return web.json_response({"state": state}, dumps=utils.convert_json)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in get_entity()")
            self.logger.warning("Namespace: %s, entity: %s", namespace, entity_id)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.get_response(request, 500, "Unexpected error in get_entity()")

    @securedata
    async def get_namespace(self, request):
        namespace = None
        try:
            namespace = request.match_info.get("namespace")

            self.logger.debug("get_namespace() called, ns=%s", namespace)
            state = self.AD.state.get_entity(namespace)

            self.logger.debug("result = %s", state)

            if state is None:
                return self.get_response(request, 404, "Namespace Not Found")

            return web.json_response({"state": state}, dumps=utils.convert_json)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in get_namespace()")
            self.logger.warning("Namespace: %s", namespace)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.get_response(request, 500, "Unexpected error in get_namespace()")

    @securedata
    async def get_namespace_entities(self, request):

        namespace = None
        try:
            namespace = request.match_info.get("namespace")

            self.logger.debug("get_namespace_entities() called, ns=%s", namespace)
            state = self.AD.state.list_namespace_entities(namespace)

            self.logger.debug("result = %s", state)

            if state is None:
                return self.get_response(request, 404, "Namespace Not Found")

            return web.json_response({"state": state}, dumps=utils.convert_json)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in get_namespace_entities()")
            self.logger.warning("Namespace: %s", namespace)
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.get_response(request, 500, "Unexpected error in get_namespace_entities()")

    @securedata
    async def get_namespaces(self, request):

        try:
            self.logger.debug("get_namespaces() called)")
            state = await self.AD.state.list_namespaces()
            self.logger.debug("result = %s", state)

            return web.json_response({"state": state}, dumps=utils.convert_json)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in get_namespaces()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.get_response(request, 500, "Unexpected error in get_namespaces()")

    @securedata
    async def get_services(self, request):

        try:
            self.logger.debug("get_services() called)")
            state = self.AD.services.list_services()
            self.logger.debug("result = %s", state)

            return web.json_response({"state": state}, dumps=utils.convert_json)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in get_services()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.get_response(request, 500, "Unexpected error in get_services()")

    @securedata
    async def get_state(self, request):
        try:
            self.logger.debug("get_state() called")
            state = self.AD.state.get_entity()

            if state is None:
                self.get_response(request, 404, "State Not Found")

            self.logger.debug("result = %s", state)

            return web.json_response({"state": state}, dumps=utils.convert_json)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in get_state()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.get_response(request, 500, "Unexpected error in get_state()")

    @securedata
    async def get_logs(self, request):
        try:
            self.logger.debug("get_logs() called")

            logs = await utils.run_in_executor(self, self.AD.logging.get_admin_logs)

            return web.json_response({"logs": logs}, dumps=utils.convert_json)
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in get_logs()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.get_response(request, 500, "Unexpected error in get_logs()")

    # noinspection PyUnusedLocal
    @securedata
    async def call_service(self, request):
        try:
            try:
                data = await request.json()
            except json.decoder.JSONDecodeError:
                return self.get_response(request, 400, "JSON Decode Error")

            args = {}
            namespace = request.match_info.get("namespace")
            domain = request.match_info.get("domain")
            service = request.match_info.get("service")
            #
            # Some value munging for dashboard
            #
            for key in data:
                if key == "service":
                    pass
                elif key == "rgb_color":
                    m = re.search(r"\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", data[key])
                    if m:
                        r = m.group(1)
                        g = m.group(2)
                        b = m.group(3)
                        args["rgb_color"] = [r, g, b]
                elif key == "xy_color":
                    m = re.search(r"\s*(\d+\.\d+)\s*,\s*(\d+\.\d+)", data[key])
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

            self.logger.debug("call_service() args = %s", args)

            res = await self.AD.services.call_service(namespace, domain, service, args)
            return web.json_response({"response": res}, status=200, dumps=utils.convert_json)

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in call_service()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return web.Response(status=500)

    @securedata
    async def fire_event(self, request):
        try:
            try:
                data = await request.json()
            except json.decoder.JSONDecodeError:
                return self.get_response(request, 400, "JSON Decode Error")

            args = {}
            namespace = request.match_info.get("namespace")
            event = request.match_info.get("event")
            #
            # Some value munging for dashboard
            #
            for key in data:
                if key == "event":
                    pass

                else:
                    args[key] = data[key]

            self.logger.debug("fire_event() args = %s", args)

            await self.AD.events.fire_event(namespace, event, **args)

            return web.Response(status=200)

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in fire_event()")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return web.Response(status=500)

    # noinspection PyUnusedLocal
    async def not_found(self, request):
        return self.get_response(request, 404, "Not Found")

    # Stream Handling

    async def stream_update(self, namespace, data):
        # self.logger.debug("stream_update() %s:%s", namespace, data)
        data["namespace"] = namespace
        self.AD.thread_async.call_async_no_wait(self.stream.process_event, data)

    # Routes, Status and Templates

    def setup_api_routes(self):
        self.app.router.add_post("/api/appdaemon/service/{namespace}/{domain}/{service}", self.call_service)
        self.app.router.add_post("/api/appdaemon/event/{namespace}/{event}", self.fire_event)
        self.app.router.add_get("/api/appdaemon/service/", self.get_services)
        self.app.router.add_get("/api/appdaemon/state/{namespace}/{entity}", self.get_entity)
        self.app.router.add_get("/api/appdaemon/state/{namespace}", self.get_namespace)
        self.app.router.add_get("/api/appdaemon/state/{namespace}/", self.get_namespace_entities)
        self.app.router.add_get("/api/appdaemon/state/", self.get_namespaces)
        self.app.router.add_get("/api/appdaemon/state", self.get_state)
        self.app.router.add_get("/api/appdaemon/logs", self.get_logs)
        self.app.router.add_post("/api/appdaemon/{app}", self.call_api)
        self.app.router.add_get("/api/appdaemon", self.get_ad)

    def setup_http_routes(self):
        self.app.router.add_get("/favicon.ico", self.not_found)
        self.app.router.add_get("/{gfx}.png", self.not_found)
        self.app.router.add_post("/logon_response", self.logon_response)

        # Add static path for JavaScript
        self.app.router.add_static("/javascript", self.javascript_dir)

        # Add static path for fonts
        self.app.router.add_static("/fonts", self.fonts_dir)

        # Add static path for webfonts
        self.app.router.add_static("/webfonts", self.webfonts_dir)

        # Add static path for images
        self.app.router.add_static("/images", self.images_dir)

        # Add static path for css
        self.app.router.add_static("/css", self.css_dir)
        if self.aui is not None:
            self.app.router.add_static("/aui", self.aui_dir)
            self.app.router.add_static("/aui/css", self.aui_css_dir)
            self.app.router.add_static("/aui/js", self.aui_js_dir)
            self.app.router.add_get("/", self.aui_page)
            if self.admin is not None:
                self.app.router.add_get("/admin", self.admin_page)
        elif self.admin is not None:
            self.app.router.add_get("/", self.admin_page)
        elif self.dashboard is not None:
            self.app.router.add_get("/", self.list_dash)
        else:
            self.app.router.add_get("/", self.error_page)

        #
        # For App based Web Server
        #
        self.app.router.add_get("/app/{route}", self.app_webserver)

        #
        # Add static path for apps
        #
        apps_static = os.path.join(self.AD.config_dir, "www")
        exists = True

        if not os.path.isdir(apps_static):  # check if the folder exists
            try:
                os.mkdir(apps_static)
            except OSError:
                self.logger.warning("Creation of the Web directory %s failed", apps_static)
                exists = False
            else:
                self.logger.debug("Successfully created the Web directory %s ", apps_static)

        if exists:
            self.app.router.add_static("/local", apps_static)
        #
        # Setup user defined static paths
        #

        for name, static_dir in self.static_dirs.items():
            if not os.path.isdir(static_dir):  # check if the folder exists
                self.logger.warning("The Web directory %s doesn't exist. So static route not set up", static_dir)

            else:
                self.app.router.add_static("/{}".format(name), static_dir)
                self.logger.debug("Successfully created the Web directory %s ", static_dir)

    def setup_dashboard_routes(self):
        self.app.router.add_get("/list", self.list_dash)
        self.app.router.add_get("/{name}", self.load_dash)

        # Setup Templates

        self.app.router.add_static("/compiled_javascript", self.dashboard_obj.compiled_javascript_dir)

        self.app.router.add_static("/compiled_css", self.dashboard_obj.compiled_css_dir)

        # Add path for custom_css if it exists

        custom_css = os.path.join(self.dashboard_obj.config_dir, "custom_css")
        if os.path.isdir(custom_css):
            self.app.router.add_static("/custom_css", custom_css)

        # Add path for custom_javascript if it exists

        custom_javascript = os.path.join(self.dashboard_obj.config_dir, "custom_javascript")
        if os.path.isdir(custom_javascript):
            self.app.router.add_static("/custom_javascript", custom_javascript)

    # API

    async def terminate_app(self, name):
        if name in self.endpoints:
            del self.endpoints[name]

        if name in self.app_routes:
            del self.app_routes[name]

    def get_response(self, request, code, error):
        res = "<html><head><title>{} {}</title></head><body><h1>{} {}</h1>Error in API Call</body></html>".format(
            code, error, code, error
        )
        app = request.match_info.get("app", "system")
        if code == 200:
            self.access.info("API Call to %s: status: %s", app, code)
        else:
            self.access.warning("API Call to %s: status: %s, %s", app, code, error)
        return web.Response(body=res, status=code)

    def get_web_response(self, request, code, error):
        res = "<html><head><title>{} {}</title></head><body><h1>{} {}</h1>Error in Web Service Call</body></html>".format(
            code, error, code, error
        )
        app = request.match_info.get("app", "system")
        if code == 200:
            self.access.info("Web Call to %s: status: %s", app, code)
        else:
            self.access.warning("Web Call to %s: status: %s, %s", app, code, error)
        return web.Response(text=res, content_type="text/html")

    @securedata
    async def call_api(self, request):

        code = 200
        ret = ""
        app = request.match_info.get("app")

        try:
            args = await request.json()
        except json.decoder.JSONDecodeError:
            return self.get_response(request, 400, "JSON Decode Error")

        try:
            ret, code = await self.dispatch_app_by_name(app, args)
        except Exception:
            self.logger.error("-" * 60)
            self.logger.error("Unexpected error during API call")
            self.logger.error("-" * 60)
            self.logger.error(traceback.format_exc())
            self.logger.error("-" * 60)

        if code == 404:
            return self.get_response(request, 404, "App Not Found")

        response = "OK"
        self.access.info("API Call to %s: status: %s %s", app, code, response)

        return web.json_response(ret, status=code, dumps=utils.convert_json)

    # Routes, Status and Templates

    async def register_endpoint(self, cb, name):

        handle = uuid.uuid4().hex

        if name not in self.endpoints:
            self.endpoints[name] = {}
        self.endpoints[name][handle] = {"callback": cb, "name": name}

        return handle

    async def unregister_endpoint(self, handle, name):
        if name in self.endpoints and handle in self.endpoints[name]:
            del self.endpoints[name][handle]

    async def dispatch_app_by_name(self, name, args):
        callback = None
        for app in self.endpoints:
            for handle in self.endpoints[app]:
                if self.endpoints[app][handle]["name"] == name:
                    callback = self.endpoints[app][handle]["callback"]
        if callback is not None:
            if asyncio.iscoroutinefunction(callback):
                return await callback(args)
            else:
                return await utils.run_in_executor(self, callback, args)
        else:
            return "", 404

    #
    # App based Web Server
    #
    async def register_route(self, cb, route, name, **kwargs):

        if not asyncio.iscoroutinefunction(cb):  # must be async function
            self.logger.warning(
                "Could not Register Callback for %s, using Route %s as Web Server Route. Callback must be Async",
                name,
                route,
            )
            return

        handle = uuid.uuid4().hex

        if name not in self.app_routes:
            self.app_routes[name] = {}

        token = kwargs.get("token")
        self.app_routes[name][handle] = {"callback": cb, "route": route, "token": token}

        return handle

    async def unregister_route(self, handle, name):
        if name in self.app_routes and handle in self.app_routes[name]:
            del self.app_routes[name][handle]

    @route_secure
    async def app_webserver(self, request):

        name = None
        route = request.match_info.get("route")
        token = request.query.get("token")

        code = 404
        error = "Requested Server does not exist"

        callback = None
        for name in self.app_routes:
            if callback is not None:  # a callback has been collected
                break

            for handle in self.app_routes[name]:
                app_route = self.app_routes[name][handle]["route"]
                app_token = self.app_routes[name][handle]["token"]

                if app_route == route:
                    if app_token is not None and app_token != token:
                        return self.get_web_response(request, "401", "Unauthorized")

                    callback = self.app_routes[name][handle]["callback"]
                    break

        if callback is not None:
            self.access.debug("Web Call to %s for %s", route, name)

            try:
                f = asyncio.ensure_future(callback(request))
                self.AD.futures.add_future(name, f)
                return await f
            except asyncio.CancelledError:
                code = 503
                error = "Request was Cancelled"

            except Exception:
                self.logger.error("-" * 60)
                self.logger.error("Unexpected error during Web call")
                self.logger.error("-" * 60)
                self.logger.error(traceback.format_exc())
                self.logger.error("-" * 60)
                code = 503
                error = "Request had an Error"

        return self.get_web_response(request, str(code), error)

    #
    # Admin
    #

    async def aui_page(self, request):
        raise web.HTTPFound("/aui/index.html")

    @secure
    async def admin_page(self, request):
        return await self._admin_page(request)

    # Insecure version
    async def _admin_page(self, request):
        response = await self.admin_obj.admin_page(request.scheme, request.host)

        return web.Response(text=response, content_type="text/html")

    async def logon_page(self, request):
        response = await utils.run_in_executor(self, self.generate_logon_page, request.scheme, request.host)
        return web.Response(text=response, content_type="text/html")

    async def error_page(self, request):
        response = await utils.run_in_executor(self, self.generate_error_page, request.scheme, request.host)
        return web.Response(text=response, content_type="text/html")

    def generate_logon_page(self, scheme, url):
        try:
            params = {}

            env = Environment(
                loader=FileSystemLoader(self.template_dir), autoescape=select_autoescape(["html", "xml"]),
            )

            template = env.get_template("logon.jinja2")
            rendered_template = template.render(params)

            return rendered_template

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error creating logon page")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

    def generate_error_page(self, scheme, url):
        try:
            params = {}

            env = Environment(
                loader=FileSystemLoader(self.template_dir), autoescape=select_autoescape(["html", "xml"]),
            )

            template = env.get_template("error.jinja2")
            rendered_template = template.render(params)

            return rendered_template

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error creating logon page")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
