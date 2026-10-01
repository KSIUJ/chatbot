"""Schematy zapytan API."""

from pydantic import BaseModel, Field

# Id rozmowy = 32 znaki hex (uuid4().hex). Nowa rozmowa dostaje id od klienta,
# zeby ponowienie po bledzie/przerwaniu trafialo do tej samej rozmowy.
CONVERSATION_ID_PATTERN = r"^[0-9a-f]{32}$"

# Gorna granica dlugosci pytania - chroni baze i kontekst LLM przed naduzyciem.
MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    # None albo nieistniejace id = nowa rozmowa
    conversation_id: str | None = Field(default=None, pattern=CONVERSATION_ID_PATTERN)
    regenerate: bool = False
