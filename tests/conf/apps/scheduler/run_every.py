from datetime import timedelta

from appdaemon import ADAPI


class RunEvery(ADAPI):
    def initialize(self) -> None:
        self.set_log_level("DEBUG")

    def start_timewarp(self) -> None:
        # This method is called to start the time warp
        self.run_every(self.scheduled_callback, start="now", interval="45:00", data="start now")
        self.run_every(self.scheduled_callback, start="now + 5:00", interval=timedelta(hours=1.37), data="start later")
        # self.run_every(self.scheduled_callback, start="sunrise", data='sunrise')
        # self.run_every(self.scheduled_callback, start="sunrise - 01:00:00", data='sunrise negative offset')

    def start_realtime(self) -> None:
        self.run_every(self.scheduled_callback, interval=timedelta(seconds=0.5), data="start default")
        self.run_every(self.scheduled_callback, start="now", interval=timedelta(seconds=1), data="start now")

    def scheduled_callback(self, data: str, **kwargs) -> None:
        self.log(f"{data}", level="DEBUG")
