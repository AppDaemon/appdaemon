import asyncio
from aiohttp import web
import aiohttp
import aiohttp_jinja2
import jinja2
import json
import os
import traceback
import re
import feedparser
import time

import appdaemon.homeassistant as ha
import appdaemon.conf as conf
import appdaemon.dashboard as dashboard

# Setup WS handler

app = web.Application()
app['websockets'] = {}

def set_paths():
    if not os.path.exists(conf.compile_dir):
        os.makedirs(conf.compile_dir)

    if not os.path.exists(os.path.join(conf.compile_dir, "javascript")):
        os.makedirs(os.path.join(conf.compile_dir, "javascript"))

    if not os.path.exists(os.path.join(conf.compile_dir, "css")):
        os.makedirs(os.path.join(conf.compile_dir, "css"))

    conf.javascript_dir = os.path.join(conf.dash_dir, "assets", "javascript")
    conf.compiled_javascript_dir = os.path.join(conf.compile_dir, "javascript")
    conf.compiled_html_dir = os.path.join(conf.compile_dir, "html")
    conf.template_dir = os.path.join(conf.dash_dir, "assets", "templates")
    conf.css_dir = os.path.join(conf.dash_dir, "assets", "css")
    conf.compiled_css_dir = os.path.join(conf.compile_dir, "css")
    conf.fonts_dir = os.path.join(conf.dash_dir, "assets", "fonts")
    conf.images_dir = os.path.join(conf.dash_dir, "assets", "images")
    conf.base_url = "http://{}:{}".format(conf.dash_host, conf.dash_port)
    conf.stream_url = "ws://{}:{}/stream".format(conf.dash_host, conf.dash_port)


# Views

# noinspection PyUnusedLocal
@asyncio.coroutine
@aiohttp_jinja2.template('dashboard.jinja2')
def list_dash(request):
    completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, dashboard.list_dashes)])
    dash_list = list(completed)[0].result()
    params = {"dash_list": dash_list, "stream_url": conf.stream_url}
    params["main"] = "1"
    return params


@asyncio.coroutine
@aiohttp_jinja2.template('dashboard.jinja2')
def load_dash(request):
    completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, _load_dash, request)])
    return list(completed)[0].result()

def _load_dash(request):
    # noinspection PyBroadException
    try:
        name = request.match_info.get('name', "Anonymous")

        # Set correct skin

        if "skin" in request.rel_url.query:
            skin = request.rel_url.query["skin"]
        else:
            skin = "default"

        #
        # Check skin exists
        #
        skindir = os.path.join(conf.config_dir, "custom_css", skin)
        if os.path.isdir(skindir):
            ha.log(conf.dash, "INFO", "Loading custom skin '{}'".format(skin))
        else:
            # Not a custom skin, try product skins
            skindir = os.path.join(conf.css_dir, skin)
            if not os.path.isdir(skindir):
                ha.log(conf.dash, "WARNING", "Skin '{}' does not exist".format(skin))
                skin = "default"
                skindir = os.path.join(conf.css_dir, "default")

        #
        # Conditionally compile Dashboard
        #

        dash = dashboard.compile_dash(name, skin, skindir, request.rel_url.query)

        if dash is None:
            errors = []
            head_includes = []
            body_includes = []
        else:
            errors = dash["errors"]

        if "widgets" in dash:
            widgets = dash["widgets"]
        else:
            widgets = {}

        include_path = os.path.join(conf.compiled_html_dir, skin, "{}_head.html".format(name.lower()))
        with open(include_path, "r") as include_file:
            head_includes = include_file.read()
        include_path = os.path.join(conf.compiled_html_dir, skin, "{}_body.html".format(name.lower()))
        with open(include_path, "r") as include_file:
            body_includes = include_file.read()

        #
        # return params
        #
        return {"errors": errors, "name": name.lower(), "skin": skin, "widgets": widgets,
                "head_includes": head_includes, "body_includes": body_includes}

    except:
        ha.log(conf.dash, "WARNING", '-' * 60)
        ha.log(conf.dash, "WARNING", "Unexpected error during DASH creation")
        ha.log(conf.dash, "WARNING", '-' * 60)
        ha.log(conf.dash, "WARNING", traceback.format_exc())
        ha.log(conf.dash, "WARNING", '-' * 60)
        return {"errors": ["An unrecoverable error occured fetching dashboard"]}

