from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from typing import Literal


@dataclass(slots=True)
class ScheduleEntry:
    name: str
    """Name of the app that registered the callback"""
    id: str
    """Unique identifier (handle) for the scheduled callback"""
    callback: partial = field(repr=False)
    """Callable to be executed when the callback is triggered"""
    basetime: datetime
    """Base time for the callback, without any offset applied"""
    timestamp: datetime
    """The resolved time when the callback will be executed, including any offset"""
    offset: float | None = None
    """Offset in seconds to be applied to the base time"""
    interval: float | None = None
    """Time interval in seconds between executions when it's being restarted"""
    repeat: bool = False
    """Whether the callback should be restarted after execution"""
    type: Literal["next_rising", "next_setting"] | None = None
    pin_app: bool | None = None
    pin_thread: int | None = None
    kwargs: dict = field(default_factory=dict)

    random_start: float | None = None
    random_end: float | None = None
