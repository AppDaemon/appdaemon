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
    name: str = "_thread_async"
    appq: asyncio.Queue

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child(self.name)
        self.appq = asyncio.Queue()

    def start(self) -> None:
        """Start the thread_async loop"""
        self.logger.debug("Starting thread_async loop")
        self.AD.loop.create_task(self.loop(), name="thread_async loop")

    def stop(self):
        """Stops the thread/async loop by putting a sentinel value in the queue."""
        self.logger.debug("stop() called for thread_async")
        # Queue a fake event to make the loop wake up and exit
        self.appq.put_nowait({"stop": True})

    async def loop(self):
        self.logger.debug("Starting thread_async loop")
        while not self.AD.stopping:
            args = None
            try:
                match args := await self.appq.get():
                    case {"stop": True}:
                        self.logger.debug("thread_async loop stopped")
                        break
                    case {"function": function, "args": myargs, "kwargs": mykwargs}:
                        self.logger.debug("thread_async loop, args=%s", args)
                        asyncio.create_task(function(*myargs, **mykwargs))
                    case _:
                        self.logger.warning("Unexpected args format: %s", args)
            except Exception:
                self.logger.warning("-" * 60)
                self.logger.warning("Unexpected error during thread_async() loop()")
                self.logger.warning("args: %s", args)
                self.logger.warning("-" * 60)
                self.logger.warning(traceback.format_exc())
                self.logger.warning("-" * 60)

    def call_async_no_wait(self, function, *args, **kwargs):
        self.appq.put_nowait({"function": function, "args": args, "kwargs": kwargs})
