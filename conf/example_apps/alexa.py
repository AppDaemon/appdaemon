import appdaemon.appapi as appapi
import random

class Alexa(appapi.AppDaemon):

    def initialize(self):
        pass

    def api_call(self, data):
        intent = self.get_alexa_intent(data)

        if intent is None:
            self.log("Alexa error encountered: {}".format(self.get_alexa_error(data)))
            return

        intents = {
            "StatusIntent": self.StatusIntent,
            "LocateAndrewIntent": self.LocateAndrewIntent,
            "LocateWendyIntent": self.LocateWendyIntent,
            "LocateJackIntent": self.LocateJackIntent,
            "LocateBrettIntent": self.LocateBrettIntent,
            "MorningModeIntent": self.MorningModeIntent,
            "DayModeIntent": self.DayModeIntent,
            "EveningModeIntent": self.EveningModeIntent,
            "NightModeIntent": self.NightModeIntent,
            "NightModeQuietIntent": self.NightModeQuietIntent,
            "SecureHouseIntent": self.SecureHouseIntent,
            "QueryHouseIntent": self.QueryHouseIntent,
            "QueryGarageDoorIntent": self.QueryGarageDoorIntent,
            "QueryHeatIntent": self.QueryHeatIntent,
            "ConditionsIntent": self.ConditionsIntent,
            "TravelIntent": self.TravelIntent,
        }

        if intent in intents:
            speech, card, title = intents[intent](data)
            response = self.format_alexa_response(speech = speech, card = card, title = title)
            self.log("Recieved Alexa request: {}, answering: {}".format(intent, speech))
        else:
            response = self.format_alexa_response(speech = "I'm sorry, the {} does not exist within AppDaemon".format(intent))

        return response, 200

    def QueryHouseIntent(self, data):
        security = self.get_app(self.args["apps"]["secure"])
        secure, response = security.query_house({"type": "query", "caller": "alexa"})
        return response, response, "Query House Security"

    def SecureHouseIntent(self, data):
        security = self.get_app(self.args["apps"]["secure"])
        secure, response = security.query_house({"type": "secure", "caller": "alexa"})
        return response, response, "Secure House"

    def MorningModeIntent(self, data):
        self.fire_event("MODE_CHANGE", mode = "Morning")
        response = "Good Morning"
        return response, response, "Morning Mode"

    def DayModeIntent(self, data):
        self.fire_event("MODE_CHANGE", mode = "Day")
        response = "Good Day"
        return response, response, "Day Mode"

    def EveningModeIntent(self, data):
        self.fire_event("MODE_CHANGE", mode = "Evening")
        response = "Good Evening"
        return response, response, "Evening Mode"

    def NightModeIntent(self, data):
        modes = self.get_app(self.args["apps"]["modes"])
        response = modes.night(False, True)
        return response, response, "Night Mode"

    def NightModeQuietIntent(self, data):
        modes = self.get_app(self.args["apps"]["modes"])
        response = modes.night(True, True)
        return response, response, "Night Mode Quiet"

    def TravelIntent(self, data):

        if self.now_is_between("05:00:00", "12:00:00"):
            commute = self.entities.sensor.wendy_home_to_work.state
            direction = "from home to work"
            response = "Wendy's commute time {} is currently {} minutes".format(direction, commute)
        elif self.now_is_between("12:00:01", "20:00:00"):
            commute = self.entities.sensor.wendy_work_to_home.state
            direction = "from work to home"
            response = "Wendy's commute time {} is currently {} minutes".format(direction, commute)
        else:
            response = "Are you kidding me? Don't go to work now!"

        return response, response, "Travel Time"

    def StatusIntent(self, data):
        response = self.HouseStatus()
        return response, response, "House Status"

    def ConditionsIntent(self, data):
        temp = float(self.entities.sensor.side_temp_corrected.state)
        if  temp <= 70:
            response = "It is {} degrees outside. The conditions have been met.".format(temp)
        else:
            response =  "It is {} degrees outside. The conditions have not been met.".format(temp)

        return response, response, "Conditions Query"

    def LocateBrettIntent(self, data):
        response = "I have no idea he never tells me anything"
        return response, response, "Where is Brett?"

    def LocateAndrewIntent(self, data):
        response = self.Andrew()
        return response, response, "Where is Andrew?"

    def LocateWendyIntent(self, data):
        response = self.Wendy()
        return response, response, "Where is Wendy?"

    def LocateJackIntent(self, data):
        response = self.Jack()
        return response, response, "Where is Jack?"

    def QueryGarageDoorIntent(self, data):
        response = self.Garage()
        return response, response, "Is the garage open?"

    def QueryHeatIntent(self, data):
        response = self.Heat()
        return response, response, "Is the heat open?"

    def HouseStatus(self):

        status = self.Heat()
        status += "The downstairs temperature is {} degrees farenheit,".format(self.entities.sensor.downstairs_thermostat_temperature.state)
        status += "The upstairs temperature is {} degrees farenheit,".format(self.entities.sensor.upstairs_thermostat_temperature.state)
        status += "The outside temperature is {} degrees farenheit,".format(self.entities.sensor.side_temp_corrected.state)
        status += self.Garage()
        status += self.Wendy()
        status += self.Andrew()
        status += self.Jack()

        return status

    def Garage(self):
        return "The garage door is {},".format(self.entities.cover.garage_door.state)

    def Heat(self):
        return "The heat is switched {},".format(self.entities.input_boolean.heating.state)

    def Wendy(self):
        if self.entities.sensor.wendy_tracker.state == "home":
            status = "Wendy is home,"
        else:
            status = "Wendy is away,"

        return status

    def Andrew(self):
        if self.entities.sensor.andrew_tracker.state == "home":
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
            "Jack just went out for a walk in the neigbourhood",
            "Jack is by his bowl waiting for treats"
        ]

        return random.choice(responses)

    def Response(self):
        responses = [
          "OK",
          "Sure",
          "If you insist",
          "Done",
          "No worries",
          "I can do that",
          "Leave it to me",
          "Consider it done",
          "As you wish",
          "By your command",
          "Affirmative",
          "Yes oh revered one",
          "I will",
          "As you decree, so shall it be",
          "No Problem"
        ]

        return random.choice(responses)
