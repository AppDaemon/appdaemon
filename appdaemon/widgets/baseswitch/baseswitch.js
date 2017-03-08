function baseswitch(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...
    
    self = this
    
    // Initialization
    
    self.widget_id = widget_id
    
    // Store on brightness or fallback to a default
        
    // Parameters may come in useful later on
    
    self.parameters = parameters
    
    // Toggle needs to be referenced from self for the timeout function
    
    self.toggle = toggle
    
    // Define callbacks for on click events
    // They are defined as functions below and can be any name as long as the
    // 'self'variables match the callbacks array below
    // We need to add them into the object for later reference
   
    self.OnButtonClick = OnButtonClick
    
    if ("enable" in self.parameters && self.parameters.enable == 1)
    {
        var callbacks =
            [
                {"selector": '#' + widget_id + ' > span', "callback": self.OnButtonClick},
            ]
    }            
    else
    {
        var callbacks = []
    }        
    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity
     
    self.OnStateAvailable = OnStateAvailable
    self.OnStateUpdate = OnStateUpdate
    
    var monitored_entities = 
        [
            {"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
        ]
    
    // Finally, call the parent constructor to get things moving
    
    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)  

    // Function Definitions
    
    // The StateAvailable function will be called when 
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    
    function OnStateAvailable(self, state)
    {        
        self.state = state.state;
        set_view(self, self.state)
    }
    
    // The OnStateUpdate function will be called when the specific entity
    // receives a state update - it's new values will be available
    // in self.state[<entity>] and returned in the state parameter
    
    function OnStateUpdate(self, state)
    {
        if (!("ignore_state" in self.parameters) || self.parameters.ignore_state == 0)
        {
            self.state = state.state;
            set_view(self, self.state)
        }
    }
    
    function OnButtonClick(self)
    {
        if (self.state == self.parameters.state_inactive)
        {
            args = self.parameters.post_service_active
        }
        else
        {
            args = self.parameters.post_service_inactive
        }
        self.call_service(self, args)
        toggle(self)
        if ("momentary" in self.parameters)
        {
            setTimeout(function() { self.toggle(self) }, self.parameters["momentary"])
        }
    }
    
    function toggle(self)
    {
        if (self.state == self.parameters.state_inactive)
        {
            self.state = self.parameters.state_active;
        }
        else
        {
            self.state = self.parameters.state_inactive;
        }
        set_view(self, self.state)
    }
    
    // Set view is a helper function to set all aspects of the widget to its 
    // current state - it is called by widget code when an update occurs
    // or some other event that requires a an update of the view
    
    function set_view(self, state, level)
    {
        if (state == self.parameters.state_inactive)
        {
            self.set_icon(self, "icon", self.icons.icon_off)
            self.set_field(self, "icon_style", self.css.icon_style_inactive)
        }
        else
        {
            self.set_icon(self, "icon", self.icons.icon_on)
            self.set_field(self, "icon_style", self.css.icon_style_active)
        }
    }
}