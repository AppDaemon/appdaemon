import socketio


class SocketIOHandler(socketio.AsyncNamespace):
    def __init__(self, ADStream, app, path, ad):

        super().__init__(path)

        self.AD = ad
        self.ADStream = ADStream
        self.app = app

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

        self.sio = socketio.AsyncServer(async_mode="aiohttp")
        self.sio.attach(self.app)

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

        self.sio.register_namespace(self.dash_stream)

        # await self.ADStream.on_connect(request)

    async def run(self):
        pass

    async def send(self, data):
        pass
