# flake8: noqa
# undefined name 'get_alexa_intent'
# undefined name 'get_alexa_error'
# undefined name 'get_alexa_slot_value'

import hassapi as hass
import random
import globals


class Alexa(hass.Hass):
    def initialize(self):
        pass

    def api_call(self, data):
        intent = get_alexa_intent(data)

        if intent is None:
            self.log("Alexa err encountered: {}".format(get_alexa_error(data)))
            return "", 201

        intents = {
            "StatusIntent": self.StatusIntent,
            "LocateIntent": self.LocateIntent,
        }

        if intent in intents:
            speech, card, title = intents[intent](data)
            response = self.format_alexa_response(speech=speech, card=card, title=title)
            self.log("Received Alexa request: {}, answering: {}".format(intent, speech))
        else:
            response = self.format_alexa_response(
                speech="I'm sorry, the {} does not exist within AppDaemon".format(intent)
            )

        return response, 200

    def StatusIntent(self, data):
        response = self.HouseStatus()
        return response, response, "House Status"

    def LocateIntent(self, data):
        user = get_alexa_slot_value(data, "User")

        if user is not None:
            if user.lower() == "jack":
                response = self.Jack()
            elif user.lower() == "andrew":
                response = self.Andrew()
            elif user.lower() == "wendy":
                response = self.Wendy()
            elif user.lower() == "brett":
                response = "I have no idea where Brett is, he never tells me anything"
            else:
                response = "I'm sorry, I don't know who {} is".format(user)
        else:
            response = "I'm sorry, I don't know who that is"

        return response, response, "Where is {}?".format(user)

    def HouseStatus(self):
        status = "The downstairs temperature is {} degrees fahrenheit,".format(
            self.entities.sensor.downstairs_thermostat_temperature.state
        )
        status += "The upstairs temperature is {} degrees fahrenheit,".format(
            self.entities.sensor.upstairs_thermostat_temperature.state
        )
        status += "The outside temperature is {} degrees fahrenheit,".format(
            self.entities.sensor.side_temp_corrected.state
        )
        status += self.Wendy()
        status += self.Andrew()
        status += self.Jack()

        return status

    def Wendy(self):
        location = self.get_state(globals.wendy_tracker)
        if location == "home":
            status = "Wendy is home,"
        else:
            status = "Wendy is away,"

        return status

    def Andrew(self):
        location = self.get_state(globals.andrew_tracker)
        if location == "home":
            status = "Andrew is home,"
        else:
            status = "Andrew is away,"

        return status

    def Jack(self):
        responses = [
            "Jack is asleep on his chair",
            "Jack just went out bowling with his kitty friends",
            "Jack is in the hall cupboard",
            "Jack is on the back of the den sofa",
            "Jack is on the bed",
            "Jack just stole a spot on daddy's chair",
            "Jack is in the kitchen looking out of the window",
            "Jack is looking out of the front door",
            "Jack is on the windowsill behind the bed",
            "Jack is out checking on his clown suit",
            "Jack is eating his treats",
            "Jack just went out for a walk in the neighborhood",
            "Jack is by his bowl waiting for treats",
        ]

        return random.choice(responses)
