import traceback
import bcrypt
import uuid
import threading
import asyncio

from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils
from appdaemon.stream.socketio_handler import SocketIOHandler
from appdaemon.stream.ws_handler import WSHandler
from appdaemon.stream.sockjs_handler import SockJSHandler


class ADStream:
    def __init__(self, ad: AppDaemon, app, transport):

        self.AD = ad
        self.logger = ad.logging.get_child("_stream")
        self.access = ad.logging.get_access()
        self.app = app
        self.transport = transport
        self.handlers = {}
        self.handlers_lock = threading.RLock()

        if self.transport == "ws":
            self.stream_handler = WSHandler(self, app, "/stream", self.AD)
        elif self.transport == "socketio":
            self.stream_handler = SocketIOHandler(self, app, "/stream", self.AD)
        elif self.transport == "sockjs":
            self.stream_handler = SockJSHandler(self, app, "/stream", self.AD)
        else:
            self.logger.warning("Unknown stream type: %s", transport)

    def get_handler(self, id):
        with self.handlers_lock:
            for handle in self.handlers:
                if self.handlers[handle].stream.client_id == id:
                    return self.handlers[handle]
        return None

    def get_handle(self, id):
        with self.handlers_lock:
            for handle in self.handlers:
                if self.handlers[handle].stream.client_id == id:
                    return handle
        return None

    async def on_connect(self, request):
        # New connection - create a handler and add it to the list
        handle = uuid.uuid4().hex
        rh = RequestHandler(self.AD, self, handle, request)
        with self.handlers_lock:
            self.handlers[handle] = rh
        await rh.stream.run()

    async def on_disconnect(self, handle):
        with self.handlers_lock:
            del self.handlers[handle]

    async def process_event(self, data):  # noqa: C901
        try:
            with self.handlers_lock:
                if len(self.handlers) > 0:
                    # self.logger.debug("Sending data: %s", data)
                    for handler in self.handlers:
                        if self.handlers[handler].authed is True:  # if authenticated
                            # await self.handlers[handler]._event(data)
                            asyncio.ensure_future(self.handlers[handler]._event(data))

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during 'process_event()'")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)


## Any method here that doesn't begin with "_" will be exposed to the stream
## directly. Only Create public methods here if you wish to make them
## stream commands.
class RequestHandler:
    def __init__(self, ad: AppDaemon, adstream, handle, request):
        self.AD = ad
        self.handle = handle
        self.adstream = adstream
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

        # Create a stream
        #
        self.stream = self.adstream.stream_handler.makeStream(
            self.AD, request, on_message=self._on_message, on_disconnect=self._on_disconnect
        )
        #

    async def _on_message(self, data):
        await self._request(data)

    async def _on_disconnect(self):
        await self.adstream.on_disconnect(self.handle)
        self.access.info("Client disconnection from %s", self.client_name)
        event_data = {
            "event_type": "stream_disconnected",
            "data": {"client_name": self.client_name},
        }

        await self.AD.events.process_event("admin", event_data)

    async def _event(self, data):
        response = {"data": data}
        if data["event_type"] == "state_changed":
            for handle, sub in self.subscriptions["state"].items():
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

                response["response_id"] = sub["response_id"]
                response["response_type"] = "state_changed"
                await self._respond(response)
                break
        else:
            for handle, sub in self.subscriptions["event"].items():
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

                response["response_id"] = sub["response_id"]
                response["response_type"] = "event"
                await self._respond(response)
                break

    async def _respond(self, data):
        self.logger.debug("--> %s", data)
        await self.stream.sendclient(data)

    async def _response_success(self, msg, data=None):
        response = {"response_type": msg["request_type"]}
        if "request_id" in msg:
            response["response_id"] = msg["request_id"]
        response["response_success"] = True
        if data is None:
            response["data"] = {}
        else:
            response["data"] = data

        response["request"] = msg

        await self._respond(response)

    async def _response_error(self, msg, error):
        response = {"response_type": msg["request_type"]}
        if "request_id" in msg:
            response["response_id"] = msg["request_id"]
        response["response_success"] = False
        response["response_error"] = error
        response["request"] = msg

        await self._respond(response)

    async def _request(self, msg):
        self.logger.debug("<-- %s", msg)

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
            data = await fn(request_data, request_id)
            if data is not None or request_id is not None:
                return await self._response_success(msg, data)
        except RequestHandlerException as e:
            return await self._response_error(msg, str(e))
        except Exception as e:
            await self._response_error(msg, "Unknown error occurred, check AppDaemon logs: {}".format(str(e)))
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

    async def hello(self, data, request_id):
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

        self.stream.set_client_name(self.client_name)

        self.access.info("New client %s connected", data["client_name"])
        response_data = {"version": utils.__version__}

        event_data = {
            "event_type": "stream_connected",
            "data": {"client_name": self.client_name},
        }

        await self.AD.events.process_event("admin", event_data)

        return response_data

    async def get_services(self, data, request_id):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        return self.AD.services.list_services()

    async def fire_event(self, data, request_id):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        if "namespace" not in data:
            raise RequestHandlerException("invalid namespace")

        if "event" not in data:
            raise RequestHandlerException("invalid event")

        event_data = data.get("data", {})

        return await self.AD.events.fire_event(data["namespace"], data["event"], **event_data)

    async def call_service(self, data, request_id):
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
            if "service" in data["data"]:
                del data["data"]["service"]

            service_data = data["data"]

        return await self.AD.services.call_service(data["namespace"], domain, service, service_data)

    async def get_state(self, data, request_id):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        namespace = data.get("namespace", None)
        entity_id = data.get("entity_id", None)

        if entity_id is not None and namespace is None:
            raise RequestHandlerException("entity_id cannot be set without namespace")

        return self.AD.state.get_entity(namespace, entity_id, self.client_name)

    async def listen_state(self, data, request_id):
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
            "response_id": request_id,
            "namespace": data["namespace"],
            "entity_id": data["entity_id"],
        }

        return handle

    async def cancel_listen_state(self, data, request_id):
        if not self.authed:
            raise RequestHandlerException("unauthorized")

        if "handle" not in data:
            raise RequestHandlerException("invalid handle")

        if data["handle"] not in self.subscriptions["state"]:
            raise RequestHandlerException("invalid handle")

        del self.subscriptions["state"][data["handle"]]

        return True

    async def listen_event(self, data, request_id):
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
            "response_id": request_id,
            "namespace": data["namespace"],
            "event": data["event"],
        }

        return handle

    async def cancel_listen_event(self, data, request_id):
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
