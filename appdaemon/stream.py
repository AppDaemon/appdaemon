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
        except Exception as e:
            self.logger.debug('-' * 60)
            self.logger.debug("Client disconnected unexpectedly")
            self.access.info("Client disconnected unexpectedly")
            self.logger.info("Data is: %s", data)
            self.logger.info("Error is: %s",e)
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
        except Exception as e:
            self.logger.debug('-' * 60)
            self.logger.debug("Unexpected client disconnection")
            self.access.info("Unexpected client disconnection {}".format(e))
            self.logger.debug('-' * 60)
            self.logger.debug(traceback.format_exc())
            self.logger.debug('-' * 60)
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

    async def _handle(self, rawmsg):
        try:
            msg = json.loads(rawmsg)
        except ValueError:
            return await self._response_error('bad json data')

        if "request_type" not in msg:
            return await self._response_error('invalid request')

        if msg['request_type'][0] == '_':
            return await self._response_error('forbidden request')

        if not hasattr(self, msg['request_type']):
            return await self._response_error('unavailable request')

        fn = getattr(self, msg['request_type'])

        if not callable(fn):
            return await self._response_error('uncallable request')

        return await fn(msg)

    async def _response(self, type, data={}):
        data["response_type"] = type
        await self.ws.send_json(data)

    async def _response_unauthed_error(self):
        return await self._response_error('unauthorized')

    async def _response_error(self, error):
        await self._response('error', {"msg": error})

    async def _check_adcookie(self, cookie):
        return await utils.run_in_executor(
            self,
            bcrypt.checkpw,
            str.encode(self.AD.http.password),
            str.encode(cookie))

    async def _auth_data(self, data):
        self.logger.info("auth data {}".format(data))
        if "password" in data:
            if data['password'] == self.AD.http.password:
                self.authed = True
                return
            else:
                self.logger.info('Password in Data does not match Config')
        else:
            self.logger.info('Password Not in Data')

        if "cookie" in data:
            if await self._check_adcookie(data['cookie']):
                self.authed = True
                return
            else:
                self.logger.info('Cookie in Data does not match Config')
        else:
            self.logger.info('Cookie not in Data')

    async def hello(self, data):
        if self.AD.http.password is None:
            self.logger.info('Password Not In Config')
            self.authed = True

        if not self.authed:
            await self._auth_data(data)

        if not self.authed:
            return await self._response_unauthed_error()

        if "client_name" not in data:
            return await self._response_unauthed_error()

        return await self._response('authed')

    async def get_state(self, data):
        if not self.authed:
            return await self._response_unauthed_error()

        ret = self.AD.state.get_entity()
        return await self._response('get_state', ret)

    async def listen_state(self, data):
        if not self.authed:
            return await self._response_unauthed_error()

        if "namespace" not in data:
            return await self._response_error('invalid listen_state namespace')

        if "entity_id" not in data:
            return await self._response_error('invalid listen_state entity_id')

        self.subscriptions['state'].append({
            "namespace": data['namespace'],
            "entity_id": data['entity_id']
        })

    async def listen_event(self, data):
        if not self.authed:
            return await self._response_unauthed_error()

        if "namespace" not in data:
            return await self._response_error('invalid listen_event namespace')

        if "event" not in data:
            return await self._response_error('invalid listen_event event')

        self.subscriptions['event'].append({
            "namespace": data['namespace'],
            "event": data['event']
        })
