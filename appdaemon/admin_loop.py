import asyncio
from logging import Logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class AdminLoop:
    """Called by :meth:`~appdaemon.appdaemon.AppDaemon.register_http`. Loop timed with :attr:`~appdaemon.AppDaemon.admin_delay`"""

    AD: "AppDaemon"
    """Reference to the AppDaemon container object
    """
    stopping: bool
    logger: Logger
    """Standard python logger named ``AppDaemon._admin_loop``
    """

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.stopping = False
        self.logger = ad.logging.get_child("_admin_loop")

    def stop(self):
        self.logger.debug("stop() called for admin_loop")
        self.stopping = True

    async def loop(self):
        """Handles calling :meth:`~.threading.Threading.get_callback_update` and :meth:`~.threading.Threading.get_q_update`"""
        while not self.stopping:
            if self.AD.http.stats_update != "none" and self.AD.sched is not None:
                await self.AD.threading.get_callback_update()
                await self.AD.threading.get_q_update()

            await asyncio.sleep(self.AD.admin_delay)
