from datetime import timedelta
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator, BeforeValidator

from typing import Annotated


class PluginConfig(BaseModel, extra="allow"):
    type: str
    name: str
    """Gets set by a field_validator in the AppDaemonConfig"""
    disable: bool = False
    persist_entities: bool = False
    refresh_delay: Annotated[timedelta, BeforeValidator(lambda v: timedelta(minutes=v))] = timedelta(minutes=10)
    """Delay between refreshes of the complete plugin state in the utility loop"""
    refresh_timeout: int = 30
    use_dictionary_unpacking: bool = True
    module_name: str = None
    class_name: str = None

    connect_timeout: int | float = 1.0
    reconnect_delay: int | float = 5.0

    namespace: str = 'default'
    namespaces: list[str] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def lower(cls, v: str, info: ValidationInfo):
        return v.lower()

    @model_validator(mode="after")
    def custom_validator(self):
        if "module_name" not in self.model_fields_set:
            self.module_name = f"appdaemon.plugins.{self.type}.{self.type}plugin"

        if "class_name" not in self.model_fields_set:
            self.class_name = f"{self.type.capitalize()}Plugin"

        return self

    @property
    def disabled(self) -> bool:
        return self.disable
