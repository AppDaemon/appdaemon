import asyncio
from appdaemon.appdaemon import AppDaemon

class AdminLoop:

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.stopping = False
        self.logger = ad.logging.get_child("_admin_loop")

    def stop(self):
        self.logger.debug("stop() called for admin_loop")
        self.stopping = True

    async def loop(self):
        old_update = {}
        while not self.stopping:
            #update = {}
            #threads = {}
            if self.AD.http.stats_update != "none" and self.AD.sched is not None:
                await self.AD.threading.get_callback_update()
                #sched = self.AD.sched.get_scheduler_entries()
                #state_callbacks = self.AD.callbacks.get_callback_entries("state")
                #event_callbacks = self.AD.callbacks.get_callback_entries("event")
                #threads = self.AD.threading.get_thread_info()
                #update["updates"] = callback_update
                #update["schedule"] = sched
                #update["state_callbacks"] = state_callbacks
                #update["event_callbacks"] = event_callbacks
                #update["updates"]["current_busy_threads"] = threads["current_busy"]
                #update["updates"]["max_busy_threads"] = threads["max_busy"]
                #update["updates"]["max_busy_threads_time"] = threads["max_busy_time"]
            #if self.AD.http.stats_update == "batch":
                #update["threads"] = threads["threads"]

            #if update != old_update:
            #    await self.AD.http.stream_update(update)

            #old_update = update

            await asyncio.sleep(self.AD.admin_delay)

