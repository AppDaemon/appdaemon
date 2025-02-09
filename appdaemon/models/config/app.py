import sys
from abc import ABC
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any, Iterable, Iterator, Literal, Optional, Union

from pydantic import BaseModel, Discriminator, Field, RootModel, Tag, field_validator
from pydantic_core import PydanticUndefinedType

from ...dependency import reverse_graph
from ...utils import read_config_file
from .sequence import SequenceConfig


class GlobalModules(RootModel):
    root: set[str]


class BaseApp(BaseModel, ABC):
    """Abstract class to contain logic that's common to both apps and global modules"""
    name: str
    config_path: Optional[Path] = None  # Needs to remain optional because it gets set later
    module_name: str = Field(alias="module")
    """Importable module name.
    """
    dependencies: set[str] = Field(default_factory=set)
    """Other apps that this app depends on. They are guaranteed to be loaded and started before this one.
    """
    disable: bool = False
    priority: float = 50.0

    @property
    def module_is_loaded(self) -> bool:
        return self.module_name in sys.modules

    @field_validator("dependencies", mode="before")
    @classmethod
    def coerce_to_list(cls, value: Union[str, set[str]]) -> set[str]:
        return set((value,)) if isinstance(value, str) else value


class GlobalModule(BaseApp):
    global_: Literal[True] = Field(alias="global")
    global_dependencies: set[str] = Field(default_factory=set)
    """Global modules that this app depends on.
    """


class AppConfig(BaseApp, extra="allow"):
    class_name: str = Field(alias="class")
    """Name of the class to use for the app. Must be accessible as an attribute of the imported `module_name`
    """
    pin_app: Optional[bool] = None
    pin_thread: Optional[int] = None
    log: Optional[str] = None
    log_level: Optional[str] = None

    def __getitem__(self, key: str):
        return getattr(self, key)

    @property
    def args(self) -> dict[str, dict]:
        return self.model_dump(by_alias=True, exclude_unset=True)


def discriminate_app(v: Any):
    match v:
        case dict():
            if v.get("global"):
                return "global"
            else:
                return "app"
    return v


AppOrGlobal = Annotated[
    Union[
        Annotated[AppConfig, Tag("app")],
        Annotated[GlobalModule, Tag("global")]
    ],
    Field(discriminator=Discriminator(discriminate_app))
]


class AllAppConfig(RootModel):
    root: dict[
        str | Literal["global_modules", "sequence"],
        Union[AppOrGlobal, GlobalModules, SequenceConfig]
    ] = Field(default_factory=dict)

    @field_validator("root", mode="before")
    @classmethod
    def set_app_names(cls, values: dict):
        values = deepcopy(values)
        if not isinstance(values, PydanticUndefinedType):
            for app_name, cfg in values.items():
                match app_name:
                    case "global_modules":
                        values[app_name] = GlobalModules.model_validate(cfg)
                    case "sequence":
                        values[app_name] = SequenceConfig.model_validate(cfg)
                    case _:
                        cfg["name"] = app_name
                        values[app_name] = cfg
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
        try:
            paths = iter(paths)
            cfg = read_config_file(next(paths))
        except StopIteration:
            return cls()
        else:
            for p in paths:
                for new, new_cfg in read_config_file(p).items():
                    if new in cfg:
                        match new:
                            case "global_modules":
                                cfg[new].extend(new_cfg)
                            case "sequence":
                                cfg[new].update(new_cfg)
                            case _:
                                # This is the case for an app being defined more than once
                                # TODO: Log some kind of warning here
                                cfg[new].update(new_cfg)
                    else:
                        cfg[new] = new_cfg
            return cls.model_validate(cfg)

    def depedency_graph(self) -> dict[str, set[str]]:
        """Maps the app names to the other apps that they depend on"""
        return {
            app_name: cfg.dependencies
            for app_name, cfg in self.root.items()
            if isinstance(cfg, (AppConfig, GlobalModule))
        }

    def reversed_dependency_graph(self) -> dict[str, set[str]]:
        """Maps each app to the other apps that depend on it"""
        return reverse_graph(self.depedency_graph())

    def app_definitions(self):
        """Returns the app name and associated config for user-defined apps. Does not include global module apps"""
        yield from (
            (app_name, cfg)
            for app_name, cfg in self.root.items()
            if isinstance(cfg, (AppConfig, SequenceConfig))
        )

    def global_modules(self) -> list[GlobalModule]:
        return [
            cfg for cfg in self.root.values()
            if isinstance(cfg, GlobalModule)
        ]

    def app_names(self) -> set[str]:
        """Returns all the app names for regular user apps and global module apps"""
        return set(app_name for app_name, cfg in self.root.items() if isinstance(cfg, BaseApp))

    def apps_from_file(self, paths: Iterable[Path]):
        if not isinstance(paths, set):
            paths = set(paths)

        return set(
            app_name
            for app_name, cfg in self.root.items()
            if isinstance(cfg, BaseApp) and
            cfg.config_path in paths
        )

    @property
    def active_app_count(self) -> int:
        """Active in this case means not disabled"""
        return len([cfg for cfg in self.root.values() if isinstance(cfg, AppConfig) and not cfg.disable])

    def get_active_app_count(self) -> tuple[int, int, int]:
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
