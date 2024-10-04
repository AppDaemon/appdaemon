from collections.abc import Iterable
from typing import Literal
from pydantic import BaseModel, Field, field_serializer, field_validator


class iOSSound(BaseModel, extra='forbid'):
    name: str
    critical: bool | None = None
    volume: int | None = None


class iOSPush(BaseModel, extra='forbid'):
    badge: int | None = None
    sound: iOSSound | None = None
    interruption_level: Literal['passive', 'active', 'time-sensitive',
                                'critical'] | None = Field(default=None, serialization_alias='interruption-level')
    presentation_options: list[Literal['alert',
                                       'badge', 'sound']] | None = None


class Action(BaseModel):
    action: str
    title: str
    uri: str | None = None


class iOSAction(Action, extra='forbid'):
    activation_mode: Literal['foreground', 'background'] | None = Field(default=None, serialization_alias='activationMode')
    authentication_required: bool | None = Field(default=None, serialization_alias='authenticationRequired')
    destructive: bool | None = None
    behavior: str | None = None
    text_input_button_title: str | None = Field(default=None, serialization_alias='textInputButtonTitle')
    text_input_placeholder: str | None = Field(default=None, serialization_alias='textInputPlaceholder')
    icon: str | None = None

    @field_validator('icon', mode='before')
    @classmethod
    def validate_icon(cls, v: str):
        assert v.startswith('sfsymbols:')
        return v


class Payload(BaseModel):
    group: str | None = None
    tag: str | None = None


class AndroidPayload(Payload, extra='forbid'):
    """Notification data specific to the Android Platform

    https://companion.home-assistant.io/docs/notifications/notifications-basic/#android-specific
    """
    actions: list[Action] | None = None
    clickAction: str | None = None
    subtitle: str | None = None

    color: str | None = None
    sticky: bool | None = None
    # https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-channels
    channel: str | None = None
    importance: Literal['high', 'low', 'max', 'min', 'default'] | None = None
    priority: Literal['low', 'high'] | None = None
    ttl: int | None = None
    vibration_pattern: list[int] | None = Field(default=None, serialization_alias='vibrationPattern')
    ledColor: str | None = None  # notification LED
    persistent: bool | None = None
    timeout: int | None = None
    icon_url: str | None = None
    visibility: Literal['public', 'private'] | None = None
    tts_text: str | None = None
    media_stream: str | None = None
    chronometer: bool | None = None
    when: int | None = None
    when_relative: bool | None = None
    alert_once: bool | None = None
    notification_icon: str | None = None
    car_ui: bool | None = None

    @field_validator('vibrationPattern', mode='before')
    @classmethod
    def validate_vibration(cls, val: str | Iterable[int]) -> list[int]:
        if isinstance(val, str):
            val = list(map(int, (n.strip() for n in val.split(','))))

        if not isinstance(val, list):
            val = list(val)

        return val

    @field_serializer('vibrationPattern')
    def serialize_vibration(self, vibrationPattern: list[int] | None) -> str | None:
        if vibrationPattern is None:
            return vibrationPattern
        return ', '.join(map(str, vibrationPattern))


class iOSPayload(Payload, extra='forbid'):
    url: str | None = None
    subject: str | None = None
    push: iOSPush | None = None
    actions: list[iOSAction] | None = None


class NotificationData(BaseModel):
    title: str
    message: str
    data: Payload | None = None


class AndroidData(NotificationData, extra='forbid'):
    data: AndroidPayload | None = None


class iOSData(NotificationData, extra='forbid'):
    data: iOSPayload | None = None


class NotifyAction(BaseModel):
    action: str
    data: NotificationData

    @field_validator('action')
    @classmethod
    def validate_action(cls, val: str):
        assert val.startswith('notify')
        return val


class AndroidAction(NotifyAction):
    data: AndroidData


class iOSAction(NotifyAction):
    data: iOSData


class Automation(BaseModel):
    alias: str | None = None
    trigger: str | None = None
    action: list[NotifyAction]
