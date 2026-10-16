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


class Action(StrictModel):
    type: Literal['close_edge', 'open_edge', 'move_stop', 'add_park', 'remove_park']
    target_id: str = Field(min_length=1, max_length=80)
    facility_id: str | None = Field(default=None, max_length=80)


class Preview(StrictModel):
    action: Action
    base_version: int = Field(ge=0)


class Proposal(Preview):
    reason: str = Field(min_length=10, max_length=1000)


class Decision(StrictModel):
    decision: Literal['approved', 'rejected']
    comment: str = Field(min_length=5, max_length=1000)
