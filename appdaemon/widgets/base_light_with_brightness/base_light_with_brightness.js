function base_light_with_brightness(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...
    
    self = this
    
    // Initialization
    
    self.widget_id = widget_id
    
    // Store on brightness or fallback to a default
        
    // Parameters may come in useful later on
    
    self.parameters = parameters
    // Parameter handling
    
    if ("monitored_entity" in self.parameters)
    {
        entity = self.parameters.monitored_entity
    }
    else
    {
        entity = self.parameters.entity
    }
    
    if ("on_brightness" in self.parameters)
    {
        self.on_brightness = self.parameters.on_brightness
    }
    else
    {
        self.on_brightness = 127
    }
       
    self.onChange = onChange
    self.OnButtonClick = OnButtonClick

    var callbacks = [
            {"selector": '#' + widget_id + ' > span', "action": "click", "callback": self.OnButtonClick},
            {"observable": "Brightness", "action": "change", "callback": self.onChange},
                    ]


            // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity
     
    self.OnStateAvailable = OnStateAvailable
    self.OnStateUpdate = OnStateUpdate
    
    if ("entity" in parameters)
    {
        var monitored_entities = 
            [
                {"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
            ]
    }
    else
    {
        var monitored_entities =  []
    }
    // Finally, call the parent constructor to get things moving
    
    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)  

    // Function Definitions
    
    // The StateAvailable function will be called when 
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnStateAvailable(self, state)
    {    
        self.state = state.state
        self.minvalue = 0
        self.maxvalue = 255
        self.stepvalue = 1
        if ("brightness" in state.attributes)
        {
            self.brightness = state.attributes.brightness
        }
        else
        {
            self.brightness = 0
        }
        set_options(self, self.minvalue, self.maxvalue, self.stepvalue, self.brightness)
        set_view(self, self.state, self.brightness)
    }
 
    function OnStateUpdate(self, state)
    {
        self.state = state.state;
        if ("brightness" in state.attributes)
        {
            self.brightness = state.attributes.brightness
        }
        else
        {
            self.brightness = 0
        }

        set_view(self, self.state, self.brightness)
    }

    function OnButtonClick(self)
    {
        if (self.state == "off")
        {
            args = self.parameters.post_service_active 
            if ("on_attributes" in self.parameters)
            {
                for (var attr in self.parameters.on_attributes)
                {
                    args[attr] = self.parameters.on_attributes[attr]
                }
            }
        }
        else
        {
            args = self.parameters.post_service_inactive
        }
        self.call_service(self, args)
        toggle(self)
    }

    function onChange(self, state)
    {
        if (self.brightness != self.ViewModel.Brightness())
        {
            self.brightness = self.ViewModel.Brightness()
            if (self.brightness == 0)
            {
                args = self.parameters.post_service_inactive
            }
            else
            {
                args = self.parameters.post_service_active 
                args["brightness"] = self.brightness
            }
	    self.call_service(self, args)
        }
    }

    function toggle(self)
    {
        if (self.state == "on")
        {
            self.state = "off";
            self.brightness = 0
        }
        else
        {
            self.state = "on";
        }
        set_view(self, self.state, self.brigthness)
    }

    function set_options(self, minvalue, maxvalue, stepvalue, state)
    {
        self.set_field(self, "MinValue", minvalue)
        self.set_field(self, "MaxValue", maxvalue)
        self.set_field(self, "StepValue", stepvalue)
    }

    function set_view(self, state, brightness)
    {
        
        if (state == "on")
        {
            // Set Icon will set the style correctly for an icon
            self.set_icon(self, "icon", self.icons.icon_on)
            // Set view will set the view for the appropriate field
            self.set_field(self, "icon_style", self.css.icon_style_active)
        }
        else
        {
            self.set_icon(self, "icon", self.icons.icon_off)
            self.set_field(self, "icon_style", self.css.icon_style_inactive)
        }
        if (typeof brightness == 'undefined')
        {
            self.set_field(self, "Brightness", 0)
        }
        else
        {
            self.set_field(self, "Brightness", brightness)
        }
    }

}