from logging import Logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class AdminLoop:
    """Called by :meth:`~appdaemon.appdaemon.AppDaemon.register_http`. Loop timed with :attr:`~appdaemon.AppDaemon.admin_delay`"""

    AD: "AppDaemon"
    """Reference to the AppDaemon container object
    """
    logger: Logger
    """Standard python logger named ``AppDaemon._admin_loop``
    """
    name: str = "_admin_loop"

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = ad.logging.get_child(self.name)

    async def loop(self):
        """Handles calling :meth:`~.threading.Threading.get_callback_update` and :meth:`~.threading.Threading.get_q_update`"""
        while not self.AD.stopping:
            if (
                self.AD.http is not None
                and self.AD.http.stats_update != "none"
                and self.AD.sched is not None
            ):  # fmt: skip
                await self.AD.threading.get_callback_update()
                await self.AD.threading.get_q_update()

            await self.AD.utility.sleep(self.AD.config.admin_delay.total_seconds(), timeout_ok=True)
