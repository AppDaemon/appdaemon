"""Tests for :py:class:`~appdaemon.utils.state.PersistentDict`, the shelf behind persistent namespaces."""

import sys
import threading
from pathlib import Path

import pytest
from appdaemon.utils.state import ADWritebackType, PersistentDict, find_unreadable_store_files

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]

GDBM_HEADER = (0x13579ACE).to_bytes(4, sys.byteorder) + b"\0" * 60


def run_in_thread(func):
    """Run ``func`` in a new thread, re-raising whatever it raised."""
    errors: list[BaseException] = []

    def target():
        try:
            func()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


@pytest.mark.parametrize("writeback_type", list(ADWritebackType))
def test_used_from_another_thread(tmp_path: Path, writeback_type: ADWritebackType) -> None:
    """The store is opened on the main thread and used from app worker threads.

    On Python 3.13+ a new store defaults to ``dbm.sqlite3``, whose connection refuses use from other threads.
    """
    db = PersistentDict(tmp_path / "ns.db", writeback_type=writeback_type)
    db["main"] = 1

    def worker():
        assert db["main"] == 1
        db["worker"] = 2
        assert "worker" in db
        assert len(db) == 2
        assert sorted(db) == ["main", "worker"]
        del db["main"]
        db.update({"bulk": 3}, save=True)
        db.sync()

    run_in_thread(worker)
    db.close()

    reopened = PersistentDict(tmp_path / "ns.db")
    assert dict(reopened) == {"worker": 2, "bulk": 3}
    reopened.close()


def test_many_threads(tmp_path: Path) -> None:
    db = PersistentDict(tmp_path / "ns.db")
    threads = [threading.Thread(target=lambda i=i: db.__setitem__(f"k{i}", i)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert dict(db) == {f"k{i}": i for i in range(20)}
    db.close()


@pytest.mark.skipif(sys.version_info < (3, 13), reason="dbm.sqlite3 was added in Python 3.13")
def test_existing_sqlite_store_used_from_another_thread(tmp_path: Path) -> None:
    """Stores that AppDaemon already created with dbm.sqlite3 open as before and work across threads."""
    import dbm.sqlite3
    import shelve

    path = tmp_path / "ns.db"
    with shelve.Shelf(dbm.sqlite3.open(str(path), "c")) as shelf:
        shelf["old"] = "value"
    assert dbm.whichdb(str(path)) == "dbm.sqlite3"

    db = PersistentDict(path)
    run_in_thread(lambda: db.__setitem__("new", db["old"]))
    assert dict(db) == {"old": "value", "new": "value"}
    db.close()


def test_existing_dumb_store_still_opens(tmp_path: Path) -> None:
    """Existing stores in other formats keep opening with the backend that created them."""
    import dbm.dumb
    import shelve

    path = tmp_path / "ns.db"
    # Before Python 3.13, PersistentDict drops the suffix from the file name
    store_path = path if sys.version_info >= (3, 13) else path.with_suffix("")
    with shelve.Shelf(dbm.dumb.open(str(store_path), "c")) as shelf:
        shelf["old"] = "value"

    db = PersistentDict(path)
    assert db.filepath == store_path
    assert dbm.whichdb(str(db.filepath)) == "dbm.dumb"
    run_in_thread(lambda: db.__setitem__("new", db["old"]))
    assert dict(db) == {"old": "value", "new": "value"}
    db.close()


def test_no_warning_for_new_or_readable_store(tmp_path: Path) -> None:
    path = tmp_path / "ns.db"
    assert find_unreadable_store_files(path) == []
    PersistentDict(path).close()
    assert find_unreadable_store_files(path) == []


def test_gdbm_file_without_gdbm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A single-file GDBM store on a Python built without ``_gdbm`` (e.g. uv's python-build-standalone)."""
    (tmp_path / "ns.db").write_bytes(GDBM_HEADER)
    monkeypatch.setitem(sys.modules, "dbm.gnu", None)  # makes `import dbm.gnu` raise ImportError

    [(path, reason)] = find_unreadable_store_files(tmp_path / "ns.db")
    assert path == tmp_path / "ns.db"
    assert "GDBM" in reason


def test_gdbm_file_with_gdbm_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "ns.db").write_bytes(GDBM_HEADER)
    monkeypatch.setattr("appdaemon.utils.state._backend_available", lambda module: True)
    assert find_unreadable_store_files(tmp_path / "ns.db") == []


@pytest.mark.parametrize("ndbm_can_open", [False, True])
def test_gdbm_pag_dir_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ndbm_can_open: bool) -> None:
    """A ``.pag``/``.dir`` pair written through GDBM's ndbm compatibility layer is only a problem if dbm.ndbm can't open it."""
    (tmp_path / "ns.db.pag").write_bytes(GDBM_HEADER)
    (tmp_path / "ns.db.dir").write_bytes(b"")
    monkeypatch.setattr("appdaemon.utils.state._ndbm_can_open", lambda filepath: ndbm_can_open)

    problems = find_unreadable_store_files(tmp_path / "ns.db")
    if ndbm_can_open:
        assert problems == []
    else:
        [(path, reason)] = problems
        assert path == tmp_path / "ns.db.pag"
        assert "GDBM" in reason
