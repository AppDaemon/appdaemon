function text(widget_id, url, parameters)
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
        value: ko.observable(),
        widget_style: ko.observable(),
        text_style: ko.observable(),
        title_style: ko.observable()
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
    
	if ("text_style" in parameters)
	{
		this.ViewModel.text_style(parameters.text_style)
	}
    
    // Fill in text
    if ("text" in parameters)
    {
        this.ViewModel.value(parameters.text)
    }
    // Get initial state
    if ("state_entity" in parameters)
    {
        this.get_state(url, parameters.state_entity)
    }

    // Methods
    
    function on_ha_data(data)
    {
        if (data.event_type == "state_changed" && data.data.entity_id == this.parameters.state_entity)
        {
            this.ViewModel.value(data.data.new_state.state)
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
                that.ViewModel.value(data.state.state)
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
}