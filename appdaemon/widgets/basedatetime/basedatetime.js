function basedatetime(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this;

    // Initialization

    self.widget_id = widget_id;

    // Store on brightness or fallback to a default

    // Parameters may come in useful later on

    self.parameters = parameters;

    self.OnChange = OnChange;

    var callbacks = [
        {"observable": "DateValue", "action": "change", "callback": self.OnChange},
        {"observable": "TimeValue", "action": "change", "callback": self.OnChange},
    ];

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

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

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnChange(self, state)
    {
        date = self.ViewModel.DateValue()
        time = self.ViewModel.TimeValue()
        args = self.parameters.post_service
        if (self.has_date && self.has_time) {
            args["datetime"] = self.state
            datetime = new Date(self.state);
            args["date"] = date;
            args["time"] = time;
        }
        else if (self.has_date) {
            args["date"] = date;
        }
        else {
            args["time"] = time;
        }
        self.call_service(self, args);
    }

    function OnStateAvailable(self, state)
    {
        self.has_date = state.attributes.has_date
        self.has_time = state.attributes.has_time
        fields = document.getElementById(self.widget_id).childNodes[2];
        datefield = document.getElementById(self.widget_id).childNodes[2].childNodes[0];
        timefield = document.getElementById(self.widget_id).childNodes[2].childNodes[1];
        if(self.has_date && self.has_time)
        {
            // do nothing
        }
        else if(self.has_time)
        {
            fields.removeChild(datefield)
        }
        else if(self.has_date)
        {
            fields.removeChild(timefield)
        }
        set_value(self, state)
    }

    function OnStateUpdate(self, state)
    {
        set_value(self, state)
    }


    function set_value(self, state)
    {
        datetime = new Date(state.state);
        if (self.has_date && self.has_time)
        {
            datevalue = datetime.getFullYear() + "-" + pad(datetime.getMonth()+1) + "-" + pad(datetime.getDate());
            timevalue = pad(datetime.getHours()) + ":" + pad(datetime.getMinutes()) + ":" + pad(datetime.getSeconds());
            self.set_field(self, "TimeValue", timevalue);
            self.set_field(self, "DateValue", datevalue);
        }
        else if (self.has_date)
        {
            datevalue = datetime.getFullYear() + "-" + pad(datetime.getMonth()+1) + "-" + pad(datetime.getDate());
            self.set_field(self, "DateValue", datevalue);
        }
        else
        {
            timevalue = pad(datetime.getHours()) + ":" + pad(datetime.getMinutes()) + ":" + pad(datetime.getSeconds());
            self.set_field(self, "TimeValue", state.state);
        }

    }

    function pad(n)
    {
        return n<10 ? '0'+n : n;
    }
}
