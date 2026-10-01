"""Polaczenie z baza i operacje na uzytkownikach, rozmowach, wiadomosciach
i licznikach statystyk. Schemat bazy tworza wylacznie migracje Alembica."""

from __future__ import annotations

import os
from collections.abc import Generator, Sequence

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .history import make_title
from .models import Conversation, Message, MessageRole, UsageCounter, User, utcnow
from .rag.sources import Source

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./chatbot.db"

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI: sesja bazy na czas jednego zapytania."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> sessionmaker[Session]:
    """Dependency FastAPI: fabryka sesji dla kodu, ktory dziala dluzej niz
    samo zapytanie (strumien odpowiedzi otwiera wlasne sesje)."""
    return SessionLocal


# USERS
# Konta zaklada i aktualizuje logowanie OIDC - patrz src/backend/auth/service.py


def get_user_by_oidc_sub(db: Session, oidc_sub: str) -> User | None:
    stmt = select(User).where(User.oidc_sub == oidc_sub)
    return db.execute(stmt).scalar_one_or_none()


def count_users(db: Session) -> int:
    """Liczba kont - kazde powstaje przy pierwszym udanym logowaniu przez KSI."""
    return db.execute(select(func.count()).select_from(User)).scalar_one()


# CONVERSATIONS
# Lista, usuwanie i wygasanie rozmow: src/backend/history.py


def create_conversation(db: Session, user_id: str, conversation_id: str | None = None) -> Conversation:
    """Zaklada rozmowe uzytkownika; conversation_id nadaje klient (32 hex),
    bez niego id jest losowe."""
    conversation = Conversation(user_id=user_id)
    if conversation_id is not None:
        conversation.id = conversation_id
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, conversation_id: str) -> Conversation | None:
    return db.get(Conversation, conversation_id)


# STATS
# Liczniki w osobnej tabeli - nie maleja, gdy stare rozmowy sa kasowane.

PROMPTS_COUNTER = "total_prompts"
ANONYMOUS_CONVERSATIONS_COUNTER = "anonymous_conversations"


def get_counter(db: Session, key: str) -> int:
    counter = db.get(UsageCounter, key)
    return counter.value if counter is not None else 0


def increment_counter(db: Session, key: str, by: int = 1) -> None:
    """Zwieksza licznik atomowo w bazie (UPDATE value = value + by), zeby
    rownolegle zapytania nie gubily inkrementow. Bez commita - commituje
    wolajacy razem ze swoja zmiana. Brakujacy wiersz jest zakladany."""
    result = db.execute(
        update(UsageCounter).where(UsageCounter.key == key).values(value=UsageCounter.value + by)
    )
    if result.rowcount:
        return
    try:
        with db.begin_nested():
            db.add(UsageCounter(key=key, value=by))
    except IntegrityError:
        # ktos wlasnie zalozyl ten wiersz - wystarczy go zwiekszyc
        db.execute(
            update(UsageCounter).where(UsageCounter.key == key).values(value=UsageCounter.value + by)
        )


# MESSAGES


def add_message(
    db: Session,
    conversation_id: str,
    role: MessageRole,
    content: str,
    sources: Sequence[Source] | None = None,
) -> Message:
    """Dopisuje wiadomosc i commituje (razem z niezacommitowanymi zmianami sesji)."""
    conversation = get_conversation(db, conversation_id)
    if conversation is None:
        raise KeyError(f"Konwersacja {conversation_id} nie istnieje")

    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=list(sources or []),
    )
    db.add(message)

    # kazda wiadomosc odswieza pozycje rozmowy w historii i odsuwa jej wygasniecie
    conversation.last_message_at = utcnow()
    if role == MessageRole.USER:
        if conversation.title is None:
            conversation.title = make_title(content)
        increment_counter(db, PROMPTS_COUNTER)
    db.commit()
    db.refresh(message)
    return message


def get_messages(db: Session, conversation_id: str) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def delete_last_assistant_message(db: Session, conversation_id: str) -> bool:
    """Oznacza do usuniecia ostatnia wiadomosc asystenta, jesli rozmowa konczy
    sie wlasnie nia (regeneracja odpowiedzi). Bez commita - wolajacy commituje
    razem z nowa odpowiedzia, wiec stara znika tylko wtedy, gdy nowa jest zapisana."""
    messages = get_messages(db, conversation_id)
    if not messages or messages[-1].role != MessageRole.ASSISTANT:
        return False

    db.delete(messages[-1])
    return True
