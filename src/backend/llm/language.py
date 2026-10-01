"""Jezyki odpowiedzi do wyboru w interfejsie (ChatRequest.language)."""

from typing import Literal

Language = Literal["pl", "en", "fr"]

DEFAULT_LANGUAGE: Language = "pl"
