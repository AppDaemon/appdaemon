function picker(widget_id, url, parameters)
{
    // Store Args
    this.widget_id = widget_id
    this.parameters = parameters
    
    // Add in methods
    this.on_ha_data = on_ha_data
    this.get_state = get_state

    // Create and initialize bindings
    this.ViewModel = 
    {
        title: ko.observable(parameters.title),
        icon: ko.observable(),
        icon_style: ko.observable(),
        state_text: ko.observable()
    };
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id))

    // Do some setup
    
    this.state = "off"
    this.icon_on = "lightbulb-o";
    if  ("icon_on" in parameters)
    {
        this.icon_on = parameters["icon_on"];
    }

    this.icon_off = "lightbulb-o";
    if  ("icon_off" in parameters)
    {
        this.icon_off = parameters["icon_off"];
    }
    
    this.state_active = "on";
    if ("state_active" in parameters)
    {
        this.state_active = parameters["state_active"]
    }

    this.state_inactive = "off";
    if ("state_inactive" in parameters)
    {
        this.state_inactive = parameters["state_inactive"]
    }

    // Get initial state
    
    // Will need attributes as well here!
    
    this.get_state(url, parameters.state_entity)

    function toggle()
    {
        if (this.state == this.state_active)
        {
            this.state = this.state_inactive;
        }
        else
        {
            this.state = this.state_active
        }
        set_view(this, this.state)
    }
    
    function on_ha_data(data)
    {
        if ("state_entity" in parameters && data.event_type == "state_changed" && data.data.entity_id == this.parameters.state_entity)
        {
            this.state = data.data.new_state.state
            set_view(this, this.state)
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
        if ("state_entity" in parameters)
        {
            var that = this;
            state_url = base_url + "/state/" + entity;
            $.get(state_url, "", function(data)
            {
                that.state = data.state;
                set_view(that, that.state)
            }, "json");
        }
        else
        {
            set_view(this, "off")
        }
    };
    
    function set_view(self, state)
    {
        
        if (state == self.state_active)
        {
            if ("warn" in self.parameters && self.parameters["warn"] == 1)
            {
                self.ViewModel.icon_style("icon-active-warn")
            }
            else
            {
                self.ViewModel.icon_style("icon-active")                
            }
            self.ViewModel.icon("fa fa-" + self.icon_on)
        }
        else
        {
            self.ViewModel.icon_style("icon-inactive")
            self.ViewModel.icon("fa fa-" + self.icon_off)            
        }
        
    }
}