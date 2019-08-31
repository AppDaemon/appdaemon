import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon
import functools
import asyncio

class Futures:

    def __init__(self, ad: AppDaemon):
        self.AD = ad

        self.futures = {}

    def add_future(self, name, f):
        f.add_done_callback(functools.partial(self.remove_future, name))
        if name not in self.futures:
            self.futures[name] = []

        self.futures[name].append(f)
        self.AD.logger.info('Registered a future in {}: {}'.format(name, f))

    def remove_future(self, name, f):
        if name in self.futures:
            self.futures[name].remove(f)
            self.AD.logger.info('Future removed from registry {}'.format(f))

        try:
            f = f.exception()
            if f is not None:
                raise f
        except asyncio.CancelledError:
            self.AD.logger.info('Future was cancelled. {}'.format(f))

    def cancel_futures(self, name):
        if name not in self.futures:
            return

        for f in self.futures[name]:
            if not f.done():
                self.AD.logger.info('Cancelling Future {}'.format(f))
                f.cancel()
