function ha_status(stream, dash, widgets)
{

    var webSocket = new ReconnectingWebSocket(stream);
            
    webSocket.onopen = function (event) 
    {
        webSocket.send(dash);
    }

    webSocket.onmessage = function (event) 
    {
        Object.keys(widgets).forEach(function (key)
        {
            if ("on_ha_data" in widgets[key])
            {
                widgets[key].on_ha_data(JSON.parse(event.data));
            }
        })
    }
    webSocket.onclose = function (event)
    {
        //window.alert("Server closed connection")
       // window.location.reload(false); 
    }

    webSocket.onerror = function (event)
    {
        //window.alert("Error occured")
        //window.location.reload(true);         
    }
}

function round(value, exp) 
{

  if (typeof exp === 'undefined' || +exp === 0)
    return Math.round(value);

  value = +value;
  exp = +exp;

  if (isNaN(value) || !(typeof exp === 'number' && exp % 1 === 0))
    return NaN;

  // Shift
  value = value.toString().split('e');
  value = Math.round(+(value[0] + 'e' + (value[1] ? (+value[1] + exp) : exp)));

  // Shift back
  value = value.toString().split('e');
  return +(value[0] + 'e' + (value[1] ? (+value[1] - exp) : -exp));
}