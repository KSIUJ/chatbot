from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Bazowa klasa po ktorej dziedzicza wszystkie modele.
    SQLAlchemy uzywa jej zeby wiedziec jakie tabele w ogole istnieja"""


def _new_id() -> str:
    """Generuje ID czyli losowy ciag znakow"""
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Conversation(Base):
    """Rozmowa w historii uzytkownika (sidebar). Nieuzywane dluzej niz
    CHAT_HISTORY_RETENTION_DAYS sa kasowane - patrz src/backend/history.py."""
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Pierwsze pytanie, skrocone - tytul na liscie w sidebarze
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Ostatnia wiadomosc: kolejnosc historii i licznik wygasania
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )

    user: Mapped["User | None"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True, nullable=False)
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Zrodla z RAG-a: {"kind", "title", "url"}; starsze wiadomosci maja tu
    # sciezki plikow (napisy) - API je pomija
    sources: Mapped[list[dict[str, str | None] | str]] = mapped_column(JSON, default=list)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class MessageFeedback(Base):
    """Ocena (lapka w gore/w dol) i/lub zgloszenie odpowiedzi asystenta.

    Jeden wiersz na (uzytkownik, wiadomosc) - kolejne klikniecia go nadpisuja,
    wiec nie da sie "nabic" ocen. Pytanie, odpowiedz i zrodla sa kopiowane przy
    pierwszej ocenie: rozmowy znikaja po CHAT_HISTORY_RETENTION_DAYS (i przy
    regeneracji odpowiedzi), a oceny zostaja jako material do zbioru
    ewaluacyjnego - message_id staje sie wtedy NULL.

    user_id tez przechodzi na NULL po usunieciu konta (anonimizacja zamiast
    kasowania): ocena dalej sluzy ewaluacji, ale nie wskazuje osoby.
    """
    __tablename__ = "message_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_message_feedback_user_message"),
        CheckConstraint("rating IN (1, -1)", name="ck_message_feedback_rating"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), index=True, nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # 1 = lapka w gore, -1 = w dol, NULL = brak oceny (zostalo samo zgloszenie)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # Zgloszenie: powod z feedback/schemas.py (ReportReason), NULL = brak zgloszenia
    report_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # open | resolved | dismissed (ReportStatus); NULL gdy nie ma zgloszenia
    report_status: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Kopia z chwili pierwszej oceny
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[dict[str, str | None] | str]] = mapped_column(JSON, default=list)
    # jezyk interfejsu podany przy ocenie (pl, en, ...)
    language: Mapped[str | None] = mapped_column(String(5), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SecurityIncident(Base):
    """Proba obejscia promptu systemowego - do przegladu przez zarzad KSI.

    Zrodlo: "heuristic" (security/injection.py), "model" (odpowiedz zaczela sie
    od [[NARUSZENIE]]) albo "both". Najwyzej jeden wiersz na pytanie
    uzytkownika (message_id); regeneracja odpowiedzi aktualizuje ten sam wiersz.

    W przeciwienstwie do ocen incydent wskazuje osobe (user_id) - zarzad musi
    wiedziec, kto probowal. conversation_id i message_id to zwykle kopie bez FK
    (rozmowy sa kasowane po CHAT_HISTORY_RETENTION_DAYS), wiec tresc pytania
    jest kopiowana. Wiersze starsze niz INCIDENT_RETENTION_DAYS sprzata
    zadanie w tle (security/incidents.py).
    """
    __tablename__ = "security_incidents"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_security_incidents_message"),
        CheckConstraint("source IN ('heuristic', 'model', 'both')", name="ck_security_incidents_source"),
        CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_security_incidents_status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # id pytania uzytkownika (messages.id); NULL gdy pytanie nie zostalo zapisane
    message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[str] = mapped_column(String(10), nullable=False)
    # nazwy regul heurystyki (RULE_NAMES); pusta lista gdy zglosil tylko model
    rules: Mapped[list[str]] = mapped_column(JSON, default=list)

    # open | resolved | dismissed (jak zgloszenia odpowiedzi)
    status: Mapped[str] = mapped_column(String(20), index=True, default="open", nullable=False)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UsageCounter(Base):
    """Liczniki statystyk (GET /stats), ktore nie maleja, gdy stare rozmowy
    sa kasowane - liczenie wierszy w messages spadaloby po kazdym czyszczeniu."""
    __tablename__ = "usage_counters"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[int] = mapped_column(default=0, nullable=False)


class AppSetting(Base):
    """Globalne ustawienie zmieniane przez zarzad w panelu administratora
    (klucz -> wartosc JSON), np. dzienny limit pytan i limity zalacznikow.
    Brak wiersza = wartosc domyslna z env (patrz limits/settings.py)."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int | str | list[str]] = mapped_column(JSON, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserLimit(Base):
    """Wyjatek od globalnego dziennego limitu pytan dla jednej osoby.
    daily_limit NULL = bez limitu, 0 = zablokowany. Admini nie maja wyjatku
    z urzedu - moga go sobie nadac jak kazdemu."""
    __tablename__ = "user_limits"
    __table_args__ = (
        CheckConstraint("daily_limit IS NULL OR daily_limit >= 0", name="ck_user_limits_daily_limit"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DailyUsage(Base):
    """Liczba pytan do modelu danej osoby w danym dniu (doba wg czasu
    polskiego, od polnocy). Zwiekszana atomowo przed wywolaniem modelu,
    zmniejszana, gdy odpowiedz nie zostala zapisana. Wiersze starsze niz
    USAGE_RETENTION_DAYS sprzata zadanie w tle (limits/usage.py)."""
    __tablename__ = "daily_usage"
    __table_args__ = (
        CheckConstraint("count >= 0", name="ck_daily_usage_count"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # id_token potrzebny tylko jako id_token_hint przy wylogowaniu z Keycloaka
    id_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
