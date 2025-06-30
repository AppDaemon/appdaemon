import asyncio
import traceback
from logging import Logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class ThreadAsync:
    """
    Module to translate from the thread world to the async world via queues
    """

    AD: "AppDaemon"
    logging: Logger
    appq: asyncio.Queue
    stop_event: asyncio.Event

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child("_thread_async")
        self.appq = asyncio.Queue(maxsize=0)
        self.stop_event = asyncio.Event()

    def start(self) -> None:
        """
        Start the thread_async loop
        """
        self.logger.debug("Starting thread_async loop")
        self.AD.loop.create_task(self.loop(), name="thread_async loop")

    def stop(self):
        self.logger.debug("stop() called for thread_async")
        self.stopping = True
        # Queue a fake event to make the loop wake up and exit
        self.appq.put_nowait({"stop": True})

    @property
    def stopping(self) -> bool:
        return self.stop_event.is_set()

    @stopping.setter
    def stopping(self, value: bool) -> None:
        if value:
            self.stop_event.set()
        else:
            self.stop_event.clear()

    async def loop(self):
        self.logger.debug("Starting thread_async loop")
        while not self.stopping:
            args = None
            try:
                args = await self.appq.get()
                if "stop" not in args:
                    self.logger.debug("thread_async loop, args=%s", args)
                    function = args["function"]
                    myargs = args["args"]
                    mykwargs = args["kwargs"]
                    asyncio.create_task(function(*myargs, **mykwargs))
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
