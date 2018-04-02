
function ha_status(stream, dash, widgets)
{

    var webSocket = new ReconnectingWebSocket(stream);
            
    webSocket.onopen = function (event) 
    {
        webSocket.send(dash);
    };

    webSocket.onmessage = function (event) 
    {
        var data = JSON.parse(event.data)
        if (data.event_type == "hadashboard")
        {
            if (data.data.command == "navigate")
            {
                var timeout_params = "";
                if ("timeout" in data.data)
                {
                    var timeout = data.data.timeout
                    if (location.search == "")
                    {
                        timeout_params = "?";
                    }
                    else
                    {
                        timeout_params = "&";
                    }
                    if ("return" in data.data)
                    {
                        ret = data.data.return
                    }
                    else
                    {
                        ret = location.pathname
                    }
                    if ("sticky")
                    {
                        sticky = data.data.sticky;
                    }
                    else
                    {
                        sticky = 0;
                    }

                    timeout_params += "timeout=" + timeout + "&return=" + ret + "&sticky=" + sticky;
                }
                window.location.href = data.data.target + location.search + timeout_params;
            }
        }
        Object.keys(widgets).forEach(function (key)
        {
            if ("on_ha_data" in widgets[key])
            {
                widgets[key].on_ha_data(data);
            }
        })
    };
    webSocket.onclose = function (event)
    {
        //window.alert("Server closed connection")
       // window.location.reload(false); 
    };

    webSocket.onerror = function (event)
    {
        //window.alert("Error occured")
        //window.location.reload(true);         
    }
}

var inheritsFrom = function (child, parent) {
    child.prototype = Object.create(parent.prototype);
};

