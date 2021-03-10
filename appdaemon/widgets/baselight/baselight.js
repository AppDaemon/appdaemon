function baselight(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this

    // Initialization

    self.widget_id = widget_id

    // Parameters may come in useful later on

    self.parameters = parameters

    // Parameter handling

    if ("monitored_entity" in self.parameters)
    {
        entity = self.parameters.monitored_entity
    }
    else
    {
        entity = self.parameters.entity
    }

    if ("on_brightness" in self.parameters)
    {
        self.on_brightness = self.parameters.on_brightness
    }
    else
    {
        self.on_brightness = 127
    }

    // Define callbacks for on click events
    // They are defined as functions below and can be any name as long as the
    // 'self'variables match the callbacks array below
    // We need to add them into the object for later reference

    self.OnButtonClick = OnButtonClick
    self.OnRaiseLevelClick = OnRaiseLevelClick
    self.OnLowerLevelClick = OnLowerLevelClick

    var callbacks =
        [
            {"selector": '#' + widget_id + ' > span', "action": "click", "callback": self.OnButtonClick},
            {"selector": '#' + widget_id + ' #level-up', "action": "click", "callback": self.OnRaiseLevelClick},
            {"selector": '#' + widget_id + ' #level-down', "action": "click", "callback": self.OnLowerLevelClick},
        ]

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable
    self.OnStateUpdate = OnStateUpdate

    var monitored_entities =
        [
            {"entity": entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
        ]

    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state

    function OnStateAvailable(self, state)
    {
        self.state = state.state;
        if ("brightness" in state.attributes)
        {
            self.level = state.attributes.brightness
        }
        else
        {
            self.level = 0
        }
        set_view(self, self.state, self.level)
    }

    // The OnStateUpdate function will be called when the specific entity
    // receives a state update - its new values will be available
    // in self.state[<entity>] and returned in the state parameter

    function OnStateUpdate(self, state)
    {
        self.state = state.state;
        if ("brightness" in state.attributes)
        {
            self.level = state.attributes.brightness
        }
        else
        {
            self.level = 0
        }

        set_view(self, self.state, self.level)
    }

    function OnButtonClick(self)
    {
        if (self.state == "off")
        {
            args = jQuery.extend(true, {}, self.parameters.post_service_active)
            if ("on_attributes" in self.parameters)
            {
                for (var attr in self.parameters.on_attributes)
                {
                    args[attr] = self.parameters.on_attributes[attr]
                }
            }
        }
        else
        {
            args = jQuery.extend(true, {}, self.parameters.post_service_inactive)
        }
        self.call_service(self, args)
        toggle(self)
    }

    function OnRaiseLevelClick(self)
    {
        self.level = self.level + 255/10;
        self.level = parseInt(self.level)
        if (self.level > 255)
        {
            self.level = 255
        }
        args = jQuery.extend(true, {}, self.parameters.post_service_active);
        args["brightness"] = self.level
        self.call_service(self, args)
    }

    function OnLowerLevelClick(self)
    {
        self.level = self.level - 255/10;
        if (self.level < 0)
        {
            self.level = 0;
        }
        self.level = parseInt(self.level)
        if (self.level == 0)
        {
            args = jQuery.extend(true, {}, self.parameters.post_service_inactive)
        }
        else
        {
            args = jQuery.extend(true, {}, self.parameters.post_service_active)
            args["brightness"] = self.level
        }
        self.call_service(self, args)
    }

    function toggle(self)
    {
        if (self.state == "on")
        {
            self.state = "off";
            self.level = 0
        }
        else
        {
            self.state = "on";
        }
        set_view(self, self.state, self.level)
    }

    // Set view is a helper function to set all aspects of the widget to its
    // current state - it is called by widget code when an update occurs
    // or some other event that requires a an update of the view

    function set_view(self, state, level)
    {

        if (state == "on")
        {
            // Set Icon will set the style correctly for an icon
            self.set_icon(self, "icon", self.icons.icon_on)
            // Set view will set the view for the appropriate field
            self.set_field(self, "icon_style", self.css.icon_style_active)
        }
        else
        {
            self.set_icon(self, "icon", self.icons.icon_off)
            self.set_field(self, "icon_style", self.css.icon_style_inactive)
        }
        if (typeof level == 'undefined')
        {
            self.set_field(self, "level", 0)
        }
        else
        {
            self.set_field(self, "level", Math.ceil((level*100/255) / 10) * 10)
        }
    }
}
