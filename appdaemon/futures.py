import asyncio
import functools
from typing import TYPE_CHECKING, Dict, List, Union

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class Futures:
    """Subsystem container for managing :class:`~asyncio.Future` objects

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"
    futures: Dict[str, List[Union[asyncio.Future, asyncio.Task]]] = {}

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad

    def add_future(self, app_name: str, future_or_task: Union[asyncio.Future, asyncio.Task]):
        future_or_task.add_done_callback(functools.partial(self.remove_future, app_name))
        if app_name not in self.futures:
            self.futures[app_name] = []

        self.futures[app_name].append(future_or_task)
        self.AD.logger.debug("Registered a future in %s: %s", app_name, future_or_task)

    def remove_future(self, app_name: str, future_or_task: Union[asyncio.Future, asyncio.Task]):
        if app_name in self.futures:
            self.futures[app_name].remove(future_or_task)
            self.AD.logger.debug("Future removed from registry %s", future_or_task)

        if not future_or_task.done() and not future_or_task.cancelled():
            self.AD.logger.debug("Cancelling future %s", future_or_task)
            future_or_task.cancel()

    def cancel_futures(self, app_name: str):
        if app_name not in self.futures:
            return

        for f in self.futures[app_name]:
            if not f.done() and not f.cancelled():
                self.AD.logger.debug("Cancelling future %s", f)
                f.cancel()
