"""Obraz z zalacznika przekazywany modelowi (dostawcy z obsluga obrazow)."""

from __future__ import annotations

import base64
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageInput:
    # image/png, image/jpeg albo image/webp
    mime: str
    data: bytes

    def base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    def data_url(self) -> str:
        """Adres data: dla API zgodnych z OpenAI (OpenRouter)."""
        return f"data:{self.mime};base64,{self.base64()}"
