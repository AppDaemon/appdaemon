import hassapi as hass
import globals

#
# App to track presence changes

# Args:
#
#
# notify = set to anything and presence changes will be notified
# day_scene_off = scene to use to turn lights off during the day
# night_scene_absent = scene to use to turn lights off at night (e.g. keep just one on)
# night_scene_present = scene to use to turn lights on at night
# input_select = input_select.house_mode,Day
# vacation = optional input boolean to turn off when someone comes home
# announce = Comma separated list of people's arrival home to announce (Friendly name of the device tracker)
# player = entity id of the media player for the announcement
#
# Release Notes
#
# Version 1.1:
#   Add media player support
# Version 1.0:
#   Initial Version


class Presence(hass.Hass):
    def initialize(self):
        # Subscribe to presence changes

        self.listen_state(self.presence_change, "device_tracker")
        self.listen_state(self.everyone_left, "group.all_devices", old="home", new="not_home")
        self.listen_state(self.someone_home, "group.all_devices", old="not_home", new="home")
        self.listen_event(self.presence_event, "PRESENCE_CHANGE")
        self.set_state("sensor.andrew_tracker", state="away")
        self.set_state("sensor.wendy_tracker", state="away")

    def presence_event(self, event_name, data, kwargs):
        # Listen for a PRESENCE_CHANGE custom event
        event_tracker = data["tracker"]
        event_type = data["type"]
        tracker = "Unknown"
        if event_tracker == "Andrew":
            tracker = globals.andrew_tracker_id
        elif event_tracker == "Wendy":
            tracker = globals.wendy_tracker_id
        self.call_service("device_tracker/see", dev_id=tracker, location_name=event_type)

    def presence_change(self, entity, attribute, old, new, kwargs):
        person = self.friendly_name(entity)
        tracker_entity = "sensor.{}_tracker".format(person.lower())
        self.set_state(tracker_entity, state=new)
        if old != new:
            if new == "not_home":
                place = "is away"
                if "announce" in self.args and self.args["announce"].find(person) != -1:
                    self.announce = self.get_app("Sound")
                    self.announce.tts("{} just left".format(person), self.args["volume"], 3)
            elif new == "home":
                place = "arrived home"
                if "announce" in self.args and self.args["announce"].find(person) != -1:
                    self.announce = self.get_app("Sound")
                    self.announce.tts("{} arrived home".format(person), self.args["volume"], 3)
            else:
                place = "is at {}".format(new)
            message = "{} {}".format(person, place)
            self.log(message)
            if "notify" in self.args:
                self.notify(message, name=globals.notify)

    def everyone_left(self, entity, attribute, old, new, kwargs):
        self.log("Everyone left")
        valid_modes = self.split_device_list(self.args["input_select"])
        input_select = valid_modes.pop(0)
        if self.get_state(input_select) in valid_modes:
            self.turn_on(self.args["day_scene_absent"])
        else:
            self.turn_on(self.args["night_scene_absent"])

    def someone_home(self, entity, attribute, old, new, kwargs):
        self.log("Someone came home")
        if "vacation" in self.args:
            self.set_state(self.args["vacation"], state="off")
        valid_modes = self.split_device_list(self.args["input_select"])
        input_select = valid_modes.pop(0)
        if self.get_state(input_select) in valid_modes:
            self.turn_on(self.args["day_scene_present"])
        else:
            self.turn_on(self.args["night_scene_present"])
