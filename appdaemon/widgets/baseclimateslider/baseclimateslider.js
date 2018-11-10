function baseclimateslider(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this

    // Initialization

    self.widget_id = widget_id

    // Store on brightness or fallback to a default

    // Parameters may come in useful later on

    self.parameters = parameters

    self.onChange = onChange
    self.onInput = onInput

    var callbacks = [
            {"observable": "SliderValue", "action": "change", "callback": self.onChange},
            {"selector": "#" + widget_id + " .slidercontainer input", "action": "input", "callback": self.onInput},
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
        self.state = state.state
        self.minvalue = parameters.min
        self.maxvalue = parameters.max
        self.stepvalue = state.attributes.step
        self.target_temperature = state.attributes.temperature
        self.current_temperature = state.attributes.current_temperature
        self.set_field(self, "unit", state.attributes.unit_of_measurement)
        set_options(self, self.minvalue, self.maxvalue, self.stepvalue, self.target_temperature, self.current_temperature, state)
        set_value(self, state)
    }

    function OnStateUpdate(self, state)
    {
        self.target_temperature = state.attributes.temperature
        set_value(self, state)
        $("#" + widget_id + " .loader").hide()
    }

    function set_value(self, state)
    {
        target = self.map_state(self, state.attributes.temperature)
        current = self.map_state(self, state.attributes.current_temperature)
        self.set_field(self, "SliderValue", target)
        self.set_field(self, "target", self.format_number(self,target))
        self.set_field(self, "current", self.format_number(self,current))
    }

    function onInput(self, state)
    {
        desiredTarget = $("#" + widget_id + " .slidercontainer input")[0].value
        self.set_field(self, "target", self.format_number(self,desiredTarget))
    }

    function onChange(self, state)
    {
        if (self.target_temperature != self.ViewModel.SliderValue())
        {
            $("#" + widget_id + " .loader").show()
            self.target_temperature = self.ViewModel.SliderValue()
	    args = self.parameters.post_service
            args["temperature"] = self.target_temperature
	    self.call_service(self, args)
        }
    }

    function set_options(self, minvalue, maxvalue, stepvalue, target_temperature, current_temperature, state)
    {
        self.set_field(self, "MinValue", minvalue)
        self.set_field(self, "MaxValue", maxvalue)
        self.set_field(self, "minValue", self.format_number(self,minvalue))
        self.set_field(self, "maxValue", self.format_number(self,maxvalue))
        self.set_field(self, "StepValue", stepvalue)
        self.set_field(self, "target", target_temperature)
        self.set_field(self, "current", current_temperature)
    }

}