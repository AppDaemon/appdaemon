function baseentitypicture(widget_id, url, skin, parameters)
{
    self = this

    // Initialization

    self.parameters = parameters;

    var callbacks = []

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities =
        [
            {"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
        ];

    if ("base_url" in parameters && parameters.base_url != "") {
        self.base_url = parameters.base_url;
    }else{
        self.base_url = "";
    }

    // Call the parent constructor to get things moving
    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    // Function Definitions

    function OnStateAvailable(self, state)
    {
        set_view(self, state)
    }

    // The OnStateUpdate function will be called when the specific entity
    // receives a state update - its new values will be available
    // in self.state[<entity>] and returned in the state parameter

    function OnStateUpdate(self, state)
    {
        set_view(self, state)
    }

    function set_view(self, state)
    {
        if("entity_picture" in state.attributes){
            self.set_field(self, "img_inernal_src", self.base_url + state.attributes["entity_picture"]);
            self.set_field(self, "img_internal_style", "");
        }else{
            self.set_field(self, "img_inernal_src", "");
            self.set_field(self, "img_internal_style", "display: none;");
        }
    }
}
