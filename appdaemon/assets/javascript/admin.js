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
        // console.log(data);
        var id;
        if ("updates" in data)
        {
            for (id in data["updates"])
            {
                document.getElementById(id).innerText = data["updates"][id];
            }
        }
        if ("schedule" in data && data["schedule"].length !== 0)
        {
            // console.log(data["schedule"]);
            document.getElementById("active_scheduler_callbacks").innerHTML = this.get_schedule_table(data["schedule"])

        }

    }
}

function get_schedule_table(data)
{
    html = "<tr><th>App</th><th>Base Time</th><th>Offset</th><th>Repeat</th><th>Callback</th><th>Kwargs</th></tr>"

    for (name in data)
    {
        for (id in data[name])
        {
            html += "<tr>";
            html += "<td>" + name + "</td>"
            html += "<td>" + data[name][id].basetime + "</td>";
            html += "<td>" + data[name][id].offset + "</td>";
            html += "<td>" + data[name][id].repeat + "</td>";
            html += "<td>" + data[name][id].callback + "</td>";
            if (data[name][id].kwargs.length !== 0)
            {
                kwargs = ""
                for (kwarg in data[name][id].kwargs)
                {
                    kwargs += " " + kwarg + "=" + data[name][id].kwargs[kwarg]
                }
            }
            else
            {
                kwargs = "None"
            }
            html += "<td>" + kwargs + "</td>";
            html += "</tr>";
        }
    }

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