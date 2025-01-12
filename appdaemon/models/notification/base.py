from abc import ABC

from pydantic import BaseModel, Field


class Action(BaseModel, ABC):
    action: str
    title: str
    uri: str | None = None


class Payload(BaseModel, ABC):
    group: str | None = None
    tag: str | None = None


class NotificationData(BaseModel, ABC):
    """https://www.home-assistant.io/integrations/notify/#action"""

    title: str | None = None
    message: str | None = None
    target: str | None = None
    data: Payload | None = None


class NotifyAction(BaseModel, ABC):
    device: str
    data: NotificationData = Field(default_factory=NotificationData)

    # def to_kwargs(self) -> dict:
    #     return self.model_dump(mode='json', exclude_none=True)


class Automation(BaseModel):
    alias: str | None = None
    trigger: str | None = None
    action: list[NotifyAction]
