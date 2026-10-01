"""Tura czatu: historia dla modelu i zapis pytania z odpowiedzia.

Wspolne dla POST /chat i POST /chat/stream. Zasada "najpierw odpowiedz":
nic nie trafia do bazy, dopoki nie ma tekstu odpowiedzi (pelnej albo
czesciowej po Stop), wiec blad modelu zostawia rozmowe bez zmian.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .database import (
    add_message,
    create_conversation,
    delete_last_assistant_message,
    get_messages,
)
from .history import make_room_for_new_conversation
from .llm.language import Language
from .models import Conversation, Message, MessageRole
from .rag.sources import Source
from .response import MessageResponse, parse_sources

SessionFactory = Callable[[], Session]


class ConversationNotOwned(LookupError):
    """Rozmowa nalezy do kogos innego - API odpowiada jak na nieistniejaca."""


@dataclass(frozen=True)
class ChatTurn:
    """Jedno pytanie uzytkownika w konkretnej rozmowie."""
    user_id: str
    conversation_id: str
    question: str
    regenerate: bool
    language: Language
    # limit rozmow na konto - nowa rozmowa wypycha najstarsza
    max_per_user: int


def to_message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        sources=parse_sources(message.sources),
    )


def build_history(previous: Sequence[Message], regenerate: bool) -> list[dict[str, str]]:
    """Historia dla modelu. Regeneracja powtarza ostatnie pytanie - ani
    odrzucona odpowiedz, ani samo pytanie nie trafiaja do historii."""
    messages = list(previous)
    if regenerate:
        if messages and messages[-1].role == MessageRole.ASSISTANT:
            messages = messages[:-1]
        if messages and messages[-1].role == MessageRole.USER:
            messages = messages[:-1]
    return [{"role": m.role.value, "content": m.content} for m in messages]


def load_history(db: Session, turn: ChatTurn) -> list[dict[str, str]]:
    """Historia rozmowy z tury; nowa rozmowa = pusta historia.

    Raises:
        ConversationNotOwned: rozmowa o tym id nalezy do innego konta.
    """
    conversation = db.get(Conversation, turn.conversation_id, populate_existing=True)
    if conversation is None:
        return []
    if conversation.user_id != turn.user_id:
        raise ConversationNotOwned(turn.conversation_id)
    return build_history(get_messages(db, conversation.id), turn.regenerate)


def save_exchange(db: Session, turn: ChatTurn, answer_text: str, sources: Sequence[Source]) -> Message:
    """Zapisuje pytanie i odpowiedz; zwraca wiadomosc asystenta.

    Nowa rozmowa: zrobienie miejsca (limit na konto), zalozenie rozmowy,
    pytanie, odpowiedz. Istniejaca: pytanie + odpowiedz, a przy regeneracji
    stara odpowiedz znika w tym samym commicie, w ktorym zapisuje sie nowa.

    Raises:
        ConversationNotOwned: rozmowa o tym id nalezy do innego konta.
    """
    conversation = db.get(Conversation, turn.conversation_id, populate_existing=True)
    if conversation is None:
        make_room_for_new_conversation(db, turn.user_id, turn.max_per_user)
        create_conversation(db, user_id=turn.user_id, conversation_id=turn.conversation_id)
        add_message(db, turn.conversation_id, MessageRole.USER, turn.question)
    elif conversation.user_id != turn.user_id:
        raise ConversationNotOwned(turn.conversation_id)
    elif turn.regenerate:
        delete_last_assistant_message(db, conversation.id)
    else:
        add_message(db, conversation.id, MessageRole.USER, turn.question)
    return add_message(db, turn.conversation_id, MessageRole.ASSISTANT, answer_text, sources)


def save_answer(
    session_factory: SessionFactory, turn: ChatTurn, answer_text: str, sources: Sequence[Source]
) -> MessageResponse:
    """save_exchange we wlasnej sesji (strumien nie ma sesji zapytania)."""
    db = session_factory()
    try:
        return to_message_response(save_exchange(db, turn, answer_text, sources))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_partial_answer(
    session_factory: SessionFactory, turn: ChatTurn, answer_text: str, sources: Sequence[Source]
) -> MessageResponse | None:
    """Zapis przerwanej odpowiedzi (Stop, zamkniecie karty) tak samo jak
    pelnej. Bez zadnego tekstu nic nie zapisuje i zwraca None."""
    text = answer_text.strip()
    if not text:
        return None
    return save_answer(session_factory, turn, text, sources)
