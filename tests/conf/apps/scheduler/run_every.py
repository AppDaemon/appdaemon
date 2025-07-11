from datetime import timedelta

from appdaemon.adapi import ADAPI
from appdaemon.adbase import ADBase


class RunEvery(ADAPI):
    def initialize(self) -> None:
        self.set_log_level("DEBUG")

        if self.AD.real_time:
            self.start_realtime()
        else:
            self.start_timewarp()

    def start_realtime(self) -> None:
        self.run_every(self.scheduled_callback, interval=timedelta(seconds=0.5), data="start default")
        self.run_every(self.scheduled_callback, start="now", interval=timedelta(seconds=1), data="start now")
        self.register_service("test/service", self.mycallback, my_kwarg="abc123")

    async def mycallback(self, namespace: str, domain: str, service: str, **kwargs):
        self.log(f"Service called: {kwargs}", level="DEBUG")

    def start_timewarp(self) -> None:
        # self.run_every(self.scheduled_callback, start="now", interval="02:37:45.7", data="start now")
        self.run_every(self.scheduled_callback, start="now + 02:00:00", interval=timedelta(hours=1), data="start later")
        # self.run_every(self.scheduled_callback, start="sunrise", data='sunrise')
        # self.run_every(self.scheduled_callback, start="sunrise - 01:00:00", data='sunrise negative offset')

    def scheduled_callback(self, data: str, **kwargs) -> None:
        self.log(f"{data}", level="DEBUG")


class RunEveryNow(ADBase):
    adapi: ADAPI

    def initialize(self) -> None:
        self.adapi = self.get_ad_api()
        self.adapi.set_log_level("DEBUG")
        start, interval, msg = self.args["start"], self.args["interval"], self.args["msg"]
        self.adapi.log("-" * 20)
        self.adapi.log(f"Starting RunEveryNow app at {interval}, starting at {start}")

        start_time = self.adapi.parse_datetime(time_str=start).strftime("%I:%M:%S.%f %p")
        self.adapi.log(f"Start time is {start_time}", level="DEBUG")
        self.adapi.run_every(self.scheduled_callback, start=start, interval=interval, data=msg)

    def scheduled_callback(self, data: str, **kwargs) -> None:
        self.adapi.log(f"{data}", level="DEBUG")


class RunHourly(RunEvery):
    def initialize(self) -> None:
        # self.set_log_level("DEBUG")
        self.run_every(self.scheduled_callback, start="now", interval=timedelta(hours=1), data="start hourly")

    def scheduled_callback(self, data: str, **kwargs) -> None:
        self.log(f"{data}", level="DEBUG")
