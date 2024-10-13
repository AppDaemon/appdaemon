from typing import Literal

from pydantic import Field, model_validator, field_serializer, BaseModel

from ...models.notification.android import AndroidData


class AndroidNotification(BaseModel, extra='forbid'):
    device: str = Field(serialization_alias='service')
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
        self = cls.model_validate({
            'device': device,
            'message': 'TTS',
            'data': {'data': {'tts_text': tts_text, 'media_stream': media_stream}}
        })

        # dont' set if it's False to not overwrite the media_stream
        if critical:
            self.critical = critical

        return self

    @property
    def critical(self):
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
        return self.service_data.data.persistent

    @persistent.setter
    def persistent(self, new: bool):
        # https://companion.home-assistant.io/docs/notifications/notifications-basic/#persistent-notification
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
