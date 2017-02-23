function baseclock(widget_id, url, parameters)
{
	// Store Args
	this.widget_id = widget_id;
	this.parameters = parameters;
	
	// Create and initialize bindings
	this.ViewModel = 
	{
		date: ko.observable(),
		time: ko.observable(),
		widget_style: ko.observable(),
		date_style: ko.observable(),
		time_style: ko.observable()
	};
	
	ko.applyBindings(this.ViewModel, document.getElementById(widget_id))

	// Setup Override Styles

	if ("widget_style" in parameters)
	{
		this.ViewModel.widget_style(parameters.widget_style)
	}
	
	if ("date_style" in parameters)
	{
		this.ViewModel.date_style(parameters.date_style)
	}
	
	if ("time_style" in parameters)
	{
		this.ViewModel.time_style(parameters.time_style)
	}
	
	updateTime(this)
	
	setInterval(updateTime, 500, this);

	function updateTime(that) 
	{
		var today = new Date();
		h = today.getHours();
		m = today.getMinutes();
		s = today.getSeconds();
		m = formatTime(m);
		that.ViewModel.date(today.toLocaleDateString());
		
		
		if ("time_format" in that.parameters && that.parameters.time_format == "24hr")
		{
			time = h + ":" + m;
			pm = ""
		}
		else
		{
			time = formatHours(h) + ":" + m;
			pm = " " + formatAmPm(h)
		}
		
		if (that.parameters.show_seconds)
		{
			time = time + ":" + formatTime(s)
		}
		
		time = time + pm
		that.ViewModel.time(time);
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
			return 12;
		}
		else
		{
			return h;
		}
	}
}