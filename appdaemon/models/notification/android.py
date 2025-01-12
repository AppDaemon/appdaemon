from collections.abc import Iterable
from typing import Literal

from pydantic import Field, field_serializer, field_validator

from .base import NotificationData
from .base import Action, Payload


class AndroidPayload(Payload, extra="forbid"):
    """Notification data specific to the Android Platform

    https://companion.home-assistant.io/docs/notifications/notifications-basic/#android-specific
    """

    group: str | None = None
    tag: str | None = None

    actions: list[Action] | None = None
    clickAction: str | None = None
    subtitle: str | None = None

    color: str | None = None
    sticky: bool | None = None
    # https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-channels
    channel: str | None = None
    importance: Literal["high", "low", "max", "min", "default"] | None = None
    priority: Literal["low", "high"] | None = None
    ttl: int | None = None
    vibration_pattern: list[int] | None = Field(default=None, alias="vibrationPattern")
    ledColor: str | None = None  # notification LED
    persistent: bool | None = None
    timeout: int | None = None
    icon_url: str | None = None
    visibility: Literal["public", "private"] | None = None
    tts_text: str | None = None
    media_stream: Literal["music_stream", "alarm_stream", "alarm_stream_max"] | None = None
    chronometer: bool | None = None
    when: int | None = None
    when_relative: bool | None = None
    alert_once: bool | None = None
    notification_icon: str | None = None
    car_ui: bool | None = None

    @field_validator("vibration_pattern", mode="before")
    @classmethod
    def validate_vibration(cls, val: str | Iterable[int]) -> list[int]:
        if isinstance(val, str):
            val = list(map(int, (n.strip() for n in val.split(","))))

        if not isinstance(val, list):
            val = list(val)

        return val

    @field_serializer("vibration_pattern")
    def serialize_vibration(self, vibration_pattern: list[int] | None) -> str | None:
        if vibration_pattern is None:
            return vibration_pattern
        return ", ".join(map(str, vibration_pattern))


class AndroidData(NotificationData, extra="forbid"):
    """https://www.home-assistant.io/integrations/notify/#action"""

    title: str | None = None
    message: str | None = None
    target: str | None = None
    data: AndroidPayload = Field(default_factory=AndroidPayload)
