var Stream = function(transport, protocol, domain, port, client_name, on_connect, on_message, on_disconnect)
{

    var self = this;
    this.client_name = client_name;
    this.on_connect = on_connect;
    this.on_message = on_message;
    this.on_disconnect = on_disconnect;
    this.outstanding_requests = {};

    if (transport === "ws")
    {
        if (protocol === 'https:')
        {
            prot = "wss:";
        }
        else
        {
            prot = "ws:"
        }
    }
    else
    {
        prot = protocol
    }

    stream_url = prot + '//' + domain + ':' + port + "/stream";

    this.uuidv4 = function()
    {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
    };

    this.ad_on_connect = function()
    {
        var data =
            {
                client_name: client_name
            };

            if (getCookie('adcreds') !== '') {
                var creds = getCookie('adcreds');
                creds = creds.substring(1, (creds.length - 1));
                data['cookie'] = creds
            }

            var request =
                {
                    request_type: "hello",
                    data: data
                };

            self.send(request);
    };

    this.ad_on_disconnect = function()
    {
        // do nothing
    };

    this.send = function(request, callback)
    {
        id = this.uuidv4();
        request["request_id"] = id;

        self.outstanding_requests[id] = {callback: callback, request: request};
        self.stream.send(request);

        return id
    };

    this.ad_on_message = function(data)
    {
        if ("response_success" in data && data.response_success === false)
        {
            console.log("Error in stream: " + data.response_error, data)
        }
        else
        {
            if ("response_type" in data)
            {
                if (data.response_type === "listen_state" || data.response_type === "listen_event")
                {
                    // Ignore it - we don't want to delete the registration
                }
                else if (data.response_type === "state_changed" || data.response_type === "event")
                {
                    // Call the function but don't delete the registration
                    id = data.response_id;
                    if (id in self.outstanding_requests) {
                        callback = self.outstanding_requests[id].callback;
                        if (callback !== undefined) {
                            callback(data)
                        }
                    }
                }
                else if (data.response_type === "hello")
                {
                    id = data.response_id;
                    delete self.outstanding_requests[id];
                    self.on_connect(data)
                }
                else
                {
                    // This is a response to a one off request, dispatch it to the requester
                    if ("response_id" in data) {
                        id = data.response_id;
                        if (id in self.outstanding_requests) {
                            callback = self.outstanding_requests[id].callback;
                            delete self.outstanding_requests[id];
                            if (callback !== undefined) {
                                callback(data)
                            }
                        } else {
                            // No callback was specified so just drop it
                            console.log("Dropping specific callback", data)
                        }
                    } else {
                        // No specific callback, so send to generic callback if we have one
                        if (self.on_message !== undefined) {
                            self.on_message(data)
                        } else {
                            // Nothing to do so drop response
                            console.log("Dropping non-specific callback", data)
                        }
                    }
                }
            }
            else
            {
                console.log("Unknown response type", data)
            }
        }
    };

    this.listen_state = function(namespace, entity, callback)
    {
        request = {
            request_type: "listen_state",
            data: {
                namespace: namespace,
                entity_id: entity
            }
        };

        return self.send(request, callback)
    };

    this.listen_event = function(namespace, event, callback)
    {
        var request = {
            request_type: "listen_event",
            data: {
                namespace: namespace,
                event: event
            }
        };

        return self.send(request, callback)
    };

    this.cancel_listen_state = function(handle)
    {

    };

    this.cancel_listen_event = function(handle)
    {

    };

    this.get_state = function(namespace, entity, callback)
    {
        var request = {
            request_type: "get_state",
            data: {}
        };

        if (namespace !== "*")
        {
            request.data.namespace = namespace
        }

        if (entity !== "*")
        {
            request.data.entity_id = entity
        }
        self.send(request, callback)
    };

    this.call_service = function(service, namespace, args, callback)
    {
        args["__name"] = "stream"
        request = {
            request_type: "call_service",
            data: {
                namespace: namespace,
                service: service,
                data: args
            }
        };

        self.send(request, callback)
    };

    if (transport === "ws")
    {
        this.stream = new WSStream(stream_url, this.ad_on_connect, this.ad_on_message, this.ad_on_disconnect)
    }
    else if (transport === "socketio")
    {
        this.stream = new SocketIOStream(stream_url, this.ad_on_connect, this.ad_on_message, this.ad_on_disconnect)
    }
    else if (transport === "sockjs")
    {
        this.stream = new SockJSStream(stream_url, this.ad_on_connect, this.ad_on_message, this.ad_on_disconnect)
    }
};

var SockJSStream = function(stream, on_connect, on_message, on_disconnect)
{
    var self = this;
    this.on_connect = on_connect;
    this.on_message = on_message;
    this.on_disconnect = on_disconnect;

    this.send = function(data)
    {
        sock.send(JSON.stringify(data));
    };

    this.sjs_on_connect = function()
    {
        self.on_connect()
    };

    this.sjs_on_message = function(event)
    {
        var data = JSON.parse(event.data);
        self.on_message(data)
    };

    this.sjs_on_disconnect = function()
    {
        self.on_disconnect()
    };

    var sock = new SockJS(stream);

    sock.onopen = this.sjs_on_connect;
    sock.onmessage = this.sjs_on_message;
    sock.onclose = this.sjs_on_disconnect;

};

var SocketIOStream = function(stream, on_connect, on_message, on_disconnect)
{

    var self = this;
    this.on_connect = on_connect;
    this.on_message = on_message;
    this.on_disconnect = on_disconnect;

    this.send = function(data)
    {
        iosocket.emit("down", JSON.stringify(data))
    };

    this.sio_on_connect = function()
    {
        self.on_connect()
    };

    this.sio_on_message = function(event)
    {
        var data = JSON.parse(event);

        self.on_message(data)
    };

    this.sio_on_disconnect = function()
    {
        self.on_disconnect()
    };

    var iosocket = io(stream);

    iosocket.on("connect", function()
    {
        self.sio_on_connect()
    });

    iosocket.on("up", function(msg)
    {
        self.sio_on_message(msg)
    });

    iosocket.on("disconnect", function()
    {
        self.sio_on_disconnect()
    });
};

var WSStream = function(stream, on_connect, on_message, on_disconnect)
{

    var self = this;
    this.on_connect = on_connect;
    this.on_message = on_message;
    this.on_disconnect = on_disconnect;

    this.send = function(data)
    {
        webSocket.send(JSON.stringify(data));
    };

    this.ws_on_connect = function()
    {
        self.on_connect()
    };

    this.ws_on_message = function(event)
    {
        var data = JSON.parse(event.data);
        self.on_message(data)
    };

    this.ws_on_disconnect = function()
    {
        self.on_disconnect()
    };

    var webSocket = new ReconnectingWebSocket(stream);

    webSocket.onopen = this.ws_on_connect;
    webSocket.onmessage = this.ws_on_message;
    webSocket.onclose = this.ws_on_disconnect;

};
