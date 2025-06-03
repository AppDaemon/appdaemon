from abc import ABC
from copy import deepcopy
from dataclasses import InitVar, dataclass, field
from pathlib import Path
from typing import Iterable

from .dependency import find_all_dependents, get_dependency_graph, get_full_module_name, reverse_graph, topo_sort
from .models.config.app import AllAppConfig, BaseApp
from .models.internal.file_check import FileCheck


@dataclass
class Dependencies(ABC):
    """Wraps an instance of ``FileCheck`` with a corresponding set of dependency graphs."""

    files: FileCheck = field(repr=False)
    ext: str = field(init=False)  # this has to be defined by the children classes
    dep_graph: dict[str, set[str]] = field(init=False)
    rev_graph: dict[str, set[str]] = field(init=False)
    bad_files: set[tuple[Path, float]] = field(default_factory=set, init=False)

    def __post_init__(self):
        self.refresh_dep_graph()

    def update(self, new_files: Iterable[Path]):
        self.files.update(new_files)
        for bf, mtime in deepcopy(self.bad_files):
            new_mtime = self.files.mtimes.get(bf)
            if new_mtime != mtime:
                assert new_mtime > mtime, f"File {bf} was modified in the future"
                self.bad_files.remove((bf, mtime))

        self.refresh_dep_graph()

    def refresh_dep_graph(self):
        raise NotImplementedError

    @classmethod
    def from_path(cls, path: Path):
        return cls.from_paths(path.rglob(f"*{cls.ext}"))

    @classmethod
    def from_paths(cls, paths: Iterable[Path]):
        return cls(files=FileCheck.from_paths(paths))

    def get_dependents(self, items: str | Iterable[str]) -> set[str]:
        """Uses ``find_all_dependents`` with the reversed graph to get the transitive
        closure for the given items.."""
        items = {items} if isinstance(items, str) else set(items)
        # items = items if isinstance(items, set) else set(items)
        items |= find_all_dependents(items, self.rev_graph)
        return items


@dataclass
class PythonDeps(Dependencies):
    ext: str = ".py"

    def update(self, new_files: Iterable[Path]):
        """This also refreshes the dependency graph"""
        return super().update(new_files)

    def refresh_dep_graph(self):
        """This causes the all python files to get read from disk"""
        bad_files = set()
        if self.bad_files:
            bad_files, _ = zip(*self.bad_files)
            bad_files = set(bad_files)

        self.dep_graph, failed = get_dependency_graph(self.files, exclude=bad_files)

        for file in failed:
            self.bad_files.add((file, self.files.mtimes.get(file, 0)))

        self.rev_graph = reverse_graph(self.dep_graph)

    def modules_to_import(self) -> set[str]:
        """Takes the union of the ``new`` and ``modified`` file sets. and converts them to importable modules names"""
        files = self.files.new | self.files.modified
        nodes = set(get_full_module_name(file) for file in files)
        return nodes

    def modules_to_delete(self) -> list[str]:
        sub_graph = {(mod := get_full_module_name(file)): self.dep_graph[mod] for file in self.files.deleted}
        return topo_sort(sub_graph)


@dataclass
class AppDeps(Dependencies):
    app_config: AllAppConfig = field(init=False, repr=False)
    ext: str = ".yaml"

    def __post_init__(self):
        self.app_config = AllAppConfig.from_config_files(self.files)
        super().__post_init__()

    def refresh_dep_graph(self):
        """Refreshes the dependency graphs by iterating through the app config"""
        self.dep_graph = self.app_config.depedency_graph()
        self.rev_graph = reverse_graph(self.dep_graph)

    def direct_module_deps(self, apps: str | Iterable[str] | None = None) -> set[str]:
        """The modules that depend on the given apps. If no set of app names is given, then
        all apps are considered.

        Args:
            apps (set[str]): Optional subset of apps to consider
        """
        # Convert to a set, if necessary
        if apps is not None:
            apps = set(apps) if not isinstance(apps, set) else apps

        return set(
            app_cfg.module_name for app_name, app_cfg in self.app_config.root.items()
            if (apps is None or app_name in apps)
        )

    def direct_app_deps(self, modules: Iterable[str]):
        """Find the apps that directly depend on any of the given modules"""
        return set(
            app_name
            for app_name, app_cfg in self.app_config.root.items()
            if isinstance(app_cfg, BaseApp) and app_cfg.module_name in modules
        )

    def all_app_deps(self, modules: Iterable[str]) -> set[str]:
        """Uses ``find_all_dependents`` to get the transitive closure of all the apps
        that depend on the given modules."""
        apps = self.direct_app_deps(modules)
        return self.get_dependents(apps)


