"""Strict API contracts. Clients cannot assign roles or moderation status."""
from typing import Literal
import re
from pydantic import StrictInt, BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Credentials(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: str
    password: str = ''

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        value=value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):raise ValueError('Введите email в формате name@mail.ru')
        return value


class Registration(Credentials):
    name: str = ''

    @field_validator('name', mode='before')
    @classmethod
    def clean_name(cls, value):
        return (value.strip() or 'Житель') if isinstance(value, str) else value


class Point(StrictModel):
    x: float = Field(ge=0,le=20000,allow_inf_nan=False)
    y: float = Field(ge=0,le=20000,allow_inf_nan=False)


class Values(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: Literal['home','stop','park','school','clinic','shop','parking','greenery'] | None = None
    x: float | None = Field(default=None, ge=0, le=20000)
    y: float | None = Field(default=None, ge=0, le=20000)
    residents: int | None = Field(default=None, ge=0, le=100000, strict=True)
    capacity: int | None = Field(default=None, ge=1, le=100000, strict=True)
    load: int | None = Field(default=None, ge=0, le=100000, strict=True)
    width: float | None = Field(default=None, ge=5, le=4000)
    height: float | None = Field(default=None, ge=5, le=4000)
    rotation: float | None = Field(default=None,ge=0,lt=180,allow_inf_nan=False)
    points: list[Point] | None = Field(default=None,min_length=2,max_length=60)
    a: str | None = Field(default=None, max_length=64)
    b: str | None = Field(default=None, max_length=64)
    closed: bool | None = Field(default=None, strict=True)


class Action(StrictModel):
    entity: Literal['object','node','edge','area','road']
    operation: Literal['add','update','delete']
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    values: Values = Field(default_factory=Values)


class Preview(StrictModel):
    action: Action | None = None
    actions: list[Action] | None = Field(default=None, min_length=1, max_length=20)
    base_version: int = Field(ge=0)

    @model_validator(mode='after')
    def exactly_one_form(self):
        if (self.action is None)==(self.actions is None):
            raise ValueError('Передайте одно действие или набор от 1 до 20 изменений')
        return self

    def changes(self):
        return [a.model_dump(exclude_none=True) for a in (self.actions or [self.action])]

    def stored_action(self):
        return {'actions':self.changes()} if self.actions is not None else self.changes()[0]


class BudgetUpdate(StrictModel):
    limit: int = Field(ge=0, le=1_000_000_000_000, strict=True)


class Proposal(Preview):
    reason: str = Field(default='', max_length=1000)


class Decision(StrictModel):
    decision: Literal['approved', 'rejected']
    comment: str = Field(default='', max_length=1000)


class ScenarioSave(Preview):
    name: str = Field(min_length=1,max_length=80)

class AnalysisOptions(StrictModel):
    park_radius: int = Field(default=500,ge=10,le=10000)
    park_radii: list[int] = Field(default_factory=lambda:[100,200,300,500,1000],min_length=1,max_length=15)
    @field_validator('park_radii')
    @classmethod
    def radii_range(cls,values):
        if any(r<10 or r>10000 for r in values):raise ValueError('Радиусы: от 10 до 10000 м')
        return sorted(set(values))

class ScenarioCompare(AnalysisOptions):
    ids: list[str] = Field(min_length=1,max_length=8)
    target: Literal['park_percent','transport_access','facility_provision','average_stop'] = 'park_percent'
    threshold: float = Field(default=50,ge=0,le=100000,allow_inf_nan=False)


class DemoReset(StrictModel):
    action: Literal['reset_all','clear_proposals','undo']


class HomeSpec(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    name: str = Field(min_length=1,max_length=80)
    x: float = Field(ge=0,le=20000,allow_inf_nan=False)
    y: float = Field(ge=0,le=20000,allow_inf_nan=False)
    width: float = Field(ge=5,le=200,allow_inf_nan=False)
    height: float = Field(ge=5,le=200,allow_inf_nan=False)
    residents: int = Field(ge=0,le=100000,strict=True)
    points: list[Point] | None = Field(default=None,min_length=3,max_length=60)
    rotation: float | None = Field(default=None,ge=0,lt=180,allow_inf_nan=False)

class HomeLayout(StrictModel):
    houses: list[HomeSpec] = Field(min_length=1,max_length=20)
    boundary: list[Point] = Field(default_factory=list,max_length=60)
    roads: list[list[Point]] = Field(default_factory=list,max_length=19)


class WorkLimits(StrictModel):
    limits: dict[str, StrictInt | None]

    @field_validator('limits')
    @classmethod
    def valid_limits(cls, values):
        from .planning import PRICES
        if any(k not in PRICES for k in values):
            raise ValueError('Неизвестный вид работ')
        if any(v is not None and not 0 <= v <= 1_000_000_000_000 for v in values.values()):
            raise ValueError('Лимит должен быть от 0 до 1 000 000 000 000 ₽')
        return values
