from dataclasses import dataclass
from typing import Any, Literal
from collections.abc import Callable


@dataclass(slots=True)
class StateDispatch:
    id: str
    name: str
    objectid: str
    type: str
    function: Callable
    attribute: str
    entity: str
    new_state: dict
    old_state: dict
    pin_app: bool
    pin_thread: int
    kwargs: dict


@dataclass(slots=True)
class EventDispatch:
    id: str
    name: str
    objectid: str
    type: Literal["event"]
    function: Callable
    data: dict[str, Any]
    pin_app: bool
    pin_thread: int
    kwargs: dict[str, Any]
