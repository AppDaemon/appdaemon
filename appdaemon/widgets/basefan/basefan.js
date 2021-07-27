function basefan(widget_id, url, skin, parameters)
{
    self = this;

    // Initialization

    self.widget_id = widget_id;

    // Parameters may come in useful later on

    self.parameters = parameters;

    self.OnPowerButtonClick = OnPowerButtonClick;
    self.On1ButtonClick = On1ButtonClick;
    self.On2ButtonClick = On2ButtonClick;
    self.On3ButtonClick = On3ButtonClick;

    self.min_level = 0;
    self.max_level = 1;

    if ("step" in self.parameters)
    {
        self.step = self.parameters.step / 100;
    }
    else
    {
        self.step = 0.02;
    }

    var callbacks =
        [
            
            {"selector": '#' + widget_id + ' #power', "action": "click", "callback": self.OnPowerButtonClick},
            {"selector": '#' + widget_id + ' #speed-1', "action": "click", "callback": self.On1ButtonClick},
            {"selector": '#' + widget_id + ' #speed-2', "action": "click", "callback": self.On2ButtonClick},
            {"selector": '#' + widget_id + ' #speed-3', "action": "click", "callback": self.On3ButtonClick}
        ];

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;
console.log(self)
    var monitored_entities =
        [
            {"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
        ];

    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state

    function OnStateAvailable(self, state)
    {
        self.entity = state.entity_id;
        self.level = state.attributes.speed_level;
        self.speed = state.attributes.speed;
        self.state = state;
        console.log(state);
        set_view(self, state)
    }

    // The OnStateUpdate function will be called when the specific entity
    // receives a state update - its new values will be available
    // in self.state[<entity>] and returned in the state parameter

    function OnStateUpdate(self, state)
    {
        self.state = state ;
        self.level = state.attributes.speed_level;
        self.speed = state.attributes.speed;
        console.log(state);
        set_view(self, state)
    }

    function OnPowerButtonClick(self) {
        console.log(self)
        args = self.parameters.post_service_fan;
    
        if (self.speed =="off"){
            args["speed"] ="medium";
        }
        else{
            args["speed"] ="off";
        }
        self.call_service(self, args);
    }

    function On1ButtonClick(self) {
        args = self.parameters.post_service_fan;
        args["speed"] ="low";
        self.call_service(self, args);
    }
    function On2ButtonClick(self) {
        args = self.parameters.post_service_fan;
        args["speed"] ="medium";
        self.call_service(self, args);
    }
    function On3ButtonClick(self) {
        args = self.parameters.post_service_fan;
        args["speed"] ="high";
        self.call_service(self, args);
    }

    
    function set_view(self, state)
    {
        
        if (state.state != "on")
        {
            self.set_icon(self, "icon", self.icons.off_icon)
            self.set_field(self, "speed_style", self.css.speed_style_hidden)
        }
        else
        //Fan is on
        {
            //turn main icon on & dispay speed selector
            self.set_icon(self, "icon", self.icons.on_icon)
            self.set_field(self, "speed_style", self.css.speed_style_visible)

            //decide which icon to mark as selected
            self.set_field(self,"speed_1_style", self.css.speed_style_inactive)
            self.set_field(self,"speed_2_style", self.css.speed_style_inactive)
            self.set_field(self,"speed_3_style", self.css.speed_style_inactive)
            switch (state.attributes.speed){
                case "low":
                    self.set_field(self,"speed_1_style", self.css.speed_style_active)
                break;
                case "medium":
                    self.set_field(self,"speed_2_style", self.css.speed_style_active)
                break;
                case "high":
                    self.set_field(self,"speed_3_style", self.css.speed_style_active)
                break;
            }
            self.set_field(self, "speed_style", self.css.speed_style_visible)

        }


    }

}