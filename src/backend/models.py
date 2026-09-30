from __future__ import annotations

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
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
    """Konto uzytkownika zakladane automatycznie przy pierwszym logowaniu przez
    Keycloak KSI (OIDC). Tozsamoscia jest `oidc_sub` - email i nazwa sa tylko
    kopia danych z Keycloaka, odswiezana przy kazdym zapytaniu."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)

    # Claim "sub" z Keycloaka - staly identyfikator konta KSI.
    oidc_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    # preferred_username z Keycloaka
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # imie i nazwisko (claim "name")
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Lokalny wylacznik konta, niezalezny od Keycloaka.
    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    context_count: Mapped[int] = mapped_column(default=DEFAULT_CONTEXT_COUNT)

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"User(id={self.id!r}, oidc_sub={self.oidc_sub!r})"


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


class UserSession(Base):
    """Sesja aplikacji po zalogowaniu przez Keycloak.

    Przegladarka dostaje tylko losowy token w ciasteczku HttpOnly; w bazie jest
    jego SHA-256 (wyciek bazy nie daje dzialajacych ciasteczek). Tokeny z
    Keycloaka sa zaszyfrowane (Fernet, klucz z AUTH_SECRET_KEY) - backend uzywa
    ich przy kazdym zapytaniu, zeby sprawdzic czlonkostwo w grupie przez userinfo.
    """
    __tablename__ = "user_sessions"

    # SHA-256 (hex) tokenu z ciasteczka
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # id_token potrzebny tylko jako id_token_hint przy wylogowaniu z Keycloaka
    id_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"UserSession(user_id={self.user_id!r}, expires_at={self.expires_at!r})"
