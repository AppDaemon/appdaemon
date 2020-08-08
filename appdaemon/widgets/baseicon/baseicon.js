function baseicon(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this;

    // Initialization

    self.widget_id = widget_id;

    // Parameters may come in useful later on

    self.parameters = parameters;

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;
    self.OnIconClick = OnIconClick;

    var monitored_entities =
        [
            {"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
        ];

        var callbacks = [
            {"selector": '#' + widget_id, "action": "click", "callback": self.OnIconClick},
        ]

    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state

    function OnStateAvailable(self, state)
    {
        self.state = state.state;
        set_view(self, self.state)
    }

    // The OnStateUpdate function will be called when the specific entity
    // receives a state update - its new values will be available
    // in self.state[<entity>] and returned in the state parameter

    function OnStateUpdate(self, state)
    {
        self.state = state.state;

        delay_time = self.parameters.update_delay;
        if (delay_time != undefined) {
            if (self.timeout != undefined) {
                clearTimeout(self.timeout);
            }
    
            self.timeout = setTimeout(() => set_view(self, self.state), delay_time * 1000);
        } else {
            set_view(self, self.state);
        }
    }

    function OnIconClick(self) {
        if (self.post_service != undefined) {
            args = self.post_service;
            args["namespace"] = self.parameters.namespace;

            self.call_service(self, args);
        }
    }

    // Set view is a helper function to set all aspects of the widget to its
    // current state - it is called by widget code when an update occurs
    // or some other event that requires a an update of the view

    function set_view(self, state, level)
    {
        if ("icons" in self.parameters)
        {
            if (state in self.parameters.icons)
            {
                self.set_icon(self, "icon", self.parameters.icons[state].icon);
                self.set_field(self, "icon_style", self.parameters.icons[state].style);
                set_service_call(self, self.parameters.icons[state]);
            }
            else if ("default" in self.parameters.icons)
            {
                self.set_icon(self, "icon", self.parameters.icons.default.icon);
                self.set_field(self, "icon_style", self.parameters.icons.default.style);
                set_service_call(self, self.parameters.default);
            }
            else
            {
                self.set_icon(self, "icon", "fa-circle-thin");
                self.set_field(self, "icon_style", "color: white");
                self.post_service = undefined;
            }

        }

        if ("state_text" in self.parameters && self.parameters.state_text == 1)
        {
            self.set_field(self, "state_text", self.map_state(self, state))
        }
    }

    function set_service_call(self, data) {
        if (data.sequence != undefined) {
            self.post_service = data.sequence;
        } else if (data.script != undefined) {
            self.post_service = {
                service: "homeassistant/turn_on",
                entity_id: data.script
            }
        } else {
            self.post_service = undefined;
        }
    }
}
