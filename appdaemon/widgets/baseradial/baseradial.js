function baseradial(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...

    self = this

    // Initialization

    self.widget_id = widget_id

    // Store on brightness or fallback to a default

    // Parameters may come in useful later on

    self.parameters = parameters

    var callbacks = []

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

    // Function Definitions

    // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnStateAvailable(self, state)
    {
        activateChart(self, state)
    }

    function OnStateUpdate(self, state)
    {
        set_value(self, state)
    }

    function set_value(self, state)
    {
        self.gauge.value = state.state
       // self.gauge.update()
    }

    function activateChart(self, state) {
        self.gauge = new RadialGauge({
            renderTo: document.getElementById(self.widget_id).getElementsByClassName('gaugeclass')[0],
            type: 'radial-gauge',
            width: '120',
            height: '120',
            //valueInt: 2,
            //valueDec: 1,
            colorTitle: '#333',
            //minValue: 17,
            //maxValue: 25,
            //minorTicks: 2,
            //strokeTicks: true,
        })
        self.gauge.value = state.state
        self.gauge.update(self.parameters.settings)
        //self.gauge.draw()
    }
}
