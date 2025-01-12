from typing import Any

from pydantic import BaseModel, Field


class PluginAttributes(BaseModel):
    bytes_sent_ps: int = 0
    bytes_recv_ps: int = 0
    requests_sent_ps: int = 0
    updates_recv_ps: int = 0
    totalcallbacks: int = 0
    instancecallbacks: int = 0


class PluginEntity(BaseModel):
    """Used by plugin management to call state.add_entity"""

    namespace: str = "admin"
    entity: str
    state: Any
    attributes: PluginAttributes = Field(default_factory=PluginAttributes)
