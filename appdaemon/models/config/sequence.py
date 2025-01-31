from datetime import timedelta
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, BeforeValidator, Discriminator, Field, PlainSerializer, RootModel, Tag


TimeType = Annotated[
    timedelta,
    BeforeValidator(lambda v: timedelta(seconds=v)),
    PlainSerializer(lambda td: td.total_seconds())
]


class SleepStep(BaseModel):
    sleep: TimeType


class WaitStateStep(BaseModel):
    entity_id: str
    state: Any
    timeout: TimeType = timedelta(minutes=15)
    namespace: str = "default"


class LoopStep(BaseModel):
    times: int
    interval: TimeType


class ServiceCallStep(BaseModel, extra="allow"):
    service: str
    loop_step: LoopStep | None = None
    # any of the extra kwargs will go to the service call


def service_validator(v: dict[str, dict[str, Any]]):
    """Puts the name of the domain/name of the service into the diction"""
    service = next(iter(v.keys()))
    v[service]["service"] = service
    return v


def step_discriminator(v: Any):
    match v:
        case dict():
            if v.get("sleep"):
                return "sleep"
            elif v.get("wait_state"):
                return "wait"
            else:
                return "service_call"
        case _:
            raise ValueError(f"Bad step: {v}")


# This type wraps up the logic for determining the type of each step
SequenceStep = Annotated[
    Union[
        Annotated[SleepStep, Tag("sleep")],
        Annotated[dict[Literal["wait_state"], WaitStateStep], Tag("wait")],
        Annotated[
            dict[str, ServiceCallStep],
            BeforeValidator(service_validator),
            Tag("service_call")
        ],
    ],
    Field(discriminator=Discriminator(step_discriminator)),
]


class Sequence(BaseModel):
    steps: list[SequenceStep]
    name: str | None = None
    namespace: str = "default"
    loop: bool = False


class SequenceConfig(RootModel):
    # needs to start with a top level `sequence` key`
    root: dict[str, Sequence]
