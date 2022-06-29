from functools import wraps
from typing import Any

import appdaemon.utils as utils


def time_constrained(start_time: str, end_time: str) -> callable:
    """checking time constraint"""

    def inner_decorator(f):
        def ignore_func():
            pass

        @wraps(f)
        def evaluator(*args, **kw):

            self = args[0]

            coro = self.AD.sched.now_is_between(start_time, end_time, self.name)
            try:
                valid = utils.run_coroutine_threadsafe(self, coro)
            except Exception as e:
                self.logger.info(e)
                valid = False

            if valid is True:
                return f(*args, **kw)

            else:
                return ignore_func()

        return evaluator

    return inner_decorator


def days_constrained(days: str) -> callable:
    """checking days constraint"""

    def inner_decorator(f):
        def ignore_func():
            pass

        @wraps(f)
        def evaluator(*args, **kw):

            self = args[0]
            coro = self.AD.sched.get_now()
            now = utils.run_coroutine_threadsafe(self, coro)
            valid = utils.check_days(now, days, self.name)

            if valid is True:
                return f(*args, **kw)

            else:
                return ignore_func()

        return evaluator

    return inner_decorator


def state_constrained(state: Any) -> callable:
    """checking state constraint"""

    def inner_decorator(f):
        def ignore_func():
            pass

        @wraps(f)
        def evaluator(*args, **kw):

            self = args[0]
            valid = True

            if len(args) < 5:
                # If its a valid state callback, must be up to 5
                self.logger.warning(
                    f"Could not use the state_constrained, as its used for a non state callback in {self.name}"
                )

            else:
                new = args[4]
                valid = utils.check_state(self.logger, new, state, self.name)

            if valid is True:
                return f(*args, **kw)

            else:
                return ignore_func()

        return evaluator

    return inner_decorator
