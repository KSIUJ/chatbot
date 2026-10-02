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
