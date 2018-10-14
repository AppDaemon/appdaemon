import traceback
import concurrent.futures
from aiohttp import web
import ssl
import bcrypt

import appdaemon.admin as admin
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

    def __init__(self, ad, loop, logger, access, **config):

        self.AD = ad
        self.logger = logger
        self.acc = access

        self.admin_password = None
        self._process_arg("admin_password", config)

        self.config_dir = None
        self._process_arg("config_dir", config)

        self.work_factor = 8
        self._process_arg("work_factor", config)

        self.admin_port = 5002
        self._process_arg("admin_port", config)

        self.dash_ssl_certificate = None
        self._process_arg("dash_ssl_certificate", config)

        self.dash_ssl_key = None
        self._process_arg("dash_ssl_key", config)

        self.stopping = False

        # Setup WS handler

        self.app = web.Application()
        self.app['websockets'] = {}

        self.loop = loop
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

        try:

            self.admin_obj = admin.Admin(self.config_dir, access, self.AD)

            self.setup_routes()

            if self.dash_ssl_certificate is not None and self.dash_ssl_key is not None:
                context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
                context.load_cert_chain(self.dash_ssl_certificate, self.dash_ssl_key)
            else:
                context = None

            handler = self.app.make_handler()

            f = loop.create_server(handler, "0.0.0.0", int(self.admin_port), ssl=context)

            loop.create_task(f)
        except:
            self.log("WARNING", '-' * 60)
            self.log("WARNING", "Unexpected error in admin thread")
            self.log("WARNING", '-' * 60)
            self.log("WARNING", traceback.format_exc())
            self.log("WARNING", '-' * 60)

    def stop(self):
        self.stopping = True

    def log(self, level, message):
        utils.log(self.logger, level, message, "ADAdmin")

    def access(self, level, message):
        utils.log(self.acc, level, message, "ADAdmin")

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

    @secure
    async def oauth(self, request):
        #response = await utils.run_in_executor(self.loop, self.executor, self.admin_obj.index, request.url)
        response = await utils.run_in_executor(self.loop, self.executor, self.admin_obj.oauth, request.query["code"])
        #return web.Response(text=response, content_type="text/html")
        raise web.HTTPFound('/plugins')

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
        self.app.router.add_get('/oauth', self.oauth)
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

