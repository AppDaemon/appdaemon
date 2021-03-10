import hassapi as hass

#
# App to manage heating:
# - Turn on at different times in morning for weekdays and weekend, only if someone present
# - Stay on all day as long someone present
# - Turn off if everyone leaves
# - Turn off at night when input_select changes state
#
# Smart Heat doesn't actually turn the heat on and off, it merely sets it to a lower temperature for off so the house does not get too cold
#
# Args:
#
# morning_on_week = Weekday on time
# morning_on_weekend = Weekend on time
# evening_on = Evening on time of noone around
# switch = Input boolean to activate and deactivate smart heat
# thermostats = comma separated list of thermostats to use
# off_temp = Temperature to set thermostats for "off"
# on_temp = Temperature to set thermostats for "on"
# input_select = Name of input_select to monitor followed by comma separated list of values for which heating should be ON
# Release Notes
#
# Version 1.0:
#   Initial Version


class SmartHeat(hass.Hass):
    def initialize(self):

        # Schedule our morning check

        # Test

        # Run every day at specific times

        evening = self.parse_time(self.args["evening_on"])
        self.run_daily(self.evening, evening)

        morning_weekend = self.parse_time(self.args["morning_on_weekend"])
        self.run_daily(self.morning, morning_weekend, constrain_days="sat,sun")

        morning_week = self.parse_time(self.args["morning_on_week"])
        self.run_daily(self.morning, morning_week, constrain_days="mon,tue,wed,thu,fri")

        # Subscribe to presence changes

        self.listen_state(self.presence_change, "device_tracker")

        # Subscribe to switch

        self.listen_state(self.switch, self.args["switch"])

        #

        # Subscribe to input_select
        #
        # Could also use a timer to turn off at a specified time

        input_select = self.split_device_list(self.args["input_select"]).pop(0)
        self.listen_state(self.mode, input_select)
        # Set current state according to switch
        self.state = self.get_state(self.args["switch"])
        self.log("Current state = {}".format(self.state))

    def mode(self, entity, attribute, old, new, kwargs):
        # Mode has changed = if it isn't in the list of modes for which we want heat, turn the heat off
        valid_modes = self.split_device_list(self.args["input_select"])
        if new not in valid_modes and self.get_state(self.args["switch"]) == "on":
            self.heat_off()

    def switch(self, entity, attribute, old, new, kwargs):
        # Toggling switch turns heat on and off as well as enabling smart behavior
        if new == "on":
            self.heat_on()
        else:
            self.heat_off()

    def evening(self, kwargs):
        # If noone home in the evening turn heat on in preparation (if someone is home heat is already on)
        self.log("Evening heat check")
        if self.noone_home() and self.get_state(self.args["switch"]) == "on":
            self.heat_on()

    def morning(self, kwargs):
        # Setup tomorrows callback
        self.log("Morning heat check")
        if self.anyone_home() and self.get_state(self.args["switch"]) == "on":
            self.heat_on()

    def presence_change(self, entity, attribute, old, new, kwargs):
        if old != new and self.get_state(self.args["switch"]) == "on":
            if self.anyone_home():
                self.heat_on()
            else:
                self.heat_off()

    def heat_on(self):
        if self.state == "off":
            self.state = "on"
            self.log("Turning heat on")
            for tstat in self.split_device_list(self.args["thermostats"]):
                self.call_service(
                    "climate/set_temperature", entity_id=tstat, temperature=self.args["on_temp"],
                )

    def heat_off(self):
        if self.state == "on":
            self.state = "off"
            self.log("Turning heat off")
            for tstat in self.split_device_list(self.args["thermostats"]):
                self.call_service(
                    "climate/set_temperature", entity_id=tstat, temperature=self.args["off_temp"],
                )
