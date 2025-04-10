from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, BeforeValidator, Discriminator, Field, RootModel, Tag, WrapSerializer, model_validator

from ... import exceptions as ade
from .common import TimeType


class SequenceStep(BaseModel):
    pass


class SleepStep(SequenceStep):
    sleep: TimeType


class WaitStateStep(SequenceStep):
    entity_id: str
    state: Any
    timeout: TimeType = timedelta(minutes=15)
    namespace: str = "default"


class LoopStep(SequenceStep):
    interval: TimeType
    times: int = 1


class ServiceCallStep(SequenceStep, extra="allow"):
    service: str
    domain: str
    namespace: str | None = None
    loop_step: LoopStep | None = None
    # any of the extra kwargs will go to the service call

    @model_validator(mode="before")
    @classmethod
    def split_domain(cls, data: dict):
        if isinstance(data, dict) and not data.get("domain"):
            data["domain"], data["service"] = data["service"].split("/", 2)
        return data


class SubSequenceStep(SequenceStep):
    sequence: str
    namespace: str = "default"


def service_call_validator(v: dict[str, dict[str, Any]]):
    """Puts the name of the domain/name of the service into the diction"""
    try:
        service = next(iter(v.keys()))
        v[service]["service"] = service
        return v[service]
    except Exception:
        raise ade.BadSequenceStepDefinition(v)


def service_call_serializer(value: Any, handler, info):
    # https://docs.pydantic.dev/latest/api/functional_serializers/#pydantic.functional_serializers.WrapSerializer
    partial_result = handler(value, info)
    service_name = partial_result.pop("service")
    return {service_name: partial_result}


def step_discriminator(v: Any):
    match v:
        case dict():
            if v.get("sleep"):
                return "sleep"
            elif v.get("wait_state"):
                return "wait"
            else:
                return "service_call"


# This type wraps up the logic for determining the type of each step
SequenceStep = Annotated[
    Union[
        Annotated[SleepStep, Tag("sleep")],
        Annotated[dict[Literal["wait_state"], WaitStateStep], Tag("wait")],
        Annotated[ServiceCallStep, BeforeValidator(service_call_validator), WrapSerializer(service_call_serializer), Tag("service_call")],
    ],
    Field(discriminator=Discriminator(step_discriminator)),
]


class Sequence(BaseModel, extra="forbid"):
    steps: list[SequenceStep]
    name: str | None = None
    namespace: str = "default"
    loop: bool = False
    hot_reload: bool = False
    """If true, apps that have run this sequence will be reloaded if the sequence definition changes while it's running."""
    config_path: Path | None = None  # Needs to remain optional because it gets set later
    """The path to the file that defines this sequence"""


class SequenceConfig(RootModel):
    # needs to start with a top level `sequence` key`
    root: dict[str, Sequence]
