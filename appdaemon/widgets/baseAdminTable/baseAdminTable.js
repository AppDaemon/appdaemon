function baseAdminTable(widget_id, url, skin, parameters)
{
    // Will be using "self" throughout for the various flavors of "this"
    // so for consistency ...
    
    self = this;
    
    // Initialization
    
    self.widget_id = widget_id;
    
    // Store on brightness or fallback to a default
        
    // Parameters may come in useful later on
    
    self.parameters = parameters;
    
    
    // Define callbacks for on click events
    // They are defined as functions below and can be any name as long as the
    // 'self'variables match the callbacks array below
    // We need to add them into the object for later reference
   
    var callbacks = []

    // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
    // Initial will be called when the dashboard loads and state has been gathered for the entity
    // Update will be called every time an update occurs for that entity
     
    var monitored_entities = [];
    
    // Finally, call the parent constructor to get things moving
    
    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);  

    // start building the tables

    window[self.widget_id] = {}
    default_table_list = Default_table_list()
    window["table_value_types"] = Table_value_types()

    // Check if namespaces are set, else default to admin
    if (!("namespace_list" in self.parameters)){
        window[self.widget_id]["namespace_list"] = ["admin"];
    } else {
        window[self.widget_id]["namespace_list"] = self.parameters.namespaces;
    }

    // add defaults for every namespace
    window[self.widget_id]["namespace_list"].forEach(_namespace => {
        default_table_list[_namespace + "entities"] = Default_entity_table();
    });

    // Check if tables are set, else default to app_table
    if (!("tables" in self.parameters)){
        window[self.widget_id]["tables"] = {"app":{"title":"App"}};
        window[self.widget_id]["namespace_list"].forEach(_namespace => {
            window[self.widget_id]["tables"][_namespace + "entities"] = {"title": _namespace + "entities"};
        });
    } else {
        if ("entities" in self.parameters.tables){
            window[self.widget_id]["show_namespaces"] = true;
            window[self.widget_id]["tables"] = {}            
            for (let _table in self.parameters.tables){
                if (_table != "entities"){
                    window[self.widget_id]["tables"][_table] = self.parameters.tables[_table];
                }
                else
                {
                    window[self.widget_id]["namespace_list"].forEach(_namespace => {
                        window[self.widget_id]["tables"][_namespace + "entities"] = self.parameters.tables["entities"];
                    });
                }                        
            }
        }
        else
        {
            window[self.widget_id]["show_namespaces"] = false;            
            window[self.widget_id]["tables"] = self.parameters.tables
            window[self.widget_id]["namespace_list"].forEach(_namespace => {
                window[self.widget_id]["tables"][_namespace + "entities"] = {"title": _namespace + "entities"};
            });
        }        
    }


    // check if table columns are defined, else set the defaults and add id as field
    for (let _table in window[self.widget_id]["tables"]){
        counter = 1;
        if (!("columns" in window[self.widget_id]["tables"][_table])){
            window[self.widget_id]["tables"][_table]["columns"] = {"id":{"order":0}};
            default_table_list[_table].forEach(_column => {
                window[self.widget_id]["tables"][_table]["columns"][_column] = {"title": _column,"order":counter};
                counter = counter + 1
            });
        }
        else
        {
            window[self.widget_id]["tables"][_table]["columns"]["id"] = {"order":0};
            for (let _column in window[self.widget_id]["tables"][_table]["columns"]){
                if (!("order" in window[self.widget_id]["tables"][_table]["columns"][_column])){
                    window[self.widget_id]["tables"][_table]["columns"][_column]["order"] = counter;
                    counter = counter + 1;
                }
            }
        }
    }

    //console.log(window[self.widget_id])



    // create the HTML tables
    for (let _table in window[self.widget_id]["tables"]){
        if (_table.includes("callback")){
            _class = "callbacks";
        } else if (_table.includes("entities")){
            _class = "entities";
        } else
        {
            _class = _table;
        }
        th_style = "";
        table_style = ""
        if ("table_style" in window[widget_id]["tables"][_table]){
            table_style = window[widget_id]["tables"][_table]["table_style"];
        }
        if ("head_style" in window[widget_id]["tables"][_table]){
            th_style = window[widget_id]["tables"][_table]["head_style"];
        }
        _thead ='<span data-bind="attr:{style: container_style}" id="' + self.widget_id + _table + '_table_id"><table style="' + table_style + '" class="' + _class + '"><thead><tr>';
        _options = '<tr>';
        sorted_columns = [];
        _orderlist = {};
        for ( let _column in window[widget_id]["tables"][_table]["columns"]){
            _orderlist[window[widget_id]["tables"][_table]["columns"][_column]["order"].toString()] = _column
        }
        for (var i=0; i<Object.keys(_orderlist).length; i++){
            _column = _orderlist[i.toString()]
            if (_column == "args" || _column == "kwargs" || _column == "attributes"){
                _class = "tooltip " + _column;
            }
            else
            {
                _class = _column;
            }
            if (_column == "id"){
                _thead = _thead + '<th style="display:none;" class="sort" data-sort="' + _column + '">' + _column + '<i class="caret"></i></th>';
                _options = _options + '<td style="display:none;" class="' + _class + '"></td>';
            } else {
                _width = ""
                if ("width" in window[widget_id]["tables"][_table]["columns"][_column]){
                    _width = 'width="'+ window[widget_id]["tables"][_table]["columns"][_column]["width"] + '" ';
                }
                td_style = "";
                if ("style" in window[widget_id]["tables"][_table]["columns"][_column]){
                    td_style = window[widget_id]["tables"][_table]["columns"][_column]["style"];
                }
                td_name = _column;
                if ("title" in window[widget_id]["tables"][_table]["columns"][_column]){
                    td_name = window[widget_id]["tables"][_table]["columns"][_column]["title"];
                }
                _thead = _thead + '<th style="' + table_style + th_style + '" ' + _width + 'class="sort" data-sort="' + _column + '">' + td_name + '<i class="caret"></i></th>';
                _options = _options + '<td style="' + table_style + td_style + '"class="' + _class + '"></td>';
            }
        }
        _thead = _thead + '</tr></thead><tbody class="list"></tbody></table></span>';
        _options = _options + '<tr>';
        document.getElementById(self.widget_id).innerHTML = document.getElementById(self.widget_id).innerHTML + _thead;
        window[self.widget_id]["tables"][_table]["options"] = _options;
    } 

    dom_ready('ws',self.widget_id);
    
}


