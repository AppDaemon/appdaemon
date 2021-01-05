function baseinputnumber(widget_id, url, skin, parameters)
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

    var callbacks = [
            {"observable": "SliderValue", "action": "change", "callback": self.onChange},
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
        self.minvalue = state.attributes.min
        self.maxvalue = state.attributes.max
        self.stepvalue = state.attributes.step
        set_options(self, self.minvalue, self.maxvalue, self.stepvalue, state)
        set_value(self, state)
    }

    function OnStateUpdate(self, state)
    {
        self.state = state.state
        set_value(self, state)
    }

    function set_value(self, state)
    {
        value = self.map_state(self, state.state)
        self.set_field(self, "SliderValue", value)
        self.set_field(self, "sliderValue", self.format_number(self,value))
    }

    function onChange(self, state)
    {
        if (self.state != self.ViewModel.SliderValue())
        {
            self.state = self.ViewModel.SliderValue()
	    args = self.parameters.post_service
            args["value"] = self.state
	    self.call_service(self, args)
        }
    }

    function set_options(self, minvalue, maxvalue, stepvalue, state)
    {
        //alert(self.maxvalue)
        self.set_field(self, "MinValue", minvalue)
        self.set_field(self, "MaxValue", maxvalue)
        self.set_field(self, "minValue", self.format_number(self,minvalue))
        self.set_field(self, "maxValue", self.format_number(self,maxvalue))
        self.set_field(self, "StepValue", stepvalue)
    }

}
