from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class HAContext(BaseModel):
    id: str
    parent_id: Optional[str] = None
    user_id: Optional[str] = None


class ServiceCallData(BaseModel):
    domain: str
    service: str
    service_data: dict


class HAState(BaseModel):
    entity_id: str
    state: str
    attributes: dict[str, Any]
    last_changed: datetime
    last_reported: datetime
    last_updated: datetime
    context: HAContext


class StateChangeData(BaseModel):
    entity_id: str
    old_state: HAState
    new_state: HAState


class HAEvent(BaseModel):
    event_type: str
    data: dict
    origin: str
    time_fired: datetime
    context: HAContext

    @classmethod
    def model_validate(cls, kwargs) -> "HAEvent":
        event_type = kwargs.get("event_type")
        event_class = EVENT_TYPE_MAPPING.get(event_type, cls)
        return event_class(**kwargs)


class CallServiceEvent(HAEvent):
    data: ServiceCallData


class StateChangeEvent(HAEvent):
    data: StateChangeData


EVENT_TYPE_MAPPING = {"call_service": CallServiceEvent, "state_changed": StateChangeEvent}