function create_tables(widget_id, entities)
{
    window[widget_id].ready = false;

    // Create the tables
    for (let _table in window[widget_id]["tables"]){ 
        if (!(_table.includes("entities"))){
            create_clear(_table, widget_id);
        }
    }

    // Iterate the namespaces for entities table

    jQuery.each(entities.state, function(namespace)
    {
        // now create the entities table
        if (window[widget_id]["namespace_list"].indexOf(namespace) >= 0){
            create_clear(namespace + "entities", widget_id);

            // if the option is set that we dont want to see it we hide the entitiestable
            if (!window[widget_id]["show_namespaces"]){
                document.getElementById(widget_id + namespace + "entities_table_id").style.visibility = "hidden"
            }
        }


        jQuery.each(entities.state[namespace], function(entity)
        {
            if (entities.state[namespace][entity] != null)
            {
                // if the entity is in the namespace we want to see we put it in the entities table
                if (window[widget_id]["namespace_list"].indexOf(namespace) >= 0){
                    if (device(entity) =="sensor"){
                        console.log(entity)
                    }
                    options = get_column_values(entities.state[namespace][entity], entity, namespace + "entities", widget_id);
                    window[widget_id]["tables"][namespace + "entities"]["values"].add(options);
                }

                if (namespace === "admin")
                {
                    // if the entity is in the namespace admin we put it in the chosen table
                    for (let _table in window[widget_id]["tables"]){
                        if (device(entity) == _table)
                        {
                            options = get_column_values(entities.state[namespace][entity], entity, _table, widget_id);
                            window[widget_id]["tables"][_table]["values"].add(options);
                        }
                    }
                }
            }
        });
        //console.log(widget_id + namespace + " completely run through")
    });
    
    //window[widget_id]["table_list"].forEach(_table => {
    //    if (window[widget_id]["table_list"].indexOf(_table) >= 0){
    //        window[widget_id][_table]["table"].sort('id');
    //    }
    //});

    for (let _table in window[widget_id]["tables"]){
        for ( let _column in window[widget_id]["tables"][_table]["columns"]){
            _orderlist[window[widget_id]["tables"][_table]["columns"][_column]["order"].toString()] = _column
        }
        for (var i=0; i<Object.keys(_orderlist).length; i++){
            _column = _orderlist[i.toString()]
           $(".tooltip." + _column).hover(open_tooltip, close_tooltip);
        }
    }

//    $(".tooltip.kwargs").hover(open_tooltip, close_tooltip);
//    $(".tooltip.attributes").hover(open_tooltip, close_tooltip);

    window[widget_id].ready = true;
    console.log(window[widget_id])
}

