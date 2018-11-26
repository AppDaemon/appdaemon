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
                document.getElementById(id).innerText = this.formatStr(data["updates"][id]);
            }
        }

        if ("schedule" in data)
        {
            // console.log(data["schedule"]);
            document.getElementById("active_scheduler_callbacks").innerHTML = this.get_schedule_table(data["schedule"])

        }

        if ("callbacks" in data)
        {
            // console.log(data["schedule"]);
            document.getElementById("active_state_callbacks").innerHTML = this.get_state_table(data["callbacks"])
            document.getElementById("active_event_callbacks").innerHTML = this.get_event_table(data["callbacks"])

        }

        if ("threads" in data)
        {
           document.getElementById("thread_table").innerHTML = this.get_thread_table(data["threads"])
        }
    }
}

function get_schedule_table(data)
{
    cb = 0;
    html = "";

    for (name in data)
    {
        for (id in data[name])
        {
            html += "<tr>";
            html += "<td>" + name + "</td>"
            html += "<td>" + data[name][id].timestamp + "</td>";
            if (data[name][id].repeat == true)
            {
                repeat = this.secondsToStr(data[name][id].kwargs["interval"])
            }
            else
            {
                repeat = "None"
            }
            html += "<td>" + repeat + "</td>";
            html += "<td>" + data[name][id].callback + "</td>";
            html += "<td>" + this.formatStr(data[name][id].pin_app) + "</td>";
            if (data[name][id].pin_thread == "-1")
            {
                thread = "None"
            }
            else
            {
                thread = data[name][id].pin_thread
            }
            html += "<td>" + thread + "</td>";
            if (data[name][id].kwargs.length !== 0)
            {
                kwargs = ""
                for (kwarg in data[name][id].kwargs)
                {
                    if (kwarg.substring(0,2) != "__" && kwarg != "interval")
                    {
                        kwargs += " " + kwarg + "='" + data[name][id].kwargs[kwarg] + "'"
                    }
                }
            }
            else
            {
                kwargs = "None"
            }
            html += "<td>" + kwargs + "</td>";
            html += "</tr>";
            cb++
        }
    }

    if (cb > 0)
    {
        result = "<table>";
        result += "<tr><th>App</th><th>Execution Time</th><th>Repeat</th><th>Callback</th><th>Pinned</th><th>Pinned Thread</th><th>Kwargs</th></tr>"
        result += html;
        result += "</table>"
    }
    else
    {
        result = "No active callbacks"
    }

    return result
}

function get_state_table(data)
{
    cb = 0;
    html = "";

    for (name in data)
    {
        for (id in data[name])
        {
            if (data[name][id].type == "state")
            {

                html += "<tr>";
                html += "<td>" + name + "</td>"
                html += "<td>" + data[name][id].entity + "</td>";
                html += "<td>" + data[name][id].function + "</td>";
                html += "<td>" + this.formatStr(data[name][id].pin_app) + "</td>";
                if (data[name][id].pin_thread == "-1")
                {
                    thread = "None"
                }
                else
                {
                    thread = data[name][id].pin_thread
                }
                html += "<td>" + thread + "</td>";

                if (data[name][id].kwargs.length !== 0)
                {
                    kwargs = ""
                    for (kwarg in data[name][id].kwargs)
                    {
                        if (kwarg.substring(0, 2) != "__")
                        {
                            kwargs += " " + kwarg + "='" + data[name][id].kwargs[kwarg] + "'"
                        }
                    }
                }
                else
                {
                    kwargs = "None"
                }
                html += "<td>" + kwargs + "</td>";
                html += "</tr>";
                cb++
            }
        }
    }
    if (cb > 0)
    {
        result = "<table>"
        result += "<tr><th>App</th><th>Entity</th><th>Function</th><th>Pinned</th><th>Pinned Thread</th><th>Kwargs</th></tr>"
        result += html
        result += "</table>"
    }
    else
    {
        result = "No active callbacks"
    }

    return result
}

function get_event_table(data)
{
    cb = 0;
    html = "";

    for (name in data)
    {
        for (id in data[name])
        {
            if (data[name][id].type == "event")
            {
                html += "<tr>";
                html += "<td>" + name + "</td>"
                html += "<td>" + data[name][id].event + "</td>";
                html += "<td>" + data[name][id].function + "</td>";
                html += "<td>" + this.formatStr(data[name][id].pin_app) + "</td>";
                if (data[name][id].pin_thread == "-1")
                {
                    thread = "None"
                }
                else
                {
                    thread = data[name][id].pin_thread
                }
                html += "<td>" + thread + "</td>";

                if (data[name][id].kwargs.length !== 0)
                {
                    kwargs = ""
                    for (kwarg in data[name][id].kwargs)
                    {
                        if (kwarg.substring(0, 2) != "__")
                        {
                            kwargs += " " + kwarg + "='" + data[name][id].kwargs[kwarg] + "'"
                        }
                    }
                }
                else
                {
                    kwargs = "None"
                }
                html += "<td>" + kwargs + "</td>";
                html += "</tr>";
                cb++
            }
        }
    }

    if (cb > 0)
    {
        result = "<table>"
        result += "<tr><th>App</th><th>Event Name</th><th>Function</th><th>Pinned</th><th>Pinned Thread</th><th>Kwargs</th></tr>"
        result += html
        result += "</table>"
    }
    else
    {
        result = "No active callbacks"
    }

       html += "<tr><th>App</th><th>Event Name</th><th>Function</th><th>Pinned</th><th>Pinned Thread</th><th>Kwargs</th></tr>"



    return result
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
        html += "<td id='" + thread + "_time_called'>" + this.formatStr(data[thread].time_called) + "</td>";
        html += "<td id='" + thread + "_is_alive'>" + this.formatStr(data[thread].is_alive) + "</td>";
        html += "<td id='" + thread + "_pinned_apps'>"
        for (app in data[thread].pinned_apps)
        {
            html += data[thread].pinned_apps[app] + " "
        }
        html += "</td>";
        html += "</tr>";
    }
    html += "</table>"

    return html
}

function formatStr(x)
{
    if (x === true)
    {
        return "True"
    }
    if (x === false)
    {
        return "False"
    }
    if (x === "1970-01-01 00:00:00")
    {
        return "Never"
    }
    return x
}

function secondsToStr (time) {

    function numberEnding (number) {
        return (number > 1 || number < 1) ? 's' : '';
    }

    var temp = time;
    var years = Math.floor(temp / 31536000);
    if (years) {
        return years + ' year' + numberEnding(years);
    }
    var days = Math.floor((temp %= 31536000) / 86400);
    if (days) {
        return days + ' day' + numberEnding(days);
    }
    var hours = Math.floor((temp %= 86400) / 3600);
    if (hours) {
        return hours + ' hour' + numberEnding(hours);
    }
    var minutes = Math.floor((temp %= 3600) / 60);
    if (minutes) {
        return minutes + ' minute' + numberEnding(minutes);
    }
    var seconds = temp % 60;
    return seconds + ' second' + numberEnding(seconds);

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