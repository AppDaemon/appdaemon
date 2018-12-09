function dom_ready(transport)
{
    // Open the default tabs

    document.getElementById("appdaemon").click();
    document.getElementById("main_log_button").click();
    document.getElementById("default_entity_button").click();

    // Start listening for Events

    var stream_url;
    if (transport === "ws")
    {
        if (location.protocol === 'https:')
        {
            wsprot = "wss:"
        }
        else
        {
            wsprot = "ws:"
        }
        stream_url = wsprot + '//' + location.host + '/stream'
    }
    else
    {
        stream_url = 'http://' + document.domain + ':' + location.port + "/stream"
    }

    admin_stream(stream_url, transport);
}

function create_tables(entities)
{
    // Create Apps Table

    id = "app-table";
    options = {
        valueNames:
            [
                'name',
                'state',
                'callbacks',
                'arguments'
            ],
        item: '<tr><td class="name"></td><td class="state"></td><td class="callbacks"></td><td class="arguments"></td></tr>'
    };

    create_clear("app_table", id, options);

    // Create Threads Table

    id = "thread-table";
    options = {
        valueNames:
            [
                'id',
                'q_size',
                'callback',
                'time_called',
                'alive',
                'pinned_apps'
            ],
        item: '<tr><td class="id"></td><td class="q_size"></td><td class="callback"></td><td class="time_called"></td><td class="alive"></td><td class="pinned_apps"></td></tr>'
    };

    create_clear("thread_table", id, options);

    // Iterate the namespaces for entities table

    jQuery.each(entities.state, function(namespace)
    {
        // Entities
        id = namespace + "-entities-table";
        options = {
            valueNames:
                [
                    'name',
                    'state',
                    'attributes'
                ],
            item: '<tr><td class="name"></td><td class="state"></td><td class="attributes"></td></tr>'
        };

        create_clear(namespace + "_table", id, options);

        // Now Iterate the Entities

        jQuery.each(entities.state[namespace], function(entity)
        {
            state = entities.state[namespace][entity].state;
            attributes = entities.state[namespace][entity].attributes;
            window[namespace + "_table"].add({
                name: entity,
                state: state, attributes: JSON.stringify(attributes)
            });

            if (namespace === "admin")
            {

                // Apps

                if (device(entity) === "app")
                {
                    callbacks = attributes.callbacks;
                    window.app_table.add({
                        name: entity,
                        state: state,
                        arguments: JSON.stringify(attributes.args),
                        callbacks: callbacks
                    });
                }

                // Threads

                if (device(entity) === "thread")
                {
                    window.thread_table.add({
                        id: name(entity),
                        q_size: attributes.q,
                        arguments: JSON.stringify(attributes.args),
                        callback: state,
                        time_called: attributes.time_called,
                        alive: attributes.is_alive,
                        pinned_apps: JSON.stringify(attributes.pinned_apps)
                    });
                }

                // Sensors

                if (device(entity) === "sensor")
                {
                    $('#' + device(entity) + "_" + name(entity)).text(state)
                }
            }
        });
        window[namespace + "_table"].sort('name')
    });

    window.app_table.sort('name');
    window.thread_table.sort('id')
}

function update_admin(data)
{
    // Process any updates
    //console.log(data);
    var id;

    // Log Update

    if (data.event_type === "__AD_LOG_EVENT")
    {
        $("#" + data.data.log_type + "_div").prepend(data.data.formatted_message + "<br>")
    }

    // Entity Update

    if (data.event_type === "state_changed")
    {
        namespace = data.namespace;
        entity = data.data.entity_id;
        state = data.data.new_state.state;
        attributes = data.data.new_state.attributes;
        item = window[namespace + "_table"].get("name", entity);
        item[0].values({name: entity, state: state, attributes: JSON.stringify(attributes)});
        if (namespace === "admin")
        {
            if (device(entity) === "app")
            {
                item = window.app_table.get("name", entity);
                item[0].values({
                    name: entity,
                    state: state,
                    callbacks: attributes.callbacks,
                    args: JSON.stringify(attributes.args)
                });
            }
            if (device(entity) === "thread")
            {
                item = window.thread_table.get("id", name(entity));
                item[0].values({
                    id: name(entity),
                    q_size: attributes.q,
                    callback: state,
                    time_called: attributes.time_called,
                    alive: attributes.is_alive,
                    pinned_apps: JSON.stringify(attributes.pinned_apps)
                })
            }
        }

        // Sensors

        if (device(entity) === "sensor")
        {
            $('#' + device(entity) + "_" + name(entity)).text(state)
        }

    }

    if (data.event_type === "__AD_ENTITY_ADDED")
    {
        namespace = data.namespace
        entity = data.data.entity_id;
        attributes = JSON.stringify(data.data.state.attributes);
        state = data.data.state.state;

        // Add To Entities
        window[namespace + "_table"].add({
            name: entity,
            state: state,
            attributes: attributes
        });
        window[namespace + "_table"].sort('name');

        if (namespace === "admin")
        {
            if (device(entity) === "app")
            {
                window.app_table.add({
                    name: entity,
                    state: state,
                    callbacks: attributes.callbacks,
                    args: JSON.stringify(attributes.args)
                });
                window.app_table.sort('name')
            }
            if (device(entity) === "thread")
            {
                window.thread_table.add({
                    id: name(entity),
                    q_size: attributes.q,
                    callback: state,
                    time_called: attributes.time_called,
                    alive: attributes.is_alive,
                    pinned_apps: JSON.stringify(attributes.pinned_apps)
                });
                window.thread_table.sort('name')
            }
        }
    }

    if (data.event_type === "__AD_ENTITY_REMOVED")
    {
        entity = data.data.entity_id;

        // Remove from entities
        window[namespace + "_table"].remove("name", data.data.entity);

        if (namespace === "admin")
        {
            if (device(entity) === "app")
            {
                window.app_table.remove("name", entity)
            }
            if (device(entity) === "thread")
            {
                window.thread_table.remove("id", name(entity))
            }
        }
    }
}

