"""
Exceptions used by appdaemon

"""
import traceback
from logging import Logger


def log_exception_chain(exception: Exception, logger: Logger, level: int = 0):
    indent = level * 2 * ' '
    exc_name = exception.__class__.__name__
    logger.error(f'{indent}{exc_name}: {exception}')
    if exception.__cause__:
        log_exception_chain(exception.__cause__, logger, level + 1)
    elif exception.__context__:
        logger.error(f'Context: {exception.__context}')
        pass
    else:
        if tb := traceback.extract_tb(exception.__traceback__):
            filename, line, func, _ = tb[-1]
            logger.error(f'{indent}  line {line} in {filename}')
        pass


class RequestHandlerException(Exception):
    pass


class NamespaceException(Exception):
    pass


class DomainException(Exception):
    pass


class ServiceException(Exception):
    pass


class AppException(Exception):
    pass


class HandlerException(Exception):
    pass


class TimeOutException(Exception):
    pass


class StartupAbortedException(Exception):
    pass


class AppClassNotFound(Exception):
    pass


class PinOutofRange(Exception):
    pass


class AppClassSignatureError(Exception):
    pass


class AppDependencyError(Exception):
    pass


class AppModuleNotFound(Exception):
    pass


class AppInstantiationError(Exception):
    pass


class AppInitializeError(Exception):
    pass


class NoObject(Exception):
    pass


class NoInitializeMethod(Exception):
    pass


class BadInitializeMethod(Exception):
    pass


class ConfigReadFailure(Exception):
    pass


class BadSequence(Exception):
    pass


class BadSequenceStep(Exception):
    pass
