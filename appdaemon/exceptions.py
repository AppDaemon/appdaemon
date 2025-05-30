"""
Exceptions used by appdaemon

"""
import asyncio
import functools
import inspect
import json
import logging
import sys
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
    user_exception_block(
        logging.getLogger('Error'),
        context.get('exception'),
        appdaemon.app_dir,
        header='Unhandled exception in event loop'
    )


def user_exception_block(logger: Logger, exception: AppDaemonException, app_dir: Path, header: str | None = None):
    """Function to generate a user-friendly block of text for an exception. Gets the whole chain of exception causes to decide what to do.
    """
    width = 75
    spacing = 4
    inset = 5
    if header is not None:
        header = f'{"=" * inset}  {header}  {"=" * (width - spacing - inset - len(header))}'
    else:
        header = '=' * width
    logger.error(header)

    chain = get_exception_cause_chain(exception)

    for i, exc in enumerate(chain):
        indent = ' ' * i * 2

        match exc:
            case ValidationError():
                errors = exc.errors()
                if errors[0]['type'] == 'missing':
                    app_name = errors[0]['loc'][0]
                    field = errors[0]['loc'][-1]
                    logger.error(f"{indent}App '{app_name}' is missing required field: {field}")
                    continue
            case AppDaemonException():
                for i, line in enumerate(str(exc).splitlines()):
                    if i == 0:
                        logger.error(f'{indent}{exc.__class__.__name__}: {line}')
                    else:
                        logger.error(f'{indent}  {line}')

                if user_line := get_user_line(exc, app_dir):
                    for line, filename, func_name in list(user_line)[::-1]:
                        logger.error(f'{indent}{filename} line {line} in {func_name}')
            case OSError() if str(exc).endswith('address already in use'):
                logger.error(f'{indent}{exc.__class__.__name__}: {exc}')
            case NameError() | ImportError():
                logger.error(f'{indent}{exc.__class__.__name__}: {exc}')
                if tb := traceback.extract_tb(exc.__traceback__):
                    frame = tb[-1]
                    file = Path(frame.filename).relative_to(app_dir.parent)
                    logger.error(f'{indent}  line {frame.lineno} in {file.name}')
                    logger.error(f'{indent}  {frame._line.rstrip()}')
                    error_len = frame.end_colno - frame.colno
                    logger.error(f'{indent}  {" " * (frame.colno - 1)}{"^" * error_len}')
            case SyntaxError():
                logger.error(f'{indent}{exc.__class__.__name__}: {exc}')
                logger.error(f'{indent}  {exc.text.rstrip()}')

                if exc.end_offset == 0:
                    error_len = len(exc.text) - exc.offset
                else:
                    error_len = exc.end_offset - exc.offset
                logger.error(f'{indent}  {" " * (exc.offset - 1)}{"^" * error_len}')
            case _:
                logger.error(f'{indent}{exc.__class__.__name__}: {exc}')
                if tb := traceback.extract_tb(exc.__traceback__):
                    # filtered = (fs for fs in tb if 'appdaemon' in fs.filename)
                    # filtered = tb
                    # ss = traceback.StackSummary.from_list(filtered)
                    lines = (line for fl in tb.format() for line in fl.splitlines())
                    for line in lines:
                        logger.error(f'{indent}{line}')

    logger.error('=' * width)


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
@dataclass
class RequestHandlerException(AppDaemonException):
    msg: str

    def __str__(self):
        return f"Error handling HTTP request: {self.msg}"


@dataclass
class PersistentNamespaceFailed(AppDaemonException):
    namespace: str
    path: Path

    def __str__(self):
        return f"Failed to create persistent namespace '{self.namespace}' at '{self.path}'"


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
    domain_services: list[str]

    def __str__(self):
        return (
            f"domain '{self.domain}' exists in namespace '{self.namespace}', "
            f"but does not contain service '{self.service}'. "
            f"Services that exist in {self.domain}: {', '.join(self.domain_services)}"
        )


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
    app_name: Path
    cfg: Any

    def __str__(self):
        return f"The key/value pair of {self.app_name}={self.cfg} is not valid"


@dataclass
class BadAppConfigFile(AppDaemonException):
    path: Path


class TimeOutException(AppDaemonException):
    pass


class StartupAbortedException(AppDaemonException):
    pass


@dataclass
class HTTPHostError(AppDaemonException):
    port: int

    def __str__(self):
        res = "Invalid host specified in URL for HTTP component\n"
        res += "As of AppDaemon 4.5 the host name specified in the URL must resolve to a known host\n"
        res += "You can restore previous behavior by using `0.0.0.0` as the host portion of the URL\n"
        res += f"For instance: `http://0.0.0.0:{self.port}`\n"
        return res


@dataclass
class HTTPFailure(AppDaemonException):
    url: str

    def __str__(self):
        return f"Failed to start HTTP service at '{self.url}'"


@dataclass
class AppStartFailure(AppDaemonException):
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


@dataclass
class PinOutofRange(AppDaemonException):
    pin_thread: int
    total_threads: int

    def __str__(self):
        return f"Pin thread {self.pin_thread} out of range. Must be between 0 and {self.total_threads - 1}"

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
class FailedImport(AppDaemonException):
    module_name: str
    app_dir: Path

    def __str__(self):
        res = f"Failed to import '{self.module_name}'\n"
        if isinstance(self.__cause__, ModuleNotFoundError):
            res += "Import paths:\n"
            paths = set(
                p for p in sys.path
                if Path(p).is_relative_to(self.app_dir)
            )
            res += '\n'.join(f'  {p}' for p in sorted(paths))
        return res


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
    bad_seq: Any | None = None

    def __str__(self):
        res = "Failed to execute sequence:"
        if isinstance(self.bad_seq, str):
            res += f' {self.bad_seq}'
        return res


class BadSchedulerCallback(AppDaemonException):
    pass


@dataclass
class BadSequenceStepDefinition(AppDaemonException):
    step: Any

    def __str__(self):
        return f"Bad sequence step definition: {self.step}"


@dataclass
class SequenceStepExecutionFail(AppDaemonException):
    n: int
    step: Any
