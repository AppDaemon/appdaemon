import copy
import shelve
import sys
import threading
from collections.abc import Iterable
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
