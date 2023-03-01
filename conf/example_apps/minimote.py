import hassapi as hass

#
# App to respond to buttons on an Aeotec Minimote
#
# Args:
#
# Minimote can send up to 8 scenes. Odd numbered scenes are short presses of the buttons, even are long presses
#
# Args:
#
# device - name of the device. This will be the ZWave name without an entity type, e.g. minimote_31
# scene_<id>_on - name of the entity to turn on when scene <id> is activated
# scene_<id>_off - name of the entity to turn off when scene <id> is activated. If the entity is a scene it will be turned on.
# scene_<id>_toggle - name of the entity to toggle when scene <id> is activated
#
# Each scene can have up to one of each type of action, or no actions - e.g. you can turn on one light and turn off another light for a particular scene if desired
#
# Release Notes
#
# Version 1.0:
#   Initial Version


class MiniMote(hass.Hass):
    def initialize(self):
        self.listen_event(self.zwave_event, "zwave.scene_activated", entity_id=self.args["device"])

    def zwave_event(self, event_name, data, kwargs):
        # self.verbose_log("Event: {}, data = {}, args = {}".format(event_name, data, kwargs))
        scene = data["scene_id"]
        on = "scene_{}_on".format(scene)
        off = "scene_{}_off".format(scene)
        toggle = "scene_{}_toggle".format(scene)

        if on in self.args:
            self.log("Turning {} on".format(self.args[on]))
            self.turn_on(self.args[on])

        if off in self.args:
            self.log("Turning {} off".format(self.args[off]))
            self.turn_off(self.args[off])

        if toggle in self.args:
            self.log("Toggling {}".format(self.args[toggle]))
            self.toggle(self.args[toggle])
