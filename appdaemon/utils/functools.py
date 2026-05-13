import functools
import inspect
import json
import random
import traceback
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from logging import Logger
from typing import Any, TypeVar

from pydantic import ValidationError

from appdaemon import exceptions as ade

R = TypeVar("R")


def unwrapped(func: Callable) -> Callable:
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    if isinstance(func, functools.partial):
        func = func.func
    return func


def has_expanded_kwargs(func):
    """Determines whether or not to use keyword argument expansion on this function by
    finding if there's a ``**kwargs`` expansion somewhere.

    Handles unwrapping (removing decorators) if necessary.
    """
    func = unwrapped(func)

    if isinstance(func, functools.partial):
        func = func.func

    return any(param.kind == param.VAR_KEYWORD for param in inspect.signature(func).parameters.values())


def has_collapsed_kwargs(func):
    func = unwrapped(func)
    params = inspect.signature(func).parameters
    p = list(params.values())[-1]
    return p.kind == p.POSITIONAL_OR_KEYWORD


def count_positional_arguments(callable: Callable) -> int:
    return len(
        [
            p for p in inspect.signature(callable).parameters.values()
            if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD or
            p.kind == inspect.Parameter.VAR_POSITIONAL
        ]
    )  # fmt: skip


def resolve_offset(
    offset: timedelta,
    random_start: timedelta | None = None,
    random_end: timedelta | None = None,
) -> timedelta:
    """Resolves a given offset with some randomization into a timedelta object.

    Args:
        offset: Base offset as a timedelta
        random_start: Start of random range as a timedelta (can be negative)
        random_end: End of random range as a timedelta

    Returns:
        The offset plus a random value in [random_start, random_end]
    """
    if random_start is not None or random_end is not None:
        r_start = random_start if random_start is not None else timedelta()
        r_end = random_end if random_end is not None else timedelta()

        span = r_end - r_start
        assert span >= timedelta(), "Random end must be greater than or equal to random start"

        random_offset = span * random.random() + r_start
        offset += random_offset
    return offset


def validate_offset_within_interval(
    offset: timedelta,
    interval: timedelta,
    event_type: str,
    random_start: timedelta | None = None,
    random_end: timedelta | None = None,
) -> None:
    """Validate that the offset (including random range) doesn't exceed the event interval.

    For repeating schedules, an offset that exceeds the interval between events would cause
    confusing behavior where the callback fires at unpredictable times relative to the intended
    base time.

    Args:
        offset: The base offset as a timedelta
        interval: The interval between events as a timedelta
        event_type: Human-readable description of the event type (e.g., "sunrise", "daily")
        random_start: Optional random range start as a timedelta
        random_end: Optional random range end as a timedelta

    Raises:
        OffsetExceedsIntervalError: If the maximum possible offset exceeds the interval
    """
    if interval <= timedelta():
        return  # Non-repeating event or invalid interval, skip validation

    r_start = random_start if random_start is not None else timedelta()
    r_end = random_end if random_end is not None else timedelta()

    # Calculate the extreme possible offsets
    min_offset = offset + r_start
    max_offset = offset + r_end

    # Check if any possible offset would exceed the interval
    if abs(min_offset) >= interval or abs(max_offset) >= interval:
        raise ade.OffsetExceedsIntervalError(
            offset=offset,
            interval=interval,
            event_type=event_type,
            random_start=random_start,
            random_end=random_end,
        )


def get_kwargs(kwargs):
    result = ""
    for kwarg in kwargs:
        if kwarg[:2] != "__":
            result += "{}={} ".format(kwarg, kwargs[kwarg])
    return result


def _sanitize_kwargs(kwargs, keys):
    for key in keys:
        if key in kwargs:
            del kwargs[key]
    return kwargs


def remove_literals(val: Any, literal: Sequence[Any]) -> Any:
    """Remove instances of literals from a nested data structure.

    Uses identity comparison (``is``) rather than equality (``==``)
    to avoid ``0 == False`` and ``0.0 == False`` pitfalls.
    """
    def _is_literal(v: Any) -> bool:
        return any(v is lit for lit in literal)

    match val:
        case str():
            return val
        case Mapping():
            return {k: remove_literals(v, literal) for k, v in val.items() if not _is_literal(v)}
        case Iterable():
            return [remove_literals(v, literal) for v in val if not _is_literal(v)]
        case _:
            return val


def clean_http_params_for_urlencode(val: Any) -> Any:
    """Recursively cleans kwargs for use as URL query parameters.

    - None and False are excluded (HA treats param presence as enabled)
    - True is converted to "true"
    - datetime objects are converted to ISO format
    - Other values are kept as-is
    """
    match val:
        case True:
            return "true"
        case str() | int() | float():
            return val
        case datetime():
            return val.isoformat()
        case Mapping():
            return {
                k: clean_http_params_for_urlencode(v)
                for k, v in val.items()
                if v is not None and v is not False
            }
        case Iterable():
            return [
                clean_http_params_for_urlencode(v)
                for v in val
                if v is not None and v is not False
            ]
        case _:
            return str(val)


def convert_json(data, **kwargs):
    def fallback_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    return json.dumps(data, default=fallback_serializer, **kwargs)


def warning_decorator(
    start_text: str | None = None,
    success_text: str | None = None,
    error_text: str | None = None,
    finally_text: str | None = None,
    reraise: bool = False,
) -> Callable[[Callable[..., Coroutine[Any, Any, R]]], Callable[..., Coroutine[Any, Any, R | None]]]:
    """Decorate an async function to log messages at various stages around it running.

    By default this does not reraise any exceptions that occur during the execution of the wrapped function.

    Only works on methods of AppDaemon subsystems because it uses the attributes:
        - self.logger
        - self.AD

    Raises:
        By default, only ever re-raises an AppDaemonException

    """

    def decorator(func: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., Coroutine[Any, Any, R | None]]:
        @functools.wraps(func)
        async def wrapper(self, *args: Any, **kwargs: Any) -> R | None:
            logger: Logger = self.logger
            error_logger: Logger = self.error
            nonlocal error_text
            error_text = error_text or f"Unexpected error running {func.__qualname__}"
            try:
                nonlocal start_text
                if start_text is not None:
                    logger.debug(start_text)

                result = await func(self, *args, **kwargs)
            except SyntaxError as e:
                logger.warning(error_text)
                log_warning_block(error_logger, header=error_text, exception_text="".join(traceback.format_exception(e, limit=-1)))
            except ade.AppDaemonException as e:
                raise e
            except ValidationError as e:
                log_warning_block(error_logger, header=error_text, exception_text=str(e))
            except Exception as e:
                log_warning_block(
                    error_logger,
                    exception_text=format_exception(e),
                    header=error_text,
                )

                if self.AD.logging.separate_error_log():
                    logger.warning(
                        "Logged an error to %s",
                        self.AD.logging.get_filename("error_log"),
                    )
                if reraise:
                    raise e
            else:
                nonlocal success_text
                if success_text:
                    logger.debug(success_text)
                return result
            finally:
                nonlocal finally_text
                if finally_text:
                    logger.debug(finally_text)

        return wrapper

    return decorator


def format_exception(e):
    # return "\n\n" + "".join(traceback.format_exception_only(e))
    return traceback.format_exc()


def log_warning_block(logger: Logger, exception_text: str, header: str | None = None, width: int = 60) -> None:
    logger.warning("-" * width)
    logger.warning(header or "Unexpe")
    exception_text = ("-" * 60) + "\n" + exception_text
    logger.warning(exception_text)
    logger.warning("-" * 60)
