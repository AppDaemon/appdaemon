function dimmer(widget_id, url, parameters)
{
    // Store Args
    this.widget_id = widget_id;
    this.parameters = parameters;
    this.utl = url;
    
    // Add in methods
    this.on_ha_data = on_ha_data;
    this.get_state = get_state;
    this.toggle = toggle;
    this.call_service = call_service;
    
    // Create and initialize bindings
    this.ViewModel = 
    {
        title: ko.observable(parameters.title),
        icon: ko.observable(),
        icon_style: ko.observable(),
        level: ko.observable()
    };
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id));

    // Do some setup
    
    this.state = "off";
    this.brightness = 0;
    this.on_brightness = 127;
    
    if ("on_brightness" in parameters)
    {
        this.on_brightness = parameters["on_brightness"]
    }
    
    this.increment = 25.4
    if ("increment" in parameters)
    {
        this.increment = parameters["increment"]
    }
    
    this.icon_on = "fa-circle";
    if  ("icon_on" in parameters)
    {
        this.icon_on = parameters["icon_on"];
    }

    this.icon_off = "fa-circle-thin";
    if  ("icon_off" in parameters)
    {
        this.icon_off = parameters["icon_off"];
    }
    
    // Setup Override Styles
    
    if ("background_color" in parameters)
    {
        $('#' + widget_id).css("background-color", parameters["background_color"])
    }
        
    if ("icon_size" in parameters)
    {
        $('#' + widget_id + ' > h2').css("font-size", parameters["icon_size"])
    }
    
    if ("title_color" in parameters)
    {
        $('#' + widget_id + ' > h1').css("color", parameters["title_color"])
    }
    
    if ("title_size" in parameters)
    {
        $('#' + widget_id + ' > h1').css("font-size", parameters["title_size"])
    }    

    // Get initial state
    if ("monitored_entity" in parameters)
    {
        entity = parameters.monitored_entity
    }
    else
    {
        entity = parameters.entity
    }
    this.get_state(url, entity)
    
    // Define onClick handler for on/off
    
    var that = this
    $('#' + widget_id + ' > span').click(
        function()
        {
            if (that.state == "on")
            {
                args = {"service": "homeassistant/turn_off", "entity_id": parameters["entity"]}

            }
            else
            {
                args = {"service": "homeassistant/turn_on", "entity_id": parameters["entity"], "brightness": that.on_brightness}
            }
            that.toggle();
            that.call_service(url, args)
        }
    )

    // Define onClick handler for Raise Brightness

    $('#' + widget_id + ' #level-up').click(
        function()
        {
            that.brightness = Math.round(that.brightness + that.increment);
            if (that.brightness > 254)
            {
                that.brightness = 254
            }
            args = {"service": "homeassistant/turn_on", "entity_id": parameters["entity"], "brightness": that.brightness}
            that.call_service(url, args) 
        }
    )

    // Define onClick handler for Lower Brightness

    $('#' + widget_id + ' #level-down').click(
        function()
        {
            that.brightness = Math.round(that.brightness - that.increment);
            if (that.brightness < 0)
            {
                that.brightness = 0
                that.state = "off"
            }
            if (that.state == "off")
            {
                console.log("setting off")
                args = {"service": "homeassistant/turn_off", "entity_id": parameters["entity"]}
                set_view(that, {"state": "off", "attributes": {"brightness": 0}})
            }
            else
            {
                args = {"service": "homeassistant/turn_on", "entity_id": parameters["entity"], "brightness": that.brightness}    
            }
            that.call_service(url, args)
        }
    )

    
    // Methods

    function toggle()
    {
        if (this.state == "on")
        {
            this.state = "off";
            this.brightness = 0
        }
        else
        {
            this.state = "on"
            this.brightness = this.on_brightness
        }

        set_view(this, {"state": this.state, "attributes": {"brightness": this.brightness}} )
    }
    
    function on_ha_data(data)
    {
        if ("monitored_entity" in parameters)
        {
            entity = this.parameters.monitored_entity
        }
        else
        {
            entity = this.parameters.entity
        }
        if (data.event_type == "state_changed" && data.data.entity_id == entity)
        {
            this.state = data.data.new_state.state
            if ("brightness" in data.data.new_state.attributes)
            {
                this.brightness = data.data.new_state.attributes["brightness"]
            }
            set_view(this, data.data.new_state)
        }
    }
    
    function call_service(base_url, args)
    {
        var that = this;
        service_url = base_url + "/" + "call_service";
        $.post(service_url, args);    
    }
        
    function get_state(base_url, entity)
    {
        if ("entity" in parameters)
        {
            var that = this;
            state_url = base_url + "/detailedstate/" + entity;
            $.get(state_url, "", function(data)
            {
                that.state = data.state.state;
                                
                if ("brightness" in data.state.attributes)
                {
                    that.brightness = data.state.attributes.brightness                    
                }
                set_view(that, data.state)
            }, "json");
        }
        else
        {
            set_view(this, {"state": "off", "attributes": {"brightness": 0}})
        }
    };
    
    function set_view(self, state)
    {
        if (state.state == "on")
        {
            if ("icon_color_active" in parameters)
            {
                $('#' + widget_id + ' > h2').css("color", parameters["icon_color_active"])
            }
            else
            {
                if ("warn" in self.parameters && self.parameters["warn"] == 1)
                {
                    $('#' + widget_id + ' > h2').css("color", "")
                    self.ViewModel.icon_style("icon-active-warn")
                }
                else
                {
                    $('#' + widget_id + ' > h2').css("color", "")
                    self.ViewModel.icon_style("dimmer-icon-on")                
                }
                value = Math.round(state.attributes.brightness/254*100)
                self.ViewModel.level(value)
            }
            self.ViewModel.icon(self.icon_on.split("-")[0] + ' ' + self.icon_on)
        }
        else
        {
            if ("icon_color_inactive" in parameters)
            {
                $('#' + widget_id + ' > h2').css("color", parameters["icon_color_inactive"])
            }
            else
            {
                $('#' + widget_id + ' > h2').css("color", "")
                self.ViewModel.icon_style("dimmer-icon-off")
            }
            self.ViewModel.icon(self.icon_off.split("-")[0] + ' ' + self.icon_off)
            self.ViewModel.level(0)            
        }
               
    }
}