var WidgetBase = function(widget_id, url, skin, parameters, monitored_entities, callbacks)
{
    child = this;
    child.url = url;
    
    // Function definitions
    
    this.set_field = function(self, field, value)
    {
        self.ViewModel[field](value)
    };
    
    this.format_number = function(self, value)
    {
        if ("precision" in self.parameters)
        {
            var precision = self.parameters.precision
        }
        else
        {
            var precision = 0
        }
        value = parseFloat(value);
        value = value.toFixed(precision);

        if ("shorten" in self.parameters && self.parameters.shorten == 1)
        {
            if (value >= 1E9)
            {
                value = (value / 1E9).toFixed(1) + "B"
            }
            else if (value >= 1E6)
            {
                value = (value / 1E6).toFixed(1) + "M"
            }
            else if (value >= 1E3)
            {
                value = (value / 1E3).toFixed(1) + "K"
            }
        }
        if ("use_comma" in self.parameters && self.parameters.use_comma == 1)
        {
            value = value.toString().replace(".", ",")
        }
        return value
    };

    
    this.map_state = function(self, value)
    {
        if ("state_map" in self.parameters)
        {
            if (value in self.parameters.state_map)
            {
                state = self.parameters.state_map[value]
            }
            else
            {
                state = value
            }
        }
        else
        {
            state = value
        }
        return (state)
    };
    
    this.set_icon = function(self, field, value)
    {
        self.ViewModel[field](value.split("-")[0] + ' ' + value)
    };
    
    this.get_state = function(child, base_url, entity)
    {
        state_url = base_url + "/state/" + parameters.namespace + "/" + entity.entity;
        $.ajax
        ({
            url: state_url,
            type: 'GET',
            success: function(data)
                    {
                        if (data.state == null)
                        {
                            if ("title" in child.ViewModel)
                            {
                                child.ViewModel.title("entity not found: " + entity.entity);
                                new_state = null
                            }
                            else
                            {
                                console.log("Entity not found: " + entity.entity)
                            }
                        }
                        else
                        {
                            new_state = data.state;
                            if ("use_hass_icon" in child.parameters &&
                                parameters.use_hass_icon == 1 &&
                                "attributes" in new_state && "icon" in new_state.attributes && new_state.attributes.icon != "False")
                            {
                                icon = new_state.attributes.icon.replace(":", "-")
                                child.icons.icon_on = icon
                                child.icons.icon_off = icon
                            }
                            if ("title_is_friendly_name" in child.parameters 
                            && child.parameters.title_is_friendly_name == 1
                            && "friendly_name" in new_state.attributes)
                            {
                                child.ViewModel.title(new_state.attributes.friendly_name)
                            }
                            if (typeof child.entity_state === 'undefined')
                            {
                                child.entity_state = {}
                            }
                            child.entity_state[entity.entity] = new_state;
                            entity.initial(child, new_state)
                        }
                    },
            error: function(data)
                    {
                        alert("Error getting state, check Java Console for details")
                    }
                  
        });
    };
   
    this.on_ha_data = function(data)
    {
        entity = data.data.entity_id;
        elen = monitored_entities.length;
        if (data.event_type == "state_changed" && data.namespace == parameters.namespace)
        {
            for (i = 0; i < elen; i++)
            {
                if (monitored_entities[i].entity == entity)
                {
                    state = data.data.new_state.state;
                    this.entity_state[entity] = data.data.new_state;
                    monitored_entities[i].update(this, data.data.new_state)
                }
            }
        }
    };
    
    this.call_service = function(child, args)
    {
        service_url = child.url + "/" + "call_service";
        args["namespace"] = parameters.namespace
        $.post(service_url, args);
    };

    // Initialization

    // Create and initialize bindings
    
    child.ViewModel = {};
    
    Object.keys(parameters.fields).forEach(function(key,index)
    {
        child.ViewModel[key] = ko.observable()
    });

    child.css = {};
    if ("css" in parameters)
    {
        Object.keys(parameters.css).forEach(function (key, index) {
            child.css[key] = parameters.css[key];
            child.ViewModel[key] = ko.observable()
        });
    }
    
    if ("static_css" in parameters)
    {
        Object.keys(parameters.static_css).forEach(function (key, index) {
            child.ViewModel[key] = ko.observable()
        });
    }
    
    child.icons = {};
    if ("icons" in parameters)
    {
        Object.keys(parameters.icons).forEach(function (key, index) {
            child.icons[key] = parameters.icons[key];
            child.ViewModel[key] = ko.observable()
        });
    }
    
    if ("static_icons" in parameters)
    {
        Object.keys(parameters.static_icons).forEach(function (key, index) {
            child.ViewModel[key] = ko.observable()
        });
    }
    
    ko.applyBindings(child.ViewModel, document.getElementById(widget_id));
    
    // Set any static values

    if ("fields" in parameters)
    {
        Object.keys(parameters.fields).forEach(function (key, index) {
            child.ViewModel[key](parameters.fields[key])
        });
    }

    if ("static_css" in parameters)
    {
        Object.keys(parameters.static_css).forEach(function (key, index) {
            child.ViewModel[key](parameters.static_css[key])
        });
    }

    if ("static_icons" in parameters)
    {
        Object.keys(parameters.static_icons).forEach(function (key, index) {
            child.ViewModel[key](parameters.static_icons[key].split("-")[0] + ' ' + parameters.static_icons[key])
        });
    }

    // Setup callbacks

    clen = callbacks.length;
    for (i=0;i < clen;i++)
    {
        if ("selector" in callbacks[i])
        {
            $(callbacks[i].selector).on(callbacks[i].action, (
                function (callback, ch, params) {
                    return function () {
                        callback(ch, params)
                    };
                }(callbacks[i].callback, child, callbacks[i].parameters))
            );
        }
        else if ("observable" in callbacks[i])
        {
            this.ViewModel[callbacks[i].observable].subscribe(
                (function(callback, ch)
              {
                  return function(newValue) {
                      callback(ch, newValue);
                  }
              }(callbacks[i].callback, child)), null, callbacks[i].action);
        }
    }

    // Grab current status for entities

    elen = monitored_entities.length;
    for (i=0;i < elen;i++)
    {
        this.get_state(child, url, monitored_entities[i])
    }
};

