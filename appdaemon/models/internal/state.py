from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, RootModel


class EntityState(BaseModel):
    """Used by state.add_entity to store the state"""

    entity_id: str
    state: Any
    last_changed: datetime | Literal["never"] = "never"
    attributes: dict[str, Any]

    @property
    def event_entity_add(self) -> dict[str, str | dict]:
        return {
            "event_type": "__AD_ENTITY_ADDED",
            "data": {"entity_id": self.entity_id, "state": self.state},
        }


class NamespaceState(RootModel):
    root: dict[str, EntityState]


class AppDaemonState(RootModel):
    root: dict[str, NamespaceState]
