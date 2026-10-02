"""Schematy API limitow: stan dziennego limitu biezacego uzytkownika."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UsageResponse(BaseModel):
    """GET /usage - ile pytan zuzyto dzisiaj, limit i chwila odnowienia."""
    used: int
    # None = bez limitu (wyjatek nadany przez zarzad)
    limit: int | None
    reset_at: datetime
    # wylacznik czatu (panel administratora); komunikat None = domyslny
    chat_enabled: bool = True
    chat_disabled_message: str | None = None
