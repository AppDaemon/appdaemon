function baseweather(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this;

    self.weather_icons =
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
    };

    // Initialization

    self.widget_id = widget_id;

    // Store on brightness or fallback to a default

    // Parameters may come in useful later on

    self.parameters = parameters;

    var callbacks = [];

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities =
    [
        {"entity": "sensor.dark_sky_temperature", "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        {"entity": "sensor.dark_sky_humidity", "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        {"entity": "sensor.dark_sky_precip_probability", "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        {"entity": "sensor.dark_sky_precip_intensity", "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        {"entity": "sensor.dark_sky_wind_speed", "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        {"entity": "sensor.dark_sky_pressure", "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        {"entity": "sensor.dark_sky_wind_bearing", "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        {"entity": "sensor.dark_sky_apparent_temperature", "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        {"entity": "sensor.dark_sky_icon", "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
    ];

    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnStateUpdate(self, state)
    {
        set_view(self, state)
    }

    function OnStateAvailable(self, state)
    {
        if (state.entity_id == "sensor.dark_sky_temperature")
        {
            self.set_field(self, "unit", state.attributes.unit_of_measurement)
        }
        set_view(self, state)
    }

    function set_view(self, state)
    {
        if (state.entity_id == "sensor.dark_sky_icon")
        {
            self.set_field(self, "dark_sky_icon", self.weather_icons[state.state])
        }
        else
        {
            var field = state.entity_id.split(".")[1];
            self.set_field(self, field, state.state)
        }
    }
}