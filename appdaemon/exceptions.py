"""
Exceptions used by appdaemon

"""
import asyncio
import functools
import inspect
import json
import logging
import traceback
from abc import ABC
from collections.abc import Iterable
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Type

from pydantic import ValidationError

if TYPE_CHECKING:
    from .appdaemon import AppDaemon


# This has to go here to prevent circular imports because the utils module already imports this one
def get_callback_sig(funcref) -> str:
    if isinstance(funcref, functools.partial):
        funcref = funcref.func
    sig = inspect.signature(funcref)
    return f"{funcref.__qualname__}{sig}"


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


def user_exception_block(logger: Logger, exception: AppDaemonException, app_dir: Path, header: str | None = None):
    """Function to generate a user-friendly block of text for an exception. Gets the whole chain of exception causes to decide what to do.
    """
    width = 75
    inset = 5
    if header is not None:
        header = f'{"=" * inset}  {header}  {"=" * (width - inset - len(header))}'
    else:
        header = '=' * width
    logger.error(header)

    chain = get_exception_cause_chain(exception)

    if isinstance(chain[-1], TypeError):
        chain.pop(-1)

    for i, exc in enumerate(chain):
        indent = ' ' * i * 2

        if isinstance(exc, ValidationError):
            errors = exc.errors()
            if errors[0]['type'] == 'missing':
                app_name = errors[0]['loc'][0]
                field = errors[0]['loc'][-1]
                logger.error(f"{indent}App '{app_name}' is missing required field: {field}")
                continue

        for i, line in enumerate(str(exc).splitlines()):
            if i == 0:
                logger.error(f'{indent}{exc.__class__.__name__}: {line}')
            else:
                logger.error(f'{indent}  {line}')

        if user_line := get_user_line(exc, app_dir):
            for line, filename, func_name in list(user_line)[::-1]:
                logger.error(f'{indent}{filename} line {line} in {func_name}')
    logger.error('=' * 75)


def unexpected_block(logger: Logger, exception: Exception):
    logger.error('=' * 75)
    logger.error(f'Unexpected error: {exception}')
    formatted = traceback.format_exc()
    for line in formatted.splitlines():
        logger.error(line)
    logger.error('=' * 75)


def get_cause_lines(chain: Iterable[Exception]) -> dict[Exception, list[traceback.FrameSummary]]:
    tracebacks = (traceback.extract_tb(exc.__traceback__) for exc in chain)
    return {exc.__class__.__name__: tb for exc, tb in zip(chain, tracebacks)}


def get_user_line(exception: Exception, base: Path):
    """Function to get the line number and filename of the user code that caused an exception"""
    if tb := traceback.extract_tb(exception.__traceback__):
        for filename, line, func, _ in tb:
            path = Path(filename)
            if path.is_relative_to(base):
                yield line, path.relative_to(base.parent), func


def get_exception_cause_chain(exception: Exception, current_chain: list[Exception] | None = None):
    current_chain = current_chain or list()
    current_chain.append(exception)
    if cause := exception.__cause__:
        return get_exception_cause_chain(cause, current_chain)
    else:
        return current_chain


