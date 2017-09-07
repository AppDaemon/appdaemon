function baseclimate(widget_id, url, skin, parameters)
{

    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this

    // Initialization

    self.widget_id = widget_id

    // Parameters may come in useful later on

    self.parameters = parameters

    self.OnRaiseLevelClick = OnRaiseLevelClick
    self.OnLowerLevelClick = OnLowerLevelClick

    var callbacks =
        [
            {"selector": '#' + widget_id + ' #level-up', "action": "click", "callback": self.OnRaiseLevelClick},
            {"selector": '#' + widget_id + ' #level-down', "action": "click", "callback": self.OnLowerLevelClick},
        ]

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable
    self.OnStateUpdate = OnStateUpdate

    if ("entity" in parameters)
    {
        var monitored_entities =
            [
                {"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
            ]
    }
    else
    {
        var monitored_entities =  []
    }

    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnStateAvailable(self, state)
    {
        self.min = state.attributes.min_temp
        self.max = state.attributes.max_temp
        self.step = 1
        self.level = state.attributes.temperature
        self.set_field(self, "unit", state.attributes.unit_of_measurement)
        set_view(self, state)
    }

    function OnStateUpdate(self, state)
    {
        self.level = state.attributes.temperature
        set_view(self, state)
    }

	function OnRaiseLevelClick(self)
    {
        self.level = parseFloat(self.level) + self.step;
		if (self.level > self.max)
		{
			self.level = self.max
		}
		args = self.parameters.post_service
        args["temperature"] = self.level
		self.call_service(self, args)
    }

	function OnLowerLevelClick(self, args)
    {
        self.level = parseFloat(self.level) - self.step;
		if (self.level < self.min)
		{
			self.level = self.min
		}
		args = self.parameters.post_service
        args["temperature"] = self.level
		self.call_service(self, args)
    }

	function set_view(self, state)
    {
        self.set_field(self, "level", self.format_number(self, state.attributes.current_temperature))
        if ("temperature" in state.attributes && state.attributes.temperature != null)
        {
            self.set_field(self, "level2", self.format_number(self, state.attributes.temperature))
        }
        else
        {
            self.set_field(self, "level2", "auto")
        }
	}
}