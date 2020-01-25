import hassapi as hass
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

"""

Get detailed Yr weather data

Arguments:
 - event: Entity name when publishing event
 - interval: Update interval, in minutes. Must be at least 10
 - source: Yr xml source
 - hours: Number of hours to forecast, at most 48

"""

disclaimer = "Weather forecast from Yr, delivered by the Norwegian Meteorological Institute and NRK"
user_agent = "HomeAssistant/Appdaemon Python/requests"


class Yr(hass.Hass):
    def initialize(self):
        self.url = self.args["source"]
        self.entity = self.args["event"]
        self.hours = self.args["hours"]

        inOneMinute = datetime.now() + timedelta(minutes=1)
        interval = int(self.args["interval"])

        if interval < 10:
            raise Exception("Update interval ({}) must be at least 10 minutes".format(interval))

        # delay first launch with one minute, run every 'interval' minutes
        self.run_every(self.updateState, inOneMinute, interval * 60)

    def updateState(self, kwargs):
        forecast = self.fetchForecast()
        self.set_app_state(self.entity, {"state": "", "attributes": forecast})

    def fetchData(self):
        res = requests.get(self.url, headers={"User-Agent": user_agent})
        return res.text

    def fetchForecast(self):
        data = self.fetchData()
        root = ET.fromstring(data)
        periods = root.find(".//tabular")
        return {
            "disclaimer": disclaimer,
            "forecast": [
                {
                    "from": x.get("from"),
                    "to": x.get("to"),
                    "weather": x.find("symbol").get("name"),
                    "symbol": x.find("symbol").get("var"),
                    "precip": x.find("precipitation").get("value"),
                    "windSpeed": x.find("windSpeed").get("mps"),
                    "windDirection": x.find("windDirection").get("deg"),
                    "temp": x.find("temperature").get("value"),
                }
                for x in periods[: self.hours]
            ],
        }
