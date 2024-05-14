import functools
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from appdaemon.appdaemon import AppDaemon


class Futures:
    """Subsystem container for managing :class:`~asyncio.Future` objects

    Attributes:
        AD: Reference to the AppDaemon container object
    """

    AD: "AppDaemon"

    def __init__(self, ad: "AppDaemon"):
        self.AD = ad

        self.futures = {}

    def add_future(self, name, f):
        f.add_done_callback(functools.partial(self.remove_future, name))
        if name not in self.futures:
            self.futures[name] = []

        self.futures[name].append(f)
        self.AD.logger.debug("Registered a future in {}: {}".format(name, f))

    def remove_future(self, name, f):
        if name in self.futures:
            self.futures[name].remove(f)

        self.AD.logger.debug("Future removed from registry {}".format(f))

        if f.cancelled():
            return

        if not f.done():
            f.cancel()

    def cancel_futures(self, name):
        if name not in self.futures:
            return

        for f in self.futures[name]:
            if not f.done() and not f.cancelled():
                self.AD.logger.debug("Cancelling Future {}".format(f))
                f.cancel()
