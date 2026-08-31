from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
    device_id: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    display_name: str
    must_change_password: bool

    model_config = {"from_attributes": True}


class ConsentIn(BaseModel):
    consent_type: str
    granted: bool
    method: str = "verbal_and_operator_confirmed"
    version: str = "consent_v1"


class SubjectIn(BaseModel):
    display_name: str
    preferred_address: str = ""
    primary_language: str = "zh-CN"
    dialect_hint: str | None = None
    gender: str | None = None
    birth_year: int | None = None
    birth_date: str | None = None
    hometown: str | None = None
    occupation: str | None = None
    family_structure: str | None = None
    bio: str | None = None


class ProjectCreate(BaseModel):
    title: str
    subject: SubjectIn


class ProjectOut(BaseModel):
    id: UUID
    title: str
    owner_id: UUID
    created_at: datetime
    subject: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class SessionCreate(BaseModel):
    title: str = ""
    primary_language: str | None = None
    dialect_hint: str | None = None


class SessionOut(BaseModel):
    id: UUID
    project_id: UUID
    subject_id: UUID
    status: str
    title: str
    cloud_processing_enabled: bool
    active_recording_ms: int
    live_state_version: int
    final_state_version: int
    postprocess_quality: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TranscriptSegmentIn(BaseModel):
    sequence_number: int
    speaker_id: str
    start_ms: int
    end_ms: int
    raw_text: str
    confidence: float | None = None
    source: str = "tencent_live"
    idempotency_key: str | None = None


class TranscriptEditIn(BaseModel):
    edited_text: str
    reason: str | None = None
    version: int


class SpeakerMapIn(BaseModel):
    speaker_id: str
    display_name: str
    role_label: str | None = None


class QuestionActionIn(BaseModel):
    question_id: str
    action: str  # pin | asked | ignore | later
    score_meta: dict[str, Any] | None = None


class EmptyState(BaseModel):
    version: int = 1
    scope: str
    timeline: list[Any] = []
    people: list[Any] = []
    places: list[Any] = []
    events: list[Any] = []
    relationships: list[Any] = []
    questions: list[Any] = []
    first_experiences: list[Any] = []
    open_loops: list[Any] = []
    gaps: list[Any] = []
    conflicts: list[Any] = []
    themes: list[Any] = []
    coverage: dict[str, Any] = {}
