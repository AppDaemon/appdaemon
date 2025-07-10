from datetime import timedelta

from appdaemon import utils
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
        self.adapi.run_every(
            self.scheduled_callback,
            start="now",
            interval=self.interval,
            data=self.args['msg']
        )

    def scheduled_callback(self, data: str, **kwargs) -> None:
        self.adapi.log(f"{data}", level="DEBUG")

    @property
    def interval(self) -> timedelta:
        return utils.parse_timedelta(self.args["interval"])


class RunHourly(RunEvery):
    def initialize(self) -> None:
        # self.set_log_level("DEBUG")
        self.run_every(self.scheduled_callback, start="now", interval=timedelta(hours=1), data="start hourly")

    def scheduled_callback(self, data: str, **kwargs) -> None:
        self.log(f"{data}", level="DEBUG")
