# import socketio

# from appdaemon import utils as utils


# class SocketIOHandler(socketio.AsyncNamespace):
#     def __init__(self, app, ADStream, path, AD):
#
#         super().__init__(path)
#
#         self.AD = AD
#         self.ADStream = ADStream
#         self.app = app
#
#         self.sio = socketio.AsyncServer(async_mode="aiohttp")
#         self.sio.attach(self.app)
#         self.sio.register_namespace(self.dash_stream)
#
#     async def on_connect(self, sid, data):
#         await self.ADStream.on_connect()
#
#     async def on_up(self, sid, data):
#         await self.ADStream.on_msg(data)
#
#     async def send(self):
#         jdata = utils.convert_json(data)
#         await self.dash_stream.emit("down", jdata)
#


class SocketIOHandler:
    def __init__(self, ADStream, app, path, ad):

        self.AD = ad
        self.ADStream = ADStream
        self.app = app

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

        # await self.ADStream.on_connect(request)

    def makeStream(self, ad, request, **kwargs):
        return SocketIOStream(ad, request, **kwargs)


class SocketIOStream:
    def __init__(self, ad, request, **kwargs):

        self.request = request
        self.on_message = kwargs["on_message"]
        self.on_disconnect = kwargs["on_disconnect"]

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

    async def run(self):
        pass

    async def send(self, data):
        pass
