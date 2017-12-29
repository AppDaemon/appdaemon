function base_light_with_colorpicker(widget_id, url, skin, parameters)
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
    
       
    self.onChange = onChange
    self.OnButtonClick = OnButtonClick

    var callbacks = [
            {"selector": '#' + widget_id + ' > span', "action": "click", "callback": self.OnButtonClick},
            {"selector": '#' + widget_id + ' > div > input', "action": "change", "callback": self.onChange},
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
        if ("rgb_color" in state.attributes)
        {
            self.rgb_color = state.attributes.rgb_color
        }
        else
        {
            self.rgb_color = []
        }
        set_view(self, self.state, self.rgb_color)
    }
 
    function OnStateUpdate(self, state)
    {
        self.state = state.state;
        if ("rgb_color" in state.attributes)
        {
            self.rgb_color = state.attributes.rgb_color
        }
        else
        {
            self.rgb_color = 0
        }

        set_view(self, self.state, self.rgb_color)
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
        setTimeout(function(){
        if (self.rgb_color != hex2rgb(self.ViewModel.hex_color()))
        {
            self.rgb_color =  hex2rgb(self.ViewModel.hex_color())
            args = self.parameters.post_service_active 
            args["rgb_color"] = self.rgb_color[0]+ "," + self.rgb_color[1]+ "," + self.rgb_color[2]
	    self.call_service(self, args)
        }
        },500)
    }

    function toggle(self)
    {
        if (self.state == "on")
        {
            self.state = "off";
        }
        else
        {
            self.state = "on";
        }
        set_view(self, self.state, self.rgb_color)
    }

    function set_view(self, state, rgb_color)
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
        if (typeof  rgb_color != 'undefined')
        {
            if (rgb_color != "")
            {
            self.set_field(self, "hex_color", rgb2hex(rgb_color))
            }
        }
    }

    function rgb2hex(rgb_color) {
        var red = rgb_color[0]
        var green = rgb_color[1]
        var blue = rgb_color[2]
        var rgb = blue | (green << 8) | (red << 16);
        return '#' + (0x1000000 + rgb).toString(16).slice(1)
    }

    function hex2rgb(hex) {
        return ['0x' + hex[1] + hex[2] | 0, '0x' + hex[3] + hex[4] | 0, '0x' + hex[5] + hex[6] | 0]
    }
}