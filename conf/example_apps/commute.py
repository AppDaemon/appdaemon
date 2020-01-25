import hassapi as hass

#
# App to send email alert if commute time is too long
#
# Args:
#
# time = time the alert will be sent
# limit = number of minutes over which the alert will be sent
# notify - list of notification services to be notified
# sensor - sensor to get the commute time from
#
# None
#
# Release Notes
#
# Version 1.0:
#   Initial Version


class Commute(hass.Hass):
    def initialize(self):
        time = self.parse_time(self.args["time"])
        self.run_daily(self.check_travel, time)

    def check_travel(self, kwargs):
        commute = int(self.get_state(self.args["sensor"]))
        self.log(commute)
        self.log(int(self.args["limit"]))
        if commute > int(self.args["limit"]):
            message = "Commute warning - current travel time from work to home is {} minutes".format(commute)
            self.log(message)
            for destination in self.args["notify"]:
                self.notify(message, title="Commute Warning", name=destination)
