function javascript(widget_id, url, skin, parameters)
{
    // Store Args
    this.widget_id = widget_id
    this.parameters = parameters
    this.skin = skin
        
    // Create and initialize bindings
    this.ViewModel = 
    {
        title: ko.observable(parameters.title),
        title2: ko.observable(parameters.title2),
        icon: ko.observable(),
        widget_style: ko.observable(),
        title_style: ko.observable(),
        title2_style: ko.observable(),
        icon_style: ko.observable()
    };
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id))

    // Setup Override Styles

    if ("widget_style" in parameters)
    {
        this.ViewModel.widget_style(parameters.widget_style)
    }    

    if ("title_style" in parameters)
    {
        this.ViewModel.title_style(parameters.title_style)
    }    

    if ("title2_style" in parameters)
    {
        this.ViewModel.title2_style(parameters.title2_style)
    }    

    if ("icon_active_style" in parameters)
    {
        this.icon_active_style = parameters.icon_active_style
    }
    else
    {
        this.icon_active_style = "color: white"
    }
    
    if ("icon_inactive_style" in parameters)
    {
        this.icon_inactive_style = parameters.icon_inactive_style
    }
    else
    {
        this.icon_inactive_style = "color: white"
    }

    if ("icon_inactive" in parameters)
    {
        this.icon_inactive = parameters.icon_inactive
    }
    else
    {
        this.icon_inactive = "fa-gear"
    }
    
    if ("icon_active" in parameters)
    {
        this.icon_active = parameters.icon_active
    }
    else
    {
        this.icon_active = "fa-spinner fa-spin"
    }
    
    this.ViewModel.icon(this.icon_inactive.split("-")[0] + ' ' + this.icon_inactive)
    this.ViewModel.icon_style(this.icon_inactive_style)
    
    // Do some setup
    
    if ("command" in parameters)
    {
        command = parameters.command
    }
    else if ("url" in parameters || "dashboard" in parameters)
    {
        if ("url" in parameters)
        {
            url = parameters.url
        }
        else
        {
            url = "/" + parameters.dashboard
        }
        i = 0
        if ("args" in parameters)
        {
            
            url = url + "?"
            
            i = 0
            for (var key in parameters.args)
            {
                if (i != 0)
                {
                    url = url + "&"
                }
                url = url + key + "=" + parameters.args[key]
                i++
            }
        }
        if ("skin" in parameters)
        {
            theskin = parameters.skin
        }
        else
        {
            theskin = skin
        }
        if (i == 0)
        {
            url = url + "?skin=" + theskin
        }
        else
        {
            url = url + "&skin=" + theskin
        }
        command = "window.location.href = '" + url + "'"
    }
    
    this.command = command
    var that = this
    $('#' + widget_id + ' > span').click(
        function()
        {
            that.ViewModel.icon(that.icon_active.split("-")[0] + ' ' + that.icon_active)
            that.ViewModel.icon_style(that.icon_active_style)
            eval(that.command);
        }
    );
    
}