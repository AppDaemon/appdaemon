lesfunction getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) === ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) === 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function get_monitored_entities(widgets)
{
    index = 0;
    entities = [];
    Object.keys(widgets).forEach(function (key) {
        var value = widgets[key];
        elen = value.monitored_entities.length;
        if ("resident_namespace" in value.parameters)
        {
            ns = value.parameters.resident_namespace
        }
        else
        {
            ns = value.parameters.namespace;
        }
        for (i=0;i < elen;i++)
        {
            entities[index++] = {entity: value.monitored_entities[i].entity, namespace: ns, widget: value}
        }
});
    return entities
}

var DashStream = function(transport, protocol, domain, port, title, widgets)
{
    var self = this;

    this.on_connect = function(data)
    {
        // Grab state

        self.stream.get_state('*', '*', self.populate_dash);

        // subscribe to all events

        self.stream.listen_event('*', '__HADASHBOARD_EVENT', self.update_dash);

        // Subscribe to just the entities we care about for this dashboard

        entities = get_monitored_entities(widgets);
        elen = entities.length;
        for (i=0;i < elen;i++)
        {
            self.stream.listen_state(entities[i].namespace, entities[i].entity, self.update_dash)
        }

    };

    this.on_message = function(data)
    {
        console.log("Generic message", data)
    };

    this.on_disconnect = function(data)
    {
        console.log("Disconnect", data)
    };

    this.populate_dash = function(data) {
        {
            entities = get_monitored_entities(widgets);
            elen = entities.length;
            for (i = 0; i < elen; i++) {
                entity = entities[i].entity;
                ns = entities[i].namespace;
                widget = entities[i].widget;
                widget.set_state(widget, data.data[ns][entity]);
            }
        }
    };

    this.update_dash = function(msg)
    {
        data = msg.data;
        if (data.event_type === "__HADASHBOARD_EVENT"  &&
           ((data.data.deviceid && data.data.deviceid === my_deviceid) ||
            (data.data.dashid && title.includes(data.data.dashid)) ||
            (!data.data.deviceid && !data.data.dashid)))    
        {
            if (data.data.command === "navigate")
            {
                var timeout_params = "";
                if ("timeout" in data.data)
                {
                    var timeout = data.data.timeout;
                    if (location.search === "")
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
        Object.keys(widgets).forEach(function (key) {
            if ("on_ha_data" in widgets[key])
            {
                widgets[key].on_ha_data(data);
            }
        })
    };

    this.stream = new Stream(transport, protocol, domain, port, title, this.on_connect, this.on_message, this.on_disconnect);

};

var inheritsFrom = function (child, parent) {
    child.prototype = Object.create(parent.prototype);
};

var WidgetBase = function(widget_id, url, skin, parameters, monitored_entities, callbacks)
{
    child = this;
    child.monitored_entities = monitored_entities;
    child.url = url;

    // Function definitions

    this.set_field = function(self, field, value)
    {
        self.ViewModel[field](value)
    };

    this.format_number = function(self, value)
    {
        var precision = 0;
        if ("precision" in self.parameters)
        {
            precision = self.parameters.precision
        }
        value = parseFloat(value);
        value = value.toFixed(precision);

        if ("shorten" in self.parameters && self.parameters.shorten === 1)
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
        if ("use_comma" in self.parameters && self.parameters.use_comma === 1)
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

    this.convert_icon = function(self, value)
    {
        bits = value.split("-");
        iprefix = bits[0];
        iname = "";
        for (var i = 1; i <  bits.length; i++)
        {
            if (i!==1)
            {
                iname += "-"
            }
            iname += bits[i]
        }
        if (iprefix === "mdi")
        {
            icon = "mdi" + ' ' + value
        }
        else
        {
           icon = iprefix + ' ' + 'fa-' + iname
        }

        return icon
    };

    this.set_icon = function(self, field, value)
    {
        self.ViewModel[field](self.convert_icon(self, value))
    };

    this.set_state = function(child, data)
    {
        if (data == null || data.state == null)
        {
            if ("title" in child.ViewModel)
            {
                child.ViewModel.title("entity not found: " + child.parameters.entity);
            }
            else
            {
                console.log("Entity not found: " + child.parameters.entity)
            }
        }
        else
        {
            if ("use_hass_icon" in child.parameters &&
                parameters.use_hass_icon === 1 &&
                "attributes" in data && "icon" in data.attributes && data.attributes.icon !== "False")
            {
                icon = data.attributes.icon.replace(":", "-");
                child.icons.icon_on = icon;
                child.icons.icon_off = icon
            }
            if ("title_is_friendly_name" in child.parameters
            && child.parameters.title_is_friendly_name === 1
            && "friendly_name" in data.attributes)
            {
                child.ViewModel.title(data.attributes.friendly_name)
            }
            if ("title2_is_friendly_name" in child.parameters
            && child.parameters.title2_is_friendly_name === 1
            && "friendly_name" in data.attributes)
            {
                child.ViewModel.title2(data.attributes.friendly_name)
            }
            if (typeof child.entity_state === 'undefined')
            {
                child.entity_state = {}
            }
            child.entity_state[child.entity] = data;
            var entity = data.entity_id;
            var elen = child.monitored_entities.length;
            for (j = 0; j < elen; j++)
            {
                if (child.monitored_entities[j].entity === entity)
                {
                    monitored_entities[j].initial(child, data)
                }
            }
        }
    };

    this.on_ha_data = function(data)
    {
        entity = data.data.entity_id;
        elen = monitored_entities.length;
        if (data.event_type === "state_changed" && data.namespace === parameters.namespace)
        {
            for (i = 0; i < elen; i++)
            {
                if (monitored_entities[i].entity === entity)
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
        if ("resident_namespace" in child.parameters)
        {
            ns = child.parameters.resident_namespace
        }
        else
        {
            ns = child.parameters.namespace;
        }

        service = args["service"];

        window.dashstream.stream.call_service(service, ns, args)
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
            child.ViewModel[key](self.convert_icon(self, parameters.static_icons[key]))
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
};
