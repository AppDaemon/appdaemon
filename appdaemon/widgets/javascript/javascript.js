function javascript(widget_id, url, skin, parameters)
{
    // Store Args
    this.widget_id = widget_id
    this.parameters = parameters
    this.skin = skin
        
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...
    
    self = this
    
    // Initialization
    
    self.widget_id = widget_id
    
    // Store on brightness or fallback to a default
        
    // Parameters may come in useful later on
    
    self.parameters = parameters
        
    // Define callbacks for on click events
    // They are defined as functions below and can be any name as long as the
    // 'self'variables match the callbacks array below
    // We need to add them into the object for later reference
   
    self.OnButtonClick = OnButtonClick

    var callbacks =
        [
            {"selector": '#' + widget_id + ' > span', "action": "click","callback": self.OnButtonClick},
        ]
       
    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity
    
    var monitored_entities = 
        []
    
    // Finally, call the parent constructor to get things moving
    
    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)  

    // Function Definitions
    
    // The StateAvailable function will be called when 
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    
    if ("command" in parameters)
    {
        command = parameters.command
    }
    else if ("url" in parameters || "dashboard" in parameters)
    {
        if ("url" in parameters)
        {
            url = parameters.url
        }
        else
        {
            url = "/" + parameters.dashboard
        }
        var i = 0;

        if ("args" in parameters)
        {
            
            url = url + "?";
            
            for (var key in parameters.args)
            {
                if (i != 0)
                {
                    url = url + "&"
                }
                url = url + key + "=" + parameters.args[key];
                i++
            }
        }
        if ("skin" in parameters)
        {
            theskin = parameters.skin
        }
        else
        {
            theskin = skin
        }

        if (i == 0)
        {
            url = url + "?skin=" + theskin;
            i++
        }
        else
        {
            url = url + "&skin=" + theskin;
            i++
        }

        if ("sticky" in parameters)
        {
            if (i == 0)
            {
                url = url + "?sticky=" + parameters.sticky;
                i++
            }
            else
            {
                url = url + "&sticky=" + parameters.sticky;
                i++
            }
        }

        if ("return" in parameters)
        {
            if (i == 0)
            {
                url = url + "?return=" + parameters.return;
                i++
            }
            else
            {
                url = url + "&return=" + parameters.return;
                i++
            }
        }

        if ("timeout" in parameters)
        {
            if (i == 0)
            {
                url = url + "?timeout=" + parameters.timeout;
                i++
            }
            else
            {
                url = url + "&timeout=" + parameters.timeout;
                i++
            }
        }



        command = "window.location.href = '" + url + "'"
    }
    
    self.set_icon(self, "icon", self.icons.icon_inactive);
    self.set_field(self, "icon_style", self.css.icon_inactive_style);
    
    self.command = command;
    
    function OnButtonClick(self)
    {
        self.set_icon(self, "icon", self.icons.icon_active);
        self.set_field(self, "icon_style", self.css.icon_active_style);
        eval(self.command);
    }
}