function baseAdminSummary(widget_id, url, skin, parameters)
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

    var monitored_entities =  [];

    window[self.widget_id] = {}
    window[self.widget_id]["entities"] = {}
    if ("entities" in parameters && parameters.entities != "")
    {
        counter = 0
        for (let entity in parameters.entities)
        {
            counter_str = counter.toString()
            monitored_entities.push({"entity": entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate})
            window[self.widget_id]["entities"][counter_str] = {}
            window[self.widget_id]["entities"][counter_str]["name"] = entity
            window[self.widget_id]["entities"][counter_str]["title"] = parameters.entities[entity]["title"]
            window[self.widget_id]["entities"][counter_str]["title_style"] = parameters.entities[entity]["title_style"]
            window[self.widget_id]["entities"][counter_str]["sensor_style"] = parameters.entities[entity]["sensor_style"]
            counter = counter + 1
        }
        window[self.widget_id]["entity_amount"] = counter
    }


    // Function Definitions
    
    // The StateAvailable function will be called when 
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods


    // create the HTML table
    table_style = ""
    if ("table_style" in parameters.table){
        table_style = parameters.table.table_style;
    }
    table_container ='<span data-bind="attr:{style: container_style}" ><table style="' + table_style + '">';
    if (parameters.table.fill_style = "vertical")
    { 
        entity_nr = 0
        for (var i=0; i<parameters.table.sensor_height; i++)
        {
            table_container = table_container + "<tr>"
            for (var j=0; j<parameters.table.sensor_width; j++)
            {
                sensor_style = ""
                sensor_title_style = ""
                if (window[self.widget_id]["entities"][entity_nr]["sensor_style"] !== undefined){
                    sensor_style = window[self.widget_id]["entities"][entity_nr]["sensor_style"]
                }
                if (window[self.widget_id]["entities"][entity_nr]["title"] !== undefined){
                    sensor_name = window[self.widget_id]["entities"][entity_nr]["title"]
                } else {
                    sensor_name = window[self.widget_id]["entities"][entity_nr]["name"]
                }
                if (window[self.widget_id]["entities"][entity_nr]["title_style"] !== undefined){
                    sensor_title_style = window[self.widget_id]["entities"][entity_nr]["title_style"]
                }
                table_container = table_container + "<td style='" + sensor_title_style + "'>" + sensor_name + "</td>"
                table_container = table_container + "<td style='" + sensor_style + "' id='" + self.widget_id + window[self.widget_id]["entities"][entity_nr]["name"] + "_value'></td>"
                entity_nr = entity_nr + 1
            }
            table_container = table_container + "</tr>"
        }
    }
    else
    {
        entity_nr = 0
        for (var i=0; i<parameters.table.sensor_width; i++)
        {
            table_container = table_container + "<tr>"
            for (var j=0; j<parameters.table.sensor_height; j++)
            {
                sensor_style = ""
                sensor_title_style = ""
                if (window[self.widget_id]["entities"][entity_nr]["sensor_style"] !== undefined){
                    sensor_style = window[self.widget_id]["entities"][entity_nr]["sensor_style"]
                }
                if (window[self.widget_id]["entities"][entity_nr]["title"] !== undefined){
                    sensor_name = window[self.widget_id]["entities"][entity_nr]["title"]
                } else {
                    sensor_name = window[self.widget_id]["entities"][entity_nr]["name"]
                }
                if (window[self.widget_id]["entities"][entity_nr]["title_style"] !== undefined){
                    sensor_title_style = window[self.widget_id]["entities"][entity_nr]["title_style"]
                }
                table_container = table_container + "<td style='" + sensor_title_style + "'>" + sensor_name + "</td>"
                table_container = table_container + "<td style='" + sensor_style + "' id='" + self.widget_id + window[self.widget_id]["entities"][entity_nr]["name"] + "_value'></td>"
                entity_nr = entity_nr + 1
            }
            table_container = table_container + "</tr>"
        }
    }
    table_container = table_container + "</table></span>"
    document.getElementById(self.widget_id).innerHTML = document.getElementById(self.widget_id).innerHTML + table_container;


    // Finally, call the parent constructor to get things moving
    
    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);



    function OnStateAvailable(self, state, entity)
    {    
        set_value(self, state, entity)
    }
 
    function OnStateUpdate(self, state, entity)
    {
        set_value(self, state, entity)
    }

    function set_value(self, state, entity)
    {
        //console.log(state)
        value = state.state
        if ("attribute" in self.parameters.entities[entity]){
            value = state.attributes[self.parameters.entities[entity]["attribute"]]
        }
        field = self.widget_id + entity + "_value"
        //console.log(field + " set to " + value)
        document.getElementById(field).innerHTML = value
        //self.set_field(self, field, self.format_number(self, value)) 
    }

}
