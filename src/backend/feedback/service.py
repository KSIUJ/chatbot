"""Oceny i zgloszenia odpowiedzi: zapis przez uzytkownika, stan w rozmowie,
przeglad i eksport dla zarzadu."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Conversation, Message, MessageFeedback, MessageRole, utcnow
from ..response import FeedbackState, parse_sources
from .schemas import AdminFeedbackItem, FeedbackKind, FeedbackRequest, ReportStatus

EMPTY_STATE = FeedbackState(rating=None, reported=False)


class FeedbackNotFound(LookupError):
    """Brak wiadomosci/wpisu albo cudze - API odpowiada 404."""


# --- uzytkownik -----------------------------------------------------------------

def _owned_answer(db: Session, message_id: str, user_id: str) -> Message:
    """Odpowiedz asystenta w rozmowie uzytkownika. Pytanie, cudza albo
    anonimowa rozmowa wygladaja jak nieistniejaca wiadomosc."""
    message = db.get(Message, message_id, populate_existing=True)
    if message is None or message.role != MessageRole.ASSISTANT:
        raise FeedbackNotFound(message_id)
    conversation = db.get(Conversation, message.conversation_id, populate_existing=True)
    if conversation is None or conversation.user_id != user_id:
        raise FeedbackNotFound(message_id)
    return message


def _question_before(db: Session, answer: Message) -> str | None:
    """Pytanie uzytkownika tuz przed odpowiedzia (do kopii w ocenie)."""
    stmt = (
        select(Message.content)
        .where(
            Message.conversation_id == answer.conversation_id,
            Message.role == MessageRole.USER,
            Message.created_at <= answer.created_at,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def to_state(row: MessageFeedback | None) -> FeedbackState:
    if row is None:
        return EMPTY_STATE
    rating = row.rating if row.rating in (1, -1) else None
    return FeedbackState(rating=rating, reported=row.report_reason is not None)


def _find(db: Session, user_id: str, message_id: str) -> MessageFeedback | None:
    stmt = select(MessageFeedback).where(
        MessageFeedback.user_id == user_id, MessageFeedback.message_id == message_id
    )
    return db.execute(stmt).scalar_one_or_none()


def _apply(row: MessageFeedback, request: FeedbackRequest) -> None:
    if request.sets_rating:
        row.rating = request.rating
    if request.language is not None:
        row.language = request.language
    if request.report is not None:
        # nowe zgloszenie zaczyna przeglad od nowa
        row.report_reason = request.report.reason
        row.comment = request.report.comment
        row.reported_at = utcnow()
        row.report_status = "open"
        row.admin_note = None
        row.reviewed_at = None
        row.reviewed_by = None


def _submit_once(db: Session, user_id: str, message_id: str, request: FeedbackRequest) -> FeedbackState:
    answer = _owned_answer(db, message_id, user_id)
    row = _find(db, user_id, message_id)
    is_new = row is None
    if row is None:
        row = MessageFeedback(
            user_id=user_id,
            message_id=message_id,
            question=_question_before(db, answer),
            answer=answer.content,
            sources=list(answer.sources or []),
        )
    _apply(row, request)

    is_empty = row.rating is None and row.report_reason is None
    if is_empty and not is_new:
        db.delete(row)
    elif not is_empty and is_new:
        db.add(row)
    db.commit()
    return EMPTY_STATE if is_empty else to_state(row)


def submit_feedback(db: Session, user_id: str, message_id: str, request: FeedbackRequest) -> FeedbackState:
    """Zapisuje ocene/zgloszenie odpowiedzi. Jeden wiersz na (uzytkownik,
    wiadomosc); wiersz bez oceny i bez zgloszenia jest kasowany.

    Bez blokady rozmowy: ta jest trzymana przez cale generowanie odpowiedzi,
    a ocena poprzedniej odpowiedzi nie moze na nie czekac. Wyscig dwoch
    rownoleglych pierwszych ocen konczy sie na unikalnym (user_id, message_id) -
    druga proba aktualizuje wiersz pierwszej.

    Raises:
        FeedbackNotFound: brak takiej odpowiedzi w rozmowach uzytkownika
            (takze gdy zniknela w trakcie zapisu).
    """
    try:
        return _submit_once(db, user_id, message_id, request)
    except IntegrityError:
        db.rollback()
    try:
        return _submit_once(db, user_id, message_id, request)
    except IntegrityError:
        # np. wiadomosc skasowana w miedzyczasie (FK w PostgreSQL)
        db.rollback()
        raise FeedbackNotFound(message_id) from None


def conversation_feedback(db: Session, user_id: str, conversation_id: str) -> dict[str, FeedbackState]:
    """Stan ocen uzytkownika dla wiadomosci rozmowy (id wiadomosci -> stan)."""
    in_conversation = select(Message.id).where(Message.conversation_id == conversation_id)
    stmt = select(MessageFeedback).where(
        MessageFeedback.user_id == user_id, MessageFeedback.message_id.in_(in_conversation)
    )
    return {row.message_id: to_state(row) for row in db.execute(stmt).scalars() if row.message_id is not None}


# --- zarzad -------------------------------------------------------------------------

def _filtered(kind: FeedbackKind | None, status: ReportStatus | None) -> Select[tuple[MessageFeedback]]:
    stmt = select(MessageFeedback)
    if kind == "reports":
        stmt = stmt.where(MessageFeedback.report_reason.is_not(None))
    elif kind == "ratings":
        stmt = stmt.where(MessageFeedback.rating.is_not(None))
    if status is not None:
        stmt = stmt.where(MessageFeedback.report_status == status)
    return stmt


def list_feedback(
    db: Session, kind: FeedbackKind, status: ReportStatus | None, limit: int, offset: int
) -> tuple[list[MessageFeedback], int]:
    """Strona wpisow od najnowszych (zgloszenia wg chwili zgloszenia, oceny
    wg ostatniej zmiany) i liczba wszystkich pasujacych."""
    stmt = _filtered(kind, status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    newest = MessageFeedback.reported_at if kind == "reports" else MessageFeedback.updated_at
    page = stmt.order_by(newest.desc(), MessageFeedback.created_at.desc(), MessageFeedback.id).limit(limit).offset(offset)
    return list(db.execute(page).scalars()), int(total)


def review_report(
    db: Session,
    feedback_id: str,
    reviewer_id: str,
    status: ReportStatus,
    admin_note: str | None,
    sets_note: bool,
) -> MessageFeedback:
    """Zmienia status zgloszenia (i ewentualnie notatke zarzadu).

    Raises:
        FeedbackNotFound: brak wpisu albo wpis bez zgloszenia (sama ocena).
    """
    row = db.get(MessageFeedback, feedback_id)
    if row is None or row.report_reason is None:
        raise FeedbackNotFound(feedback_id)
    row.report_status = status
    if sets_note:
        row.admin_note = admin_note
    if status == "open":
        row.reviewed_at = None
        row.reviewed_by = None
    else:
        row.reviewed_at = utcnow()
        row.reviewed_by = reviewer_id
    db.commit()
    db.refresh(row)
    return row


def to_admin_item(row: MessageFeedback) -> AdminFeedbackItem:
    return AdminFeedbackItem(
        id=row.id,
        message_id=row.message_id,
        rating=row.rating,
        report_reason=row.report_reason,
        comment=row.comment,
        report_status=row.report_status,
        admin_note=row.admin_note,
        reported_at=row.reported_at,
        reviewed_at=row.reviewed_at,
        question=row.question,
        answer=row.answer,
        sources=parse_sources(row.sources),
        language=row.language,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --- eksport CSV -----------------------------------------------------------------------

CSV_COLUMNS = (
    "id", "created_at", "updated_at", "rating", "report_reason", "report_status",
    "comment", "admin_note", "language", "question", "answer", "sources",
)
# Tekst od uzytkownikow i modelu - arkusz moglby go wykonac jako formule.
_TEXT_COLUMNS = frozenset({"comment", "admin_note", "question", "answer"})
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _neutralize(value: str) -> str:
    """CSV injection: komorka zaczynajaca sie od =, +, -, @ dostaje apostrof
    (OWASP) - Excel/Sheets pokaza ja jako tekst. Przy budowaniu zbioru
    ewaluacyjnego w Pythonie wiodacy apostrof trzeba zdjac."""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def _csv_row(row: MessageFeedback) -> list[str]:
    sources = json.dumps([s.model_dump() for s in parse_sources(row.sources)], ensure_ascii=False)
    values: dict[str, str] = {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "rating": "" if row.rating is None else str(row.rating),
        "report_reason": row.report_reason or "",
        "report_status": row.report_status or "",
        "comment": row.comment or "",
        "admin_note": row.admin_note or "",
        "language": row.language or "",
        "question": row.question or "",
        "answer": row.answer,
        "sources": sources,
    }
    return [_neutralize(values[c]) if c in _TEXT_COLUMNS else values[c] for c in CSV_COLUMNS]


def export_rows(db: Session, kind: FeedbackKind | None, status: ReportStatus | None) -> Iterable[MessageFeedback]:
    """Wpisy do eksportu od najstarszych (kolejnosc powstawania zbioru)."""
    stmt = _filtered(kind, status).order_by(MessageFeedback.created_at, MessageFeedback.id)
    return db.execute(stmt).scalars()


def to_csv(rows: Iterable[MessageFeedback]) -> str:
    """CSV z kopiami pytan i odpowiedzi. Caly plik w pamieci - zbior ocen
    jest maly (najwyzej tysiace wierszy) i tak jest prosciej niz strumien
    z sesja bazy otwarta po zakonczeniu zapytania."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(_csv_row(row))
    return buffer.getvalue()
