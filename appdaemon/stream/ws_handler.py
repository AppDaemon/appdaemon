import traceback
import json

import aiohttp
from aiohttp import web
import asyncio

from appdaemon import utils as utils


class WSHandler:
    def __init__(self, ADStream, app, path, ad):

        self.AD = ad
        self.ADStream = ADStream
        self.app = app

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

        self.app.router.add_get(path, self.wshandler)

    async def wshandler(self, request):
        #
        # We have a connection
        #
        # Add handler
        await self.ADStream.on_connect(request)

    def makeStream(self, ad, request, **kwargs):
        return WSStream(ad, request, **kwargs)


class WSStream:
    def __init__(self, ad, request, **kwargs):

        self.request = request
        self.on_message = kwargs["on_message"]
        self.on_disconnect = kwargs["on_disconnect"]

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()
        self.client_name = kwargs.get("client_name")

    def set_client_name(self, client_name):
        self.client_name = client_name

    async def run(self):
        self.lock = asyncio.Lock()
        self.ws = web.WebSocketResponse()
        await self.ws.prepare(self.request)

        try:
            while True:
                msg = await self.ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        msg = json.loads(msg.data)
                        await self.on_message(msg)
                    except ValueError:
                        self.logger.warning("Unexpected error in JSON conversion when receiving from stream")
                        self.logger.debug("-" * 60)
                        self.logger.debug("BAD JSON Data: {}", msg.data)
                        self.logger.debug("-" * 60)
                        self.logger.debug(traceback.format_exc())
                        self.logger.debug("-" * 60)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.access.info("WebSocket connection closed with exception {}", self.ws.exception())
        except Exception:
            self.logger.debug("-" * 60)
            self.logger.debug("Unexpected client disconnection from client %s", self.client_name)
            self.logger.debug("-" * 60)
            self.logger.debug(traceback.format_exc())
            self.logger.debug("-" * 60)
        finally:
            await self.on_disconnect()
            self.logger.debug("Closing websocket ...")
            await self.ws.close()
            self.logger.debug("Done")

    async def sendclient(self, data):
        try:
            async with self.lock:
                await self.ws.send_json(data, dumps=utils.convert_json)

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
