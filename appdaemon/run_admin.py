import traceback
import concurrent.futures
from aiohttp import web
import ssl
import bcrypt
import asyncio

import appdaemon.admin as admin
import appdaemon.utils as utils
import appdaemon.stream as stream

from appdaemon.appdaemon import AppDaemon

def securedata(myfunc):
    """
    Take care of streams and service calls
    """

    async def wrapper(*args):

        self = args[0]
        if self.dash_password is None:
            return await myfunc(*args)
        else:
            if "adadmincreds" in args[1].cookies:
                match = await utils.run_in_executor(self.loop, self.executor, bcrypt.checkpw, str.encode(self.dash_password), str.encode(args[1].cookies["adadmincreds"]))
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
        if self.admin_password == None:
            return await myfunc(*args)
        else:
            if "adadmincreds" in args[1].cookies:
                match = await utils.run_in_executor(self.loop, self.executor, bcrypt.checkpw,
                                                    str.encode(self.admin_password),
                                                    str.encode(args[1].cookies["adadmincreds"]))
                if match:
                    return await myfunc(*args)
                else:
                    return await self.forcelogon(args[1])
            elif "dash_password" in args[1].query and args[1].query["dash_password"] == self.dash_password:
                return await myfunc(*args)
            else:
                return await self.forcelogon(args[1])

    return wrapper


class RunAdmin:

    def __init__(self, ad: AppDaemon, loop, logging, **config):

        self.AD = ad
        self.logging = logging
        self.logger = ad.logging.get_child("_run_admin")
        self.access = ad.logging.get_access()
        self.admin_password = None
        self._process_arg("admin_password", config)

        self.config_dir = None
        self._process_arg("config_dir", config)

        self.work_factor = 8
        self._process_arg("work_factor", config)

        self.port = 5002
        self._process_arg("port", config)

        self.transport = "ws"
        self._process_arg("transport", config)

        self.dash_ssl_certificate = None
        self._process_arg("dash_ssl_certificate", config)

        self.dash_ssl_key = None
        self._process_arg("dash_ssl_key", config)

        self.stats_update = "realtime"
        self._process_arg("stats_update", config)

        self.stopping = False

        self.app = web.Application()

        self.stream = stream.ADStream(self.AD, self.app, self.transport, self.on_connect, self.on_message)

        self.loop = loop
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

        try:

            self.admin_obj = admin.Admin(self.config_dir, logging, self.AD, **config)

            self.setup_routes()

            if self.dash_ssl_certificate is not None and self.dash_ssl_key is not None:
                context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
                context.load_cert_chain(self.dash_ssl_certificate, self.dash_ssl_key)
            else:
                context = None

            handler = self.app.make_handler()

            f = loop.create_server(handler, "0.0.0.0", int(self.port), ssl=context)

            loop.create_task(f)

            # start update loop

            self.AD.loop.create_task(self.admin_loop())

        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected error in admin thread")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)

    # Stream Handling

    async def admin_update(self, updates):
        await self.stream.send_update(updates)

    async def on_message(self, data):
        self.access.info("New admin browser connection")

    async def on_connect(self):
        pass

    def stop(self):
        self.stopping = True

    async def admin_loop(self):
        while not self.stopping:
            old_update = {}
            update = {}
            threads = {}
            if self.AD.admin.stats_update != "none" and self.AD.sched is not None:
                callback_update = self.AD.threading.get_callback_update()
                sched = self.AD.sched.get_scheduler_entries()
                state_callbacks = self.AD.callbacks.get_callback_entries("state")
                event_callbacks = self.AD.callbacks.get_callback_entries("event")
                threads = self.AD.threading.get_thread_info()
                update["updates"] = callback_update
                update["schedule"] = sched
                update["state_callbacks"] = state_callbacks
                update["event_callbacks"] = event_callbacks
                update["updates"]["current_busy_threads"] = threads["current_busy"]
                update["updates"]["max_busy_threads"] = threads["max_busy"]
                update["updates"]["max_busy_threads_time"] = threads["max_busy_time"]
            if self.AD.admin.stats_update == "batch":
                update["threads"] = threads["threads"]

            if update != old_update:
                await self.admin_update(update)

            old_update = update

            await asyncio.sleep(self.AD.admin_delay)

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    @staticmethod
    def check_password(password, hash):
        return bcrypt.checkpw, str.encode(password), str.encode(hash)

    async def process_logon(self, request):
        data = await request.post()
        success = False
        password = data["password"]

        if password == self.admin_password:
            self.access("INFO", "Succesful logon from {}".format(request.host))
            hashed = bcrypt.hashpw(str.encode(self.admin_password), bcrypt.gensalt(self.work_factor))

            # utils.verbose_log(conf.dash, "INFO", hashed)

            response = await self.index(request)
            response.set_cookie("adadmincreds", hashed.decode("utf-8"))

        else:
            self.access("WARNING", "Unsuccessful logon from {}".format(request.host))
            response = await self.process_logon(request)

        return response


    # Views

    # noinspection PyUnusedLocal
    async def show_logon(self, request):
        response = await utils.run_in_executor(self.loop, self.executor, self.admin_obj.logon)
        return web.Response(text=response, content_type="text/html")

    @secure
    async def index(self, request):
        response = await utils.run_in_executor(self.loop, self.executor, self.admin_obj.index, request.scheme, request.host)
        return web.Response(text=response, content_type="text/html")

    @secure
    async def appdaemon(self, request):
        response = await utils.run_in_executor(self.loop, self.executor, self.admin_obj.appdaemon, request.scheme, request.host)
        return web.Response(text=response, content_type="text/html")

    @secure
    async def apps(self, request):
        response = await utils.run_in_executor(self.loop, self.executor, self.admin_obj.apps, request.scheme, request.host)
        return web.Response(text=response, content_type="text/html")

    @secure
    async def plugins(self, request):
        response = await utils.run_in_executor(self.loop, self.executor, self.admin_obj.plugins, request.scheme, request.host)
        return web.Response(text=response, content_type="text/html")


    # noinspection PyUnusedLocal
    async def not_found(self, request):
        return web.Response(status=404)

    # noinspection PyUnusedLocal
    async def error(self, request):
        return web.Response(status=401)

    # Routes, Status and Templates

    def setup_routes(self):
        self.app.router.add_get('/favicon.ico', self.not_found)
        self.app.router.add_get('/{gfx}.png', self.not_found)
        self.app.router.add_post('/logon', self.show_logon)
        self.app.router.add_get('/', self.index)
        self.app.router.add_get('/appdaemon', self.appdaemon)
        self.app.router.add_get('/apps', self.apps)
        self.app.router.add_get('/plugins', self.plugins)

        # Setup Templates

        # Add static path for images
        self.app.router.add_static('/images', self.admin_obj.images_dir)
        # Add static path for css
        self.app.router.add_static('/css', self.admin_obj.css_dir)
        # Add static path for javascript
        self.app.router.add_static('/javascript', self.admin_obj.javascript_dir)

