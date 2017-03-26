function basemedia(widget_id, url, skin, parameters)
{
    self = this;

    // Initialization

    self.widget_id = widget_id;

    // Parameters may come in useful later on

    self.parameters = parameters;

    self.OnStopButtonClick = OnStopButtonClick;
    self.OnPauseButtonClick = OnPauseButtonClick;
    self.OnPlayButtonClick = OnPlayButtonClick;
    self.OnRaiseLevelClick = OnRaiseLevelClick;
    self.OnLowerLevelClick = OnLowerLevelClick;

    self.min_level = 0;
    self.max_level = 1;
    self.step = 0.1;

    var callbacks =
        [
            {"selector": '#' + widget_id + ' #stop', "callback": self.OnStopButtonClick},
            {"selector": '#' + widget_id + ' #pause', "callback": self.OnPauseButtonClick},
            {"selector": '#' + widget_id + ' #play', "callback": self.OnPlayButtonClick},
            {"selector": '#' + widget_id + ' #level-up', "callback": self.OnRaiseLevelClick},
            {"selector": '#' + widget_id + ' #level-down', "callback": self.OnLowerLevelClick},
        ];

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

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
        self.level = state.attributes.volume_level;
        set_view(self, state)
    }

    // The OnStateUpdate function will be called when the specific entity
    // receives a state update - it's new values will be available
    // in self.state[<entity>] and returned in the state parameter

    function OnStateUpdate(self, state)
    {
        set_view(self, state)
    }

    function OnStopButtonClick(self)
    {
        if (self.entity_state[self.entity].state !== "idle")
        {
            args = self.parameters.post_service_stop;
            self.call_service(self, args)
        }
    }

    function OnPauseButtonClick(self)
    {
        if (self.entity_state[self.entity].state !== "paused")
        {
            args = self.parameters.post_service_pause;
            self.call_service(self, args)
        }
    }

    function OnPlayButtonClick(self)
    {
        if (self.entity_state[self.entity].state !== "playing")
        {
            args = self.parameters.post_service_play;
            self.call_service(self, args)
        }
    }

    function OnRaiseLevelClick(self)
    {
        self.level = self.level + self.step;
        if (self.level > self.max_level)
        {
            self.level = self.max_level
        }

        args = self.parameters.post_service_level;
        args["volume_level"] = self.level;
        self.call_service(self, args)

    }

    function OnLowerLevelClick(self)
    {
        self.level = self.level - self.step;
        if (self.level < self.min_level)
        {
            self.level = self.min_level
        }

        args = self.parameters.post_service_level;
        args["volume_level"] = self.level;
        self.call_service(self, args)


    }

    function set_view(self, state)
    {
        if (state.state === "playing")
        {
            self.set_field(self, "play_icon_style", self.css.icon_style_active)
        }
        else
        {
            self.set_field(self, "play_icon_style", self.css.icon_style_inactive)
        }
        if (state.state === "paused")
        {
            self.set_field(self, "pause_icon_style", self.css.icon_style_active)
        }
        else
        {
            self.set_field(self, "pause_icon_style", self.css.icon_style_inactive)
        }
        if (state.state === "idle")
        {
            self.set_field(self, "stop_icon_style", self.css.icon_style_active)
        }
        else
        {
            self.set_field(self, "stop_icon_style", self.css.icon_style_inactive)
        }

        self.set_field(self, "artist", state.attributes.media_artist);
        self.set_field(self, "album", state.attributes.media_album_name);
        self.set_field(self, "media_title", state.attributes.media_content_id);
        self.set_field(self, "level", state.attributes.volume_level * 100)

    }
}