import asyncio
import json

from aiohttp import web
import ssl
import traceback

import appdaemon.utils as utils

app = web.Application()

class ADAPI():

    def __init__(self, ad, loop, logger, access, **config):

        self.AD = ad
        self.logger = logger
        self.access = access

        self.api_key = None
        self._process_arg("api_key", config)

        self.api_ssl_certificate = None
        self._process_arg("api_ssl_certificate", config)

        self.api_ssl_key = None
        self._process_arg("api_ssl_key", config)

        self.api_port = 0
        self._process_arg("api_port", config)

        try:
            self.setup_api()

            if self.api_ssl_certificate is not None and self.api_ssl_key is not None:
                context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
                context.load_cert_chain(self.api_ssl_certificate, self.api_ssl_key)
            else:
                context = None

            handler = app.make_handler()

            f = loop.create_server(handler, "0.0.0.0", int(self.api_port), ssl=context)
            loop.create_task(f)
        except:
            self.log("WARNING", '-' * 60)
            self.log("WARNING", "Unexpected error in api thread")
            self.log("WARNING", '-' * 60)
            self.log("WARNING", traceback.format_exc())
            self.log("WARNING", '-' * 60)

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    def log(self, level, message):
        utils.log(self.logger, level, message, "AppDaemon")

    def log_access(self, level, message):
        utils.log(self.access, level, message, "AppDaemon")

    @staticmethod
    def get_response(code, error):
        res = "<html><head><title>{} {}</title></head><body><h1>{} {}</h1>Error in API Call</body></html>".format(code, error, code, error)
        return res

    async def call_api(self, request):

        code = 200
        ret = ""

        app = request.match_info.get('app')

        if self.api_key is not None:
            if (("x-ad-access" not in request.headers) or (request.headers["x-ad-access"] != self.api_key)) \
                    and (("api_password" not in request.query) or (request.query["api_password"] != self.api_key)):

                code = 401
                response = "Unauthorized"
                res = self.get_response(code, response)
                self.log("INFO", "API Call to {}: status: {} {}".format(app, code, response))
                return web.Response(body=res, status=code)

        try:
            args = await request.json()
        except json.decoder.JSONDecodeError:
            code = 400
            response = "JSON Decode Error"
            res = self.get_response(code, response)
            self.log("INFO", "API Call to {}: status: {} {}".format(app, code, response))
            return web.Response(body = res, status = code)

        try:
            ret, code = await self.AD.dispatch_app_by_name(app, args)
        except:
            self.log("WARNING", '-' * 60)
            self.log("WARNING", "Unexpected error during API call")
            self.log("WARNING", '-' * 60)
            self.log("WARNING", traceback.format_exc())
            self.log("WARNING", '-' * 60)

        if code == 404:
            response = "App Not Found"
            res = self.get_response(code, response)
            self.log("INFO", "API Call to {}: status: {} {}".format(app, code, response))
            return web.Response(body = res, status = code)

        response = "OK"
        res = self.get_response(code, response)
        self.log_access("INFO", "API Call to {}: status: {} {}".format(app, code, response))

        return web.json_response(ret, status = code)

    # Routes, Status and Templates

    def setup_api(self):
        app.router.add_post('/api/appdaemon/{app}', self.call_api)
