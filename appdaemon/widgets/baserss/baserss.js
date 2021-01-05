function baserss(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this;

    // Initialization

    self.widget_id = widget_id;

    // Store on brightness or fallback to a default

    // Parameters may come in useful later on

    self.parameters = parameters;

    //
    // RSS Info is always in the admin namespace
    //
    self.parameters.namespace = "admin";

    var callbacks = [];

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

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnStateAvailable(self, state)
    {
        set_value(self, state)
    }

    function OnStateUpdate(self, state)
    {
        set_value(self, state)
    }

    function set_value(self, state)
    {
        self.story = 0;
        clearTimeout(self.timer);
        show_next_story(self);
        self.timer = setInterval(show_next_story, self.parameters.interval * 1000, self);
    }

    function show_next_story(self)
    {
        var stories = self.entity_state[parameters.entity].state.feed.entries;
        self.set_field(self, "text", stories[self.story].title);
        if ("show_description" in self.parameters && self.parameters.show_description === 1)
        {
            if ("summary" in stories[self.story])
            {
                self.set_field(self, "description", stories[self.story].summary)
            }
            if ("description" in stories[self.story])
            {
                self.set_field(self, "description", stories[self.story].description)
            }
        }
        self.story = self.story + 1;
        if ((self.story >= stories.length) || ("recent" in parameters && self.story >= parameters.recent))
        {
            self.story = 0;
        }
    }
}
