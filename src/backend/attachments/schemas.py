"""Schematy API zalacznikow."""

from __future__ import annotations

from pydantic import BaseModel

from ..limits.settings import AttachmentType


class AttachmentUploadResponse(BaseModel):
    """POST /attachments - zapisany (jeszcze niewyslany) zalacznik."""
    id: str
    name: str
    size: int
    type: AttachmentType
    # liczba stron PDF; None dla innych rodzajow
    pages: int | None = None
    # dlugosc wyciagnietego tekstu; None dla obrazow
    chars: int | None = None
