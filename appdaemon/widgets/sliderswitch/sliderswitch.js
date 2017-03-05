function sliderswitch(widget_id, url, skin, parameters)
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
        title2: ko.observable(parameters.title2),
        icon: ko.observable(),
        icon_style: ko.observable(),
        icon_class: ko.observable(),
        units: ko.observable(),
        level: ko.observable(),
        state_text: ko.observable(),
		title_style: ko.observable(),
		title2_style: ko.observable(),
		state_text_style: ko.observable(),
		level_style: ko.observable(),
		units_style: ko.observable(),
		level_up_style: ko.observable(),
		level_down_style: ko.observable(),
		icon_up: ko.observable(),
		icon_down: ko.observable(),
		widget_style: ko.observable()
    };
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id));

    // Do some setup
    
    this.level_attribute = "level"
    if ("level_attribute" in parameters)
    {
        this.level_attribute = parameters["level_attribute"]
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
    
    this.min_level = 0;
    if ("min_level" in parameters)
    {
        this.min_level = parameters["min_level"]
    }
    
    this.max_level = 254;
    if ("max_level" in parameters)
    {
        this.max_level = parameters["max_level"]
    }

    this.on_level = (this.max_level - this.min_level) / 2 ;
    this.level = this.min_level;
    
    this.state = this.state_inactive;
    
    if ("on_level" in parameters)
    {
        this.on_level = parameters["on_level"]
    }

    if ("units" in parameters)
    {
        this.ViewModel.units(parameters.units)
    }
    
    this.step = 25.4
    if ("step" in parameters)
    {
        this.step = parameters["step"]
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

	if ("widget_style" in parameters)
	{
		this.ViewModel.widget_style(parameters.widget_style)
	}   

	if ("title_style" in parameters)
	{
		this.ViewModel.title_style(parameters.title_style)
	}   

	if ("title2_style" in parameters)
	{
		this.ViewModel.title2_style(parameters.title2_style)
	}   

	if ("icon_down" in parameters)
	{
		this.ViewModel.icon_down(parameters.icon_down.split("-")[0] + ' ' + parameters.icon_down)
	}

	if ("icon_up" in parameters)
	{
		this.ViewModel.icon_up(parameters.icon_up.split("-")[0] + ' ' + parameters.icon_up)
	}   
	
	if ("state_text_style" in parameters)
	{
		this.ViewModel.state_text_style(parameters.state_text_style)
	}   
	
	if ("level_style" in parameters)
	{
		this.ViewModel.level_style(parameters.level_style)
		this.ViewModel.units_style(parameters.level_style)
	}   
	
	if ("level_up_style" in parameters)
	{
		this.ViewModel.level_up_style(parameters.level_up_style)
	}   

	if ("level_down_style" in parameters)
	{
		this.ViewModel.level_down_style(parameters.level_down_style)
	}   
	
    // Get initial state
   
    this.get_state(url, parameters.state_entity)

    var that = this
    
    // Define onClick handler for on/off
    if ("post_service_active" in parameters || "post_service_inactive" in parameters)
    {
        $('#' + widget_id + ' > span').click(
            function()
            {
                args = "";
                if (that.state == that.state_active)
                {
                    if ("post_service_inactive" in parameters)
                    {
                        args = parameters["post_service_inactive"]
                    }
                }
                else
                {
                    if ("post_service_active" in parameters)
                    {
                        args = parameters["post_service_active"]
                        if ("on_level" in parameters)
                        {
                            args[that.level_attribute] = round(that, that.on_level)
                        }
                    }
                }
                if (args != "")
                {
                    that.toggle();
                    that.call_service(url, args)
                }
                if ("momentary" in parameters)
                {
                    setTimeout(function() { that.toggle() }, parameters["momentary"])
                }
            }
        )
    }
    // Define onClick handler for Raise level

    $('#' + widget_id + ' #level-up').click(
        function()
        {
            
            that.level = that.level + that.step;
            if (that.level > that.max_level)
            {
                that.level = that.max_level
            }
            if ("post_service_level" in parameters)
            {
                args = parameters["post_service_level"]
                if ("post_service_level_attribute" in parameters)
                {
                    args[parameters["post_service_level_attribute"]] = round(that, that.level)
                }
                else
                {
                    args[that.level_attribute] = round(that, that.level)
                }
            }
            else
            {
                args = parameters["post_service_active"]
                if ("post_service_level_attribute" in parameters)
                {
                    args[parameters["post_service_level_attribute"]] = round(that, that.level)
                }
                else
                {
                    args[that.level_attribute] = round(that, that.level)
                }
            }
            that.call_service(url, args)
        }
    )

    // Define onClick handler for Lower level

    $('#' + widget_id + ' #level-down').click(
        function()
        {
            that.level = that.level - that.step;
            if (that.level < that.min_level)
            {
                that.level = that.min_level
                that.state = that.state_inactive
            }

            if ("post_service_level" in parameters)
            {
                args = parameters["post_service_level"]
                if ("post_service_level_attribute" in parameters)
                {
                    args[parameters["post_service_level_attribute"]] = round(that, that.level)
                }
                else
                {
                    args[that.level_attribute] = round(that, that.level)
                }
            }
            else
            {
                if (that.state == that.state_inactive)
                {
                    args = parameters["post_service_inactive"]
                    new_view = new_view = {"state": that.state_inactive, "attributes": {}}
                    if ("post_service_level_attribute" in parameters)
                    {
                        args[parameters["post_service_level_attribute"]] = round(that, that.level)
                        new_view.attributes[parameters["post_service_level_attribute"]] = round(that, that.min_level)
                    }
                    else
                    {
                        //args[that.level_attribute] = round(that, that.level)
                        new_view.attributes[that.level_attribute] = round(that, that.min_level)
                    }
                    set_view(that, new_view, "")
                }
                else
                {
                    args = parameters["post_service_active"]
                    args[that.level_attribute] = round(that, that.level)
                }
            }
            
            that.call_service(url, args)
        }
    )

    
    // Methods

    function toggle()
    {
        if (this.state == this.state_active)
        {
            this.state = this.state_inactive;
            if (this.parameters.inactive_level_valid)
            {
                this.level = this.level
            }
            else
            {
                this.level = this.min_level                
            }
        }
        else
        {
            this.state = this.state_active
            if (this.parameters.inactive_level_valid)
            {
                this.level = this.level
            }
            else
            {
                this.level = this.min_level                
            }
        }
    }
    
    function on_ha_data(data)
    {
        if ("monitored_entity" in this)
        {
            entity = this.monitored_entity
        }
        else
        {
            entity = this.parameters.state_entity
        }
        if (data.event_type == "state_changed" && data.data.entity_id == entity)
        {
            state_text = ""
            this.state = data.data.new_state.state
            if (this.level_attribute in data.data.new_state.attributes)
            {
                if (this.level_attribute == "state")
                {
                    this.level = data.data.new_state.state
                }
                else
                {    
                    this.level = data.data.new_state.attributes[this.level_attribute]
                }
            }
            
            if ("state_text_attribute" in this.parameters)
            {
                state_text = data.data.new_state.attributes[this.parameters["state_text_attribute"]]
            }
            set_view(this, data.data.new_state, state_text)
        }
    }
    
    function round(self, value)
    {
        if (self.parameters.round)
        {
            return Math.round(value)
        }
        else
        {
            return value
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
                if (data.state == null)
                {
                    that.ViewModel.title("Entity not found")
                }
                else
                {
                    
                    if (data.state.entity_id != entity)
                    {
                        // This is a group and we need to monitor a member
                        that.monitored_entity = data.state.entity_id
                    }
                    
                    that.state = data.state.state;
                    
                    if (that.level_attribute == "state")
                    {
                        that.level = Number(data.state.state)
                    }
                    else
                    {
                        if (that.level_attribute in data.state.attributes)
                        {
                            that.level = Number(data.state.attributes[that.level_attribute])
                        }
                    }
                    
                    state_text = ""
                    if ("state_text_attribute" in that.parameters)
                    {
                        state_text = data.state.attributes[that.parameters["state_text_attribute"]]
                    }
                    
                    if ("title_is_friendly_name" in that.parameters)
                    {
                        if ("friendly_name" in data.state.attributes)
                        {
                            that.ViewModel.title(data.state.attributes["friendly_name"])
                        }
                        else
                        {
                            that.ViewModel.title(that.widget_id)
                        }
                    }
                    
                    if ("step_attribute" in that.parameters)
                    {
                        that.step = data.state.attributes[that.parameters["step_attribute"]]
                    }
                    
                    if ("min_attribute" in that.parameters)
                    {
                        that.min_level = data.state.attributes[that.parameters["min_attribute"]]
                    }
                    
                    if ("max_attribute" in that.parameters)
                    {
                        that.max_level = data.state.attributes[that.parameters["max_attribute"]]
                    }
                    set_view(that, data.state, state_text)
                }
            }, "json");
        }
        else
        {
            new_view = {"state": that.state_active, "attributes": {}}
            new_view.attributes[that.level_attribute] = that.min_level
            set_view(this, new_view, "")
        }
    };
    
    function set_view(self, state, state_text)
    {
        if (state_text != "")
        {
            if ("truncate_name" in self.parameters)
            {
               state_text = state_text.substring(0, self.parameters.truncate_name)
            }
            self.ViewModel.state_text(state_text)
        }
        if (state.state == self.state_active)
        {
			if ("icon_style_active" in parameters)
			{
				self.ViewModel.icon_style(parameters["icon_style_active"])
				self.ViewModel.icon_class("icon-active")                
			}
			else
			{
				self.ViewModel.icon_style("")
				self.ViewModel.icon_class("icon-active")                
			}
			if (self.level_attribute == "state")
			{
				level = state.state                   
			}
			else                
			{
				level = state.attributes[self.level_attribute]
			}
			if (self.parameters.numeric)
			{
				value = level
			}
			else
			{
				value = (Math.round((level - self.min_level)/(self.max_level - self.min_level)*10))*10
			}
			self.ViewModel.level(value)
            
            self.ViewModel.icon(self.icon_on.split("-")[0] + ' ' + self.icon_on)
        }
        else
        {
			if ("icon_style_inactive" in parameters)
			{
				self.ViewModel.icon_style(parameters["icon_style_inactive"])
				self.ViewModel.icon_class("icon-inactive")                
			}
			else
			{
				self.ViewModel.icon_style("")
				self.ViewModel.icon_class("icon-inactive")                
			}
            self.ViewModel.icon(self.icon_off.split("-")[0] + ' ' + self.icon_off)
            if (parameters.inactive_level_valid)
            {
                if (self.level_attribute == "state")
                {
                    level = state.state                   
                }
                else                
                {
                    level = state.attributes[self.level_attribute]
                }
                if (self.parameters.numeric)
                {
                    value = level
                }
                else
                {
                    value = (Math.round((level - self.min_level)/(self.max_level - self.min_level)*10))*10
                }
                if (isNaN(value))
                {
                    self.ViewModel.level(self.min_level)
                }
                else
                {
                    self.ViewModel.level(value)
                }
            }
            else
            {
                self.ViewModel.level(self.min_level)            
            }
        }
               
    }
}