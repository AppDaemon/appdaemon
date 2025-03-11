"""
Exceptions used by appdaemon

"""
from collections.abc import Coroutine
from dataclasses import dataclass
import functools
import json
import shutil
import traceback
from abc import ABC
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .adbase import ADBase


def get_user_line(exception: Exception, base: Path) -> tuple[int, str]:
    if tb := traceback.extract_tb(exception.__traceback__):
        for filename, line, func, _ in tb:
            if Path(filename).is_relative_to(base):
                return line, filename


def get_exception_cause_chain(exception: Exception, current_chain: list[Exception] | None = None):
    current_chain = current_chain or list()
    current_chain.append(exception)
    if cause := exception.__cause__:
        return get_exception_cause_chain(cause, current_chain)
    else:
        return current_chain


def get_log_offset(app_name: str) -> int:
    return 35 + len(app_name)


def log_exception_block(exception: Exception, logger: Logger, app_name: str, base: Path):
    width = shutil.get_terminal_size().columns - get_log_offset(app_name)
    logger.error('=' * width)
    log_exception_chain(exception, logger, base)
    logger.error('=' * width)


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
        case BadSequence():
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
    # elif exception.__context__:
    #     logger.error(f'Context: {exception.__context}')
    #     pass


def wrap_app_method(method: Callable):
    @functools.wraps(method)
    def wrapped(*args, **kwargs):
        try:
            # Check if the method is a functools.partial object
            if isinstance(method, functools.partial):
                original_method = method.func
            else:
                original_method = method

            app: "ADBase" = original_method.__self__
            logger = app.err

            return method(*args, **kwargs)
        except AppDaemonException as exc:
            log_exception_block(exc, logger, app.name, app.app_dir)

    return wrapped


def wrap_async_method(method: Coroutine[Any, Any, Any]):
    @functools.wraps(method)
    async def wrapped(self, *args, **kwargs):
        try:
            return await method(self, *args, **kwargs)
        except AppDaemonException as exc:
            # self = args[0]
            logger = self.error
            log_exception_block(exc, logger, kwargs['calling_app'], self.AD.app_dir)
            pass

    return wrapped


class AppDaemonException(Exception, ABC):
    """Abstract base class for all AppDaemon exceptions to inherit from"""
    pass

class RequestHandlerException(AppDaemonException):
    pass


class NamespaceException(AppDaemonException):
    pass


class DomainException(AppDaemonException):
    pass


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


class AppInitializeError(AppDaemonException):
    pass


class NoObject(AppDaemonException):
    pass


class NoInitializeMethod(AppDaemonException):
    pass


class BadInitializeMethod(AppDaemonException):
    pass


class BadUserServiceCall(AppDaemonException):
    pass


class ConfigReadFailure(AppDaemonException):
    pass


@dataclass
class BadSequence(AppDaemonException):
    msg: str
    bad_seq: Any

    def __post_init__(self):
        super(Exception, self).__init__(self.msg)


class BadSequenceStep(AppDaemonException):
    pass
