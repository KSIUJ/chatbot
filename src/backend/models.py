from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

#struktury danych backendu
#TODO jak będzie baza to się pozmienia wszystko ale pola plus minus są git


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class User:
    id: str = field(default_factory=lambda: uuid4().hex)
    username: str = ""


@dataclass
class Message:
    role: MessageRole
    content: str
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sources: list[str] = field(default_factory=list)  #info od RAGa


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: uuid4().hex)
    user_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[Message] = field(default_factory=list)
