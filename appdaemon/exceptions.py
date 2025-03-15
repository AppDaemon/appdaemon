"""
Exceptions used by appdaemon

"""
import asyncio
import json
import logging
import traceback
from abc import ABC
from collections.abc import Iterable
from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .appdaemon import AppDaemon

@dataclass
class AppDaemonException(Exception, ABC):
    """Abstract base class for all AppDaemon exceptions to inherit from"""
    # msg: str

    def __post_init__(self):
        if msg := getattr(self, 'msg', None):
            super(Exception, self).__init__(msg)


def exception_handler(appdaemon: "AppDaemon", loop: asyncio.AbstractEventLoop, context: dict):
    """Handler to attach to the main event loop as a backstop for any async exception"""
    user_exception_block(logging.getLogger('Error'), context['exception'], appdaemon.app_dir)


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
        for i, line in enumerate(str(exc).splitlines()):
            if i == 0:
                logger.error(f'{indent}{exc.__class__.__name__}: {line}')
            else:
                logger.error(f'{indent}  {line}')

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


# Used in the adstream module
class RequestHandlerException(AppDaemonException):
    pass


@dataclass
class NamespaceException(AppDaemonException):
    namespace: str

    def __str__(self):
        return f"Unknown namespace '{self.namespace}'"


@dataclass
class DomainException(AppDaemonException):
    namespace: str
    domain: str

    def __str__(self):
        return f"domain '{self.domain}' does not exist in namespace '{self.namespace}'"


@dataclass
class ServiceException(AppDaemonException):
    namespace: str
    domain: str
    service: str

    def __str__(self):
        return f"domain '{self.domain}' exists in namespace '{self.namespace}', but does not contain service '{self.service}'"


@dataclass
class CallbackException(AppDaemonException):
    callback: str
    app_name: str

    def __str__(self):
        return f"error in method '{self.callback}' for app '{self.app_name}'"
    

@dataclass
class StateCallbackFail(AppDaemonException):
    app_name: str
    entity_id: str
    args: dict[str, Any]

    def __str__(self):
        return f"State callback failed for '{self.entity_id}' in app '{self.app_name}'"


@dataclass
class SchedulerCallbackFail(AppDaemonException):
    app_name: str
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)

    def __str__(self):
        base = f"Scheduler callback failed for app '{self.app_name}'"

        if self.args:
            base += f'\nargs: {self.args}'

        if self.kwargs:
            base += f'\nkwargs: {json.dumps(self.kwargs, indent=4, default=str)}'

        return base


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


@dataclass
class BadSequenceStepDefinition(AppDaemonException):
    step: Any

    def __str__(self):
        return f"Bad sequence step definition: {self.step}"


@dataclass
class SequenceStepExecutionFail(AppDaemonException):
    step: Any
