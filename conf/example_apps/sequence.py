import hassapi as hass


"""
    App to fire a sequence of events when a particular state is met
    Args:
        input: switch or device to monitor to fire the sequence
        state: new state that fires the sequence
        sequence a list of sequence entries:
            - entity: entity to call service on
              service: name of the service
              delay: delay from the event firing after which this entry will activate

    e.g.

      input: input_boolean.studio
      state: "off"
      sequence:
        - entity: switch.basement_speakers_switch
          service: switch/turn_off
          delay: 0
        - entity: switch.basement_desk_switch
          service: switch/turn_off
          delay: 5

    Release Notes
    Version 1.0:
        Initial Version
"""


class Sequence(hass.Hass):
    def initialize(self):
        if "input" in self.args and "state" in self.args:
            self.listen_state(self.state_change, self.args["input"], new=self.args["state"])

    def state_change(self, entity, attribute, old, new, kwargs):
        # self.verbose_log("{} turned {}".format(entity, new))
        if "sequence" in self.args:
            for entry in self.args["sequence"]:
                self.run_in(
                    self.action,
                    entry["delay"],
                    device=entry["entity"],
                    service=entry["service"],
                )

    def action(self, kwargs):
        self.log("Calling {} on {}".format(kwargs["device"], kwargs["service"]))
        self.call_service(kwargs["service"], entity_id=kwargs["device"])
