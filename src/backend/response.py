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


class ChatResponse(BaseModel):
    conversation_id: str
    message: MessageResponse  # odpowiedz asystenta


class HealthResponse(BaseModel):
    status: str = "ok"