@asyncio.coroutine
def update_rss(loop):
    # Grab RSS Feeds

    if conf.rss_feeds is not None and conf.rss_update is not None:
        while not conf.stopping:
            if conf.rss_last_update == None or (conf.rss_last_update + conf.rss_update) <= time.time():
                conf.rss_last_update = time.time()

                for feed_data in conf.rss_feeds:
                    completed, pending = yield from asyncio.wait(
                        [conf.loop.run_in_executor(conf.executor, feedparser.parse, feed_data["feed"])])
                    feed = list(completed)[0].result()

                    new_state = {"feed": feed}
                    with conf.ha_state_lock:
                        conf.ha_state[feed_data["target"]] = new_state

                    data = {"event_type": "state_changed", "data": {"entity_id": feed_data["target"], "new_state": new_state}}
                    ws_update(data)

            yield from asyncio.sleep(1)


@asyncio.coroutine
def get_state(request):
    entity = request.match_info.get('entity')

    if entity in conf.ha_state:
        state = conf.ha_state[entity]
    else:
        state = None

    return web.json_response({"state": state})


# noinspection PyUnusedLocal
@asyncio.coroutine
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

    #completed, pending = yield from asyncio.wait([conf.loop.run_in_executor(conf.executor, ha.call_service, data)])
    ha.call_service(service, **args)
    return web.Response(status=200)

# noinspection PyUnusedLocal
@asyncio.coroutine
def not_found(request):
    return web.Response(status=404)


# Websockets Handler

@asyncio.coroutine
def on_shutdown(application):
    for ws in application['websockets']:
        yield from ws.close(code=aiohttp.WSCloseCode.GOING_AWAY,
                            message='Server shutdown')


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
                ha.log(conf.dash, "INFO",
                       "New dashboard connected: {}".format(msg.data))
                request.app['websockets'][ws]["dashboard"] = msg.data
            elif msg.type == aiohttp.WSMsgType.ERROR:
                ha.log(conf.dash, "INFO",
                       "ws connection closed with exception {}".format(ws.exception()))
    except:
        ha.log(conf.dash, "INFO", "Dashboard disconnected")
    finally:
        request.app['websockets'].pop(ws, None)

    return ws


def ws_update(jdata):
    ha.log(conf.dash,
           "DEBUG",
           "Sending data to {} dashes: {}".format(len(app['websockets']), jdata))

    data = json.dumps(jdata)

    for ws in app['websockets']:

        if "dashboard" in app['websockets'][ws]:
            ha.log(conf.dash,
                   "DEBUG",
                   "Found dashboard type {}".format(app['websockets'][ws]["dashboard"]))
            ws.send_str(data)


# Routes, Status and Templates

def setup_routes():
    app.router.add_get('/favicon.ico', not_found)
    app.router.add_get('/{gfx}.png', not_found)
    app.router.add_get('/stream', wshandler)
    app.router.add_post('/call_service', call_service)
    app.router.add_get('/state/{entity}', get_state)
    app.router.add_get('/', list_dash)
    app.router.add_get('/{name}', load_dash)

    # Setup Templates
    aiohttp_jinja2.setup(app,
                         loader=jinja2.FileSystemLoader(conf.template_dir))

    # Add static path for JavaScript

    app.router.add_static('/javascript', conf.javascript_dir)
    app.router.add_static('/compiled_javascript', conf.compiled_javascript_dir)

    # Add static path for css
    app.router.add_static('/css', conf.css_dir)
    app.router.add_static('/compiled_css', conf.compiled_css_dir)

    # Add path for custom_css if it exists

    custom_css = os.path.join(conf.config_dir, "custom_css")
    if os.path.isdir(custom_css):
        app.router.add_static('/custom_css', custom_css)

        # Add static path for fonts
    app.router.add_static('/fonts', conf.fonts_dir)

    # Add static path for images
    app.router.add_static('/images', conf.images_dir)


# Setup

def run_dash(loop):
    # noinspection PyBroadException
    try:
        set_paths()
        setup_routes()

        handler = app.make_handler()
        f = loop.create_server(handler, "0.0.0.0", int(conf.dash_port))
        conf.srv = loop.run_until_complete(f)
        conf.rss = loop.run_until_complete(update_rss(loop))
    except:
        ha.log(conf.dash, "WARNING", '-' * 60)
        ha.log(conf.dash, "WARNING", "Unexpected error in dashboard thread")
        ha.log(conf.dash, "WARNING", '-' * 60)
        ha.log(conf.dash, "WARNING", traceback.format_exc())
        ha.log(conf.dash, "WARNING", '-' * 60)
