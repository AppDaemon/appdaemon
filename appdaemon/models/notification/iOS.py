from typing import Literal
from pydantic import BaseModel, Field, field_validator

from .base import NotificationData, Payload, NotifyAction, Action


class iOSSound(BaseModel, extra="forbid"):
    name: str
    critical: bool | None = None
    volume: int | None = None


class iOSPush(BaseModel, extra="forbid"):
    badge: int | None = None
    sound: iOSSound | None = None
    interruption_level: Literal["passive", "active", "time-sensitive", "critical"] | None = Field(default=None, serialization_alias="interruption-level")
    presentation_options: list[Literal["alert", "badge", "sound"]] | None = None


class iOSAction(Action, extra="forbid"):
    activation_mode: Literal["foreground", "background"] | None = Field(default=None, serialization_alias="activationMode")
    authentication_required: bool | None = Field(default=None, serialization_alias="authenticationRequired")
    destructive: bool | None = None
    behavior: str | None = None
    text_input_button_title: str | None = Field(default=None, serialization_alias="textInputButtonTitle")
    text_input_placeholder: str | None = Field(default=None, serialization_alias="textInputPlaceholder")
    icon: str | None = None

    @field_validator("icon", mode="before")
    @classmethod
    def validate_icon(cls, v: str):
        assert v.startswith("sfsymbols:")
        return v


class iOSPayload(Payload, extra="forbid"):
    url: str | None = None
    subject: str | None = None
    push: iOSPush | None = None
    actions: list[iOSAction] | None = None


class iOSData(NotificationData, extra="forbid"):
    data: iOSPayload | None = None


class iOSAction(NotifyAction):
    data: iOSData
