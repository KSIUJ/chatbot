from datetime import datetime
from pydantic import BaseModel
from .models import MessageRole
#tu szablony odpowiedzi

class MessageResponse(BaseModel):
    id: str
    role: MessageRole
    content: str
    created_at: datetime
    sources: list[str] = [] #info od RAGa


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


class LogoutResponse(BaseModel):
    # Adres wylogowania z Keycloaka - frontend przekierowuje tam przegladarke.
    # None, gdy Keycloak jest niedostepny (sesja aplikacji i tak jest skasowana).
    logout_url: str | None
