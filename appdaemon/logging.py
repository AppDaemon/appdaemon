import io
import traceback
import logging
import inspect
import datetime
from threading import local
from functools import wraps


class CallStackManager:

    def __init__(self):
        self._local = local()

    @property
    def call_stack(self):
        if not hasattr(self._local, 'call_stack'):
            self._local.call_stack = []
        return self._local.call_stack

    def __enter__(self):
        frame = inspect.currentframe()
        if frame is not None:
            frame = frame.f_back.f_back
        self.call_stack.append(frame)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.call_stack.pop()

call_stack_manager = CallStackManager()


class CallStackManagerLogger(logging.Logger):

    def findCaller(self, stack_info=False):
        call_stack = call_stack_manager.call_stack
        if not call_stack:
            return super().findCaller(stack_info)
        f = call_stack[0]
        if f is None:
            return super().findCaller(stack_info)

        co = f.f_code

        sinfo = None
        if stack_info:
            sio = io.StringIO()
            sio.write('Stack (most recent call last):\n')
            traceback.print_stack(f, file=sio)
            sinfo = sio.getvalue()
            if sinfo[-1] == '\n':
                sinfo = sinfo[:-1]
            sio.close()

        return co.co_filename, f.f_lineno, co.co_name, sinfo


class CustomFormatter(logging.Formatter):

    converter = datetime.datetime.fromtimestamp
    default_time_format = '%Y-%m-%d %H:%M:%S.%f'

    def __init__(self, fmt=None, datefmt=None, style='%', timestamp_conv=None):
        super().__init__(fmt, datefmt, style)
        if timestamp_conv:
            self.converter = timestamp_conv

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        if not datefmt:
            datefmt = self.default_time_format
        return dt.strftime(datefmt)


def log_limit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with call_stack_manager:
            return func(*args, **kwargs)
    return wrapper


logging.setLoggerClass(CallStackManagerLogger)
