from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TzSource = Literal["aoe", "explicit", "date_only_default", "requester_tz_fallback", "relative"]
Kind = Literal["deadline", "abstract_deadline", "notification", "camera_ready", "rebuttal", "other"]
ExtractSource = Literal["rules", "llm"]


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1)
    tz: str | None = Field(default=None, description="Requester IANA timezone, e.g. Asia/Karachi")
    fast: bool = Field(default=False, description="Skip the LLM tier; rules-only, instant")


class Localized(BaseModel):
    tz: str
    iso: datetime
    human: str


class Alternate(BaseModel):
    basis: Literal["aoe", "utc", "requester_tz"]
    iso: datetime
    human: str


class Remaining(BaseModel):
    expired: bool
    total_seconds: int
    days: int
    hours: int
    minutes: int
    seconds: int
    human: str


class Deadline(BaseModel):
    raw_text: str
    label: str | None = None
    kind: Kind
    aoe: bool
    tz_source: TzSource
    source: ExtractSource
    deadline_utc: datetime
    epoch_seconds: int
    local: Localized
    alternates: list[Alternate] = []
    note: str | None = None
    remaining: Remaining


class ExtractResponse(BaseModel):
    now_utc: datetime
    requester_tz: str
    degraded: bool
    deadlines: list[Deadline]


class NowResponse(BaseModel):
    now_utc: datetime
    tz: str
    local: Localized


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    degraded: bool
    model_path: str
    model_error: str | None = None
