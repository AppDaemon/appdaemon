function baseAdminLog(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...
    
    self = this;
    
    // Initialization
    
    self.widget_id = widget_id;
    self.parameters = parameters;
    
    
    log_style = ""
    if ("log_style" in self.parameters){
       log_style = self.parameters.log_style
    }   
    document.getElementById(self.widget_id).innerHTML = document.getElementById(self.widget_id).innerHTML + "<table style='" + log_style + "' id='" + self.widget_id + "_log'></table>";

    var callbacks = [];

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity
     
    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities =  [];


    monitored_entities.push({"entity": self.parameters.fields.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate})
    // Finally, call the parent constructor to get things moving
    
    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);
    parameters.namespace = "admin"
    service_args = {"service": "log_widget/start","log_lines": self.parameters.max_loglines, "entity": self.parameters.fields.entity}
    setTimeout(self.call_service, 1000, self, service_args);

    // Function Definitions
    
    // The StateAvailable function will be called when 
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state
    // Methods

    function OnStateAvailable(self, state, entity)
    {    
        console.log("initial " + entity)
        //console.log(state)
    }
 
    function OnStateUpdate(self, state, entity)
    {
        //console.log(state)
        special_style = ""
        line_style = ""
        if ("logline_style" in self.parameters.fields){
            line_style = self.parameters.fields.logline_style
        }
        if ("special_css" in self.parameters.fields){
            for (let style_name in self.parameters.fields.special_css){
                _text = self.parameters.fields.special_css[style_name].check_for
                if (state.data.formatted_message.includes(_text)){
                    special_style = special_style + self.parameters.fields.special_css[style_name].line_style
                }
            }
        }
        if ("replace_text" in self.parameters.fields){
            for (let replace_name in self.parameters.fields.replace_text){
                _text = self.parameters.fields.replace_text[replace_name].check_for
                replace_text = self.parameters.fields.replace_text[replace_name].replace_with
                state.data.formatted_message = state.data.formatted_message.replace(_text,replace_text)
                //console.log("replace " + _text + " with " + replace_text)
            }
        }
        _style = line_style + special_style + "display: inline-block;float:left;"
        newlogline = "<tr>"
        if ("split_into_columns" in self.parameters){
            if ("max_columns" in self.parameters){
                newloglineparts = state.data.formatted_message.split(self.parameters.split_into_columns,self.parameters.max_columns)
            } else {
                newloglineparts = state.data.formatted_message.split(self.parameters.split_into_columns)
            }
            for (var i=0; i<newloglineparts.length; i++){
                cell_width = ""
                if ("cell_widths" in self.parameters){
                    if( i <= self.parameters.cell_widths.length){
                        cell_width = "width='" + self.parameters.cell_widths[i] + "'";
                    }
                }
                newlogline = newlogline + "<td " + cell_width + " style='" + _style + "' id='" + self.widget_id + "_logline'>" + newloglineparts[i] + "</td>"
            }
        } else {
            newlogline = newlogline + "<td style='" + _style + "' id='" + self.widget_id + "_logline'>" + state.data.formatted_message + "</td>"
        }
        newlogline = newlogline + "</tr>"
        document.getElementById(self.widget_id + "_log").innerHTML = newlogline + document.getElementById(self.widget_id + "_log").innerHTML
        logline_amount = $("#" + self.widget_id + "_log > tbody").length
        //console.log(logline_amount)
        loglines = document.getElementById(self.widget_id + "_log")
        for (var i=self.parameters.max_loglines; i<logline_amount; i++)
        {
            loglines.removeChild(loglines.lastChild);
        }
    }

}
