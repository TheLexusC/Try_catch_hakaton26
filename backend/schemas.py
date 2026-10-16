"""Strict API contracts. Clients cannot assign roles or moderation status."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Credentials(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()


class Registration(Credentials):
    name: str = Field(min_length=2, max_length=60)

    @field_validator('name', mode='before')
    @classmethod
    def clean_name(cls, value):
        return value.strip() if isinstance(value, str) else value


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
    action: Action
    base_version: int = Field(ge=0)


class Proposal(Preview):
    reason: str = Field(min_length=10, max_length=1000)


class Decision(StrictModel):
    decision: Literal['approved', 'rejected']
    comment: str = Field(min_length=5, max_length=1000)
