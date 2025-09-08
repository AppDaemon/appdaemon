from datetime import datetime

from appdaemon import ADAPI
from appdaemon.adbase import ADBase


class SchedulerDiag(ADBase):
    adapi: ADAPI

    def initialize(self) -> None:
        self.adapi = self.get_ad_api()
        match self.args.get("dump_type"):
            case "sun":
                self.AD.loop.create_task(self.AD.sched.dump_sun())
            case "threads":
                self.AD.threading.dump_threads()
            case "nows":
                self.adapi.run_in(self.test_nows_sync, 0)
                self.adapi.run_in(self.test_nows_async, 0.25)

    def test_nows_sync(self, **kwargs):
        naive_now = self.adapi.get_now(aware=False)
        assert isinstance(naive_now, datetime) and naive_now.tzinfo is None, 'Bad naive get_now'

        now = self.adapi.get_now()
        assert isinstance(now, datetime) and now.tzinfo is not None, 'Bad aware get_now'

        now_ts = self.adapi.get_now_ts()
        assert isinstance(now_ts, float)

        self.adapi.log('Now:         %s', naive_now)
        self.adapi.log('Aware now:   %s', now)

        diff = round(naive_now.timestamp() - now.timestamp(), 3)
        assert diff == 0
        self.adapi.log('Diff:        %.2f', diff)

    async def test_nows_async(self, **kwargs):
        naive_now = await self.adapi.get_now(aware=False)
        assert isinstance(naive_now, datetime) and naive_now.tzinfo is None, 'Bad naive get_now'

        now = await self.adapi.get_now()
        assert isinstance(now, datetime) and now.tzinfo is not None, 'Bad aware get_now'

        now_ts = await self.adapi.get_now_ts()
        assert isinstance(now_ts, float)

        self.adapi.log('Now:         %s', naive_now)
        self.adapi.log('Aware now:   %s', now)

        diff = round(naive_now.timestamp() - now.timestamp(), 3)
        assert diff == 0
        self.adapi.log('Diff:        %.2f', diff)
