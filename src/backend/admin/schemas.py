"""Schematy API panelu administratora: limity, uzytkownicy, diagnostyka."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.fields import FieldInfo

from ..limits.settings import (
    DAILY_QUESTION_LIMIT_RANGE,
    MAX_ATTACHMENTS_PER_DAY_RANGE,
    MAX_FILE_MB_RANGE,
    MAX_FILES_PER_MESSAGE_RANGE,
    USER_DAILY_LIMIT_RANGE,
    AttachmentType,
    IntRange,
    LimitSettings,
    normalize_types,
)

MAX_NOTE_LENGTH = 500
MAX_QUERY_LENGTH = 200


def _bounded(allowed: IntRange) -> FieldInfo:
    return Field(ge=allowed.minimum, le=allowed.maximum)


# --- ustawienia globalne -------------------------------------------------------------------

class AttachmentLimitsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_file_mb: Annotated[int, _bounded(MAX_FILE_MB_RANGE)]
    max_files_per_message: Annotated[int, _bounded(MAX_FILES_PER_MESSAGE_RANGE)]
    max_per_day: Annotated[int, _bounded(MAX_ATTACHMENTS_PER_DAY_RANGE)]
    allowed_types: list[AttachmentType] = Field(min_length=1)

    @field_validator("allowed_types")
    @classmethod
    def _unique_types(cls, value: list[AttachmentType]) -> list[AttachmentType]:
        return list(normalize_types(value))


class LimitSettingsModel(BaseModel):
    """PUT /admin/settings - pelna zamiana globalnych limitow."""
    model_config = ConfigDict(extra="forbid")

    daily_question_limit: Annotated[int, _bounded(DAILY_QUESTION_LIMIT_RANGE)]
    attachments: AttachmentLimitsModel

    @classmethod
    def from_settings(cls, settings: LimitSettings) -> LimitSettingsModel:
        a = settings.attachments
        return cls(
            daily_question_limit=settings.daily_question_limit,
            attachments=AttachmentLimitsModel(
                max_file_mb=a.max_file_mb,
                max_files_per_message=a.max_files_per_message,
                max_per_day=a.max_per_day,
                allowed_types=list(a.allowed_types),
            ),
        )


class IntRangeModel(BaseModel):
    min: int
    max: int


class SettingsRanges(BaseModel):
    """Zakresy wartosci - formularz pokazuje je jako min/max pol."""
    daily_question_limit: IntRangeModel
    user_daily_limit: IntRangeModel
    max_file_mb: IntRangeModel
    max_files_per_message: IntRangeModel
    max_per_day: IntRangeModel


class AdminSettingsResponse(LimitSettingsModel):
    """GET/PUT /admin/settings: obowiazujace limity, wartosci domyslne z env,
    wszystkie znane rodzaje plikow i zakresy."""
    defaults: LimitSettingsModel
    available_types: list[AttachmentType]
    ranges: SettingsRanges


def ranges_model() -> SettingsRanges:
    def model(allowed: IntRange) -> IntRangeModel:
        return IntRangeModel(min=allowed.minimum, max=allowed.maximum)

    return SettingsRanges(
        daily_question_limit=model(DAILY_QUESTION_LIMIT_RANGE),
        user_daily_limit=model(USER_DAILY_LIMIT_RANGE),
        max_file_mb=model(MAX_FILE_MB_RANGE),
        max_files_per_message=model(MAX_FILES_PER_MESSAGE_RANGE),
        max_per_day=model(MAX_ATTACHMENTS_PER_DAY_RANGE),
    )


# --- uzytkownicy i wyjatki -------------------------------------------------------------------

class UserLimitRequest(BaseModel):
    """PUT /admin/users/{id}/limit. unlimited=true -> bez limitu (bez
    daily_limit); inaczej daily_limit jest wymagany (0 = zablokowany)."""
    model_config = ConfigDict(extra="forbid")

    unlimited: bool
    daily_limit: Annotated[int, _bounded(USER_DAILY_LIMIT_RANGE)] | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def _consistent(self) -> UserLimitRequest:
        if self.unlimited and self.daily_limit is not None:
            raise ValueError("unlimited wyklucza daily_limit")
        if not self.unlimited and self.daily_limit is None:
            raise ValueError("podaj daily_limit albo unlimited=true")
        return self


class UserOverrideModel(BaseModel):
    unlimited: bool
    daily_limit: int | None
    note: str | None
    updated_at: datetime


class AdminUserItem(BaseModel):
    id: str
    name: str | None
    username: str | None
    email: str | None
    last_login_at: datetime | None
    used_today: int
    # None = bez limitu
    effective_limit: int | None
    override: UserOverrideModel | None


class AdminUserPage(BaseModel):
    items: list[AdminUserItem]
    total: int
    limit: int
    offset: int


# --- diagnostyka ---------------------------------------------------------------------------------

class LlmDiagnostics(BaseModel):
    provider: str
    model: str
    started_at: datetime
    uptime_seconds: float
    total_calls: int
    total_errors: int
    recent_calls: int
    recent_errors: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    last_error: str | None
    last_error_at: datetime | None


class UsageDiagnostics(BaseModel):
    questions_today: int | None
    questions_7d: int | None
    active_users_today: int | None
    active_users_7d: int | None
    error: str | None


class TotalsDiagnostics(BaseModel):
    users: int | None
    conversations: int | None
    messages: int | None
    open_reports: int | None
    open_incidents: int | None
    error: str | None


class RagDiagnostics(BaseModel):
    vector_count: int | None
    vector_error: str | None
    lexical_count: int | None
    lexical_size_bytes: int | None
    lexical_error: str | None
    last_ingest_at: datetime | None
    last_ingest_error: str | None


class StorageDiagnostics(BaseModel):
    database_size_bytes: int | None
    database_error: str | None
    disk_free_bytes: int | None
    disk_total_bytes: int | None
    disk_error: str | None


class DiagnosticsResponse(BaseModel):
    generated_at: datetime
    llm: LlmDiagnostics
    usage: UsageDiagnostics
    totals: TotalsDiagnostics
    rag: RagDiagnostics
    storage: StorageDiagnostics
