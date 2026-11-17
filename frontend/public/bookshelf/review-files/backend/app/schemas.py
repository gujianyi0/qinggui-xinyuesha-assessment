from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class SessionInput(StrictModel):
    title: str = Field(default="新的游戏问题", min_length=1, max_length=160)


class RunInput(StrictModel):
    message: str = Field(min_length=1, max_length=8000)
    snapshot_id: str | None = Field(default=None, max_length=160)
    request_id: UUID | None = None
    ruling_scene_id: Literal['SC01', 'SC02', 'SC03', 'SC04', 'SC05', 'SC06', 'SC07', 'SC08'] | None = None
    ruling_mode: Literal['actual', 'reference'] = 'actual'
    ruling_conditions: dict = Field(default_factory=dict, max_length=20)


class DraftInput(StrictModel):
    session_id: str | None = None
    category: Literal["rules", "client"] = "rules"
    actual: str = Field(default="", max_length=8000)
    expected: str = Field(default="", max_length=8000)
    steps: str = Field(default="", max_length=8000)
    context: str = Field(default="", max_length=8000)
    platform: str = Field(default="", max_length=120)
    client_version: str = Field(default="", max_length=120)


class DraftPatch(StrictModel):
    revision: int = Field(ge=1)
    category: Literal["rules", "client"] | None = None
    actual: str | None = Field(default=None, max_length=8000)
    expected: str | None = Field(default=None, max_length=8000)
    steps: str | None = Field(default=None, max_length=8000)
    context: str | None = Field(default=None, max_length=8000)
    platform: str | None = Field(default=None, max_length=120)
    client_version: str | None = Field(default=None, max_length=120)


class ConfirmInput(StrictModel):
    revision: int = Field(ge=1)


class JobInput(StrictModel):
    snapshot_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=120)


class QQInput(StrictModel):
    self_id: str | int
    user_id: str | int
    message_type: Literal["private", "group"]
    group_id: str | int | None = None
    message_id: str | int
    raw_message: str = Field(min_length=1, max_length=8000)


class DeliveryInput(StrictModel):
    status: Literal["sent", "failed", "unknown"]
    platform_message_id: str | int | None = None
    error: str | None = Field(default=None, max_length=240)
