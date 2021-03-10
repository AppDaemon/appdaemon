function basedisplay(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this;

    // Initialization

    self.widget_id = widget_id;

    // Store on brightness or fallback to a default

    // Parameters may come in useful later on

    self.parameters = parameters;

    var callbacks = [];

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;
    self.OnSubStateAvailable = OnSubStateAvailable;
    self.OnSubStateUpdate = OnSubStateUpdate;

    var monitored_entities =  [];

    if ("entity" in parameters && parameters.entity != "")
    {
        // Make sure that we monitor the entity, not an attribute of it
        split_entity = parameters.entity.split(".")
        self.entity = split_entity[0] + "." + split_entity[1]
        if (split_entity.length > 2)
        {
            self.entity_attribute = split_entity[2]
        }
        // Check if the sub_entity should be created by monitoring an attribute of the entity
        if ("entity_to_sub_entity_attribute" in parameters && parameters.entity_to_sub_entity_attribute != "")
        {
            self.sub_entity = self.entity
            self.sub_entity_attribute = parameters.entity_to_sub_entity_attribute
        }
    }

    // Only set up the sub_entity if it was not created already with the entity + attribute
    if ("sub_entity" in parameters && parameters.sub_entity != "" && !("sub_entity" in self))
    {
        // Make sure that we monitor the sub_entity, not an attribute of it
        split_sub_entity = parameters.sub_entity.split(".")
        self.sub_entity = split_sub_entity[0] + "." + split_sub_entity[1]
        if (split_sub_entity.length > 2)
        {
            self.sub_entity_attribute = split_sub_entity[2]
        }
        // Check if the entity should be created by monitoring an attribute of the sub_entity
        if ("sub_entity_to_entity_attribute" in parameters && !("entity" in self))
        {
            self.entity = self.sub_entity
            self.entity_attribute = parameters.sub_entity_to_entity_attribute
        }
    }

    if ("entity" in self)
    {
        monitored_entities.push({"entity": self.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate})
    }
    if ("sub_entity" in self)
    {
        monitored_entities.push({"entity": self.sub_entity, "initial": self.OnSubStateAvailable, "update": self.OnSubStateUpdate})
    }

    // Finally, call the parent constructor to get things moving

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

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

    function OnSubStateAvailable(self, state)
    {
        set_sub_value(self, state)
    }

    function OnSubStateUpdate(self, state)
    {
        set_sub_value(self, state)
    }

    function set_value(self, state)
    {
        if ("entity_attribute" in self) {
            value = state.attributes[self.entity_attribute]
        }
        else
        {
                value = state.state
        }

        if (isNaN(value))
        {
            self.set_field(self, "value_style", self.parameters.css.text_style);
            self.set_field(self, "value", self.map_state(self, value))
        }
        else
        {
            self.set_field(self, "value_style", self.parameters.css.value_style);
            self.set_field(self, "value", self.format_number(self, value));
            self.set_field(self, "unit_style", self.parameters.css.unit_style);
            if ("units" in self.parameters)
            {
                self.set_field(self, "unit", self.parameters.units)
            }
            else
            {
                self.set_field(self, "unit", state.attributes["unit_of_measurement"])
            }
        }
    }

    function set_sub_value(self, state)
    {
        if ("sub_entity_attribute" in self && self.sub_entity_attribute != "")
        {
            value = state.attributes[self.sub_entity_attribute]
        }
        else
        {
                value = state.state
        }

        if ("sub_entity_map" in self.parameters)
        {
            self.set_field(self, "state_text", self.parameters.sub_entity_map[value])
        }
        else
        {
            self.set_field(self, "state_text", value)
        }
    }
}
