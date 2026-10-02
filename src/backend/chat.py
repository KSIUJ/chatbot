"""Tura czatu: historia dla modelu i zapis pytania z odpowiedzia.

Wspolne dla POST /chat i POST /chat/stream. Zasada "najpierw odpowiedz":
nic nie trafia do bazy, dopoki nie ma tekstu odpowiedzi (pelnej albo
czesciowej po Stop), wiec blad modelu zostawia rozmowe bez zmian.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from .attachments.service import link_attachments, resolve_turn_attachments
from .database import (
    add_message,
    create_conversation,
    delete_last_assistant_message,
    get_messages,
)
from .history import make_room_for_new_conversation
from .limits.settings import get_attachment_limits
from .llm.attachments import PromptAttachment
from .llm.language import Language
from .llm.provider import provider_supports_images
from .models import Attachment, Conversation, Message, MessageRole
from .rag.sources import Source
from .response import AttachmentInfo, FeedbackState, MessageResponse, parse_sources
from .security.incidents import record_incident

logger = logging.getLogger(__name__)

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
    # reguly heurystyki (security/injection.py) pasujace do pytania i (z
    # prefiksem "attachment:") do tresci zalacznikow
    injection_rules: tuple[str, ...] = ()
    # zalaczniki dla modelu (tekst, obrazy)
    attachments: tuple[PromptAttachment, ...] = ()
    # niewyslane zalaczniki przypinane do pytania po zapisie odpowiedzi
    attachment_ids: tuple[str, ...] = ()


def with_attachments(db: Session, turn: ChatTurn, requested_ids: Sequence[str]) -> ChatTurn:
    """Tura uzupelniona o zalaczniki: podane id, przy regeneracji te
    z powtarzanego pytania, a za nimi pliki wyslane wczesniej w tej rozmowie.
    Wolane przed zuzyciem limitu pytan i modelem.

    Raises:
        AttachmentError: 404 attachment_not_found, 422 too_many_files albo
            422 images_unsupported.
    """
    resolved = resolve_turn_attachments(
        db,
        user_id=turn.user_id,
        conversation_id=turn.conversation_id,
        requested_ids=requested_ids,
        regenerate=turn.regenerate,
        max_files=get_attachment_limits(db).max_files_per_message,
        images_supported=provider_supports_images(),
    )
    if not resolved.prompt:
        return turn
    return replace(
        turn,
        attachments=resolved.prompt,
        attachment_ids=resolved.link_ids,
        injection_rules=tuple(dict.fromkeys([*turn.injection_rules, *resolved.injection_rules])),
    )


def model_kwargs(turn: ChatTurn) -> dict[str, object]:
    """Argumenty answer()/stream_answer() dla tury; attachments tylko gdy sa."""
    kwargs: dict[str, object] = {"language": turn.language}
    if turn.attachments:
        kwargs["attachments"] = list(turn.attachments)
    return kwargs


def attachment_infos(rows: Sequence[Attachment]) -> list[AttachmentInfo]:
    return [AttachmentInfo(id=row.id, name=row.name, size=row.size, type=row.kind) for row in rows]


def to_message_response(
    message: Message, feedback: FeedbackState | None = None, attachments: Sequence[Attachment] = ()
) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        sources=parse_sources(message.sources),
        feedback=feedback,
        attachments=attachment_infos(attachments),
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
    Niewyslane zalaczniki tury sa przypinane do pytania w commicie odpowiedzi.

    Raises:
        ConversationNotOwned: rozmowa o tym id nalezy do innego konta.
    """
    conversation = db.get(Conversation, turn.conversation_id, populate_existing=True)
    if conversation is None:
        make_room_for_new_conversation(db, turn.user_id, turn.max_per_user)
        create_conversation(db, user_id=turn.user_id, conversation_id=turn.conversation_id)
        question_id: str | None = add_message(db, turn.conversation_id, MessageRole.USER, turn.question).id
    elif conversation.user_id != turn.user_id:
        raise ConversationNotOwned(turn.conversation_id)
    elif turn.regenerate:
        delete_last_assistant_message(db, conversation.id)
        question_id = _latest_question_id(db, conversation.id)
    else:
        question_id = add_message(db, conversation.id, MessageRole.USER, turn.question).id
    if question_id is not None:
        link_attachments(db, turn.user_id, turn.conversation_id, question_id, turn.attachment_ids)
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


def _latest_question_id(db: Session, conversation_id: str) -> str | None:
    """Id ostatniego pytania w rozmowie - tuz po zapisie odpowiedzi (pod
    blokada rozmowy) to pytanie z biezacej tury, takze przy regeneracji."""
    stmt = (
        select(Message.id)
        .where(Message.conversation_id == conversation_id, Message.role == MessageRole.USER)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def record_turn_incident(
    session_factory: SessionFactory, turn: ChatTurn, model_flagged: bool, answer_saved: bool
) -> None:
    """Incydent dla tury z trafieniem heurystyki i/lub znacznikiem od modelu
    (jeden na pytanie). Wolane na koncu tury, takze po bledzie modelu; bez
    zapisanej odpowiedzi incydent nie wskazuje wiadomosci.

    Blad zapisu incydentu jest logowany i nie psuje odpowiedzi - uzytkownik
    dostal juz odpowiedz, a proba i tak trafia do logow (warning ponizej)."""
    if not turn.injection_rules and not model_flagged:
        return
    logger.warning(
        "possible prompt injection: user %s, conversation %s, rules %s, model marker %s",
        turn.user_id, turn.conversation_id, list(turn.injection_rules), model_flagged,
    )
    db = session_factory()
    try:
        record_incident(
            db,
            user_id=turn.user_id,
            conversation_id=turn.conversation_id,
            message_id=_latest_question_id(db, turn.conversation_id) if answer_saved else None,
            question=turn.question,
            rules=turn.injection_rules,
            model_flagged=model_flagged,
        )
    except Exception:
        db.rollback()
        logger.exception("recording security incident failed (conversation %s)", turn.conversation_id)
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
