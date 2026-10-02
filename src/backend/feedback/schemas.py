"""Schematy ocen i zgloszen odpowiedzi: zapytanie uzytkownika i API adminow."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..llm.language import Language
from ..response import SourceResponse

Rating = Literal[1, -1]
# blad merytoryczny, nieaktualne, nieodpowiednie/obrazliwe, inne
ReportReason = Literal["wrong", "outdated", "inappropriate", "other"]
# open = czeka na zarzad; resolved = poprawione; dismissed = odrzucone
ReportStatus = Literal["open", "resolved", "dismissed"]
# reports = wpisy ze zgloszeniem, ratings = wpisy z ocena
FeedbackKind = Literal["reports", "ratings"]

# Limity tekstu - komentarz pisze kazdy czlonek, wiec bez limitu baza by puchla.
MAX_COMMENT_LENGTH = 1000
MAX_ADMIN_NOTE_LENGTH = 1000


def _clean_text(value: str | None) -> str | None:
    """Obcina biale znaki; pusty tekst = brak tekstu."""
    if value is None:
        return None
    text = value.strip()
    return text or None


class ReportInput(BaseModel):
    """Zgloszenie odpowiedzi: powod i opcjonalny komentarz."""
    model_config = ConfigDict(extra="forbid")

    reason: ReportReason
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_LENGTH)

    @field_validator("comment")
    @classmethod
    def _clean_comment(cls, value: str | None) -> str | None:
        return _clean_text(value)


class FeedbackRequest(BaseModel):
    """PUT /messages/{id}/feedback.

    - `rating` pominiete = ocena bez zmian, `null` = usuniecie oceny,
    - `report` dodaje albo zastepuje zgloszenie (wraca do statusu open);
      zgloszenia nie da sie wycofac - trafilo juz do zarzadu,
    - `language` = jezyk interfejsu, zapisywany w kopii do ewaluacji.
    """
    model_config = ConfigDict(extra="forbid")

    rating: Rating | None = None
    report: ReportInput | None = None
    language: Language | None = None

    @property
    def sets_rating(self) -> bool:
        return "rating" in self.model_fields_set

    @model_validator(mode="after")
    def _requires_change(self) -> FeedbackRequest:
        if not self.sets_rating and self.report is None:
            raise ValueError("podaj rating albo report")
        return self


class AdminFeedbackItem(BaseModel):
    """Wpis w GET /admin/feedback - bez danych osobowych zglaszajacego."""
    id: str
    # None = odpowiedz juz nie istnieje (rozmowa usunieta albo regenerowana)
    message_id: str | None
    rating: int | None
    report_reason: str | None
    comment: str | None
    report_status: str | None
    admin_note: str | None
    reported_at: datetime | None
    reviewed_at: datetime | None
    question: str | None
    answer: str
    sources: list[SourceResponse]
    language: str | None
    created_at: datetime
    updated_at: datetime


class AdminFeedbackPage(BaseModel):
    items: list[AdminFeedbackItem]
    total: int
    limit: int
    offset: int


class AdminReviewRequest(BaseModel):
    """PATCH /admin/feedback/{id}. Pominieta notatka zostaje bez zmian,
    `null` albo pusty tekst ja kasuje."""
    model_config = ConfigDict(extra="forbid")

    status: ReportStatus
    admin_note: str | None = Field(default=None, max_length=MAX_ADMIN_NOTE_LENGTH)

    @field_validator("admin_note")
    @classmethod
    def _clean_note(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @property
    def sets_note(self) -> bool:
        return "admin_note" in self.model_fields_set
