"""Strict API contracts. Clients cannot assign roles or moderation status."""
from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class Values(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: Literal['home','stop','park','school','clinic','shop'] | None = None
    x: float | None = Field(default=None, ge=0, le=20000)
    y: float | None = Field(default=None, ge=0, le=20000)
    residents: int | None = Field(default=None, ge=0, le=100000, strict=True)
    capacity: int | None = Field(default=None, ge=1, le=100000, strict=True)
    load: int | None = Field(default=None, ge=0, le=100000, strict=True)
    a: str | None = Field(default=None, max_length=64)
    b: str | None = Field(default=None, max_length=64)
    closed: bool | None = Field(default=None, strict=True)


class Action(StrictModel):
    entity: Literal['object','node','edge']
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
    comment: str = Field(min_length=5, max_length=1000)
