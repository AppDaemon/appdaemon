function basealarm(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this

    // Initialization

    self.widget_id = widget_id

    // Parameters may come in useful later on

    self.parameters = parameters

    self.OnButtonClick = OnButtonClick
    self.OnCloseClick = OnCloseClick
    self.OnDigitClick = OnDigitClick
    self.OnArmHomeClick = OnArmHomeClick
    self.OnArmAwayClick = OnArmAwayClick
    self.OnDisarmClick = OnDisarmClick
    self.OnTriggerClick = OnTriggerClick


    var callbacks =
        [
            {"selector": '#' + widget_id + ' > span', "action": "click", "callback": self.OnButtonClick},
            {"selector": '#' + widget_id + ' #close', "action": "click", "callback": self.OnCloseClick},
            {"selector": '#' + widget_id + ' #0', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "0"}},
            {"selector": '#' + widget_id + ' #1', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "1"}},
            {"selector": '#' + widget_id + ' #2', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "2"}},
            {"selector": '#' + widget_id + ' #3', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "3"}},
            {"selector": '#' + widget_id + ' #4', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "4"}},
            {"selector": '#' + widget_id + ' #5', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "5"}},
            {"selector": '#' + widget_id + ' #6', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "6"}},
            {"selector": '#' + widget_id + ' #7', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "7"}},
            {"selector": '#' + widget_id + ' #8', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "8"}},
            {"selector": '#' + widget_id + ' #9', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "9"}},
            {"selector": '#' + widget_id + ' #BS', "action": "click", "callback": self.OnDigitClick, "parameters": {"digit" : "BS"}},
            {"selector": '#' + widget_id + ' #AH', "action": "click", "callback": self.OnArmHomeClick},
            {"selector": '#' + widget_id + ' #AA', "action": "click", "callback": self.OnArmAwayClick},
            {"selector": '#' + widget_id + ' #DA', "action": "click", "callback": self.OnDisarmClick},
            {"selector": '#' + widget_id + ' #TR', "action": "click", "callback": self.OnTriggerClick},

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

    self.set_view = set_view

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnStateAvailable(self, state)
    {
        self.set_field(self, "state", self.map_state(self, state.state))
    }

    function OnStateUpdate(self, state)
    {
        self.set_field(self, "state", self.map_state(self, state.state))
    }

    function OnButtonClick(self)
    {
        self.code = self.parameters.initial_string
        self.set_view(self)

        $('#' + widget_id + ' > #Dialog').removeClass("modalDialogClose")
        $('#' + widget_id + ' > #Dialog').addClass("modalDialogOpen")
    }

    function OnCloseClick(self)
    {
        $('#' + widget_id + ' > #Dialog').removeClass("modalDialogOpen")
        $('#' + widget_id + ' > #Dialog').addClass("modalDialogClose")
    }

    function OnDigitClick(self, parameters)
    {
        if (parameters.digit == "BS")
        {
            if (self.code != self.parameters.initial_string)
            {
                if (self.code.length == 1)
                {
                    self.code = self.parameters.initial_string
                }
                else
                {
                    self.code = self.code.substring(0, self.code.length - 1);
                }
            }
        }
        else
        {
            if (self.code == self.parameters.initial_string)
            {
                self.code = parameters.digit
            }
            else
            {
                self.code = self.code + parameters.digit
            }
        }
        self.set_view(self)
    }

    function OnArmHomeClick(self)
    {

        args = self.parameters.post_service_ah
        args["code"] = self.code
        self.call_service(self, args)

        self.code = self.parameters.initial_string
        self.set_view(self)
    }

    function OnArmAwayClick(self)
    {
        args = self.parameters.post_service_aa
        args["code"] = self.code
        self.call_service(self, args)

        self.code = self.parameters.initial_string
        self.set_view(self)
    }

    function OnDisarmClick(self)
    {
        args = self.parameters.post_service_da
        args["code"] = self.code
        self.call_service(self, args)

        self.code = self.parameters.initial_string
        self.set_view(self)
    }

    function OnTriggerClick(self)
    {
        args = self.parameters.post_service_tr
        args["code"] = self.code
        self.call_service(self, args)

        self.code = self.parameters.initial_string
        self.set_view(self)
    }

    function set_view(self)
    {
        self.set_field(self, "code", self.code)
    }
}
