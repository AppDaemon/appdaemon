"""
Exceptions used by appdaemon

"""
import asyncio
from collections.abc import Coroutine, Iterable
from dataclasses import dataclass
import functools
import json
import logging
from re import I
import shutil
import traceback
from abc import ABC
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

if TYPE_CHECKING:
    from .adbase import ADBase


@dataclass
class AppDaemonException(Exception, ABC):
    """Abstract base class for all AppDaemon exceptions to inherit from"""
    # msg: str

    def __post_init__(self):
        if msg := getattr(self, 'msg', None):
            super(Exception, self).__init__(msg)


def exception_handler(loop: asyncio.AbstractEventLoop, context: dict):
    """Handler to attach to the main event loop as a backstop for any async exception"""
    user_exception_block(logging.getLogger('Error'), context['exception'])


def user_exception_block(logger: Logger, exception: AppDaemonException, app_dir: Path):
    """Function to generate a user-friendly block of text for an exception. Gets the whole chain of exception causes to decide what to do.
    """
    chain = get_exception_cause_chain(exception)
    logger.error('=' * 75)

    # lines = get_cause_lines(chain)
    # user_lines = {exc.__class__.__name__: list(get_user_line(exc, app_dir)) for exc in chain}
    # pass
    for i, exc in enumerate(chain):
        indent = ' ' * i * 2
        logger.error(f'{indent}{exc.__class__.__name__}: {exc}')
        if user_line := get_user_line(exc, app_dir):
            for line, filename in list(user_line)[-1:]:
                logger.error(f'{indent}{filename} line {line}')
    logger.error('=' * 75)


def task_finisher(task: asyncio.Task, new_exc: AppDaemonException, logger: Logger, app_name: str):
    try:
        if exc := task.exception():
            raise new_exc from exc
    except AppDaemonException as final:
        user_exception_block(logger, final)


def get_cause_lines(chain: Iterable[Exception]) -> dict[Exception, list[traceback.FrameSummary]]:
    tracebacks = (traceback.extract_tb(exc.__traceback__) for exc in chain)
    return {exc.__class__.__name__: tb for exc, tb in zip(chain, tracebacks)}


def get_user_line(exception: Exception, base: Path):
    """Function to get the line number and filename of the user code that caused an exception"""
    if tb := traceback.extract_tb(exception.__traceback__):
        for filename, line, func, _ in tb:
            path = Path(filename)
            if path.is_relative_to(base):
                yield line, path.relative_to(base.parent)


def get_exception_cause_chain(exception: Exception, current_chain: list[Exception] | None = None):
    current_chain = current_chain or list()
    current_chain.append(exception)
    if cause := exception.__cause__:
        return get_exception_cause_chain(cause, current_chain)
    else:
        return current_chain


def get_log_offset(app_name: str) -> int:
    return 35 + len(app_name)


# def log_exception_block(exception: Exception, logger: Logger, app_name: str, base: Path):
#     width = shutil.get_terminal_size().columns - get_log_offset(app_name)
#     chain = get_exception_cause_chain(exception)
#     logger.error('=' * width)
#     log_exception_chain(exception, logger, base)
#     logger.error('=' * width)


def log_user_line(logger: Logger, exception: Exception, base: Path, indent: int):
    # chain = get_exception_cause_chain(exception)
    if user_line := get_user_line(exception, base):
        line, filename = user_line
        filename = Path(filename).relative_to(base.parent)
        logger.error(f'{indent}  {filename.as_posix()} line {line}')


def log_exception_chain(
    exception: Exception,
    logger: Logger,
    base: Path,
    level: int = 0,
    line: tuple = None,
):
    """Function to prettily format chains of exceptions that from repeatedly
    using the ``raise ... from ...`` syntax."""
    indent = level * 2 * ' '
    exc_name = exception.__class__.__name__

    logger.error(f'{indent}{exc_name}: {exception}')

    match exception:
        case SequenceExecutionFail():
            # if isinstance(exception.__cause__, BadSequenceStep):
            cause = exception.__cause__
            cause_name = cause.__class__.__name__
            logger.error(f'  {indent}{cause_name}: {cause}')

            offset = get_log_offset(logger.name.split('.')[-1]) * ' '
            seq_str = json.dumps(exception.bad_seq, indent=2, default=str)
            seq_str = '\n'.join(
                f'{indent}{offset}  {line}' if i != 0 else f'{indent}  {line}'
                for i, line in enumerate(seq_str.splitlines())
            )
            log_user_line(logger, exception, base, indent)

            logger.error(seq_str)
            return # Doesn't really matter what happened to directly cause this

        case BadUserServiceCall():
            log_exception_chain(exception.__cause__, logger, base, level + 1, line)
            log_user_line(logger, exception, base, indent)
            return

    if exception.__cause__:
        log_exception_chain(exception.__cause__, logger, base, level + 1, line)


def wrap_app_method(method: Callable):
    @functools.wraps(method)
    def wrapped(*args, **kwargs):
        try:
            # Check if the method is a functools.partial object
            if isinstance(method, functools.partial):
                original_method = method.func
            else:
                original_method = method

            app: ADBase = original_method.__self__
            logger = app.err

            return method(*args, **kwargs)
        except AppDaemonException as exc:
            # log_exception_block(exc, logger, app.name, app.app_dir)
            raise exc

    return wrapped


# def wrap_async_method(method: Coroutine[Any, Any, Any]):
#     @functools.wraps(method)
#     async def wrapped(self, *args, **kwargs):
#         try:
#             return await method(self, *args, **kwargs)
#         except AppDaemonException as exc:
#             # self = args[0]
#             logger = self.error
#             log_exception_block(exc, logger, kwargs['calling_app'], self.AD.app_dir)
#             pass

#     return wrapped


class RequestHandlerException(AppDaemonException):
    pass


class NamespaceException(AppDaemonException):
    pass


@dataclass
class DomainException(AppDaemonException):
    namespace: str
    domain: str
    service: str


class ServiceException(AppDaemonException):
    pass


class AppException(AppDaemonException):
    pass


class HandlerException(AppDaemonException):
    pass


class TimeOutException(AppDaemonException):
    pass


class StartupAbortedException(AppDaemonException):
    pass


class AppClassNotFound(AppDaemonException):
    pass


class PinOutofRange(AppDaemonException):
    pass


class AppClassSignatureError(AppDaemonException):
    pass


class AppDependencyError(AppDaemonException):
    pass


class AppModuleNotFound(AppDaemonException):
    pass


class AppInstantiationError(AppDaemonException):
    pass


class NoObject(AppDaemonException):
    pass


class NoInitializeMethod(AppDaemonException):
    pass


class BadInitializeMethod(AppDaemonException):
    pass


@dataclass
class InitializationFail(AppDaemonException):
    app_name: str
    msg: str = ''


class BadUserServiceCall(AppDaemonException):
    pass


class ConfigReadFailure(AppDaemonException):
    pass


@dataclass
class SequenceExecutionFail(AppDaemonException):
    msg: str
    bad_seq: Any | None = None


class BadSchedulerCallback(AppDaemonException):
    pass


class BadSequenceStepDefinition(AppDaemonException):
    pass


@dataclass
class SequenceStepExecutionFail(AppDaemonException):
    step: Any
