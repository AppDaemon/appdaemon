function display(widget_id, url, parameters)
{
    // Store Args
    this.widget_id = widget_id
    this.parameters = parameters
    
    // Add in methods
    this.on_ha_data = on_ha_data
    this.format_value = format_value
    this.get_state = get_state
    
    // Create and initialize bindings
    this.ViewModel = 
    {
        title: ko.observable(parameters.title),
        value: ko.observable(),
        unit: ko.observable(parameters.units),
		widget_style: ko.observable(),
		title_style: ko.observable(),
		value_style: ko.observable(),
		unit_style: ko.observable()
    };
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id))

	// Setup Override Styles

	if ("widget_style" in parameters)
	{
		this.ViewModel.widget_style(parameters.widget_style)
	}

	if ("title_style" in parameters)
	{
		this.ViewModel.title_style(parameters.title_style)
	}
    
	if ("value_style" in parameters)
	{
		this.ViewModel.value_style(parameters.value_style)
	}
    
	if ("unit_style" in parameters)
	{
		this.ViewModel.unit_style(parameters.unit_style)
	}
    
    
    // Get initial state
    this.get_state(url, parameters.state_entity)

    // Methods

    function on_ha_data(data)
    {
        if (data.event_type == "state_changed" && data.data.entity_id == this.parameters.state_entity)
        {
            this.ViewModel.value(this.format_value(data.data.new_state.state))
        }
    }
        
    function get_state(base_url, entity)
    {
        var that = this;
        url = base_url + "/state/" + entity;
        $.get(url, "", function(data)
        {
            if (data.state == null)
            {
                that.ViewModel.title("Entity not found")
            }
            else
            {
                that.ViewModel.value(that.format_value(data.state.state))
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

            }
        }, "json");    
    };
        
    function format_value(value)
    {
        if ("precision" in this.parameters)
        {
            value = round(value, this.parameters.precision)
        }
        
        if ("shorten" in this.parameters && this.parameters.shorten == 1)
        {
            if (value >= 1E9)
            {
                value = round(value / 1E9, 1) + "B"
            }
            else if (value >= 1E6)
            {
                value = round(value / 1E6, 1) + "M"
            }
            else if (value >= 1E3)
            {
                value = round(value / 1E3, 1) + "K"
            }
        }
        return value
    }

}