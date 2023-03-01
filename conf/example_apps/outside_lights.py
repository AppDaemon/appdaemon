import hassapi as hass

#
# App to turn lights on and off at sunrise and sunset
#
# Args:
#
# on_scene: scene to activate at sunset
# off_scene: scene to activate at sunrise


class OutsideLights(hass.Hass):
    def initialize(self):
        # Run at Sunrise
        self.run_at_sunrise(self.sunrise_cb)

        # Run at Sunset
        self.run_at_sunset(self.sunset_cb)

    def sunrise_cb(self, kwargs):
        self.log("OutsideLights: Sunrise Triggered")
        self.cancel_timers()
        self.turn_on(self.args["off_scene"])

    def sunset_cb(self, kwargs):
        self.log("OutsideLights: Sunset Triggered")
        self.cancel_timers()
        self.turn_on(self.args["on_scene"])

    def cancel_timers(self):
        if "timers" in self.args:
            apps = self.args["timers"].split(",")
            for app in apps:
                App = self.get_app(app)
                App.cancel()
