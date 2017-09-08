import asyncio
import json

from aiohttp import web
import ssl
import traceback

import appdaemon.conf as conf
import appdaemon.utils as ha

app = web.Application()

def get_response(code, error):
    res = "<html><head><title>{} {}</title></head><body><h1>{} {}</h1>Error in API Call</body></html>".format(code, error, code, error)
    return res

@asyncio.coroutine
def call_api(request):
    app = request.match_info.get('app')

    if conf.api_key is not None:
        if (("x-ad-access" not in request.headers) or (request.headers["x-ad-access"] != conf.api_key))\
            and (("api_password" not in request.query) or (request.query["api_password"] != conf.api_key)):
            code = 401
            response = "Unauthorized"
            res = get_response(code, response)
            ha.log(conf.logger, "INFO", "API Call to {}: status: {} {}".format(app, code, response))
            return web.Response(body=res, status=code)

    try:
        args = yield from request.json()
    except json.decoder.JSONDecodeError:
        code = 400
        response = "JSON Decode Error"
        res = get_response(code, response)
        ha.log(conf.logger, "INFO", "API Call to {}: status: {} {}".format(app, code, response))
        return web.Response(body = res, status = code)

    try:
        ret, code = yield from ha.dispatch_app_by_name(app, args)
    except:
        if conf.errorfile != "STDERR" and conf.logfile != "STDOUT":
            # When explicitly logging to stdout and stderr, suppress
            # log messages about writing an error (since they show up anyway)
            ha.log(conf.logger, "WARNING", "Logged an error to {}".format(conf.errorfile))
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", "Unexpected error during API call")
        ha.log(conf.error, "WARNING", '-' * 60)
        ha.log(conf.error, "WARNING", traceback.format_exc())
        ha.log(conf.error, "WARNING", '-' * 60)

    if code == 404:
        response = "App Not Found"
        res = get_response(code, response)
        ha.log(conf.logger, "INFO", "API Call to {}: status: {} {}".format(app, code, response))
        return web.Response(body = res, status = code)

    response = "OK"
    res = get_response(code, response)
    ha.log(conf.logger, "INFO", "API Call to {}: status: {} {}".format(app, code, response))

    return web.json_response(ret, status = code)


# Routes, Status and Templates

def setup_api():
    app.router.add_post('/api/appdaemon/{app}', call_api)

def run_api(loop, tasks):
    # noinspection PyBroadException
    try:
        setup_api()

        if conf.api_ssl_certificate is not None and conf.api_ssl_key is not None:
            context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            context.load_cert_chain(conf.api_ssl_certificate, conf.api_ssl_key)
        else:
            context = None

        handler = app.make_handler()

        f = loop.create_server(handler, "0.0.0.0", int(conf.api_port), ssl = context)
        tasks.append(asyncio.async(f))
    except:
        ha.log(conf.dash, "WARNING", '-' * 60)
        ha.log(conf.dash, "WARNING", "Unexpected error in api thread")
        ha.log(conf.dash, "WARNING", '-' * 60)
        ha.log(conf.dash, "WARNING", traceback.format_exc())
        ha.log(conf.dash, "WARNING", '-' * 60)