function create_clear(table, id, options)
{
    if (table in window)
    {
        window[table].clear();
        window[table].update();
    }
    else
    {
        window[table] = new List(id, options);
    }
}

function name(entity)
{
    return entity.split(".")[1]
}

function device(entity)
{
    return entity.split(".")[0]
}

function admin_stream(stream, transport)
{

    if (transport === "ws")
    {
        var webSocket = new ReconnectingWebSocket(stream);

        webSocket.onopen = function (event) {
            webSocket.send("Admin Browser");
            get_state(create_tables);
        };

        webSocket.onmessage = function (event) {
            var data = JSON.parse(event.data);
            update_admin(data)
        };

        webSocket.onclose = function (event) {
            //window.alert("Server closed connection")
            // window.location.reload(false);
        };

        webSocket.onerror = function (event) {
            //window.alert("Error occured")
            //window.location.reload(true);
        };
    }
    else
    {
        var iosocket = io.connect(stream);

        iosocket.on("connect", function () {
            iosocket.emit("up", "Admin Browser");
            get_state(create_tables);
        });

        iosocket.on("down", function (msg) {
            var data = JSON.parse(msg);
            update_admin(data)
        });

    }
}

function openTab(evt, tabname, tabgroup) {
    // Declare all variables
    var i, tabcontent, tablinks;

    // Get all elements with class="tabcontent" and hide them
    $('.' + tabgroup + 'content').each(function(index, elem){elem.style.display = "none"});
    // Get all elements with class="tablinks" and remove the class "active"
    $('.' + tabgroup + 'links').each(function(index, elem){elem.className = elem.className.replace(" active", "")});
    // Show the current tab, and add an "active" class to the button that opened the tab
    $('#' + tabname).css("display", "block");
    evt.currentTarget.className += " active";
}

function logout()
{
    document.cookie = "adcreds" + '=;expires=Thu, 01 Jan 1970 00:00:01 GMT;';
    window.location.href = "/";
}

function authorize(url)
{
    window.location.href = url;
}

function deauthorize()
{
    window.location.href = "/";
}

function get_entity(namespace, entity, f)
{
    var state_url = "/api/state/" + namespace + "/" + entity;
    $.ajax
    ({
        url: state_url,
        type: 'GET',
        success: function(data)
                {
                    f(data);
                },
        error: function(data)
                {
                    alert("Error getting state, check Java Console for details")
                }

    });
}

function get_namespaces(f)
{
    var state_url = "/api/state/";
    $.ajax
    ({
        url: state_url,
        type: 'GET',
        success: function(data)
                {
                    f(data);
                },
        error: function(data)
                {
                    alert("Error getting state, check Java Console for details")
                }

    });
}

function get_namespace(namespace, f)
{
    var state_url = "/api/state/" + namespace;
    $.ajax
    ({
        url: state_url,
        type: 'GET',
        success: function(data)
                {
                    f(namespace, data);
                },
        error: function(data)
                {
                    alert("Error getting state, check Java Console for details")
                }

    });
}

function get_state(f)
{
    var state_url = "/api/state";
    $.ajax
    ({
        url: state_url,
        type: 'GET',
        success: function(data)
                {
                    f(data);
                },
        error: function(data)
                {
                    alert("Error getting state, check Java Console for details")
                }

    });
}
