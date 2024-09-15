from abc import ABC
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator
from pydantic_core import PydanticUndefinedType

from ..dependency import reverse_graph
from ..utils import read_config_file


class GlobalModules(RootModel):
    root: Set[str]


class BaseApp(BaseModel, ABC):
    name: Optional[str] = None  # Needs to remain optional because it gets set later
    config_path: Optional[Path] = None  # Needs to remain optional because it gets set later
    module_name: str = Field(alias="module")
    """Importable module name.
    """
    dependencies: Set[str] = Field(default_factory=set)
    """Other apps that this app depends on. They are guaranteed to be loaded and started before this one.
    """
    global_dependencies: Set[str] = Field(default_factory=set)
    """Global modules that this app depends on.
    """
    global_: bool = Field(alias="global")


class GlobalModule(BaseApp):
    global_: bool = Field(default=True, alias="global")
    global_dependencies: Set[str] = Field(default_factory=set)
    """Global modules that this app depends on.
    """


class Sequence(RootModel):
    class SequenceItem(BaseModel):
        class SequenceStep(RootModel):
            root: Dict[str, Dict]

        name: str
        namespace: str = "default"
        steps: List[SequenceStep]

    root: Dict[str, SequenceItem]


class AppConfig(BaseApp, extra="allow"):
    class_name: str = Field(alias="class")
    """Name of the class to use for the app. Must be accessible as an attribute of the imported `module_name`
    """

    global_: bool = Field(default=True, alias="global")
    disable: bool = False
    pin_app: Optional[bool] = None
    pin_thread: Optional[int] = None
    log: Optional[str] = None
    log_level: Optional[str] = None

    @field_validator("dependencies", "global_dependencies", mode="before")
    @classmethod
    def coerce_to_list(cls, value: Union[str, Set[str]]) -> Set[str]:
        return set((value,)) if isinstance(value, str) else value

    def __getitem__(self, key: str):
        return getattr(self, key)

    @property
    def args(self) -> Dict[str, Dict]:
        return self.model_dump(by_alias=True, exclude_unset=True)


class AllAppConfig(RootModel):
    root: Dict[str, Union[AppConfig, GlobalModule, GlobalModules, Sequence]] = {}

    @model_validator(mode="before")
    @classmethod
    def set_app_names(cls, values: Dict):
        if not isinstance(values, PydanticUndefinedType):
            for app_name, cfg in values.items():
                match app_name:
                    case "global_modules":
                        values[app_name] = GlobalModules.model_validate(cfg)
                    case "sequence":
                        values[app_name] = Sequence.model_validate(cfg)
                    case _:
                        cfg["name"] = app_name
                        values[app_name] = cfg

                match cfg:
                    case BaseApp():
                        values[app_name]["name"] = app_name
                    case dict():
                        if cfg.get("global"):
                            values[app_name] = GlobalModule.model_validate(cfg)

            return values

    def __getitem__(self, key: str):
        return self.root[key]

    @property
    def __iter__(self) -> Iterator[Path]:
        return self.root.__iter__

    @classmethod
    def from_config_file(cls, path: Path):
        return cls.model_validate(read_config_file(path))

    @classmethod
    def from_config_files(cls, paths: Iterable[Path]):
        paths = iter(paths)
        self = cls.from_config_file(next(paths))
        for p in paths:
            self.root.update(cls.from_config_file(p).root)
        return self

    def depedency_graph(self) -> Dict[str, Set[str]]:
        """Maps the app names to the other apps that they depend on"""
        return {
            app_name: cfg.dependencies | cfg.global_dependencies
            for app_name, cfg in self.root.items()
            if isinstance(cfg, (AppConfig, GlobalModule))
        }

    def reversed_dependency_graph(self) -> Dict[str, Set[str]]:
        """Maps each app to the other apps that depend on it"""
        return reverse_graph(self.depedency_graph())

    def app_definitions(self):
        """Returns the app name and associated config for user-defined apps. Does not include global module apps"""
        yield from ((app_name, cfg) for app_name, cfg in self.root.items() if isinstance(cfg, AppConfig))

    def app_names(self) -> Set[str]:
        """Returns all the app names for regular user apps and global module apps"""
        return set(app_name for app_name, cfg in self.root.items() if isinstance(cfg, BaseApp))

    def apps_from_file(self, paths: Iterable[Path]):
        if not isinstance(paths, set):
            paths = set(paths)

        return set(
            app_name
            for app_name, cfg in self.root.items()
            if isinstance(cfg, (AppConfig, GlobalModule)) and cfg.config_path in paths
        )

    @property
    def active_app_count(self) -> int:
        """Active in this case means not disabled"""
        return len([cfg for cfg in self.root.values() if isinstance(cfg, AppConfig) and not cfg.disable])

    def get_active_app_count(self) -> Tuple[int, int, int]:
        active = 0
        inactive = 0
        glbl = 0
        for cfg in self.root.values():
            if isinstance(cfg, AppConfig):
                if cfg.disable:
                    inactive += 1
                else:
                    active += 1
            elif isinstance(cfg, GlobalModule):
                glbl += 1
        return active, inactive, glbl
