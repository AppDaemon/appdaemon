function baseweathersummary(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this;

    self.weather_icons =
    {
      "weather-pouring": '&#xe009',
      "weather-snowy": '&#xe036',
      "weather-hail": '&#xe003',
      "weather-windy": '&#xe021',
      "weather-fog": '&#xe01b',
      "weather-cloudy": '&#xe000',
      "weather-sunny": '&#xe028',
      "weather-night": '&#xe02d',
      "weather-partlycloudy": '&#xe001',
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

    var monitored_entities = []

    monitored_entities.push({"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate})
    
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
        set_view(self, state)
    }

    function set_view(self, state)
    {
	weather = state.attributes.entity_picture.replace("/static/images/darksky/", "")
	weather = weather.replace(".svg", "")
	console.log(self.weather_icons[weather])
        self.set_field(self, "icon", self.weather_icons[weather])
        self.set_field(self, "state_text", state.state)
    }
}
