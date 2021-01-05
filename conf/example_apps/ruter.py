import hassapi as hass
import requests
import json
from datetime import datetime

"""

Get travel info for Oslo public transport

Arguments:
 - event: Entity name when publishing event
 - departures: Number of departures to publish for each line
 - interval: Update interval, in minutes
 - x_min, x_max, y_min, y_max: Box coordinates for area to find stops in, in the UTM coordinate system

"""


class Ruter(hass.Hass):
    def initialize(self):
        self.apiUrl = "http://reisapi.ruter.no"
        self.departures = self.args["departures"]
        self.entity = self.args["event"]

        now = datetime.now()
        interval = int(self.args["interval"])

        self.run_every(self.updateState, now, interval * 60)

    def fetch(self, path):
        res = requests.get(self.apiUrl + path)
        return json.loads(res.text)

    def updateState(self, kwargs=None):
        departures = self.getDepartures()
        self.set_app_state(self.entity, {"state": "", "attributes": departures})

    def getDepartures(self):
        ruter = {}
        stops = self.fetch(
            "/Place/GetStopsByArea?xmin={x_min}&xmax={x_max}&ymin={y_min}&ymax={y_max}".format(**self.args)
        )

        for stop in stops:
            name = stop["Name"]
            if name not in ruter:
                ruter[name] = {}

            departures = self.fetch("/StopVisit/GetDepartures/{}".format(stop["ID"]))
            for departure in departures:
                info = departure["MonitoredVehicleJourney"]
                line = info["PublishedLineName"] + " " + info["DestinationName"]
                platform = info["MonitoredCall"]["DeparturePlatformName"]

                if platform not in ruter[name]:
                    ruter[name][platform] = {}

                if line not in ruter[name][platform]:
                    ruter[name][platform][line] = []

                if len(ruter[name][platform][line]) < self.departures:
                    ruter[name][platform][line].append(
                        {"time": info["MonitoredCall"]["ExpectedArrivalTime"], "monitored": info["Monitored"]}
                    )

        return ruter
