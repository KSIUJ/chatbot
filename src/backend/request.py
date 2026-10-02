"""Schematy zapytan API."""

from typing import Annotated

from pydantic import BaseModel, Field

from .limits.settings import MAX_FILES_PER_MESSAGE_RANGE
from .llm.language import DEFAULT_LANGUAGE, Language

# Id rozmowy = 32 znaki hex (uuid4().hex). Nowa rozmowa dostaje id od klienta,
# zeby ponowienie po bledzie/przerwaniu trafialo do tej samej rozmowy.
CONVERSATION_ID_PATTERN = r"^[0-9a-f]{32}$"

# Gorna granica dlugosci pytania - chroni baze i kontekst LLM przed naduzyciem.
MAX_MESSAGE_LENGTH = 4000

ATTACHMENT_ID_PATTERN = r"^[0-9a-f]{32}$"
# gorna granica z zakresu ustawien panelu; obowiazujacy limit jest w bazie
MAX_ATTACHMENT_IDS = MAX_FILES_PER_MESSAGE_RANGE.maximum


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    # None albo nieistniejace id = nowa rozmowa
    conversation_id: str | None = Field(default=None, pattern=CONVERSATION_ID_PATTERN)
    regenerate: bool = False
    # jezyk interfejsu - w nim model odpowiada
    language: Language = DEFAULT_LANGUAGE
    # zalaczniki z POST /attachments (niewyslane albo juz w tej rozmowie);
    # limit na wiadomosc z panelu sprawdza backend (too_many_files)
    attachment_ids: list[Annotated[str, Field(pattern=ATTACHMENT_ID_PATTERN)]] = Field(
        default_factory=list, max_length=MAX_ATTACHMENT_IDS
    )
