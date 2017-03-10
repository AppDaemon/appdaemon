function baseiframe(widget_id, url, skin, parameters)
{
    self = this
    
    // Initialization
    
    self.parameters = parameters;
    
    var callbacks = []
    
    var monitored_entities = []
    
    // Call the parent constructor to get things moving
    
    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)  

    // Set the url
    
    if ("url_list" in parameters)
    {
        self.url = 0;
        refresh_frame(self)
    }
    
    function refresh_frame(self)
    {
        $('#' + widget_id + ' .frame').attr('src', self.parameters.url_list[self.url]);
        
        if ("refresh" in self.parameters)
        {
            self.url = self.url + 1;
            if (self.url == self.parameters.url_list.length)
            {
                self.url = 0;
            }
            setTimeout(function() {refresh_frame(self)}, self.parameters.refresh * 1000);
        }
    }
}