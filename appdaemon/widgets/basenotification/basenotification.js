function basenotification(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this

    // Initialization

    self.widget_id = widget_id

    // Store on brightness or fallback to a default

    // Parameters may come in useful later on

    self.parameters = parameters

    // Define callbacks for on click events
    // They are defined as functions below and can be any name as long as the
    // 'self'variables match the callbacks array below
    // We need to add them into the object for later reference

    self.OnButtonClick = OnButtonClick

    var callbacks =
        [
            {"selector": ['#' + widget_id, '.dismiss'], "callback": self.OnButtonClick, "live": true},
        ]

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable
    self.OnStateUpdate = OnStateUpdate

    self.entity_state = {}

    var monitored_entities =
        [
            {"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate, "initial_with_null": self.OnStateAvailable}
        ]

    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state

    function OnStateAvailable(self, state)
    {
        self.state = state;
        set_view(self, self.state)
    }

    // The OnStateUpdate function will be called when the specific entity
    // receives a state update - it's new values will be available
    // in self.state[<entity>] and returned in the state parameter

    function OnStateUpdate(self, state)
    {
        self.state = state;
        set_view(self, self.state)
    }

    function OnButtonClick(self)
    {
        self.call_service(self, self.parameters.post_service_dismiss)
        set_view(self, null)
    }

    // Set view is a helper function to set all aspects of the widget to its
    // current state - it is called by widget code when an update occurs
    // or some other event that requires a an update of the view

    function set_view(self, state, level)
    {
        self.set_field(self, "display", state!=null);

        if (state != null && "state" in state) {
            self.set_field(self, "state_text", state.state);
        } else {
            self.set_field(self, "state_text", null);
        }
        if (state != null && "attributes" in state && "title" in state.attributes) {
            self.set_field(self, "title", state.attributes.title);
        } else {
            self.set_field(self, "title", null);
        }

        if (state!=null) {
            self.audio = new Audio("/sounds/tos-redalert.mp3");
            self.audio.addEventListener('ended', function() {
                this.currentTime = 0;
                this.play();
            });
            self.audio.play();
        } else {
            if (self.audio) {
                self.audio.pause();
            }
        }

    }
}
