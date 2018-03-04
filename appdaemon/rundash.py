import asyncio
import json
import os
import re
import time
import traceback
import concurrent
from urllib.parse import urlparse
import aiohttp
import feedparser
from aiohttp import web
import ssl
import bcrypt

import appdaemon.dashboard as dashboard
import appdaemon.utils as utils

def securedata(myfunc):
    """
    Take care of streams and service calls
    """

    async def wrapper(*args):

        self = args[0]
        if self.dash_password is None:
            return await myfunc(*args)
        else:
            if "adcreds" in args[1].cookies:
                match = await utils.run_in_executor(self.loop, self.executor, bcrypt.checkpw, str.encode(self.dash_password), str.encode(args[1].cookies["adcreds"]))
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
        if self.dash_password == None:
            return await myfunc(*args)
        else:
            if "adcreds" in args[1].cookies:
                match = await utils.run_in_executor(self.loop, self.executor, bcrypt.checkpw,
                                                    str.encode(self.dash_password),
                                                    str.encode(args[1].cookies["adcreds"]))
                if match:
                    return await myfunc(*args)
                else:
                    return await self.forcelogon(args[1])
            else:
                return await self.forcelogon(args[1])

    return wrapper


class RunDash():

    def __init__(self, ad, loop, logger, access, **config):

        self.AD = ad
        self.logger = logger
        self.acc = access

        self.dashboard_dir = None
        self._process_arg("dashboard_dir", config)

        self.dash_password = None
        self._process_arg("dash_password", config)

        self.dash_url = None
        self._process_arg("dash_url", config)

        self.config_dir = None
        self._process_arg("config_dir", config)

        self.dash_compile_on_start = False
        self._process_arg("dash_compile_on_start", config)

        self.dash_force_compile = False
        self._process_arg("dash_force_compile", config)

        self.work_factor = 8
        self._process_arg("work_factor", config)

        self.profile_dashboard = False
        self._process_arg("profile_dashboard", config)

        self.dash_ssl_certificate = None
        self._process_arg("dash_ssl_certificate", config)

        self.dash_ssl_key = None
        self._process_arg("dash_ssl_key", config)

        self.rss_feeds = None
        self._process_arg("rss_feeds", config)

        self.rss_update = None
        self._process_arg("rss_update", config)

        self.rss_last_update = None

        self.stopping = False

        url = urlparse(self.dash_url)

        dash_net = url.netloc.split(":")
        self.dash_host = dash_net[0]
        try:
            self.dash_port = dash_net[1]
        except IndexError:
            self.dash_port = 80

        if self.dash_host == "":
            raise ValueError("Invalid host for 'dash_url'")

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


        # Setup WS handler

        self.app = web.Application()
        self.app['websockets'] = {}

        self.loop = loop
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

        try:
            self.dashboard_obj = dashboard.Dashboard(self.config_dir, access,
                                                 dash_compile_on_start=self.dash_compile_on_start,
                                                 dash_force_compile=self.dash_force_compile,
                                                 profile_dashboard=self.profile_dashboard,
                                                 dashboard_dir = self.dashboard_dir,
                                                     )
            self.setup_routes()

            if self.dash_ssl_certificate is not None and self.dash_ssl_key is not None:
                context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
                context.load_cert_chain(self.dash_ssl_certificate, self.dash_ssl_key)
            else:
                context = None

            handler = self.app.make_handler()

            f = loop.create_server(handler, "0.0.0.0", int(self.dash_port), ssl=context)

            loop.create_task(f)
            loop.create_task(self.update_rss())
        except:
            self.log("WARNING", '-' * 60)
            self.log("WARNING", "Unexpected error in dashboard thread")
            self.log("WARNING", '-' * 60)
            self.log("WARNING", traceback.format_exc())
            self.log("WARNING", '-' * 60)

    def stop(self):
        self.stopping = True

    def log(self, level, message):
        utils.log(self.logger, level, message, "HADasboard")

    def access(self, level, message):
        utils.log(self.acc, level, message, "HADashboard")

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    def check_password(self, password, hash):
        return bcrypt.checkpw, str.encode(password), str.encode(hash)



    async def forcelogon(self, request):
        response = await utils.run_in_executor(self.loop, self.executor, self.dashboard_obj.get_dashboard_list,
                                                    {"logon": 1})
        return web.Response(text=response, content_type="text/html")


    async def logon(self, request):
        data = await request.post()
        success = False
        password = data["password"]

        if password == self.dash_password:
            self.access("INFO", "Succesful logon from {}".format(request.host))
            hashed = bcrypt.hashpw(str.encode(self.dash_password), bcrypt.gensalt(self.work_factor))

            # utils.verbose_log(conf.dash, "INFO", hashed)

            response = await self.list_dash_no_secure(request)
            response.set_cookie("adcreds", hashed.decode("utf-8"))

        else:
            self.access("WARNING", "Unsuccesful logon from {}".format(request.host))
            response = await self.list_dash(request)

        return response


    # Views


    # noinspection PyUnusedLocal
    @secure
    async def list_dash(self, request):
        return (await self._list_dash(request))


    async def list_dash_no_secure(self, request):
        return (await self._list_dash(request))

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
                                self.log("WARNING", "Error in RSS feed {}: {}".format(feed_data["feed"], feed["bozo_exception"]))
                            else:
                                new_state = {"feed": feed}

                                # RSS Feeds always live in the default namespace
                                self.AD.set_state("default", feed_data["target"], new_state)

                                data = {"event_type": "state_changed",
                                        "data": {"entity_id": feed_data["target"], "new_state": new_state}}

                                await self.ws_update("default", data)

                    await asyncio.sleep(1)
                except:
                    self.log("WARNING", '-' * 60)
                    self.log("WARNING", "Unexpected error in dashboard thread")
                    self.log("WARNING", '-' * 60)
                    self.log("WARNING", traceback.format_exc())
                    self.log("WARNING", '-' * 60)



    @securedata
    async def get_state(self, request):

        entity_id = request.match_info.get('entity')
        namespace = request.match_info.get('namespace')

        state = self.AD.get_entity(namespace, entity_id)

        return web.json_response({"state": state})


    def get_response(self, code, error):
        res = "<html><head><title>{} {}</title></head><body><h1>{} {}</h1>Error in API Call</body></html>".format(code,
                                                                                                                  error,
                                                                                                                  code,
                                                                                                                  error)
        return res


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
                else:
                    args[key] = data[key]

            plugin = self.AD.get_plugin(namespace)
            await plugin.call_service (service, **args)
            return web.Response(status=200)

        except:
            self.log("WARNING", '-' * 60)
            self.log("WARNING", "Unexpected error in call_service()")
            self.log("WARNING", '-' * 60)
            self.log("WARNING", traceback.format_exc())
            self.log("WARNING", '-' * 60)
            return web.Response(status=500)

    # noinspection PyUnusedLocal
    async def not_found(self, request):
        return web.Response(status=404)


    # noinspection PyUnusedLocal
    async def error(self, request):
        return web.Response(status=401)


    # Websockets Handler

    async def on_shutdown(self, application):
        for ws in application['websockets']:
            await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY,
                                message='Server shutdown')


    @securedata
    async def wshandler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        request.app['websockets'][ws] = {}
        # noinspection PyBroadException
        try:
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self.access("INFO",
                           "New dashboard connected: {}".format(msg.data))
                    request.app['websockets'][ws]["dashboard"] = msg.data
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.access("INFO",
                           "ws connection closed with exception {}".format(ws.exception()))
        except:
            self.access("INFO", "Dashboard disconnected")
        finally:
            request.app['websockets'].pop(ws, None)

        return ws

    async def ws_update(self, namespace, jdata):
        if len(self.app['websockets']) > 0:
            self.log("DEBUG",
                   "Sending data to {} dashes: {}".format(len(self.app['websockets']), jdata))
        jdata["namespace"] = namespace
        data = json.dumps(jdata)

        for ws in self.app['websockets']:

            if "dashboard" in self.app['websockets'][ws]:
                self.log(
                       "DEBUG",
                       "Found dashboard type {}".format(self.app['websockets'][ws]["dashboard"]))
                await ws.send_str(data)


    # Routes, Status and Templates

    def setup_routes(self):
        self.app.router.add_get('/favicon.ico', self.not_found)
        self.app.router.add_get('/{gfx}.png', self.not_found)
        self.app.router.add_post('/logon', self.logon)
        self.app.router.add_get('/stream', self.wshandler)
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

        # Add static path for images
        self.app.router.add_static('/images', self.dashboard_obj.images_dir)

