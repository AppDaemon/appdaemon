import asyncio
import json
import os
import re
import time
import traceback

import aiohttp
import feedparser
from aiohttp import web
import ssl
import bcrypt

import appdaemon.conf as conf
import appdaemon.dashboard as dashboard
import appdaemon.utils as utils

# Setup WS handler

app = web.Application()
app['websockets'] = {}


def check_password(password, hash):
    return bcrypt.checkpw, str.encode(password), str.encode(hash)


def securedata(myfunc):
    """
    Take care of streams and service calls
    """

    def wrapper(request):

        if conf.dash_password == None:
            return myfunc(request)
        else:
            if "adcreds" in request.cookies:
                # TODO - run this in an executor thread
                match = bcrypt.checkpw, str.encode(conf.dash_password), str.encode(request.cookies["adcreds"])
                if match:
                    return myfunc(request)
                else:
                    return error(request)
            else:
                return error(request)

    return wrapper


def secure(myfunc):
    """
    Take care of screen based security
    """

    def wrapper(request):

        if conf.dash_password == None:
            return myfunc(request)
        else:
            if "adcreds" in request.cookies and bcrypt.checkpw(str.encode(conf.dash_password),
                                                               str.encode(request.cookies["adcreds"])):
                return myfunc(request)
            else:
                return forcelogon(request)

    return wrapper


def forcelogon(request):
    return {"logon": 1}


@asyncio.coroutine
def logon(request):
    data = yield from request.post()
    success = False
    password = data["password"]

    if password == conf.dash_password:
        utils.log(conf.dash, "INFO", "Succesful logon from {}".format(request.host))

        hashed = bcrypt.hashpw(str.encode(conf.dash_password), bcrypt.gensalt())

        # utils.log(conf.dash, "INFO", hashed)

        response = yield from list_dash_no_secure(request)
        response.set_cookie("adcreds", hashed.decode("utf-8"))

    else:
        utils.log(conf.dash, "WARNING", "Unsuccesful logon from {}".format(request.host))
        response = yield from list_dash(request)

    return response


# Views


# noinspection PyUnusedLocal
@asyncio.coroutine
@secure
def list_dash(request):
    return (_list_dash(request))


@asyncio.coroutine
def list_dash_no_secure(request):
    return (_list_dash(request))


def _list_dash(request):
    response = yield from utils.run_in_executor(conf.loop, conf.executor, conf.dashboard_obj.get_dashboard_list)
    return web.Response(text=response, content_type="text/html")


@asyncio.coroutine
@secure
def load_dash(request):
    name = request.match_info.get('name', "Anonymous")
    params = request.query
    skin = params.get("skin", "default")
    recompile = params.get("recompile", False)
    if recompile == '1':
        recompile = True

    response = yield from utils.run_in_executor(conf.loop, conf.executor, conf.dashboard_obj.get_dashboard, name, skin, recompile)

    return web.Response(text=response, content_type="text/html")


@asyncio.coroutine
def update_rss():
    # Grab RSS Feeds

    if conf.rss_feeds is not None and conf.rss_update is not None:
        while not conf.stopping:
            if conf.rss_last_update == None or (conf.rss_last_update + conf.rss_update) <= time.time():
                conf.rss_last_update = time.time()

                for feed_data in conf.rss_feeds:
                    feed = yield from utils.run_in_executor(conf.loop, conf.executor, feedparser.parse, feed_data["feed"])

                    new_state = {"feed": feed}
                    with conf.ha_state_lock:
                        conf.ha_state[feed_data["target"]] = new_state

                    data = {"event_type": "state_changed",
                            "data": {"entity_id": feed_data["target"], "new_state": new_state}}
                    ws_update(data)

            yield from asyncio.sleep(1)


@asyncio.coroutine
@securedata
def get_state(request):
    entity = request.match_info.get('entity')

    if entity in conf.ha_state:
        state = conf.ha_state[entity]
    else:
        state = None

    return web.json_response({"state": state})


def get_response(code, error):
    res = "<html><head><title>{} {}</title></head><body><h1>{} {}</h1>Error in API Call</body></html>".format(code,
                                                                                                              error,
                                                                                                              code,
                                                                                                              error)
    return res


# noinspection PyUnusedLocal
@asyncio.coroutine
@securedata
def call_service(request):
    data = yield from request.post()
    args = {}
    service = data["service"]
    for key in data:
        if key == "service":
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

    # completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, utils.call_service, data)])
    utils.call_service(service, **args)
    return web.Response(status=200)


