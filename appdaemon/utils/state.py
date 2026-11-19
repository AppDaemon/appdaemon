import copy
import importlib
import shelve
import sqlite3
import sys
import threading
from collections.abc import Iterable
from contextlib import suppress
from enum import Enum
from pathlib import Path
from typing import Any


class ADWritebackType(str, Enum):
    """Represents different strategies for AppDaemon to write persistent namespaces to disk.

    See :py:meth:`shelve.open` for more details about writeback modes for the underlying shelf object and
    `user Defined Namespaces <https://appdaemon.readthedocs.io/en/latest/APPGUIDE.html#user-defined-namespaces>`_
    """
    safe = "safe"
    """The namespace is written to disk every time a change is made so will be up to date even if a crash happens. The
    downside is that there is a possible performance impact for systems with slower disks, or that set state on many
    UDNS at a time."""
    hybrid = "hybrid"
    """A compromise setting in which the namespaces are saved periodically (once each time around the utility loop,
    usually once every second- with this setting a maximum of 1 second of data will be lost if AppDaemon crashes."""


def _share_sqlite_connection(db: Any) -> None:
    """Let a ``dbm.sqlite3`` database be used from threads other than the one that opened it.

    Since Python 3.13, :py:mod:`dbm` creates new files with ``dbm.sqlite3``. Its connection is opened with the default
    ``check_same_thread=True``, so it raises :py:exc:`sqlite3.ProgrammingError` as soon as an app's worker thread touches
    a namespace that was opened on the main thread. The other backends have no such restriction.

    ``dbm.sqlite3`` has no option for this, so the connection is replaced with an equivalent one to the same file that
    allows cross-thread use. Access is serialized by :py:attr:`PersistentDict.rlock`.
    """
    try:
        from dbm.sqlite3 import _Database
    except ImportError:
        return
    if not isinstance(db, _Database):
        return

    old_cx: sqlite3.Connection = db._cx
    # (seq, name, file) of the main database; resolves the path the same way dbm.sqlite3 did
    db_file = old_cx.execute("PRAGMA database_list").fetchone()[2]
    new_cx = sqlite3.connect(db_file, autocommit=True, check_same_thread=False)
    with suppress(sqlite3.OperationalError):
        new_cx.execute("PRAGMA journal_mode = wal")
    old_cx.close()
    db._cx = new_cx


_SQLITE_HEADER = b"SQLite format 3\0"
# Magic numbers at the start of a GDBM file, as checked by dbm.whichdb (plus the GDBM >= 1.21 extended format)
_GDBM_MAGICS = {0x13579ACD, 0x13579ACE, 0x13579ACF, 0x13579AD0, 0x13579AD1}


def _backend_available(module: str) -> bool:
    try:
        importlib.import_module(module)
    except ImportError:
        return False
    return True


def _sniff_backend(path: Path) -> tuple[str, str] | None:
    """Return ``(module, description)`` for files whose format can be told from the header, without importing it."""
    try:
        with path.open("rb") as f:
            header = f.read(16)
    except OSError:
        return None
    if header.startswith(_SQLITE_HEADER):
        return "dbm.sqlite3", "SQLite"
    if len(header) >= 4 and _GDBM_MAGICS & {int.from_bytes(header[:4], "little"), int.from_bytes(header[:4], "big")}:
        return "dbm.gnu", "GDBM"
    return None


def find_unreadable_store_files(filepath: str | Path) -> list[tuple[Path, str]]:
    """Find files of an existing shelf at ``filepath`` that the running Python has no dbm backend for.

    :py:mod:`dbm` doesn't fail on these: it creates a new, empty store next to them instead, so the namespace silently
    starts empty. A common case is a GDBM store (a single file, or a ``.pag``/``.dir`` pair written through GDBM's ndbm
    compatibility layer) on a Python built without ``_gdbm``, such as the python-build-standalone builds used by uv.

    Returns:
        A list of ``(path, reason)`` tuples, empty if nothing is wrong.
    """
    filepath = Path(filepath)
    problems = []

    match _sniff_backend(filepath):
        case (module, description) if not _backend_available(module):
            problems.append((filepath, f"{description} database, but this Python has no {module} module"))

    # dbm.whichdb reports any .pag/.dir pair as dbm.ndbm without checking it. Depending on the library dbm.ndbm is
    # linked against, a .pag written by GDBM may not open, in which case dbm.ndbm creates a separate empty store.
    pag = filepath.with_name(f"{filepath.name}.pag")
    match _sniff_backend(pag):
        case ("dbm.gnu", description) if not _ndbm_can_open(filepath):
            problems.append((pag, f"{description} database that this Python's dbm.ndbm can't open"))

    return problems


