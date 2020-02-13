import socketio


class SocketIOHandler:
    def __init__(self, ADStream, app, path, ad):

        self.AD = ad
        self.ADStream = ADStream
        self.app = app
        self.path = path

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

        self.sio = socketio.AsyncServer(async_mode="aiohttp")

        self.sio.on("connect", self.connect)
        self.sio.on("down", self.down)

        self.sio.attach(self.app)

    async def down(self, sid, data):
        self.logger.debug("IOSocket Down sid={}".format(sid,))
        print(sid, data)

    async def connect(self, sid, environ):
        self.logger.debug("IOSocket Connect sid={} env={}".format(sid, environ))
        await self.ADStream.on_connect({"sid": sid, "environ": environ})

    def makeStream(self, ad, request, **kwargs):
        return SocketIOStream(ad, self.path, request, self.sio, **kwargs)


class SocketIOStream(socketio.AsyncNamespace):
    def __init__(self, ad, path, request, sio, **kwargs):

        super().__init__(path)

        self.sio = sio
        self.sid = request["sid"]
        self.on_message = kwargs["on_message"]
        self.on_disconnect = kwargs["on_disconnect"]

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

    async def run(self):
        pass

    async def sendclient(self, data):
        await self.sio.emit("up", data, room=self.sid)
