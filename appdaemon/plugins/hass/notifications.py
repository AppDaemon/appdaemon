from typing import Literal

from pydantic import Field, model_validator, field_serializer, BaseModel

from ...models.notification.android import AndroidData


class AndroidNotification(BaseModel, extra='forbid'):
    """Wrapper for configuring Android notification service calls

    This class is used to create a notification for the Android mobile app and contains some conveniences for correctly
    customizing the notification.

    Example:

        >>> android_notification = AndroidNotification(
                device='pixel_9',
                message='Hello World!',
                title='AppDaemon',
            )
        >>> self.service_call(**android_notification.to_service_call())
    """
    device: str = Field(serialization_alias='service')
    """This gets combined with ``notify/mobile_app_<device>`` to determine which notification service to call."""
    message: str = Field(exclude=True)
    title: str | None = Field(default=None, exclude=True)
    tag: str | None = Field(default='apdaemon', exclude=True)
    service_data: AndroidData = Field(default_factory=AndroidData, alias='data')

    @model_validator(mode='after')
    def validate_data_after(self):
        self.service_data.message = self.message
        self.service_data.title = self.title
        self.service_data.data.tag = self.tag
        return self

    @field_serializer('device')
    def convert_to_ad_service(self, device: str) -> str:
        return f'notify/mobile_app_{device}'

    def to_service_call(self) -> dict:
        """Dump the configuration to a dictionary that can be directly used with ``call_service``."""
        kwargs = self.model_dump(mode='json', exclude_none=True, by_alias=True)
        if data := kwargs.pop('data', False):
            kwargs.update(data)
        return kwargs

    @classmethod
    def tts(
        cls,
        device: str,
        tts_text: str,
        media_stream: Literal['music_stream', 'alarm_stream', 'alarm_stream_max'] | None = 'music_stream',
        critical: bool = False,
    ) -> 'AndroidNotification':
        """Create an instance AndroidNotification pre-configured for TTS notifications.

        This includes setting the message to `TTS` as described in the Home Assistant documentation. See
        `Text To Speech Notifications <https://companion.home-assistant.io/docs/notifications/notifications-basic#text-to-speech-notifications>`_
        for more information.
        """
        self = cls.model_validate({
            'device': device,
            'message': 'TTS',
            'data': {'data': {'tts_text': tts_text, 'media_stream': media_stream}}
        })

        # don't set if it's False so as to not overwrite the media_stream
        if critical:
            self.critical = critical

        return self

    @property
    def critical(self):
        """For Android, notifications will appear immediately in most cases. However, in some cases (such as phone being
        stationary or when screen has been turned off for prolonged period of time), default notifications will not ring
        the phone until screen is turned on. To override that behavior, set this property to ``True``.

        See `Critical Notifications <https://companion.home-assistant.io/docs/notifications/critical-notifications/#android>`_
        for more information.
        """
        return self.service_data.data.media_stream == 'alarm_stream_max'

    @critical.setter
    def critical(self, critical: bool):
        # https://companion.home-assistant.io/docs/notifications/critical-notifications#android
        if critical:
            self.service_data.data.priority = 'high'
            self.service_data.data.ttl = 0
            self.service_data.data.media_stream = 'alarm_stream_max'
        else:
            self.service_data.data.priority = None
            self.service_data.data.ttl = None
            self.service_data.data.media_stream = 'music_stream'

    @property
    def color(self):
        return self.service_data.data.color

    @color.setter
    def color(self, new: str):
        self.service_data.data.color = new

    @property
    def countdown(self):
        return self.service_data.data.when

    @countdown.setter
    def countdown(self, new: int):

        # https://companion.home-assistant.io/docs/notifications/notifications-basic/#chronometer-notifications
        self.service_data.data.when = new
        self.service_data.data.chronometer = True
        self.service_data.data.when_relative = True

    @property
    def icon(self):
        return self.service_data.data.notification_icon

    @icon.setter
    def icon(self, icon: str):
        self.service_data.data.notification_icon = f'mdi:{icon}' if not icon.startswith('mdi:') else icon

    @property
    def persistent(self):
        """Persistent notifications are notifications that cannot be dismissed by swiping away. These are useful if you
        have something important like an alarm being triggered. In order to use this property you must set the tag
        property as well. The persistent property only takes boolean (``true``/``false``) values, with ``false`` being
        the default. The persistent notification will still be dismissed once selected, to avoid this use the ``sticky``
        parameter so the notification stays.

        Changing the value of this property will also change the value of the ``sticky`` property automatically because
        that's usually the intended behavior.

        See `Persistent Notification <https://companion.home-assistant.io/docs/notifications/notifications-basic/#persistent-notification>`_
        for more information.
        """
        return self.service_data.data.persistent

    @persistent.setter
    def persistent(self, new: bool):
        self.service_data.data.persistent = new
        self.service_data.data.sticky = new

    @property
    def timeout(self):
        return self.service_data.data.timeout

    @timeout.setter
    def timeout(self, new: int):
        self.service_data.data.timeout = new

    def add_action(self, action: str, title: str, uri: str | None = None):
        if not self.service_data.data.actions:
            self.service_data.data.actions = list()

        self.service_data.data.actions.append(dict(
            action=action,
            title=title,
            uri=uri
        ))

        return action
