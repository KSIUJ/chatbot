"""Schematy API limitow: stan dziennego limitu biezacego uzytkownika."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AttachmentUsage(BaseModel):
    """Limity zalacznikow dla pola pytania i dzisiejsze zuzycie."""
    max_file_mb: int
    # obrazy: mniejszy z MAX_IMAGE_MB i max_file_mb
    max_image_mb: int
    max_files_per_message: int
    # 0 = zalaczniki wylaczone
    max_per_day: int
    used_today: int
    allowed_types: list[str]
    # czy biezacy dostawca LLM przyjmuje obrazy
    images_supported: bool


class UsageResponse(BaseModel):
    """GET /usage - ile pytan zuzyto dzisiaj, limit i chwila odnowienia."""
    used: int
    # None = bez limitu (wyjatek nadany przez zarzad)
    limit: int | None
    reset_at: datetime
    # wylacznik czatu (panel administratora); komunikat None = domyslny
    chat_enabled: bool = True
    chat_disabled_message: str | None = None
    attachments: AttachmentUsage | None = None
