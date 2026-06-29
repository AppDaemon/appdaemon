"""Compatibility exports for the :mod:`appdaemon.utils` package.

Historically, many modules imported helpers from ``appdaemon.utils`` as a
flat module. Keep these re-exports so older call sites continue to work while
the internals are split across submodules.
"""

from appdaemon.version import __version__, __version_comments__

from .functools import convert_json
from .functools import remove_literals
from .file import read_config_file
from .perf import get_object_size
from .str import format_timedelta
from .threading import run_in_executor

__all__ = [
    "__version__",
    "__version_comments__",
    "convert_json",
    "remove_literals",
    "read_config_file",
    "get_object_size",
    "format_timedelta",
    "run_in_executor",
]
