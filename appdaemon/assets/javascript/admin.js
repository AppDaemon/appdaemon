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
        if ("updates" in data)
        {
            for (id in data["updates"])
            {
                document.getElementById(id).innerText = (data["updates"][id]);
            }
        }

        if ("schedule" in data)
        {
            // console.log(data["schedule"]);
            document.getElementById("active_scheduler_callbacks").innerHTML = this.get_schedule_table(data["schedule"])

        }

        if ("state_callbacks" in data)
        {
            // console.log(data["schedule"]);
            document.getElementById("active_state_callbacks").innerHTML = this.get_state_table(data["state_callbacks"])
        }

        if ("event_callbacks" in data)
        {
            // console.log(data["schedule"]);
            document.getElementById("active_event_callbacks").innerHTML = this.get_event_table(data["event_callbacks"])
        }

        if ("threads" in data)
        {
           document.getElementById("thread_table").innerHTML = this.get_thread_table(data["threads"])
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
                html += "<td>" + name + "</td>"
                html += "<td>" + data[name][id].entity + "</td>";
                html += "<td>" + data[name][id].function + "</td>";
                html += "<td>" + data[name][id].pin_app + "</td>";
                html += "<td>" + data[name][id].pin_thread + "</td>";
                html += "<td>" + data[name][id].kwargs + "</td>";
                html += "</tr>";
            }
        }
    }

    html += "</table>"

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
        html = "<table>"
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

    html += "</table>"

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
        html += "<td id='" + thread + "_is_pinned_apps'>" + data[thread].pinned_apps + "</td>";
        html += "</tr>";
    }
    html += "</table>"

    return html
}

function openTab(evt, tabname) {
    // Declare all variables
    var i, tabcontent, tablinks;

    // Get all elements with class="tabcontent" and hide them
    tabcontent = document.getElementsByClassName("tabcontent");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }

    // Get all elements with class="tablinks" and remove the class "active"
    tablinks = document.getElementsByClassName("tablinks");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }

    // Show the current tab, and add an "active" class to the button that opened the tab
    document.getElementById(tabname).style.display = "block";
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