import socketio
import json
import traceback

import appdaemon.utils as utils


class SocketIOHandler:
    def __init__(self, ADStream, app, path, ad):
        self.AD = ad
        self.ADStream = ADStream
        self.app = app
        self.path = path

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

        self.sio = socketio.AsyncServer(async_mode="aiohttp")

        self.ns = NameSpace(self.ADStream, self.path, self.AD)
        self.sio.register_namespace(self.ns)

        self.sio.attach(self.app)

    def makeStream(self, ad, request, **kwargs):
        return SocketIOStream(ad, self.ns, request)


class NameSpace(socketio.AsyncNamespace):
    def __init__(self, ADStream, path, AD):
        super().__init__(path)

        self.AD = AD
        self.logger = AD.logging.get_child("_stream")
        self.access = AD.logging.get_access()
        self.ADStream = ADStream

    async def on_down(self, sid, data):
        self.logger.debug("IOSocket Down sid={} data={}".format(sid, data))
        try:
            msg = json.loads(data)
            handler = self.ADStream.get_handler(sid)
            await handler._on_message(msg)
        except TypeError as e:
            self.logger.debug("-" * 60)
            self.logger.warning("Unexpected error in JSON conversion when reading from stream")
            self.logger.debug("Data is: %s", data)
            self.logger.debug("Error is: %s", e)
            self.logger.debug("-" * 60)
        except Exception:
            self.logger.debug("-" * 60)
            self.logger.debug("Client disconnected unexpectedly")
            self.access.info("Client disconnected unexpectedly")
            self.logger.debug("-" * 60)
            self.logger.debug(traceback.format_exc())
            self.logger.debug("-" * 60)

    async def on_connect(self, sid, environ):
        self.logger.debug("IOSocket Connect sid={} env={}".format(sid, environ))
        await self.ADStream.on_connect({"sid": sid, "environ": environ})

    async def on_disconnect(self, sid):
        self.logger.debug("IOSocket disconnect sid={}".format(sid))
        handler = self.ADStream.get_handler(sid)
        await handler._on_disconnect()


class SocketIOStream:
    def __init__(self, ad, namespace, request):
        self.ns = namespace
        self.client_id = request["sid"]

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

        self.client_name = None

    def set_client_name(self, client_name):
        self.client_name = client_name

    async def run(self):
        pass

    async def sendclient(self, data):
        self.logger.debug("IOSocket Send sid={} data={}".format(self.client_id, data))
        data["client_id"] = self.client_id
        try:
            msg = utils.convert_json(data)
            await self.ns.emit("up", msg, room=self.client_id)
        except TypeError as e:
            self.logger.debug("-" * 60)
            self.logger.warning("Unexpected error in JSON conversion when writing to stream from %s", self.client_name)
            self.logger.debug("Data is: %s", data)
            self.logger.debug("Error is: %s", e)
            self.logger.debug("-" * 60)
        except Exception:
            self.logger.debug("-" * 60)
            self.logger.debug("Client disconnected unexpectedly from %s", self.client_name)
            self.access.info("Client disconnected unexpectedly from %s", self.client_name)
            self.logger.debug("-" * 60)
            self.logger.debug(traceback.format_exc())
            self.logger.debug("-" * 60)
