function baseheater(widget_id, url, skin, parameters)
{
    self = this
    self.widget_id = widget_id
    self.parameters = parameters

    if ("monitored_entity" in self.parameters)
    {
        entity = self.parameters.monitored_entity
    }
    else
    {
        icon_entity = self.parameters.icon_entity
        slider_entity = self.parameters.slider_entity
    }


    self.onChange = onChange
    self.OnButtonClick = OnButtonClick

    var callbacks = [
            {"selector": '#' + widget_id + ' > span', "action": "click", "callback": self.OnButtonClick},
            {"observable": "Temperature", "action": "change", "callback": self.onChange},
                    ]

    self.OnStateAvailable = OnStateAvailable
    self.OnStateUpdate = OnStateUpdate

    if ("icon_entity" in parameters)
    {
        var monitored_entities =
            [
                {"entity": parameters.icon_entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
                {"entity": parameters.slider_entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
            ]
    }
    else
    {
        var monitored_entities =  []
    }

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)


    function OnStateAvailable(self, state)
    {
        if ("min" in state.attributes)
        {
            self.minvalue = state.attributes.min
            self.maxvalue = state.attributes.max
            self.stepvalue = state.attributes.step
            self.thermovalue = state.state
            set_options(self, self.minvalue, self.maxvalue, self.stepvalue, self.thermovalue)
        }
        else
        {
            self.state = state.state
            set_iconview(self, self.state)
        }
    }

    function OnStateUpdate(self, state)
    {
        if ("min" in state.attributes)
        {
            self.thermovalue = state.state
            set_sliderview(self, self.thermovalue)
        }
        else
        {
            self.state = state.state
            set_iconview(self, self.state)
        }
    }

    function OnButtonClick(self)
    {
        if (self.state == "off")
        {
            args = self.parameters.post_service_active
        }
        else
        {
            args = self.parameters.post_service_inactive
        }
        //alert(args)
        self.call_service(self, args)
        toggle(self)
    }

    function onChange(self, state)
    {
        if (self.thermovalue != self.ViewModel.Temperature())
        {
            self.thermovalue = self.ViewModel.Temperature()
            args = self.parameters.post_service_slider_change
            args["value"] = self.thermovalue
	    self.call_service(self, args)
        }
    }

    function toggle(self)
    {
        if (self.state == "on")
        {
            self.state = "off";
        }
        else
        {
            self.state = "on";
        }
        set_iconview(self, self.state)
    }

    function set_options(self, minvalue, maxvalue, stepvalue, state)
    {
        self.set_field(self, "MinValue", minvalue)
        self.set_field(self, "MaxValue", maxvalue)
        self.set_field(self, "StepValue", stepvalue)
        self.set_field(self, "Temperature", state)
    }

    function set_iconview(self, state)
    {
        if (state == "on")
        {
            self.set_icon(self, "icon", self.icons.icon_on)
            self.set_field(self, "icon_style", self.css.icon_style_active)
        }
        else
        {
            self.set_icon(self, "icon", self.icons.icon_off)
            self.set_field(self, "icon_style", self.css.icon_style_inactive)
        }
    }

    function set_sliderview(self, state)
    {
        if (typeof state == 'undefined')
        {
            self.set_field(self, "Temperature", 0)
        }
        else
        {
            self.set_field(self, "Temperature", state)
        }
    }

}
