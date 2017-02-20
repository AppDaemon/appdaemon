function javascript(widget_id, url, parameters)
{
    // Store Args
    this.widget_id = widget_id
    this.parameters = parameters
        
    // Create and initialize bindings
    this.ViewModel = 
    {
        title: ko.observable(parameters.title),
        icon: ko.observable(parameters.icon.split("-")[0] + ' ' + parameters.icon),
    };
    
    ko.applyBindings(this.ViewModel, document.getElementById(widget_id))

    // Setup Override Styles
    
    if ("background_color" in parameters)
    {
        $('#' + widget_id).css("background-color", parameters["background_color"])
    }
    
    if ("icon_color" in parameters)
    {
        $('#' + widget_id + ' > h2').css("color", parameters["icon_color"])
    }
    
    if ("icon_size" in parameters)
    {
        $('#' + widget_id + ' > h2').css("font-size", parameters["icon_size"])
    }
    
    if ("title_color" in parameters)
    {
        $('#' + widget_id + ' > h1').css("color", parameters["title_color"])
    }
    
    if ("title_size" in parameters)
    {
        $('#' + widget_id + ' > h1').css("font-size", parameters["title_size"])
    }
    
    // Do some setup
        
    var that = this
    $('#' + widget_id).on('click', '*',
        function()
        {
            eval(parameters.command);
        }
    );
    
}