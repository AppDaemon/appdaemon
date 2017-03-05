function slider(widget_id, url, skin, parameters)
{
	// Store Args
	this.widget_id = widget_id;
	this.parameters = parameters;
	this.utl = url;
	
	// Add in methods
	this.on_ha_data = on_ha_data;
	this.get_state = get_state;
	this.call_service = call_service;
	
	// Create and initialize bindings
	this.ViewModel = 
	{
		title: ko.observable(parameters.title),
		title2: ko.observable(parameters.title2),
		unit: ko.observable(parameters.units),
		level: ko.observable(),
		unit2: ko.observable(),
		level2: ko.observable(),
		title_style: ko.observable(parameters.title_style),
		title2_style: ko.observable(parameters.title2_style),
		level_style: ko.observable(parameters.level_style),
		unit_style: ko.observable(parameters.unit_style),
		level2_style: ko.observable(parameters.level2_style),
		unit2_style: ko.observable(parameters.unit2_style),
		level_up_style: ko.observable(parameters.level_up_style),
		level_down_style: ko.observable(parameters.level_down_style),
		icon_up: ko.observable(),
		icon_down: ko.observable(),
		widget_style: ko.observable(parameters.widget_style)
	};
	
	ko.applyBindings(this.ViewModel, document.getElementById(widget_id));

	// Do some setup
		
	
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
		
	this.step = 25.4
	if ("step" in parameters)
	{
		this.step = parameters["step"]
	}
	
	// Setup Override Styles

	if ("icon_down" in parameters)
	{
		this.ViewModel.icon_down(parameters.icon_down.split("-")[0] + ' ' + parameters.icon_down)
	}

	if ("icon_up" in parameters)
	{
		this.ViewModel.icon_up(parameters.icon_up.split("-")[0] + ' ' + parameters.icon_up)
	}	
		
	
	// Get initial state
   
	this.get_state(url, parameters.state_entity)

	var that = this
	
	// Define onClick handler for Raise level

	$('#' + widget_id + ' #level-up').click(
		function()
		{
			that.level = parseFloat(that.level) + that.step;
			if (that.level > that.max_level)
			{
				that.level = that.max_level
			}
			if ("post_service" in parameters)
			{
				args = parameters["post_service"]
                if ("level_attribute" in parameters)
                {
                    args[parameters.level_attribute] = round(that, that.level)
                }
                else
                {
                    args["value"] = round(that, that.level)
                }
			}
			that.call_service(url, args)
		}
	)

	// Define onClick handler for Lower level

	$('#' + widget_id + ' #level-down').click(
		function()
		{
			that.level = parseFloat(that.level) - that.step;
			if (that.level < that.min_level)
			{
				that.level = that.min_level
				that.state = that.state_inactive
			}

			if ("post_service" in parameters)
			{
				args = parameters["post_service"]
                if ("level_attribute" in parameters)
                {
                    args[parameters.level_attribute] = round(that, that.level)
                }
                else
                {
                    args["value"] = round(that, that.level)
                }
			}
			that.call_service(url, args)

		}
	)

	
	// Methods

	function on_ha_data(data)
	{

		entity = this.parameters.state_entity
		if (data.event_type == "state_changed" && data.data.entity_id == entity)
		{
            current = ""
            if ("level_attribute" in this.parameters)
            {
                this.level = parseFloat(data.data.new_state.attributes[this.parameters.level_attribute]);
                if (isNaN(data.data.new_state.attributes[that.parameters.level_attribute]))
                {
                    current = "AUTO"                            
                }
                else
                {
                    current = parseFloat(data.data.new_state.attributes[this.parameters.state_attribute]);
                }
            }
            else
            {    
                if ("state_attribute" in this.parameters)
                {
                    this.level = parseFloat(data.data.new_state.attributes[this.parameters.state_attribute]);
                }
                else
                {
                    this.level = parseFloat(data.data.new_state.state);
                }
            }
			set_view(this, this.level, current)
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
        current = ""
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
                    if ("level_attribute" in that.parameters)
                    {
                        that.level = parseFloat(data.state.attributes[that.parameters.level_attribute]);
                        if (data.state.attributes[that.parameters.level_attribute] == null)
                        {
                            current = "AUTO"                            
                        }
                        else
                        {
                            current = parseFloat(data.state.attributes[that.parameters.state_attribute]);
                        }
                    }
                    else
                    {
                        if ("state_attribute" in that.parameters)
                        {
                            that.level = parseFloat(data.state.attributes[that.parameters.state_attribute]);
                        }
                        else
                        {
                            that.level = parseFloat(data.state.state);
                        }
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
					set_view(that, that.level, current)
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
	
	function set_view(self, level, current)
	{
        if ("level_attribute" in self.parameters)
        {
            self.ViewModel.level(current)
            self.ViewModel.level2(level)
            self.ViewModel.unit2(self.parameters.units)
		}
        else
        {
            self.ViewModel.level(level)
        }
	}
}