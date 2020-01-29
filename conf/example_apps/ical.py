import hassapi as hass
import requests
import ics
import arrow
from datetime import datetime, timedelta

"""

Load and publish iCal data, e.g a Google Calendar feed

NB: This app need the "ics" Python module.

Arguments:
 - event: Entity name when publishing event
 - interval: Update interval, in minutes
 - feed: Feed url
 - max_days: Maximum number of days to include
 - max_events: Maximum number of calendar events to include

"""


class Calendar(hass.Hass):
    def initialize(self):
        self.feed = self.args["feed"]
        self.entity = self.args["event"]
        self.max_events = int(self.args["max_events"])
        self.max_days = int(self.args["max_days"])
        interval = int(self.args["interval"])

        inOneMinute = datetime.now() + timedelta(minutes=1)
        self.run_every(self.updateState, inOneMinute, interval * 60)

    def updateState(self, kwargs=None):
        self.log("loading data from ical feed")
        data = requests.get(self.feed).text
        ical = ics.Calendar(data)
        self.log("ical data loaded")

        now = arrow.now()
        future = arrow.now().replace(days=self.max_days)

        events = [
            {"name": e.name, "location": e.location, "begin": e.begin.isoformat(), "end": e.end.isoformat()}
            for e in ical.events
            if now < e.begin < future
        ][: self.max_events]

        self.set_app_state(self.entity, {"state": "", "attributes": events})
