import asyncio
import functools
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hassplugin import HassPlugin


class ServiceCallStatus(Enum):
    OK = auto()
    TIMEOUT =auto()
    TERMINATING = auto()


def looped_coro(coro, sleep_time: int | float):
    """Repeatedly runs a coroutine, sleeping between runs"""

    @functools.wraps(coro)
    async def loop(self: "HassPlugin", *args, **kwargs):
        while not self.stopping:
            try:
                await coro()
            except Exception:
                self.logger.error(f"Error running {coro.__name__} - retrying in {sleep_time}s")
            finally:
                await asyncio.sleep(sleep_time)

    return loop


def hass_check(func):
    """Essentially swallows the function call if the Home Assistant plugin isn't connected, in which case the function will return None.
    """
    async def no_func():
        pass

    @functools.wraps(func)
    def func_wrapper(self: "HassPlugin", *args, **kwargs):
        if not self.connect_event.is_set():
            self.logger.warning("Attempt to call Home Assistant while disconnected: %s", func.__name__)
            return no_func()
        else:
            return func(self, *args, **kwargs)

    return func_wrapper