@dataclass
class DependencyManager:
    """Keeps track of all the python files and the app config files (either yaml or toml)

    Instantiating this class will walk the app_directory with ``pathlib.Path.rglob``
    to find all the files. This happens both for app config files and app python files.

    The main purpose of breaking this out from ``AppManagement`` is to make it
    independently testable.
    """

    python_files: InitVar[Iterable[Path]]
    config_files: InitVar[Iterable[Path]]
    python_deps: PythonDeps = field(init=False)
    app_deps: AppDeps = field(init=False)

    def __post_init__(self, python_files: Iterable[Path], config_files: Iterable[Path]):
        self.python_deps = PythonDeps.from_paths(python_files)
        self.app_deps = AppDeps.from_paths(config_files)

    @property
    def config_files(self) -> set[Path]:
        return set(self.app_deps.files.paths)

    def get_dependent_apps(self, modules: Iterable[str]) -> set[str]:
        """Finds all of the apps that depend on the given modules, even indirectly"""
        modules |= self.python_deps.get_dependents(modules)
        return self.app_deps.all_app_deps(modules)

    def update_python_files(self, new_files: Iterable[Path]):
        """Updates the dependency graph of python files.

        This is used to map which modules import which other modules and requires
        reading the contents of each python file to find the import statements.
        """
        return self.python_deps.update(new_files)

    def dependent_modules(self, modules: str | Iterable[str]):
        """Uses ``find_all_dependents`` with the reversed dependency graph to find the
        transitive closure of the python module dependencies."""
        return self.python_deps.get_dependents(modules)

    def modules_from_apps(self, apps: str | Iterable[str], dependents: bool = True) -> set[str]:
        """Find the importable names of all the python modules that the given apps depend on.

        This includes the transitive closure by default.

        Args:
            apps (str | Iterable[str]):
            dependents (bool): Whether to include the transitive closure
        """
        # These are the modules that are directly referenced in the app configs in the module key
        base_modules = self.app_deps.direct_module_deps(apps)
        if dependents:
            # This includes all the other indirectly dependent modules
            all_modules = self.python_deps.get_dependents(base_modules)
            return all_modules
        else:
            return base_modules

    def dependent_apps(self, modules: str | Iterable[str], transitive: bool = True) -> set[str]:
        """Find the apps that are dependent on any of the modules given. This includes the
        transitive closure of both the module and app dependencies."""
        if transitive:
            modules = self.dependent_modules(modules)
        return self.app_deps.all_app_deps(modules)

    def apps_to_terminate(self) -> set[str]:
        modules = self.python_deps.modules_to_delete()
        apps = self.dependent_apps(modules, transitive=False)
        return apps

    # Currently unused
    def modules_to_import(self) -> set[str]:
        return self.python_deps.modules_to_import()

    def python_sort(self, modules: set[str]) -> set[str]:
        modules |= self.dependent_modules(modules)
        order = [n for n in topo_sort(self.python_deps.dep_graph) if n in modules]

        # Namespace packages won't be in the graph, so we add them to the end
        # https://docs.python.org/3/reference/import.html#namespace-packages
        if (diff := modules - set(order)):
            order.extend(diff)

        return order
