import threading
import uuid
from copy import copy, deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from logging import Logger
from pathlib import Path
from typing import Any, Literal

from ...dependency import find_all_dependents, topo_sort
from ...dependency_manager import DependencyManager


class UpdateMode(Enum):
    """Used as an argument for :meth:`AppManagement.check_app_updates` to set the mode of the check.

    INIT
        Triggers AppManagement._init_update_mode to run during check_app_updates
    NORMAL
        Normal update mode, for when :meth:`AppManagement.check_app_updates` is called by :meth:`.utility_loop.Utility.loop`
    TERMINATE
        Terminate all apps
    """

    INIT = auto()
    NORMAL = auto()
    RELOAD_APPS = auto()
    PLUGIN_FAILED = auto()
    PLUGIN_RESTART = auto()
    TERMINATE = auto()



@dataclass
class LoadingActions:
    """Stores what's going to happen to apps/modules during check_app_updates.

    Attributes:
        init: Which apps/modules are new
        reload: Which apps/modules need to be reloaded or restarted
        term: Which apps/modules need to be stopped and removed
        failed: Which apps/modules failed be started and/or removed
    """

    init: set[str] = field(default_factory=set)
    reload: set[str] = field(default_factory=set)
    term: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)

    @property
    def changes(self) -> bool:
        return any(map(bool, (self.init, self.reload, self.term)))

    @property
    def init_set(self) -> set[str]:
        """The set of items that are either new or need to be reloaded"""
        return (self.init | self.reload) - self.failed

    def import_sort(self, dm: DependencyManager) -> list[str]:
        """Finds the python files that need to be imported.

        Uses a dependency graph to sort the internal ``init`` and ``reload`` sets together
        """
        items = copy(self.init_set)
        items |= find_all_dependents(items, dm.python_deps.rev_graph)
        order = [n for n in topo_sort(dm.python_deps.dep_graph) if n in items]
        return order

    def start_sort(self, dm: DependencyManager, logger: Logger = None) -> list[str]:
        """Finds the apps that need to be started.

        Uses a dependency graph to sort the internal ``init`` and ``reload`` sets together
        """
        items = copy(self.init_set)
        items |= find_all_dependents(items, dm.app_deps.dep_graph)
        priorities = {
            app_name: dm.app_deps.app_config.root[app_name].priority
            for app_name in items
        }
        priority_deps = {
            app_name: set(
                dep for dep, dep_priority in priorities.items()
                if dep_priority < app_priority
            )
            for app_name, app_priority in priorities.items()
        }

        dep_graph = deepcopy(dm.app_deps.dep_graph)
        for app, deps in dep_graph.items():
            # need to make sure the app isn't in it's own dependencies
            for dep in priority_deps.get(app, set()):
                sub_deps = find_all_dependents({app}, dm.app_deps.rev_graph)
                if dep in sub_deps:
                    if logger is not None:
                        logger.warning(f'Applying priority will cause a circular dependency: {app} -> {dep}')
                else:
                    deps.add(dep)

        order = [n for n in topo_sort(dep_graph) if n in items]
        return order

    @property
    def term_set(self) -> set[str]:
        return self.reload | self.term

    def term_sort(self, dm: DependencyManager):
        """Finds all the apps that need to be terminated.

        Uses a dependency graph to sort the internal ``reload`` and ``term`` sets together
        """
        items = copy(self.term_set)
        items |= find_all_dependents(items, dm.app_deps.rev_graph)
        order = [n for n in topo_sort(dm.app_deps.rev_graph) if n in items]
        return order


@dataclass
class UpdateActions:
    """Class to wrap various statuses for the `AppManagement.check_app_updates` method"""
    modules: LoadingActions = field(init=False, default_factory=LoadingActions)
    apps: LoadingActions = field(init=False, default_factory=LoadingActions)
    sequences: LoadingActions = field(init=False, default_factory=LoadingActions)


@dataclass
class ManagedObject:
    type: Literal["app", "plugin", "sequence"]
    object: Any
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    module_path: Path | None = None
    pin_app: bool | None = None
    pin_thread: int | None = None
    running: bool = False
    use_dictionary_unpacking: bool = False
    callback_counter: int = 0
    lock: threading.RLock = field(init=False, default_factory=threading.RLock)

    def increment_callback_counter(self, n: int = 1) -> None:
        """Increments the callback counter by one"""
        with self.lock:
            self.callback_counter += n
