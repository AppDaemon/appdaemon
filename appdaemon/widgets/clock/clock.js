function clock(widget_id, url, parameters)
{
    // Store Args
    this.widget_id = widget_id;
    this.parameters = parameters;
    
    // Create and initialize bindings
    this.ViewModel = 
    {
        date: ko.observable(),
        time: ko.observable()
    };
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id))

    updateTime(this.ViewModel)
    
    // Setup Override Styles
    
    if ("background_color" in parameters)
    {
        $('#' + widget_id).css("background-color", parameters["background_color"])
    }
    
    if ("text_color" in parameters)
    {
        $('#' + widget_id + ' > h2').css("color", parameters["text_color"])
    }
    
    if ("text_size" in parameters)
    {
        $('#' + widget_id + ' > h2').css("font-size", parameters["text_size"])
    }
    
    if ("title_color" in parameters)
    {
        $('#' + widget_id + ' > h1').css("color", parameters["title_color"])
    }
    
    if ("title_size" in parameters)
    {
        $('#' + widget_id + ' > h1').css("font-size", parameters["title_size"])
    }
    
    setInterval(updateTime, 500, this.ViewModel);

    function updateTime(view) 
    {
        var today = new Date();
        h = today.getHours();
        m = today.getMinutes();
        m = formatTime(m);
        view.date(today.toLocaleDateString());
        view.time(formatHours(h) + ":" + m + " " + formatAmPm(h));
    }

    function formatTime(i)
    {
        if (i < 10 )
        {
            return "0" + i;
        }
        else
        {
            return i;
        }
    }

    function formatAmPm(h)
    {
        if (h >= 12)
        {
            return "PM";
        }
        else
        {
            return "AM";
        }
    }

    function formatHours(h)
    {
        if (h > 12)
        {
            return h - 12;
        }
        else if (h == 0)
        {
            return 0;
        }
        else
        {
            return h;
        }
    }
}