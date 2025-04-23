from collections.abc import Iterable
from typing import Literal

from pydantic import Field, field_serializer, field_validator

from .base import NotificationData
from .base import Action, Payload


class AndroidPayload(Payload, extra="forbid"):
    """Data specific to the Android Platform used for configuring notifications.

    For more information, see the
    `Android Specific <https://companion.home-assistant.io/docs/notifications/notifications-basic/#android-specific>`_
    section of the Home Assistant documentation.
    """

    group: str | None = None
    tag: str | None = None

    actions: list[Action] | None = None
    clickAction: str | None = None
    subtitle: str | None = None

    color: str | None = None
    sticky: bool | None = None
    """Setting sticky to ``True`` will keep the notification from being dismissed when the user selects it. Setting it
    to ``False`` (default) will dismiss the notification upon selecting it. See
    `Sticky Notification <https://companion.home-assistant.io/docs/notifications/notifications-basic/#sticky-notification>`_
    for more information.
    """
    # https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-channels
    channel: str | None = None
    """Notification channels (on some devices: notification categories) allow you to separate your notifications easily
    (i.e. alarm vs laundry) and customize aspects like the notification sound and a lot of other device specific
    features. Devices running Android 8.0+ are able to create and manage notification channels on the fly using
    automations. Once a channel is created you can navigate to your notification settings and you will find the newly
    created channel, from there you can customize the behavior based on what your device allows.

    See `Notification Channels <https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-channels>`_
    for more information.
    """
    importance: Literal["high", "low", "max", "min", "default"] | None = None
    priority: Literal["low", "high"] | None = None
    ttl: int | None = None
    vibration_pattern: list[int] | None = Field(default=None, alias="vibrationPattern")
    ledColor: str | None = None  # notification LED
    persistent: bool | None = None
    """Persistent notifications are notifications that cannot be dismissed by swiping away. These are useful if you have
    something important like an alarm being triggered. In order to use this property you must set the tag property as
    well. The persistent property only takes boolean (``true``/``false``) values, with ``false`` being the default. The
    persistent notification will still be dismissed once selected, to avoid this use the ``sticky`` parameter so the
    notification stays.

    See `Persistent Notification <https://companion.home-assistant.io/docs/notifications/notifications-basic/#persistent-notification>`_
    for more information.
    """
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
