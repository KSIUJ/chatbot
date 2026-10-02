"""Schematy API incydentow bezpieczenstwa dla zarzadu (/admin/incidents)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# heuristic = heurystyka backendu, model = znacznik [[NARUSZENIE]], both = oba
IncidentSource = Literal["heuristic", "model", "both"]


class IncidentUser(BaseModel):
    """Kto probowal - kopia danych z Keycloaka w tabeli users."""
    id: str
    name: str | None
    username: str | None
    email: str | None


class AdminIncidentItem(BaseModel):
    """Wpis w GET /admin/incidents. Zawiera dane osoby (inaczej niz oceny)."""
    id: str
    user_id: str | None
    # None = konto juz nie istnieje
    user: IncidentUser | None
    conversation_id: str | None
    message_id: str | None
    question: str
    source: str
    rules: list[str]
    status: str
    admin_note: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminIncidentPage(BaseModel):
    items: list[AdminIncidentItem]
    total: int
    limit: int
    offset: int
