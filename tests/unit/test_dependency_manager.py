"""Tests for the dependency graph refresh in ``appdaemon.dependency_manager``."""

import os
from pathlib import Path

import pytest
from appdaemon.dependency_manager import AppDeps, Dependencies, PythonDeps

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


MODULE_A = """\
import os


def a():
    return os.getcwd()
"""

MODULE_B = """\
import module_a


def b():
    return module_a.a()
"""


@pytest.fixture
def app_dir(tmp_path: Path) -> Path:
    (tmp_path / "module_a.py").write_text(MODULE_A)
    (tmp_path / "module_b.py").write_text(MODULE_B)
    return tmp_path


def python_files(path: Path) -> set[Path]:
    return set(path.glob("*.py"))


class CountingPythonDeps(PythonDeps):
    """``PythonDeps`` that records how often the graph was actually rebuilt."""

    def refresh_dep_graph(self):
        self.refresh_count = getattr(self, "refresh_count", 0) + 1
        return super().refresh_dep_graph()


def test_graph_is_built_on_init(app_dir: Path):
    deps = CountingPythonDeps.from_paths(python_files(app_dir))

    assert deps.refresh_count == 1
    assert deps.dep_graph["module_b"] == {"module_a"}


def test_unchanged_files_do_not_rebuild_the_graph(app_dir: Path):
    """The utility loop calls ``update`` on every pass; re-parsing every file
    each time is what makes ``check_app_updates`` cost seconds (issue #2599)."""
    deps = CountingPythonDeps.from_paths(python_files(app_dir))
    before = deps.refresh_count
    graph_before = dict(deps.dep_graph)

    for _ in range(5):
        deps.update(python_files(app_dir))

    assert deps.refresh_count == before
    assert deps.dep_graph == graph_before


@pytest.mark.parametrize("change", ["modified", "new", "deleted"])
def test_changed_files_rebuild_the_graph(app_dir: Path, change: str):
    deps = CountingPythonDeps.from_paths(python_files(app_dir))
    before = deps.refresh_count

    if change == "modified":
        target = app_dir / "module_b.py"
        target.write_text(MODULE_B + "\nimport json\n")
        # mtime resolution can be coarse enough to hide a same-instant write
        stat = target.stat()
        os.utime(target, (stat.st_atime, stat.st_mtime + 10))
    elif change == "new":
        (app_dir / "module_c.py").write_text(MODULE_A)
    else:
        (app_dir / "module_b.py").unlink()

    deps.update(python_files(app_dir))

    assert deps.refresh_count == before + 1


def test_fixing_a_bad_file_retries_it(app_dir: Path):
    """A file that failed to parse is retried once it changes, because the fixed
    file lands in ``FileCheck.modified``."""
    broken = app_dir / "module_broken.py"
    broken.write_text("def oops(:\n")

    deps = CountingPythonDeps.from_paths(python_files(app_dir))
    assert broken in {path for path, _ in deps.bad_files}

    # Nothing changed: the bad file stays parked, no rebuild.
    before = deps.refresh_count
    deps.update(python_files(app_dir))
    assert deps.refresh_count == before
    assert broken in {path for path, _ in deps.bad_files}

    broken.write_text(MODULE_A)
    stat = broken.stat()
    os.utime(broken, (stat.st_atime, stat.st_mtime + 10))

    deps.update(python_files(app_dir))

    assert deps.refresh_count == before + 1
    assert broken not in {path for path, _ in deps.bad_files}
    assert "module_broken" in deps.dep_graph


def test_app_deps_still_refresh_unconditionally():
    """Only ``PythonDeps`` opts out: ``AppDeps.refresh_dep_graph`` is cheap and
    walks the already-parsed app config rather than the filesystem."""
    assert AppDeps.needs_refresh is Dependencies.needs_refresh
    assert PythonDeps.needs_refresh is not Dependencies.needs_refresh
