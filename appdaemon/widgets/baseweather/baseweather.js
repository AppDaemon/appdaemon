function baseweather(widget_id, url, skin, parameters)
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
    this.ViewModel.unit_style = ko.observable()
	this.ViewModel.widget_style = ko.observable()
	this.ViewModel.main_style = ko.observable()
	this.ViewModel.sub_style = ko.observable()
   
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id))
    
	// Setup Override Styles

	if ("widget_style" in parameters)
	{
		this.ViewModel.widget_style(parameters.widget_style)
	}    

	if ("main_style" in parameters)
	{
		this.ViewModel.main_style(parameters.main_style)
	}    

	if ("unit_style" in parameters)
	{
		this.ViewModel.unit_style(parameters.unit_style)
	}    

	if ("sub_style" in parameters)
	{
		this.ViewModel.sub_style(parameters.sub_style)
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
            that.ViewModel.dark_sky_icon(that.icons[data.state.state])
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_temperature";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_temperature(data.state.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_humidity";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_humidity(data.state.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_apparent_temperature";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_apparent_temperature(data.state.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_precip_probability";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_precip_probability(data.state.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_precip_intensity";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_precip_intensity(data.state.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_wind_speed";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_wind_speed(data.state.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_wind_bearing";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_wind_bearing(data.state.state)
        }, "json");    

        url = base_url + "/state/" + "sensor.dark_sky_pressure";
        $.get(url, "", function(data)
        {
            that.ViewModel.dark_sky_pressure(data.state.state)
        }, "json");    
    };
}