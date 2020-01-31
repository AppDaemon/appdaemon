function basecamera(widget_id, url, skin, parameters)
{
    self = this

     // Initialization

     self.parameters = parameters;

     var callbacks = []

     self.OnStateAvailable = OnStateAvailable
    self.OnStateUpdate = OnStateUpdate

     var monitored_entities =
        [
            {"entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate},
        ];

     // Call the parent constructor to get things moving

     WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

     // Set the url

     self.index = 0;
    refresh_frame(self)
    self.timeout = undefined

     function refresh_frame(self)
    {
        if ("base_url" in self.parameters && "access_token" in self) {
            var endpoint = '/api/camera_proxy/'
            if ('stream' in self.parameters && self.parameters.stream) {
                endpoint = '/api/camera_proxy_stream/'
            }

             var url = self.parameters.base_url + endpoint + self.parameters.entity + '?token=' + self.access_token
        }
        else
        {
            var url = '/images/Blank.gif'
        }

         if (url.indexOf('?') > -1)
        {
            url = url + "&time=" + Math.floor((new Date).getTime()/1000);
        }
        else
        {
            url = url + "?time=" + Math.floor((new Date).getTime()/1000);
        }
        self.set_field(self, "img_src", url);
        self.index = 0

         var refresh = 10
         if ('stream' in self.parameters && self.parameters.stream == "on") {
            refresh = 0
        }
        if ("refresh" in self.parameters)
        {
            refresh = self.parameters.refresh
        }

        if (refresh > 0)
        {
            clearTimeout(self.timeout)
            self.timeout = setTimeout(function() {refresh_frame(self)}, refresh * 1000);
        }

     }

     // Function Definitions

     // The StateAvailable function will be called when
    // self.state[<entity>] has valid information for the requested entity
    // state is the initial state

     function OnStateAvailable(self, state)
    {
        self.state = state.state;
        self.access_token = state.attributes.access_token
        refresh_frame(self)
    }

     // The OnStateUpdate function will be called when the specific entity
    // receives a state update - its new values will be available
    // in self.state[<entity>] and returned in the state parameter

     function OnStateUpdate(self, state)
    {
        self.state = state.state;
        self.access_token = state.attributes.access_token
        refresh_frame(self)
    }

 }
