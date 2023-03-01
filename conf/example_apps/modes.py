import hassapi as hass
import datetime
import appdaemon
import globals

#
# App to manage house modes
#
# I manage my automations around the concept of a house mode. Using an automation to set a mode can then be used by other
# Apps to simplify state checking. For instance, if I set the mode to Evening at a certain light level, there is
# no easy way for another app to be sure if that event has occurred in another app. To handle this
# I have defined an input_select called "house_mode". This app sets it to various values depending on the appropriate criteria.
# Other apps can read it to figure out what they should do.
#
# Args:
#
# Since this code is very specific to my setup I haven't bothered with parameters.
#
# Release Notes
#
# Version 1.0:
#   Initial Version


class Modes(hass.Hass):
    def initialize(self):
        # get current mode
        self.mode = self.get_state("input_select.house_mode")
        # Create some callbacks
        self.listen_event(self.mode_event, "MODE_CHANGE")
        self.listen_state(self.light_event, "sensor.side_multisensor_luminance")
        self.listen_state(self.motion_event, "binary_sensor.downstairs_sensor")
        self.listen_state(self.presence_change, "device_tracker")
        time = datetime.datetime.fromtimestamp(appdaemon.conf.now)
        self.log(f"Time: {time}")

    def presence_change(self, entity, attribute, old, new, kwargs):
        if old != new:
            if entity == globals.wendy_tracker and new != "home" and self.mode == "Morning":
                self.log("Wendy left - changing lighting")
                self.turn_on("scene.downstairs_on")

    def light_event(self, entity, attribute, old, new, kwargs):
        # Use light levels to switch to Day or Evening modes as appropriate
        lux = float(new)
        if self.mode == "Morning" or self.mode == "Night" and self.now_is_between("sunrise", "12:00:00"):
            if lux > 200:
                self.day()

        if self.mode == "Day" and self.now_is_between("sunset - 02:00:00", "sunset"):
            if lux < 200:
                self.evening()

    def motion_event(self, entity, attribute, old, new, kwargs):
        # Use motion form someone coming downstairs to trigger morning mode (switches on a downstairs lamp)
        if new == "on" and self.mode == "Night" and self.now_is_between("04:30:00", "10:00:00"):
            self.morning()

    def mode_event(self, event_name, data, kwargs):
        # Listen for a MODE_CHANGE custom event - triggered from a HASS script either manually or via Alexa
        # When event occurs switch to the appropriate mode
        mode = data["mode"]

        if mode == "Morning":
            self.morning()
        elif mode == "Day":
            self.day()
        elif mode == "Evening":
            self.evening()
        elif mode == "Night":
            self.night()
        elif mode == "Night Quiet":
            self.night(True)

    # Main mode functions - set the house up appropriately for the mode in question as well as set the house_mode flag correctly

    def morning(self):
        # Set the house up for morning
        self.mode = "Morning"
        self.log("Switching mode to Morning")
        self.cancel_timers()
        self.select_option("input_select.house_mode", "Morning")
        self.turn_on("scene.wendys_lamp")
        self.notify("Switching mode to Morning", name=globals.notify)

    def day(self):
        # Set the house up for daytime
        self.mode = "Day"
        self.log("Switching mode to Day")
        self.select_option("input_select.house_mode", "Day")
        self.turn_on("scene.downstairs_off")
        self.turn_on("scene.upstairs_off")
        self.notify("Switching mode to Day", name=globals.notify)

    def evening(self):
        # Set the house up for evening
        andrew = self.get_state(globals.andrew_tracker)
        self.mode = "Evening"
        self.log("Switching mode to Evening")
        self.select_option("input_select.house_mode", "Evening")
        if self.anyone_home() or self.get_state("input_boolean.vacation") == "on":
            self.turn_on("scene.downstairs_on")
        else:
            self.turn_on("scene.downstairs_front")

        if andrew == "home":
            self.turn_on("scene.office_on")

        self.notify("Switching mode to Evening", name=globals.notify)

    def night(self, quiet=False, alexa=False):
        #
        # Set the house up for night
        #
        # Quiet flag just turns the downstairs off and does not turn on any upstairs lights to avoid
        # Waking up anyone sleeping
        #
        self.mode = "Night"
        self.log("Switching mode to Night")
        self.select_option("input_select.house_mode", "Night")

        if self.anyone_home() and not quiet:
            self.turn_on("scene.upstairs_hall_on")
        else:
            self.turn_on("scene.upstairs_hall_off")

        wendy = self.get_state(globals.wendy_tracker)
        andrew = self.get_state(globals.andrew_tracker)

        # Switch on correct bedside lights according to presence
        if not quiet:
            if self.everyone_home():
                self.turn_on("scene.bedroom_on")
            elif wendy == "home":
                self.turn_on("scene.bedroom_on_wendy")
            elif andrew == "home":
                self.turn_on("scene.bedroom_on_andrew")

        # self.fire_event("SECURE", type = "query", secure_message = "Goodnight", insecure_message = "No problem but you might want to check the following items: ")
        security = self.get_app("Security")
        if not quiet:
            secmess = [
                "Goodnight",
                "Night night - don't let the bed bugs bite",
                "Night night - lets see if you can beat jack up to bed",
                "OK, turning the lights off for you",
                "OK, but no Snoring!",
            ]
        else:
            secmess = "Good night - try not to wake Wendy up"

        secargs = {
            "type": "secure",
            "secure_message": secmess,
            "not_secure_message": "The house is not secure",
            "insecure_message": "The following items are not secure: ",
            "securing_message": "I have secured the following items: ",
            "failed_message: ": "The following items failed to secure: ",
            "secure": 1,
        }

        if alexa:
            secargs["caller"] = "alexa"

        secure, response = security.query_house(secargs)

        self.notify("Switching mode to Night", name=globals.notify)

        # We turned the upstairs lights on, wait 5 seconds before turning off the downstairs lights
        self.run_in(self.downstairs_off, 5)
        return response

    def downstairs_off(self, kwargs):
        # Timed callback
        self.turn_on("scene.downstairs_off")

    def cancel_timers(self):
        if "timers" in self.args:
            apps = self.args["timers"].split(",")
            for app in apps:
                App = self.get_app(app)
                App.cancel()