function update_admin(widget_id, data)
{

    if (window[widget_id].ready !== true)
    {
        return
    }

    // Process any updates

    var id;

    // Log Update

    //if (data.event_type === "__AD_LOG_EVENT")
    //{
    //    $("#" + data.data.log_type + "_div").prepend(data.data.formatted_message + "<br>")
    //}

    //console.log("STATE CHANGED ************************************************")
    //console.log(data)


    // Entity Update

    if (data.event_type === "state_changed")
    {
        namespace = data.namespace;
        entity = data.data.entity_id;

        if (window[widget_id]["namespace_list"].indexOf(namespace) < 0){
            return
        }
        if (!(device(entity) in window[widget_id]["tables"])){
            return
        }

        if (window[widget_id]["namespace_list"].indexOf(namespace) >= 0) {
            //console.log("changing " + widget_id + namespace + "." + entity) 
            options = get_column_values(data.data.new_state, entity, namespace + "entities", widget_id);
            item = window[widget_id]["tables"][namespace + "entities"]["values"].get("id", entity);
            item[0].values(options);
        }
        if (namespace === "admin")
        {
            for (let _table in window[widget_id]["tables"]){
                if (device(entity) == _table)
                {
                    options = get_column_values(data.data.new_state, entity, _table, widget_id);
                    //console.log(widget_id + _table + " table : " + entity)
                    //console.log(options)
                    item = window[widget_id]["tables"][_table]["values"].get("id", entity);
                    //console.log(item)
                    item[0].values(options);
                }
            }


            // Sensors

            //if (device(entity) === "sensor")
            //{
            //    $('#' + device(entity) + "_" + name(entity)).text(state)
            //}
        }
    }

    if (data.event_type === "__AD_ENTITY_ADDED")
    {
        namespace = data.namespace;
        entity = data.data.entity_id;

        // Add To Entities table
        if (window[widget_id]["namespace_list"].indexOf(namespace) >= 0)
        {
            options = get_column_values(data.data.state, entity, namespace + "entities", widget_id);
            window[widget_id]["tables"][namespace + "entities"]["values"].add(options);
            //window[widget_id]["tables"][namespace + "entities"]["values"].sort('id');
            //console.log("added " + widget_id + namespace + "." + entity) 
        }

        if (namespace === "admin")
        {
            for (let _table in window[widget_id]["tables"]){
                if (device(entity) === _table)
                {
                    options = get_column_values(data.data.state, entity, _table, widget_id);
                    //console.log(widget_id][_table][" table : " + name(entity))
                    window[widget_id]["tables"][_table]["values"].add(options);
                    //window[widget_id]["tables"][_table]["values"].sort('id')
                }
            }
        }
    }

    if (data.event_type === "__AD_ENTITY_REMOVED")
    {
        entity = data.data.entity_id;
        // Remove from entities
        if (window[widget_id]["namespace_list"].indexOf(namespace) >= 0){
            window[widget_id]["tables"][namespace + "entities"]["values"].remove("id", entity);
            //console.log("removed " + widget_id + namespace + "." + entity + " from " + namespace + "entities table")
        }
        if (namespace === "admin")
        {
            for (let _table in window[widget_id]["tables"]){
                if (device(entity) == _table)
                {
                    window[widget_id]["tables"][_table]["values"].remove("id", entity)
                }
            }
        }
    }
}

