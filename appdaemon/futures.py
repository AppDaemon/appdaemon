import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class Futures:
    """Subsystem container for managing :class:`~asyncio.Future` objects
    """

    AD: "AppDaemon"
    """Reference to the top-level AppDaemon container object"""
    futures: dict[str , list[asyncio.Future]]
    """Dictionary of futures registered by app name"""

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad
        self.logger = self.AD.logging.get_child("_futures")
        self.futures = defaultdict(list)

    def add_future(self, app_name: str, future: asyncio.Future):
        """Add a future to the registry and a callback that removes itself from the registry after it finishes."""
        self.futures[app_name].append(future)
        def safe_remove(f):
            try:
                self.futures[app_name].remove(f)
            except ValueError:
                pass
        future.add_done_callback(safe_remove)
        if isinstance(future, asyncio.Task):
            self.logger.debug(f"Registered a task for {app_name}: {future.get_name()}")
        else:
            self.logger.debug(f"Registered a future for {app_name}: {future}")

    def cancel_future(self, future: asyncio.Future):
        if not future.done() and not future.cancelled():
            if isinstance(future, asyncio.Task):
                self.logger.debug(f"Cancelling task {future.get_name()}")
            else:
                self.logger.debug(f"Cancelling future {future}")
            future.cancel()

    def cancel_futures(self, app_name: str):
        for f in self.futures.pop(app_name, []):
            self.cancel_future(f)