def wrap_async(logger: Logger, app_dir: Path, header: str | None = None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except AppDaemonException as e:
                user_exception_block(logger, e, app_dir, header)
            except Exception as e:
                unexpected_block(logger, e)
        return wrapper
    return decorator


def wrap_sync(logger: Logger, app_dir: Path, header: str | None = None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except AppDaemonException as e:
                user_exception_block(logger, e, app_dir, header)
            except Exception as e:
                unexpected_block(logger, e)
        return wrapper
    return decorator


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
class AppCallbackFail(AppDaemonException):
    """Base class for exceptions caused by callbacks made in user apps."""
    app_name: str
    funcref: functools.partial

    def __str__(self, base: str | None = None):
        base = base or f"Callback failed for app '{self.app_name}'"

        if args := self.funcref.args:
            base += f'\nargs: {args}'

        if kwargs := self.funcref.keywords:
            base += f'\nkwargs: {json.dumps(kwargs, indent=4, default=str)}'

        return base


@dataclass
class StateCallbackFail(AppCallbackFail):
    entity: str

    def __str__(self):
        res = super().__str__(f"State callback failed for '{self.entity}' from '{self.app_name}'")

        # Type errors are a special case where we can give some more advice about how the callback should be written
        if isinstance(self.__cause__, TypeError):
            res += f'\n{self.__cause__}'
            res += '\nState callbacks should have the following signature:'
            res += '\n  state_callback(self, entity, attribute, old, new, **kwargs)'
            res += '\nSee https://appdaemon.readthedocs.io/en/latest/APPGUIDE.html#state-callbacks for more information'

        return res


@dataclass
class SchedulerCallbackFail(AppCallbackFail):
    def __str__(self):
        res = super().__str__(f"Scheduled callback failed for app '{self.app_name}'")

        if isinstance(self.__cause__, TypeError):
            res += f'\nCallback has signature: {get_callback_sig(self.funcref)}'
            res += f'\n{self.__cause__}\n'
        return res


@dataclass
class EventCallbackFail(AppCallbackFail):
    event: str | None = None

    def __str__(self):
        res = super().__str__(f"Scheduled callback failed for app '{self.app_name}'")

        if isinstance(self.__cause__, TypeError):
            res += f'\n{self.__cause__}'
            res += '\nState callbacks should have the following signature:'
            res += '\n  my_callback(self, event_name, data, **kwargs):'
            res += '\nSee https://appdaemon.readthedocs.io/en/latest/APPGUIDE.html#event-callbacks for more information'
        return res


@dataclass
class CallbackException(AppDaemonException):
    callback: str
    app_name: str

    def __str__(self):
        return f"error in method '{self.callback}' for app '{self.app_name}'"


@dataclass
class BadAppConfig(AppDaemonException):
    path: Path


class TimeOutException(AppDaemonException):
    pass


class StartupAbortedException(AppDaemonException):
    pass


@dataclass
class StartFailure(AppDaemonException):
    app_name: str

    def __str__(self):
        return f"App '{self.app_name}' failed to start"


@dataclass
class MissingAppClass(AppDaemonException):
    app_name: str
    module: str
    file: Path
    class_name: str

    def __str__(self):
        res = f"{self.module} does not have a class named '{self.class_name}'\n"
        res += f"Module path: {self.file}"
        return res


class PinOutofRange(AppDaemonException):
    pass


@dataclass
class BadClassSignature(AppDaemonException):
    class_name: str

    def __str__(self):
        return f"Class '{self.class_name}' takes the wrong number of arguments. Check the inheritance"


@dataclass
class AppDependencyError(AppDaemonException):
    app_name: str
    rel_path: Path
    dep_name: str
    dependencies: set[str]

    def __str__(self, base: str = ''):
        res = base
        res += f"\nall dependencies: {self.dependencies}"
        res += f"\n{self.rel_path}"
        return res


@dataclass
class DependencyMissing(AppDependencyError):
    def __str__(self):
        return super().__str__(f"'{self.app_name}' depends on '{self.dep_name}', but it's wasn't found")


@dataclass
class DependencyNotRunning(AppDependencyError):
    def __str__(self):
        return super().__str__(f"'{self.app_name}' depends on '{self.dep_name}', but it's not running")


@dataclass
class GlobalNotLoaded(AppDependencyError):
    def __str__(self):
        return super().__str__(f"'{self.app_name}' depends on '{self.dep_name}', but it's not loaded")


@dataclass
class AppModuleNotFound(AppDaemonException):
    module_name: str

    def __str__(self):
        return f"Unable to import '{self.module_name}'"


@dataclass
class AppInstantiationError(AppDaemonException):
    app_name: str
    # class_name: str

    def __str__(self):
        return f"Failed to create object for '{self.app_name}'"


@dataclass
class NoInitializeMethod(AppDaemonException):
    class_ref: Type
    module_path: Path

    def __str__(self):
        res = f"{self.class_ref} does not have an initialize method\n"
        res += f"{self.module_path}"
        return res


@dataclass
class BadInitializeMethod(AppDaemonException):
    class_ref: Type
    module_path: Path
    signature: inspect.Signature

    def __str__(self):
        res = f"{self.class_ref} has a bad initialize method\n"
        res += f"{self.class_ref.__name__}.initialize{self.signature}\n"
        res += f"{self.module_path}"
        return res


@dataclass
class InitializationFail(AppDaemonException):
    app_name: str

    def __str__(self):
        res = f"initialize() method failed for app '{self.app_name}'"
        if isinstance(self.__cause__, TypeError):
            res += f'\n{self.__cause__}'
            res += '\ninitialize() should be structured like this:'
            res += '\n  def initialize(self):'
            # res += '\n      ...'
        return res


class BadUserServiceCall(AppDaemonException):
    pass


@dataclass
class ConfigReadFailure(AppDaemonException):
    file: Path


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
