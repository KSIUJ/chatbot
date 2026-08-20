from __future__ import annotations

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Bazowa klasa po ktorej dziedzicza wszystkie modele.
    SQLAlchemy uzywa jej zeby wiedziec jakie tabele w ogole istnieja"""


def _new_id() -> str:
    """Generuje ID czyli losowy ciag znakow"""
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"

class MessageFeedback(str, enum.Enum):
    """Ocena odpowiedzi asystenta - lapka w gore/dol"""
    UP = "up"
    DOWN = "down"


# Domyslna liczba kontekstow jesli uzytkownik nie ustawil wlasnej
DEFAULT_CONTEXT_COUNT = 5


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Hash hasla by nie trzymac w postaci jawnej.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True)

    # Czy uzytkownik potwierdzil maila kodem wyslanym przy rejestracji
    # (osobne od is_active - to jest "czy konto aktywne/niezablokowane")
    zweryfikowany: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    context_count: Mapped[int] = mapped_column(default=DEFAULT_CONTEXT_COUNT)

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"User(id={self.id!r}, email={self.email!r})"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User | None"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Conversation(id={self.id!r}, user_id={self.user_id!r})"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Lista zrodel z RAG-a
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)

    feedback: Mapped[MessageFeedback | None] = mapped_column(SAEnum(MessageFeedback), nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Message(id={self.id!r}, role={self.role!r})"


class EmailCode(Base):
    """Kody weryfikacji maila wysylane przy rejestracji."""
    __tablename__ = "email_codes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    kod: Mapped[str] = mapped_column(String(6), nullable=False)
    typ: Mapped[str] = mapped_column(String(20), nullable=False)  # na razie zawsze "verify"
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(default=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"EmailCode(id={self.id!r}, user_id={self.user_id!r}, typ={self.typ!r})"


class BlacklistedToken(Base):
    """Token uniewazniony przez logout - trzymany do naturalnego wygasniecia."""
    __tablename__ = "blacklisted_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    token: Mapped[str] = mapped_column(String(500), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"BlacklistedToken(id={self.id!r})"