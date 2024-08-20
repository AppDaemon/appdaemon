function baseweather(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this;

    // Initialization

    self.widget_id = widget_id;

    // Parameters may come in useful later on

    self.parameters = parameters;

    var callbacks = [];

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    // Map will be used to know what field are we going to update from what sensor
    self.entities_map = {}

    var monitored_entities = []

    var entities = $.extend({}, parameters.entities, parameters.sensors);
    for (var key in entities)
    {
        var entity = entities[key]
        if (entity != '' && check_if_forecast_sensor(parameters.show_forecast, entity))
        {
            monitored_entities.push({
                "entity": entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate
            })
            self.entities_map[entity] = key
        }
    }

    // If forecast is disabled - don't monitor the forecast sensors
    function check_if_forecast_sensor(show_forecast, entity)
    {
        if (show_forecast)
        {
          return true
        }
        else if(entity.substring(entity.length - 2) === "_1")
        {
          return false
        }
        else
        {
          return true
        }
    }
    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    // Function Definitions

    // The OnStateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnStateUpdate(self, state)
    {
        set_view(self, state)
    }

    function OnStateAvailable(self, state)
    {
        field = self.entities_map[state.entity_id]
        if (field == 'temperature')
        {
            self.set_field(self, "unit", state.attributes.unit_of_measurement)
        }
        else if (field == 'wind_speed')
        {
            self.set_field(self, "wind_unit", state.attributes.unit_of_measurement)
        }
        else if (field == 'pressure')
        {
            self.set_field(self, "pressure_unit", state.attributes.unit_of_measurement)
        }
        else if (field == 'precip_intensity')
        {
            self.set_field(self, "rain_unit", state.attributes.unit_of_measurement)
        }
        set_view(self, state)
    }

    function set_view(self, state)
    {
        field = self.entities_map[state.entity_id]
        if (field)
        {
            if (field == 'icon' || field == 'forecast_icon')
            {
                self.set_field(self, field, state.state)
                return
            }

            if (field == 'precip_type')
            {
                self.set_field(self, "precip_type_icon", self.parameters.icons[state.state])
            }
            else if (field == 'forecast_precip_type')
            {
                self.set_field(self, "forecast_precip_type_icon", self.parameters.icons[state.state])
            }
            else if (field == 'wind_bearing')
            {
                var counts = [0, 45, 90, 135, 180, 225, 270, 315]
                var goal = (parseInt(state.state) + 90) % 360
                var closest = counts.reduce(function(prev, curr) {
                      return (Math.abs(curr - goal) < Math.abs(prev - goal) ? curr : prev);
                });
                self.set_field(self, "bearing_icon", "mdi-rotate-" + closest)
            }
            self.set_field(self, field, self.format_number(self, state.state))
        }
    }
}
