"""Schematy odpowiedzi API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .models import MessageRole
from .rag.sources import SourceKind


class SourceResponse(BaseModel):
    """Zrodlo odpowiedzi: strona wydzialu, profil USOS albo plik z mordora."""
    kind: SourceKind
    title: str = Field(min_length=1)
    url: str | None = None


def parse_sources(raw: object) -> list[SourceResponse]:
    """Zrodla zapisane w Message.sources. Stare wpisy (sciezki plikow jako
    napisy) i wpisy niepasujace do schematu sa pomijane."""
    if not isinstance(raw, list):
        return []
    sources = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            sources.append(SourceResponse.model_validate(entry))
        except ValidationError:
            continue
    return sources


class FeedbackState(BaseModel):
    """Ocena odpowiedzi przez biezacego uzytkownika - frontend pokazuje ja po
    przeladowaniu (wiadomosci asystenta w GET /conversations/{id})."""
    rating: Literal[1, -1] | None
    reported: bool


class MessageResponse(BaseModel):
    id: str
    role: MessageRole
    content: str
    created_at: datetime
    sources: list[SourceResponse] = Field(default_factory=list)  # zrodla z RAG-a
    # tylko odpowiedzi asystenta w GET /conversations/{id}; None = nie dotyczy
    feedback: FeedbackState | None = None


class ConversationResponse(BaseModel):
    id: str
    created_at: datetime
    messages: list[MessageResponse]


class ConversationSummary(BaseModel):
    """Pozycja historii w sidebarze (GET /conversations)."""
    id: str
    title: str | None
    last_message_at: datetime


class ConversationList(BaseModel):
    """Historia + limity z env - frontend pokazuje je w notce pod lista."""
    conversations: list[ConversationSummary]
    max_per_user: int
    retention_days: int


class ChatResponse(BaseModel):
    conversation_id: str
    message: MessageResponse  # odpowiedz asystenta


class HealthResponse(BaseModel):
    status: str = "ok"


class StatsResponse(BaseModel):
    accounts_created: int  # konta = osoby, ktore choc raz zalogowaly sie przez KSI
    anonymous_conversations: int  # historyczne - od logowania przez KSI nie powstaja nowe
    total_prompts: int


class UserResponse(BaseModel):
    """Zalogowany czlonek KSI (GET /auth/me)."""
    id: str
    email: str | None
    username: str | None
    name: str | None
    # w grupie OIDC_ADMIN_GROUP - moze przegladac oceny i zgloszenia
    is_admin: bool = False


class LogoutResponse(BaseModel):
    # Adres wylogowania z Keycloaka - frontend przekierowuje tam przegladarke.
    # None, gdy Keycloak jest niedostepny (sesja aplikacji i tak jest skasowana).
    logout_url: str | None
