from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .dependency import find_all_dependents, get_dependency_graph, get_full_module_name, reverse_graph, topo_sort
from .models.app_config import AllAppConfig, AppConfig
from .models.internal.file_check import FileCheck


@dataclass
class Dependencies(ABC):
    files: FileCheck = field(repr=False)
    ext: str = field(init=False)  # this has to be defined by the children classes
    dep_graph: dict[str, set[str]] = field(init=False)
    rev_graph: dict[str, set[str]] = field(init=False)

    def __post_init__(self):
        self.refresh_dep_graph()

    def update(self, new_files: Iterable[Path]):
        self.files.update(new_files)
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
        """Uses ``find_all_dependents`` with the reversed graph to recursively find all the indirectly dependent nodes"""
        items = {items} if isinstance(items, str) else set(items)
        # items = items if isinstance(items, set) else set(items)
        items |= find_all_dependents(items, self.rev_graph)
        return items


@dataclass
class PythonDeps(Dependencies):
    ext: str = ".py"

    def update(self, new_files: Iterable[Path]):
        """This causes the python files to get read"""
        return super().update(new_files)

    def refresh_dep_graph(self):
        self.dep_graph = get_dependency_graph(self.files)
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
        self.dep_graph = self.app_config.depedency_graph()
        self.rev_graph = reverse_graph(self.dep_graph)

    def direct_app_deps(self, modules: Iterable[str]):
        """Find the apps that directly depend on any of the given modules"""
        return set(
            app_name
            for app_name, app_cfg in self.app_config.root.items()
            if isinstance(app_cfg, AppConfig) and app_cfg.module_name in modules
        )

    def all_app_deps(self, modules: Iterable[str]) -> set[str]:
        """Find all the apps that depend on the given modules, even indirectly

        Uses ``find_all_dependents``
        """
        return self.get_dependents(self.direct_app_deps(modules))


@dataclass
class DependencyManager:
    """Keeps track of all the python files and the app config files (either yaml or toml)

    Instantiating this class will walk the app_directory with ``pathlib.Path.rglob`` to find all the files. This happens both for app config files and app python files.

    The main purpose of breaking this out from ``AppManagement`` is to make it independently testable.
    """

    app_dir: Path
    python_deps: PythonDeps = field(init=False)
    app_deps: AppDeps = field(init=False)

    def __post_init__(self):
        """Instantiation docstring"""
        self.python_deps = PythonDeps.from_path(self.app_dir)
        self.app_deps = AppDeps.from_path(self.app_dir)

    @property
    def config_files(self) -> set[Path]:
        return set(self.app_deps.files.paths)

    def get_dependent_apps(self, modules: Iterable[str]) -> set[str]:
        """Finds all of the apps that depend on the given modules, even indirectly"""
        modules |= self.python_deps.get_dependents(modules)
        return self.app_deps.all_app_deps(modules)

    def update_python_files(self, new_files: Iterable[Path]):
        """Updates the dependency graph of python files.

        This is used to map which modules import which other modules and requires reading the contents of each python file to find the import statements.
        """
        return self.python_deps.update(new_files)

    def modules_to_import(self) -> set[str]:
        return self.python_deps.modules_to_import()

    def affected_apps(self, modules: Iterable[str]) -> set[str]:
        """All the apps that are affected by the modules being (re)imported"""
        return self.app_deps.all_app_deps(modules)

    def affected_graph(self, modules: Iterable[str]) -> dict[str, set[str]]:
        """The dependency subgraph for the affected apps"""
        return {app: self.app_deps.dep_graph[app] for app in self.affected_apps(modules)}

    def dependent_modules(self, modules: str | Iterable[str]):
        """Uses ``find_all_dependents`` with the reversed dependency graph to recursively find all the indirectly dependent modules"""
        return self.python_deps.get_dependents(modules)

    def dependent_apps(self, modules: str | Iterable[str]) -> set[str]:
        """Finds any apps that depend on any modules that depend on any of the given modules."""
        return self.app_deps.all_app_deps(self.dependent_modules(modules))

    def apps_to_terminate(self) -> set[str]:
        mods = self.python_deps.modules_to_delete()
        apps = self.app_deps.all_app_deps(mods)
        return apps
