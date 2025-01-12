from pydantic import BaseModel

from typing import Literal


class NamespaceConfig(BaseModel):
    writeback: Literal["safe", "hybrid"] = "safe"
    persist: bool = False
