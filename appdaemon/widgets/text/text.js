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
    };
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id))

    // Setup Override Styles
    
    if ("background_color" in parameters)
    {
        $('#' + widget_id).css("background-color", parameters["background_color"])
    }
    
    if ("text_color" in parameters)
    {
        $('#' + widget_id + ' > h2').css("color", parameters["text_color"])
    }
    
    if ("text_size" in parameters)
    {
        $('#' + widget_id + ' > h2').css("font-size", parameters["text_size"])
    }
    
    if ("title_color" in parameters)
    {
        $('#' + widget_id + ' > h1').css("color", parameters["title_color"])
    }
    
    if ("title_size" in parameters)
    {
        $('#' + widget_id + ' > h1').css("font-size", parameters["title_size"])
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