def _ndbm_can_open(filepath: Path) -> bool:
    try:
        import dbm.ndbm
    except ImportError:
        return False
    try:
        dbm.ndbm.open(str(filepath), "r").close()
    except (dbm.ndbm.error, OSError):
        return False
    return True


class PersistentDict(shelve.DbfilenameShelf):
    """
    Dict-like object that uses a shelf to persist its contents.

    A “shelf” is a persistent, dictionary-like object. The difference with “dbm” databases is that the values (not the
    keys!) in a shelf can be essentially arbitrary Python objects — anything that the pickle module can handle. This
    includes most class instances, recursive data types, and objects containing lots of shared sub-objects. The keys are
    ordinary strings.
    """

    writeback_type: ADWritebackType
    safe: bool
    rlock: threading.RLock
    filepath: Path

    def __init__(self, filename: str | Path, writeback_type: ADWritebackType = ADWritebackType.safe) -> None:
        match writeback_type:
            case ADWritebackType.safe:
                # This is the default condition for shelf objects, which saves all assignments to the dict to disk.
                writeback = False
            case ADWritebackType.hybrid:
                # From the Python docs:
                # If the optional writeback parameter is set to True, all entries accessed are also cached in memory,
                # and written back on sync() and close(); this can make it handier to mutate mutable entries in the
                # persistent dictionary, but, if many entries are accessed, it can consume vast amounts of memory for
                # the cache, and it can make the close operation very slow since all accessed entries are written back
                # (there is no way to determine which accessed entries are mutable, nor which ones were actually mutated).
                writeback = True

        filepath = Path(filename).resolve()
        if sys.version_info.minor < 13:
            filepath = filepath.with_suffix("")
        else:
            filepath = filepath.with_suffix(".db")

        super().__init__(str(filepath), writeback=writeback)
        _share_sqlite_connection(self.dict)
        self.writeback_type = writeback_type
        self.safe = writeback_type == ADWritebackType.safe
        self.rlock = threading.RLock()
        self.filepath = filepath
        # print(f'PersistentDict using writeback mode: {self.writeback_type}, writeback={writeback}')

    @property
    def is_safe(self) -> bool:
        return self.writeback_type == ADWritebackType.safe

    def __contains__(self, key):
        with self.rlock:
            return super().__contains__(key)

    def __copy__(self):
        return dict(self)

    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self), memo=memo)

    def __delitem__(self, key):
        with self.rlock:
            super().__delitem__(key)

    def __getitem__(self, key):
        with self.rlock:
            return super().__getitem__(key)

    def __iter__(self):
        with self.rlock:
            for item in super().__iter__():
                yield item

    def __len__(self):
        with self.rlock:
            return super().__len__()

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, dict(self))

    def __setitem__(self, key, val):
        with self.rlock:
            super().__setitem__(key, val)
            if self.safe:
                self.sync()

    def sync(self):
        with self.rlock:
            super().sync()

    def update(self, new: dict[str, Any], save: bool = False) -> None:
        with self.rlock:
            for key, val in new.items():
                super().__setitem__(key, val)
            if self.is_safe or save:
                self.sync()


class AttrDict(dict):
    """Dictionary subclass whose entries can be accessed by attributes
    (as well as normally).
    """

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

    @staticmethod
    def from_nested_dict(data):
        """Construct nested AttrDicts from nested dictionaries."""
        if not isinstance(data, dict):
            return data
        else:
            return AttrDict({key: AttrDict.from_nested_dict(data[key]) for key in data})


class StateAttrs(dict):
    def __init__(self, dict):
        device_dict = {}
        devices = set()
        for entity in dict:
            if "." in entity:
                device, name = entity.split(".")
                devices.add(device)
        for device in devices:
            entity_dict = {}
            for entity in dict:
                if "." in entity:
                    thisdevice, name = entity.split(".")
                    if device == thisdevice:
                        entity_dict[name] = dict[entity]
            device_dict[device] = AttrDict.from_nested_dict(entity_dict)

        self.__dict__ = device_dict



def check_state(logger, new_state, callback_state, name) -> bool:
    passed = False

    try:
        if isinstance(callback_state, (str, int, float)):
            passed = new_state == callback_state

        elif isinstance(callback_state, Iterable):
            passed = new_state in callback_state

        elif callback_state.__name__ == "<lambda>":  # lambda function
            passed = callback_state(new_state)

    except Exception as e:
        logger.warning("Could not evaluate state check due to %s, from %s", e, name)
        passed = False

    return passed
