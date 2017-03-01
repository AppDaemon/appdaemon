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
		icon: ko.observable(parameters.icon.split("-")[0] + ' ' + parameters.icon),
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

	if ("icon_style" in parameters)
	{
		this.ViewModel.icon_style(parameters.icon_style)
	}	 
	// Do some setup
	
	if ("command" in parameters)
	{
		command = parameters.command
	}
	else if ("url" in parameters)
	{
		url = parameters.url
		i = 0
		if ("args" in parameters)
		{
			console.log(parameters.args)
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
		console.log(command)
	}
	
	this.command = command
	var that = this
	$('#' + widget_id + ' > span').click(
		function()
		{
			eval(that.command);
		}
	);
	
}