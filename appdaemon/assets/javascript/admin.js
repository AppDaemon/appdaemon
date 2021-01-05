function getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) === ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) === 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function dom_ready(transport)
{
    window.ready = false;

    // Open the default tabs

    $("#appdaemon_button")[0].click();
    $("#main_log_button")[0].click();
    $("#default_entity_button")[0].click();

    window.adminstream = new AdminStream(transport, location.protocol, document.domain, location.port);
}

function create_tables(msg)
{
    entities = msg.data;
    window.ready = false;

    // Create Apps Table

    id = "app-table";
    options = {
        valueNames:
            [
                'name',
                'state',
                'instancecallbacks',
                'totalcallbacks',
                'arguments'
            ],
        item: '<tr><td class="name"></td><td class="state"></td><td class="instancecallbacks"></td><td class="totalcallbacks"></td><td class="tooltip arguments"></td></tr>'
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

    // Create scheduler callbacks table

    id = "scheduler-callback-table";
    options = {
        valueNames:
            [
                'id',
                'app',
                'execution_time',
                'repeat',
                'function',
                'fired',
                'executed',
                'pinned',
                'pinned_thread',
                'kwargs'
            ],
        item: '<tr><td class="app"></td><td class="execution_time"></td><td class="repeat"></td><td class="function"></td><td class="fired"></td></td><td class="executed"></td></td><td class="pinned"></td><td class="pinned_thread"></td><td class="tooltip kwargs"></td></tr>'
    };

    create_clear("scheduler_callback_table", id, options);

    // Create state callbacks table

    id = "state-callback-table";
    options = {
        valueNames:
            [
                'id',
                'app',
                'last_changed',
                'entity',
                'function',
                'fired',
                'executed',
                'pinned',
                'pinned_thread',
                'kwargs'
            ],
        item: '<tr></td><td class="app"></td><td class="last_changed"></td><td class="entity"></td><td class="function"><td class="fired"></td></td><td class="executed"></td><td class="pinned"></td><td class="pinned_thread"></td><td class="tooltip kwargs"></td></tr>'
    };

    create_clear("state_callback_table", id, options);

    // Create event callbacks table

    id = "event-callback-table";
    options = {
        valueNames:
            [
                'id',
                'app',
                'last_changed',
                'event_name',
                'function',
                'fired',
                'executed',
                'pinned',
                'pinned_thread',
                'kwargs'
            ],
        item: '<tr></td><td class="app"><td class="last_changed"></td><td class="event_name"></td><td class="function"></td><td class="fired"></td></td><td class="executed"><td class="pinned"></td><td class="pinned_thread"></td><td class="tooltip kwargs"></td></tr>'
    };

    create_clear("event_callback_table", id, options);

    // Iterate the namespaces for entities table

    jQuery.each(entities, function(namespace)
    {
        // Entities
        id = namespace + "-entities-table";
        options = {
            valueNames:
                [
                    'name',
                    'state',
                    'last_changed',
                    'attributes'
                ],
            item: '<tr><td class="name"></td><td class="state"><td class="last_changed"></td><td class="tooltip attributes"></td></tr>'
        };

        create_clear(namespace + "_table", id, options);

        // Now Iterate the Entities

        entity_list = [];

        jQuery.each(entities[namespace], function(entity)
        {
            if (entities[namespace][entity] != null)
            {
                state = entities[namespace][entity].state;
                last_changed = entities[namespace][entity].last_changed;
                attributes = entities[namespace][entity].attributes;

                entity_list.push({
                    name: entity,
                    state: state, last_changed: last_changed, attributes: JSON.stringify(attributes)
                });

                if (namespace === "admin")
                {

                    // Apps

                    if (device(entity) === "app")
                    {
                        instancecallbacks = attributes.instancecallbacks;
                        totalcallbacks = attributes.totalcallbacks;
                        window.app_table.add({
                            name: name(entity),
                            state: state,
                            instancecallbacks: instancecallbacks,
                            totalcallbacks: totalcallbacks,
                            arguments: JSON.stringify(attributes.args),
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

                    // Scheduler Callbacks

                    if (device(entity) === "scheduler_callback")
                    {
                        window.scheduler_callback_table.add({
                            id: name(entity),
                            app: attributes.app,
                            execution_time: attributes.execution_time,
                            repeat: attributes.repeat,
                            function: attributes.function,
                            fired: attributes.fired,
                            executed: attributes.executed,
                            pinned: attributes.pinned,
                            pinned_thread: attributes.pinned_thread,
                            kwargs: JSON.stringify(attributes.kwargs)
                        });
                    }

                    // State Callbacks

                    if (device(entity) === "state_callback")
                    {
                        window.state_callback_table.add({
                            id: name(entity),
                            app: attributes.app,
                            last_changed: last_changed,
                            entity: attributes.listened_entity,
                            function: attributes.function,
                            fired: attributes.fired,
                            executed: attributes.executed,
                            pinned: attributes.pinned,
                            pinned_thread: attributes.pinned_thread,
                            kwargs: JSON.stringify(attributes.kwargs)
                        });
                    }

                    // Event Callbacks

                    if (device(entity) === "event_callback")
                    {
                        window.event_callback_table.add({
                            id: name(entity),
                            app: attributes.app,
                            last_changed: last_changed,
                            event_name: attributes.event_name,
                            function: attributes.function,
                            fired: attributes.fired,
                            executed: attributes.executed,
                            pinned: attributes.pinned,
                            pinned_thread: attributes.pinned_thread,
                            kwargs: JSON.stringify(attributes.kwargs)
                        });
                    }

                    // Sensors

                    if (device(entity) === "sensor")
                    {
                        $('#' + device(entity) + "_" + name(entity)).text(state)
                    }
                }
            }
        });

        // Add to the entities tab

        window[namespace + "_table"].add(entity_list);
        window[namespace + "_table"].sort('name')
    });

    window.app_table.sort('name');
    window.thread_table.sort('id');
    window.scheduler_callback_table.sort('app');
    window.state_callback_table.sort('app');
    window.event_callback_table.sort('app');

    $(".tooltip.arguments").hover(open_tooltip, close_tooltip);
    $(".tooltip.kwargs").hover(open_tooltip, close_tooltip);
    $(".tooltip.attributes").hover(open_tooltip, close_tooltip);

    window.ready = true;

}

function open_tooltip(e)
{

    tooltip = $("#tooltiptext");
    text = JSON.stringify(JSON.parse($(this).text()), null, 2);
    tooltip.text(text);
    width = tooltip.outerWidth();
    height = tooltip.outerHeight();
    x = e.pageX;
    y = e.pageY;

    remainder = $(window).height() + $(window).scrollTop() - y - height;
    if (remainder < 5)
    {
        tooltip.css("top", e.pageY - height);
    }
    else
    {
        tooltip.css("top", e.pageY);
    }


    tooltip.css("left", e.pageX - width - 10);
    tooltip.css("visibility", "visible")
}

function close_tooltip(e)
{
    $("#tooltiptext").css("visibility", "hidden")
}

function update_admin(msg)
{

    data = msg.data;

    if (window.ready !== true)
    {
        return
    }

    // Process any updates

    //console.log(data);

    var id;

    // Log Update

    if (data.event_type === "__AD_LOG_EVENT")
    {
        $("#" + data.data.log_type + "_div").prepend(data.data.formatted_message + "<br>")
    }

    // Entity Update

    if (data.event_type === "state_changed") {
        namespace = data.namespace;
        entity = data.data.entity_id;
        last_changed = data.data.new_state.last_changed;
        state = data.data.new_state.state;
        attributes = data.data.new_state.attributes;
        item = window[namespace + "_table"].get("name", entity);
        if (item.length > 0)
        {

            // TODO: This breaks if a new entity shows up

            item[0].values({
                name: entity,
                state: state,
                last_changed: last_changed,
                attributes: JSON.stringify(attributes)
            });
        }
        if (namespace === "admin")
        {
            if (device(entity) === "app")
            {
                item = window.app_table.get("name", name(entity));
                if (item.length > 0)
                {
                    item[0].values({
                    name: name(entity),
                    state: state,
                    instancecallbacks: attributes.instancecallbacks,
                    totalcallbacks: attributes.totalcallbacks,
                    arguments: JSON.stringify(attributes.args)
                    });
                }
            }
            if (device(entity) === "thread")
            {
                item = window.thread_table.get("id", name(entity));
                if (item.length > 0)
                {
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

            if (device(entity) === "scheduler_callback")
            {
                item = window.scheduler_callback_table.get("id", name(entity));
                if (item.length > 0)
                {
                    item[0].values({
                        id: name(entity),
                        app: attributes.app,
                        execution_time: attributes.execution_time,
                        repeat: attributes.repeat,
                        function: attributes.function,
                        fired: attributes.fired,
                        executed: attributes.executed,
                        pinned: attributes.pinned,
                        pinned_thread: attributes.pinned_thread,
                        kwargs: JSON.stringify(attributes.kwargs)
                    })
                }
            }


            if (device(entity) === "state_callback")
            {
                item = window.state_callback_table.get("id", name(entity));
                if (item.length > 0)
                {
                    item[0].values({
                        id: name(entity),
                        app: attributes.app,
                        last_changed: last_changed,
                        entity: attributes.listened_entity,
                        function: attributes.function,
                        fired: attributes.fired,
                        executed: attributes.executed,
                        pinned: attributes.pinned,
                        pinned_thread: attributes.pinned_thread,
                        kwargs: JSON.stringify(attributes.kwargs)
                    });
                }
                window.state_callback_table.sort('app')
            }

            if (device(entity) === "event_callback")
            {
                item = window.event_callback_table.get("id", name(entity));
                if (item.length > 0)
                {
                    item[0].values({
                        id: name(entity),
                        app: attributes.app,
                        last_changed: last_changed,
                        event_name: attributes.event_name,
                        function: attributes.function,
                        fired: attributes.fired,
                        executed: attributes.executed,
                        pinned: attributes.pinned,
                        pinned_thread: attributes.pinned_thread,
                        kwargs: JSON.stringify(attributes.kwargs)
                    });
                }
                window.event_callback_table.sort('app')
            }

            // Sensors

            if (device(entity) === "sensor")
            {
                $('#' + device(entity) + "_" + name(entity)).text(state)
            }
        }
    }

    if (data.event_type === "__AD_ENTITY_ADDED")
    {
        namespace = data.namespace;
        entity = data.data.entity_id;
        last_changed = data.data.state.last_changed;
        attributes = data.data.state.attributes;
        state = data.data.state.state;

        // Add To Entities
        window[namespace + "_table"].add({
            name: entity,
            last_changed: last_changed,
            state: state,
            attributes: attributes
        });
        window[namespace + "_table"].sort('name');

        if (namespace === "admin")
        {
            if (device(entity) === "app")
            {
                window.app_table.add({
                    name: name(entity),
                    state: state,
                    instancecallbacks: instancecallbacks,
                    totalcallbacks: totalcallbacks,
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

            if (device(entity) === "scheduler_callback")
            {
                window.scheduler_callback_table.add({
                    id: name(entity),
                    app: attributes.app,
                    execution_time: attributes.execution_time,
                    repeat: attributes.repeat,
                    function: attributes.function,
                    fired: attributes.fired,
                    executed: attributes.executed,
                    pinned: attributes.pinned,
                    pinned_thread: attributes.pinned_thread,
                    kwargs: JSON.stringify(attributes.kwargs)
                });
                window.scheduler_callback_table.sort('app')
            }


            if (device(entity) === "state_callback")
            {
                window.state_callback_table.add({
                    id: name(entity),
                    last_changed: last_changed,
                    app: attributes.app,
                    entity: attributes.listened_entity,
                    function: attributes.function,
                    fired: attributes.fired,
                    executed: attributes.executed,
                    pinned: attributes.pinned,
                    pinned_thread: attributes.pinned_thread,
                    kwargs: JSON.stringify(attributes.kwargs)
                });
                window.state_callback_table.sort('app')
            }

            if (device(entity) === "event_callback")
            {
                window.event_callback_table.add({
                    id: name(entity),
                    app: attributes.app,
                    last_changed: last_changed,
                    event_name: attributes.event_name,
                    function: attributes.function,
                    fired: attributes.fired,
                    executed: attributes.executed,
                    pinned: attributes.pinned,
                    pinned_thread: attributes.pinned_thread,
                    kwargs: JSON.stringify(attributes.kwargs)
                });
                window.event_callback_table.sort('app')
            }
        }
    }

    if (data.event_type === "__AD_ENTITY_REMOVED")
    {
        entity = data.data.entity_id;

        // Remove from entities
        window[namespace + "_table"].remove("name", entity);

        if (namespace === "admin")
        {
            if (device(entity) === "app")
            {
                window.app_table.remove("name", name(entity))
            }
            if (device(entity) === "thread")
            {
                window.thread_table.remove("id", name(entity))
            }
            if (device(entity) === "scheduler_callback")
            {
                window.scheduler_callback_table.remove("id", name(entity))
            }
            if (device(entity) === "state_callback")
            {
                window.state_callback_table.remove("id", name(entity))
            }
            if (device(entity) === "event_callback")
            {
                window.event_callback_table.remove("id", name(entity))
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

var AdminStream = function(transport, protocol, domain, port) {

    var self = this;

    this.on_connect = function(data) {

        // Grab state

        self.stream.get_state('*', '*', create_tables);

        // subscribe to all events

        self.stream.listen_event('*', '*', update_admin);

        // Subscribe to all state changes

        self.stream.listen_state('*', '*', update_admin)

    };

    this.on_message = function (data) {
        // Do Nothing
    };

    this.on_disconnect = function () {
        // do nothing
    };

    this.stream = new Stream(transport, protocol, domain, port, "Admin Client", this.on_connect, this.on_message, this.on_disconnect);
};

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