# noinspection PyUnusedLocal
@asyncio.coroutine
def not_found(request):
    return web.Response(status=404)


# noinspection PyUnusedLocal
@asyncio.coroutine
def error(request):
    return web.Response(status=401)


# Websockets Handler

@asyncio.coroutine
def on_shutdown(application):
    for ws in application['websockets']:
        yield from ws.close(code=aiohttp.WSCloseCode.GOING_AWAY,
                            message='Server shutdown')


@securedata
@asyncio.coroutine
def wshandler(request):
    ws = web.WebSocketResponse()
    yield from ws.prepare(request)

    request.app['websockets'][ws] = {}
    # noinspection PyBroadException
    try:
        while True:
            msg = yield from ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                utils.log(conf.dash, "INFO",
                       "New dashboard connected: {}".format(msg.data))
                request.app['websockets'][ws]["dashboard"] = msg.data
            elif msg.type == aiohttp.WSMsgType.ERROR:
                utils.log(conf.dash, "INFO",
                       "ws connection closed with exception {}".format(ws.exception()))
    except:
        utils.log(conf.dash, "INFO", "Dashboard disconnected")
    finally:
        request.app['websockets'].pop(ws, None)

    return ws


def ws_update(jdata):
    if len(app['websockets']) > 0:
        utils.log(conf.dash,
               "DEBUG",
               "Sending data to {} dashes: {}".format(len(app['websockets']), jdata))

    data = json.dumps(jdata)

    for ws in app['websockets']:

        if "dashboard" in app['websockets'][ws]:
            utils.log(conf.dash,
                   "DEBUG",
                   "Found dashboard type {}".format(app['websockets'][ws]["dashboard"]))
            ws.send_str(data)


# Routes, Status and Templates

def setup_routes(dashboard):
    app.router.add_get('/favicon.ico', not_found)
    app.router.add_get('/{gfx}.png', not_found)
    app.router.add_post('/logon', logon)
    app.router.add_get('/stream', wshandler)
    app.router.add_post('/call_service', call_service)
    app.router.add_get('/state/{entity}', get_state)
    app.router.add_get('/', list_dash)
    app.router.add_get('/{name}', load_dash)

    # Setup Templates

    # Add static path for JavaScript

    app.router.add_static('/javascript', dashboard.javascript_dir)
    app.router.add_static('/compiled_javascript', dashboard.compiled_javascript_dir)

    # Add static path for css
    app.router.add_static('/css', dashboard.css_dir)
    app.router.add_static('/compiled_css', dashboard.compiled_css_dir)

    # Add path for custom_css if it exists

    custom_css = os.path.join(dashboard.config_dir, "custom_css")
    if os.path.isdir(custom_css):
        app.router.add_static('/custom_css', custom_css)

        # Add static path for fonts
    app.router.add_static('/fonts', dashboard.fonts_dir)

    # Add static path for images
    app.router.add_static('/images', dashboard.images_dir)


# Setup

def run_dash(loop, tasks):
    # noinspection PyBroadException
    try:
        conf.dashboard_obj = dashboard.Dashboard(conf.config_dir, conf.dash,
                                             dash_compile_on_start=conf.dash_compile_on_start,
                                             dash_force_compile=conf.dash_force_compile,
                                             profile_dashboard=conf.profile_dashboard,
                                             dashboard_dir = conf.dashboard_dir,
                                             )
        setup_routes(conf.dashboard_obj)

        if conf.dash_ssl_certificate is not None and conf.dash_ssl_key is not None:
            context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            context.load_cert_chain(conf.dash_ssl_certificate, conf.dash_ssl_key)
        else:
            context = None

        handler = app.make_handler()

        f = loop.create_server(handler, "0.0.0.0", int(conf.dash_port), ssl=context)

        tasks.append(asyncio.async(f))
        tasks.append(asyncio.async(update_rss()))
        return f
    except:
        utils.log(conf.dash, "WARNING", '-' * 60)
        utils.log(conf.dash, "WARNING", "Unexpected error in dashboard thread")
        utils.log(conf.dash, "WARNING", '-' * 60)
        utils.log(conf.dash, "WARNING", traceback.format_exc())
        utils.log(conf.dash, "WARNING", '-' * 60)
