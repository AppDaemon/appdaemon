"""
Exceptions used by appdaemon

"""


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
