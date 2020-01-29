import socketio
import aiohttp
from aiohttp import web
import traceback
import bcrypt
import uuid
import json
import threading

from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils


# socketio handler
class DashStream(socketio.AsyncNamespace):
    def __init__(self, ADStream, path, AD):

        super().__init__(path)

        self.AD = AD
        self.ADStream = ADStream

    async def on_connect(self, sid, data):
        await self.ADStream.on_connect()

    async def on_up(self, sid, data):
        await self.ADStream.on_msg(data)


class ADStream:
    def __init__(self, ad: AppDaemon, app, transport):

        self.AD = ad
        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()
        self.app = app
        self.transport = transport
        self.streams = {}
        self.streams_lock = threading.RLock()

        if self.transport == "ws":
            self.app.router.add_get("/stream", self.wshandler)
        else:
            self.dash_stream = DashStream(self, "/stream", self.AD)
            self.sio = socketio.AsyncServer(async_mode="aiohttp")
            self.sio.attach(self.app)
            self.sio.register_namespace(self.dash_stream)

    async def send_update(self, data):  # noqa: C901
        try:
            with self.streams_lock:
                if len(self.streams) > 0:
                    self.logger.debug("Sending data: %s", data)
                    for stream in self.streams:
                        if data["event_type"] == "state_changed":
                            for handle, sub in self.streams[stream].subscriptions["state"].items():
                                if sub["namespace"].endswith("*"):
                                    if not data["namespace"].startswith(sub["namespace"][:-1]):
                                        continue
                                else:
                                    if not data["namespace"] == sub["namespace"]:
                                        continue

                                if sub["entity_id"].endswith("*"):
                                    if not data["data"]["entity_id"].startswith(sub["entity_id"][:-1]):
                                        continue
                                else:
                                    if not data["data"]["entity_id"] == sub["entity_id"]:
                                        continue

                                await self.streams[stream].stream_send(data)
                                break
                        else:
                            for handle, sub in self.streams[stream].subscriptions["event"].items():
                                if sub["namespace"].endswith("*"):
                                    if not data["namespace"].startswith(sub["namespace"][:-1]):
                                        continue
                                else:
                                    if not data["namespace"] == sub["namespace"]:
                                        continue

                                if sub["event"].endswith("*"):
                                    if not data["event_type"].startswith(sub["event"][:-1]):
                                        continue
                                else:
                                    if not data["event_type"] == sub["event"]:
                                        continue

                                await self.streams[stream].stream_send(data)
                                break
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during 'send_update()'")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

    # @securedata
    async def wshandler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        rh = RequestHandler(self.AD, self.transport, ws)
        handle = uuid.uuid4().hex
        with self.streams_lock:
            self.streams[handle] = rh

        # noinspection PyBroadException
        try:
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await rh._handle(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.access.info("WebSocket connection closed with exception {}", ws.exception())
        except Exception:
            self.logger.debug("-" * 60)
            self.logger.debug("Unexpected client disconnection from %s", rh.client_name)
            self.access.info("Unexpected client disconnection from %s", rh.client_name)
            self.logger.debug("-" * 60)
            self.logger.debug(traceback.format_exc())
            self.logger.debug("-" * 60)
            # await ws.close()
        finally:
            with self.streams_lock:
                self.streams.pop(handle, None)

            event_data = {
                "event_type": "websocket_disconnected",
                "data": {"client_name": rh.client_name},
            }

            await self.AD.events.process_event("admin", event_data)

        return ws

    # Websockets Handler

    async def on_shutdown(self, application):
        with self.streams_lock:
            for stream in self.streams:
                try:
                    await self.streams[stream].stream.close()
                except Exception:
                    self.logger.debug("-" * 60)
                    self.logger.warning("Unexpected error in on_shutdown()")
                    self.logger.debug("-" * 60)
                    self.logger.debug(traceback.format_exc())
                    self.logger.debug("-" * 60)


## Any method here that doesn't begin with "_" will be exposed to the stream
## directly. Only Create public methods here if you wish to make them
## stream commands.
class RequestHandler:
    def __init__(self, ad: AppDaemon, transport, stream):
        self.AD = ad
        self.transport = transport
        self.stream = stream
        self.authed = False
        self.client_name = None
        self.subscriptions = {
            "state": {},
            "event": {},
        }

        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()

        if self.AD.http.password is None:
            self.authed = True

    async def stream_send(self, data):
        try:
            self.logger.debug("--> %s", data)
            if self.transport == "ws":
                await self.stream.send_json(data, dumps=utils.convert_json)
            else:
                # TODO replace with SocksJS
                jdata = utils.convert_json(data)
                await self.dash_stream.emit("down", jdata)
        except TypeError as e:
            self.logger.debug("-" * 60)
            self.logger.warning("Unexpected error in JSON conversion when writing to stream")
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

    async def _response_success(self, msg, data={}):
        response = {"response_type": msg["request_type"]}
        if "request_id" in msg:
            response["response_id"] = msg["request_id"]
        response["response_success"] = True
        response["data"] = data
        response["request"] = msg

        await self.stream_send(response)

    async def _response_error(self, msg, error):
        response = {"response_type": msg["request_type"]}
        if "request_id" in msg:
            response["response_id"] = msg["request_id"]
        response["response_success"] = False
        response["response_error"] = error
        response["request"] = msg

        await self.stream_send(response)

    async def _handle(self, rawmsg):
        self.logger.debug("<-- %s", rawmsg)
        try:
            msg = json.loads(rawmsg)
        except ValueError:
            return await self._response_error(rawmsg, "bad json data")

        if "request_type" not in msg:
            return await self._response_error(msg, "invalid request")

        if msg["request_type"][0] == "_":
            return await self._response_error(msg, "forbidden request")

        if not hasattr(self, msg["request_type"]):
            return await self._response_error(msg, "unavailable request")

        fn = getattr(self, msg["request_type"])

        if not callable(fn):
            return await self._response_error(msg, "uncallable request")

        request_data = msg.get("data", {})
        request_id = msg.get("request_id", None)

        try:
            data = await fn(request_data)
            if data is not None or request_id is not None:
                return await self._response_success(msg, data)
        except RequestHandlerException as e:
            return await self._response_error(msg, str(e))
        except Exception as e:
            await self._response_error(msg, "Unknown error occured, check AppDaemon logs: {}".format(str(e)))
            raise

    async def _check_adcookie(self, cookie):
        return await utils.run_in_executor(self, bcrypt.checkpw, str.encode(self.AD.http.password), str.encode(cookie))

    async def _auth_data(self, data):
        if "password" in data:
            if data["password"] == self.AD.http.password:
                self.authed = True
                return

        if "cookie" in data:
            if await self._check_adcookie(data["cookie"]):
                self.authed = True
                return

    async def hello(self, data):
        if "client_name" not in data:
            raise RequestHandlerException("client_name required")
        else:
            self.client_name = data["client_name"]

        if self.AD.http.password is None:
            self.authed = True

        if not self.authed:
            await self._auth_data(data)

        if not self.authed:
            raise RequestHandlerException("authorization failed")

        self.access.info("New client %s connected", data["client_name"])
        response_data = {"version": utils.__version__}

        event_data = {
            "event_type": "websocket_connected",
            "data": {"client_name": self.client_name},
        }

        await self.AD.events.process_event("admin", event_data)

        return response_data

    async def get_services(self, data):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        return self.AD.services.list_services()

    async def fire_event(self, data):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        if "namespace" not in data:
            raise RequestHandlerException("invalid namespace")

        if "event" not in data:
            raise RequestHandlerException("invalid event")

        event_data = data.get("data", {})

        return await self.AD.events.fire_event(data["namespace"], data["event"], **event_data)

    async def call_service(self, data):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        if "namespace" not in data:
            raise RequestHandlerException("invalid namespace")

        if "service" not in data:
            raise RequestHandlerException("invalid service")
        else:
            service = data["service"]

        if "domain" not in data:
            d, s = service.split("/")
            if d and s:
                domain = d
                service = s
            else:
                raise RequestHandlerException("invalid domain")
        else:
            domain = data["domain"]

        if "data" not in data:
            service_data = {}
        else:
            service_data = data["data"]

        return await self.AD.services.call_service(data["namespace"], domain, service, service_data)

    async def get_state(self, data):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        namespace = data.get("namespace", None)
        entity_id = data.get("entity_id", None)

        if entity_id is not None and namespace is None:
            raise RequestHandlerException("entity_id cannot be set without namespace")

        return self.AD.state.get_entity(namespace, entity_id, self.client_name)

    async def listen_state(self, data):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        if "namespace" not in data:
            raise RequestHandlerException("invalid namespace")

        if "entity_id" not in data:
            raise RequestHandlerException("invalid entity_id")

        handle = data.get("handle", uuid.uuid4().hex)

        if handle in self.subscriptions["state"]:
            raise RequestHandlerException("handle already exists")

        self.subscriptions["state"][handle] = {
            "namespace": data["namespace"],
            "entity_id": data["entity_id"],
        }

        return handle

    async def cancel_listen_state(self, data):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        if "handle" not in data:
            raise RequestHandlerException("invalid handle")

        if data["handle"] not in self.subscriptions["state"]:
            raise RequestHandlerException("invalid handle")

        del self.subscriptions["state"][data["handle"]]

        return True

    async def listen_event(self, data):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        if "namespace" not in data:
            raise RequestHandlerException("invalid namespace")

        if "event" not in data:
            raise RequestHandlerException("invalid event")

        handle = data.get("handle", uuid.uuid4().hex)

        if handle in self.subscriptions["event"]:
            raise RequestHandlerException("handle already exists")

        self.subscriptions["event"][handle] = {
            "namespace": data["namespace"],
            "event": data["event"],
        }

        return handle

    async def cancel_listen_event(self, data):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        if "handle" not in data:
            raise RequestHandlerException("invalid handle")

        if data["handle"] not in self.subscriptions["event"]:
            raise RequestHandlerException("invalid handle")

        del self.subscriptions["event"][data["handle"]]

        return True


class RequestHandlerException(Exception):
    pass
