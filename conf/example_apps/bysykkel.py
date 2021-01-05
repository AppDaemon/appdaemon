import hassapi as hass
import requests
import json
from datetime import datetime

"""

Get availability for Oslo City Bikes

Arguments:
 - event: Entity name when publishing event
 - interval: Update interval, in minutes

"""


class Bysykkel(hass.Hass):
    def initialize(self):
        self.apiUrl = "http://reisapi.ruter.no"
        self.entity = self.args["event"]

        now = datetime.now()
        interval = int(self.args["interval"])

        self.run_every(self.updateState, now, interval * 60)

    def fetch(self, path):
        res = requests.get(self.apiUrl + path)
        return json.loads(res.text)

    def updateState(self, kwargs=None):
        status = self.getStatus()
        self.set_app_state(self.entity, {"state": "", "attributes": status})

    def getStatus(self):
        stations = self.fetch(
            "/Place/GetCityBikeStations?latmin={lat_min}&latmax={lat_max}&longmin={long_min}&longmax={long_max}".format(
                **self.args
            )
        )

        return [
            {
                "title": s["Title"],
                "subtitle": s["Subtitle"],
                "bikes": s["Availability"]["Bikes"],
                "locks": s["Availability"]["Locks"],
            }
            for s in stations
        ]
