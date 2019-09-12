import socketio
import json
import aiohttp
from aiohttp import web
import traceback
import bcrypt

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

        if self.transport == "ws":
            self.app['websockets'] = {}
            self.app.router.add_get('/stream', self.wshandler)
        else:
            self.dash_stream = DashStream(self, '/stream', self.AD)
            self.sio = socketio.AsyncServer(async_mode='aiohttp')
            self.sio.attach(self.app)
            self.sio.register_namespace(self.dash_stream)

    async def send_update(self, data):
        try:
            if self.transport == "ws":
                if len(self.app['websockets']) > 0:
                    self.logger.debug("Sending data: %s", json.dumps(data))
                    for ws in self.app['websockets']:
                        rh = self.app['websockets'][ws]
                        if data['event_type'] == 'state_changed':
                            for sub in rh.subscriptions['state']:
                                if sub['namespace'].endswith('*'):
                                    if not data['namespace'].startswith(sub['namespace'][:-1]):
                                        continue
                                else:
                                    if not data['namespace'] == sub['namespace']:
                                        continue
                            
                                if sub['entity_id'].endswith('*'):
                                    if not data['data']['entity_id'].startswith(sub['entity_id'][:-1]):
                                        continue
                                else:
                                    if not data['data']['entity_id'] == sub['entity_id']:
                                        continue
                                
                                await ws.send_json(data)
                                break
                        else:
                            for sub in rh.subscriptions['event']:
                                if sub['namespace'].endswith('*'):
                                    if not data['namespace'].startswith(sub['namespace'][:-1]):
                                        continue
                                else:
                                    if not data['namespace'] == sub['namespace']:
                                        continue
                            
                                if sub['event'].endswith('*'):
                                    if not data['event_type'].startswith(sub['event'][:-1]):
                                        continue
                                else:
                                    if not data['event_type'] == sub['event']:
                                        continue
                                
                                await ws.send_json(data)
                                break


            else:
                await self.dash_stream.emit('down', jdata)
        except TypeError as e:
            self.logger.debug('-' * 60)
            self.logger.warning("Unexpected error in JSON conversion")
            self.logger.debug("Data is: %s", data)
            self.logger.debug("Error is: %s",e)
            self.logger.debug('-' * 60)
        except:
            self.logger.debug('-' * 60)
            self.logger.debug("Client disconnected unexpectedly")
            self.access.info("Client disconnected unexpectedly")
            self.logger.debug('-' * 60)
            self.logger.debug(traceback.format_exc())
            self.logger.debug('-' * 60)

    #@securedata
    async def wshandler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        rh = RequestHandler(self.AD, ws, self.app)
        request.app['websockets'][ws] = rh

        # noinspection PyBroadException
        try:
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await rh._handle(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.access.info("WebSocket connection closed with exception {}", ws.exception())
        except:
            self.logger.warning('-' * 60)
            self.logger.warning("Unexpected client disconnection")
            self.access.info("Unexpected client disconnection")
            self.logger.warning('-' * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning('-' * 60)
            await ws.close()
        finally:
            request.app['websockets'].pop(ws, None)

        return ws

    # Websockets Handler

    async def on_shutdown(self, application):
        for ws in application['websockets']:
            try:
                print(ws.closed)
                await ws.close()
                print("done")
            except:
                self.logger.debug('-' * 60)
                self.logger.warning("Unexpected error in on_shutdown()")
                self.logger.debug('-' * 60)
                self.logger.debug(traceback.format_exc())
                self.logger.debug('-' * 60)

## Any method here that doesn't begin with "_" will be exposed to the websocket
## directly. Only Create public methods here if you wish to make them
## websocket commands.
class RequestHandler:

    def __init__(self, ad: AppDaemon, ws, app):
        self.AD = ad
        self.ws = ws
        self.app = app
        self.authed = False
        self.subscriptions = {
            'state': [],
            'event': [],
        }

        self.logger = ad.logging.get_child("_stream")


        if self.AD.http.password is None:
            self.authed = True

    async def _response_success(self, msg, data={}):
        response = {}
        response['response_type'] = msg['request_type']
        if "request_id" in msg:
            response['response_id'] = msg['request_id']
        response['response_success'] = True
        response['data'] = data

        await self.ws.send_json(response)

    async def _response_error(self, msg, error):
        response = {}
        response['response_type'] = msg['request_type']
        if "request_id" in msg:
            response['response_id'] = msg['request_id']
        response['response_success'] = False
        response['response_error'] = error
        response['request'] = msg

        await self.ws.send_json(response)

    async def _handle(self, rawmsg):
        try:
            msg = json.loads(rawmsg)
        except ValueError:
            return await self._response_error(rawmsg, 'bad json data')

        self.logger.info(msg)

        if "request_type" not in msg:
            return await self._response_error(msg, 'invalid request')

        if msg['request_type'][0] == '_':
            return await self._response_error(msg, 'forbidden request')

        if not hasattr(self, msg['request_type']):
            return await self._response_error(msg, 'unavailable request')

        fn = getattr(self, msg['request_type'])

        if not callable(fn):
            return await self._response_error(msg, 'uncallable request')

        request_data = msg.get('data', {})
        request_id = msg.get('request_id', None)

        self.logger.info("trying {}".format(request_data))

        success = False
        try:
            data = await fn(request_data)
            success = True
        except Exception as e:
            self.logger.info('RequestHandler Exception %s', str(e))
            success = False
            data = str(e)

        if success is False:
            return await self._response_error(msg, data)

        if data is not None or request_id is not None:
            return await self._response_success(msg, data)
        
        return

    async def _check_adcookie(self, cookie):
        return await utils.run_in_executor(
            self,
            bcrypt.checkpw,
            str.encode(self.AD.http.password),
            str.encode(cookie))

    async def _auth_data(self, data):
        if "password" in data:
            if data['password'] == self.AD.http.password:
                self.authed = True
                return

        if "cookie" in data:
            if await self._check_adcookie(data['cookie']):
                self.authed = True
                return

    async def hello(self, data):
        if "client_name" not in data:
            raise Exception('client_name required')

        if self.AD.http.password is None:
            self.authed = True

        if not self.authed:
            await self._auth_data(data)

        if not self.authed:
            raise Exception('authorization failed')

        return True

    async def call_service(self, data):
        if not self.authed:
            raise Exception('unauthorized')

        if "namespace" not in data:
            raise Exception('invalid namespace')

        if "service" not in data:
            raise Exception('invalid service')
        else:
            service = data['service']

        if "domain" not in data:
            d, s = service.split("/")
            if d and s:
                domain = d
                service = s
            else:
                raise Exception('invalid domain')
        else:
            domain = data['domain']

        if "data" not in data:
            service_data = {}
        else:
            service_data = data['data']

        return await self.AD.services.call_service(data['namespace'], domain, service, service_data)

    async def get_state(self, data):
        if not self.authed:
            raise Exception('unauthorized')

        return self.AD.state.get_entity()

    async def listen_state(self, data):
        if not self.authed:
            raise Exception('unauthorized')

        if "namespace" not in data:
            raise Exception('invalid namespace')

        if "entity_id" not in data:
            raise Exception('invalid entity_id')

        self.subscriptions['state'].append({
            "namespace": data['namespace'],
            "entity_id": data['entity_id']
        })

        return

    async def listen_event(self, data):
        if not self.authed:
            raise Exception('unauthorized')

        if "namespace" not in data:
            raise Exception('invalid namespace')

        if "event" not in data:
            raise Exception('invalid event')

        self.subscriptions['event'].append({
            "namespace": data['namespace'],
            "event": data['event']
        })

        return
