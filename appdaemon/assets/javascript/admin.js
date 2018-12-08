function dom_ready(transport)
{
    // Open the default tabs

    document.getElementById("appdaemon").click();
    document.getElementById("main_log_button").click();
    document.getElementById("default_entity_button").click();


    // Entities

    get_namespaces(create_entity_tables);

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

function create_entity_table(namespace, entities)
{
    id = namespace + "-entities-table"
    window.namespace[namespace] = new List(id);
    entities.forEach(function(entity)
    {
        console.log(entity)
        window.namespace[namespace].add({"name": entity.entity_id})
    });
}

function create_entity_tables(namespaces)
{
    namespaces.state.forEach(function(ns)
    {
        get_namespace(ns, create_entity_table)
    });
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
    var state_url = "/api/state" + namespace;
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

function admin_stream(stream, transport)
{

    if (transport === "ws")
    {
        var webSocket = new ReconnectingWebSocket(stream);

        webSocket.onopen = function (event) {
            webSocket.send("Admin Browser");
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
        });

        iosocket.on("down", function (msg) {
            var data = JSON.parse(msg);
            update_admin(data)
        });

    }

    this.update_admin = function (data)
    {
        // Process any updates
        //console.log(data);
        var id;

        if (data.event_type === "__AD_LOG_EVENT")
        {
            $("#" + data.data.log_type + "_div").prepend(data.data.formatted_message + "<br>")
        }

        // Old stuff


        if ("updates" in data)
        {
            for (id in data["updates"])
            {
                $('#' + id).text(data["updates"][id]);
            }
        }

        if ("schedule" in data)
        {
            $('#active_scheduler_callbacks').html(get_schedule_table(data["schedule"]))
        }

        if ("state_callbacks" in data)
        {
            // console.log(data["schedule"]);
            $('#active_state_callbacks').html(get_state_table(data["state_callbacks"]))
        }

        if ("event_callbacks" in data)
        {
            // console.log(data["schedule"]);
            $('#active_event_callbacks').html(get_event_table(data["event_callbacks"]))
        }

        if ("threads" in data)
        {
           $('#thread_table').html(get_thread_table(data["threads"]))
        }

    }
}

function get_schedule_table(data)
{
    if (Object.keys(data).length === 0)
    {
        html = "No active callbacks";
    }
    else
    {
        html = "<table>";
        html += "<tr><th>App</th><th>Execution Time</th><th>Repeat</th><th>Callback</th><th>Pinned</th><th>Pinned Thread</th><th>Kwargs</th></tr>"

        for (name in data)
        {
            for (id in data[name])
            {
                html += "<tr>";
                html += "<td>" + name + "</td>"
                html += "<td>" + data[name][id].timestamp + "</td>";
                html += "<td>" + data[name][id].interval + "</td>";
                html += "<td>" + data[name][id].callback + "</td>";
                html += "<td>" + data[name][id].pin_app + "</td>";
                html += "<td>" + data[name][id].pin_thread + "</td>";
                html += "<td>" + data[name][id].kwargs + "</td>";
                html += "</tr>";
            }
        }

        html += "</table>"
    }

    return html
}

function get_state_table(data)
{
    if (Object.keys(data).length === 0)
    {
        html = "No active callbacks";
    }
    else
    {

        html = "<table>"
        html += "<tr><th>App</th><th>Entity</th><th>Function</th><th>Pinned</th><th>Pinned Thread</th><th>Kwargs</th></tr>"

        for (name in data)
        {
            for (id in data[name])
            {

                html += "<tr>";
                html += "<td>" + name + "</td>";
                html += "<td>" + data[name][id].entity + "</td>";
                html += "<td>" + data[name][id].function + "</td>";
                html += "<td>" + data[name][id].pin_app + "</td>";
                html += "<td>" + data[name][id].pin_thread + "</td>";
                html += "<td>" + data[name][id].kwargs + "</td>";
                html += "</tr>";
            }
        }
    }

    html += "</table>";

    return html
}

function get_event_table(data)
{
    if (Object.keys(data).length === 0)
    {
        html = "No active callbacks";
    }
    else
    {
        html = "<table>";
        html += "<tr><th>App</th><th>Event Name</th><th>Function</th><th>Pinned</th><th>Pinned Thread</th><th>Kwargs</th></tr>"
        for (name in data)
        {
            for (id in data[name])
            {
                html += "<tr>";
                html += "<td>" + name + "</td>"
                html += "<td>" + data[name][id].event + "</td>";
                html += "<td>" + data[name][id].function + "</td>";
                html += "<td>" + data[name][id].pin_app + "</td>";
                html += "<td>" +  data[name][id].pin_thread + "</td>"
                html += "<td>" +  data[name][id].kwargs + "</td>"
                html += "</tr>";
            }
        }
    }

    html += "</table>";

    return html
}

function get_thread_table(data)
{
    html = "<table>"
    html += "<tr><th>ID</th><th>Queue Size</th><th>Callback</th><th>Time Called</th><th>Alive</th><th>Pinned Apps</th></tr>"
    for (thread in data)
    {
        html += "<tr>";
        html += "<td>" + thread + "</td>";
        html += "<td id='" + thread + "_qsize'>" + data[thread].qsize + "</td>";
        html += "<td id='" + thread + "_callback'>" + data[thread].callback + "</td>";
        html += "<td id='" + thread + "_time_called'>" + data[thread].time_called + "</td>";
        html += "<td id='" + thread + "_is_alive'>" + data[thread].is_alive + "</td>";
        html += "<td id='" + thread + "_pinned_apps'>" + data[thread].pinned_apps + "</td>";
        html += "</tr>";
    }
    html += "</table>"

    return html
}

function openTab(evt, tabname, tabgroup) {
    // Declare all variables
    var i, tabcontent, tablinks;

    // Get all elements with class="tabcontent" and hide them
    $('.' + tabgroup + 'content').each(function(index, elem){elem.style.display = "none"})
    // Get all elements with class="tablinks" and remove the class "active"
    $('.' + tabgroup + 'links').each(function(index, elem){elem.className = elem.className.replace(" active", "")})
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