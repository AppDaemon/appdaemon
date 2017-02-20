function weather(widget_id, url, parameters)
{
    // Store Args
    this.widget_id = widget_id
    this.parameters = parameters
    
    // Add in methods
    this.on_ha_data = on_ha_data
    this.get_state = get_state
    
    this.sensors =
    [
        "dark_sky_temperature",
        "dark_sky_humidity",
        "dark_sky_precip_probability",
        "dark_sky_precip_intensity",
        "dark_sky_wind_speed",
        "dark_sky_pressure",
        "dark_sky_wind_bearing",
        "dark_sky_apparent_temperature",
        "dark_sky_icon"
    ]

    this.icons =
    {
      "rain": '&#xe009',
      "snow": '&#xe036',
      "sleet": '&#xe003',
      "wind": '&#xe021',
      "fog": '&#xe01b',
      "cloudy": '&#xe000',
      "clear-day": '&#xe028',
      "clear-night": '&#xe02d',
      "partly-cloudy-day": '&#xe001',
      "partly-cloudy-night": '&#xe002'    
    }
    
    // Create and initialize bindings
    
    this.ViewModel = {}
    var arrayLength = this.sensors.length;
    for (var i = 0; i < arrayLength; i++) 
    {
        this.ViewModel[this.sensors[i]] = ko.observable()
    }
    
    this.ViewModel.unit = ko.observable(parameters.units)
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id))
    
    // Setup Override Styles
    
    if ("background_color" in parameters)
    {
        $('#' + widget_id).css("background-color", parameters["background_color"])
    }
    
    if ("text_color" in parameters)
    {
        $('#' + widget_id + ' > .secondary-info').css("color", parameters["text_color"])
    }
    
    if ("text_size" in parameters)
    {
        $('#' + widget_id + ' > .secondary-info').css("font-size", parameters["text_size"])
    }
    
    if ("title_color" in parameters)
    {
        $('#' + widget_id + ' > .primary-climacon').css("color", parameters["title_color"])
        $('#' + widget_id + ' > .primary-info').css("color", parameters["title_color"])
    }
    
    if ("title_size" in parameters)
    {
        $('#' + widget_id + ' > .primary-climacon').css("font-size", parameters["title_size"])
        $('#' + widget_id + ' > .primary-info').css("font-size", parameters["title_size"])
    }
    
    if ("unit_color" in parameters)
    {
        $('#' + widget_id + ' > .primary-unit').css("color", parameters["unit_color"])
    }
    
    if ("unit_size" in parameters)
    {
        $('#' + widget_id + ' > .primary-unit').css("font-size", parameters["unit_size"])
    }
    
    
    
    // Get initial state
    this.get_state(url, parameters.entity)

    // Methods

    function on_ha_data(data)
    {
        if (data.event_type == "state_changed")
        {
            var arrayLength = this.sensors.length;
            for (var i = 0; i < arrayLength; i++) 
            {
                if (data.data.entity_id == "sensor." + this.sensors[i])
                {
                    if (this.sensors[i] == "dark_sky_icon")
                    {
                        state = this.icons[data.data.new_state.state]
                    }
                    else
                    {
                        state = data.data.new_state.state
                    }
                    this.ViewModel[this.sensors[i]](state)
                }
            }
        }
    }
        
    function get_state(base_url)
    {
        var that = this;
        url = base_url + "/state/" + "sensor.dark_sky_icon";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_icon(that.icons[data.state])
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_temperature";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_temperature(data.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_humidity";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_humidity(data.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_apparent_temperature";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_apparent_temperature(data.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_precip_probability";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_precip_probability(data.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_precip_intensity";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_precip_intensity(data.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_wind_speed";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_wind_speed(data.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_wind_bearing";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_wind_bearing(data.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_pressure";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_pressure(data.state)
        }, "json");    

    };
}