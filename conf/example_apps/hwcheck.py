import hassapi as hass
import globals


class HWCheck(hass.Hass):
    def initialize(self):
        self.listen_event(self.ha_event, "ha_started")
        self.listen_event(self.appd_event, "appd_started")

    def ha_event(self, event_name, data, kwargs):
        self.log_notify("Home Assistant is up", "INFO")
        self.run_in(self.hw_check, self.args["delay"])

    def appd_event(self, event_name, data, kwargs):
        self.log_notify("AppDaemon is up", "INFO")

    def hw_check(self, kwargs):
        state = self.get_state()

        if "zwave" in self.args and self.args["zwave"] not in state:
            self.log_notify("ZWAVE not started after delay period", "WARNING")
        if "hue" in self.args and self.args["hue"] not in state:
            self.log_notify("HUE not started after delay period", "WARNING")

    def log_notify(self, msg, level):
        self.log(msg, level)
        self.notify(msg, name=globals.notify)

    def terminate(self):
        self.log("Terminating!", "INFO")
