from typing import Any

from pydantic import Field, model_validator, field_serializer, BaseModel

from ...models.notification.android import AndroidData


class AndroidNotification(BaseModel):
    device: str = Field(serialization_alias='service')
    tag: str = Field(default=None, exclude=True)
    data: AndroidData = Field(default_factory=AndroidData)

    @model_validator(mode='before')
    def validate_data(self: dict, __context: Any) -> None:
        if 'data' not in self:
            self['data'] = {}

        if title := self.pop('title', False):
            match self['data']:
                case dict():
                    self['data']['title'] = title
                case AndroidData():
                    self['data'].title = title

        if msg := self.pop('message', False):
            match self['data']:
                case dict():
                    self['data']['message'] = msg
                case AndroidData():
                    self['data'].message = msg

        if tag := self.pop('tag', False):
            match self['data']:
                case dict():
                    if 'data' not in self['data']:
                        self['data']['data'] = {}
                    self['data']['data']['tag'] = tag
                case AndroidData():
                    self['data'].data.tag = tag

        return self

    @field_serializer('device')
    def convert_to_ad_service(self, device: str):
        return f'notify/mobile_app_{device}'

    def to_kwargs(self) -> dict:
        kwargs = self.model_dump(mode='json', exclude_none=True, by_alias=True)
        data = kwargs.pop('data')
        kwargs.update(data)
        return kwargs
