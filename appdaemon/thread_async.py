import asyncio
import traceback

from appdaemon.appdaemon import AppDaemon


class ThreadAsync:

    """
    Module to translate from the thread world to the async world via queues
    """

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.stopping = False
        self.logger = ad.logging.get_child("_thread_async")
        #
        # Initial Setup
        #

        self.appq = asyncio.Queue(maxsize=0)

    def stop(self):
        self.logger.debug("stop() called for thread_async")
        self.stopping = True
        # Queue a fake event to make the loop wake up and exit
        self.appq.put_nowait({"stop": True})

    async def loop(self):
        while not self.stopping:
            args = None
            try:
                args = await self.appq.get()
                if "stop" not in args:
                    self.logger.debug("thread_async loop, args=%s", args)
                    function = args["function"]
                    myargs = args["args"]
                    mykwargs = args["kwargs"]
                    asyncio.ensure_future(function(*myargs, **mykwargs))
                    # self.logger.debug("calling task_done()")
                    # self.appq.task_done()
            except Exception:
                self.logger.warning("-" * 60)
                self.logger.warning("Unexpected error during thread_async() loop()")
                self.logger.warning("args: %s", args)
                self.logger.warning("-" * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning("-" * 60)

    def call_async_no_wait(self, function, *args, **kwargs):
        self.appq.put_nowait({"function": function, "args": args, "kwargs": kwargs})
