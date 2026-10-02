"""Incydenty bezpieczenstwa: zapis proby obejscia promptu, przeglad przez
zarzad KSI i sprzatanie starych wpisow."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..feedback.schemas import ReportStatus
from ..models import SecurityIncident, User, utcnow
from .schemas import AdminIncidentItem, IncidentSource, IncidentUser

# Incydenty wskazuja osobe - nie trzymamy ich dluzej niz pol roku.
INCIDENT_RETENTION_DAYS = 180
# Pytanie i tak ma limit w ChatRequest; tu na wypadek innych wywolan.
MAX_QUESTION_LENGTH = 4000


class IncidentNotFound(LookupError):
    """Brak incydentu o tym id - API odpowiada 404."""


def incident_source(rules: Sequence[str], model_flagged: bool) -> IncidentSource | None:
    """Zrodlo incydentu; None = nie ma czego zglaszac."""
    if rules and model_flagged:
        return "both"
    if rules:
        return "heuristic"
    if model_flagged:
        return "model"
    return None


def _merge(row: SecurityIncident, rules: Sequence[str], model_flagged: bool) -> None:
    """Drugi sygnal dla tego samego pytania (np. regeneracja odpowiedzi)."""
    merged = list(dict.fromkeys([*(row.rules or []), *rules]))
    flagged = model_flagged or row.source in ("model", "both")
    row.rules = merged
    row.source = incident_source(merged, flagged) or row.source


def _record_once(
    db: Session,
    user_id: str | None,
    conversation_id: str | None,
    message_id: str | None,
    question: str,
    rules: Sequence[str],
    model_flagged: bool,
) -> SecurityIncident:
    existing = None
    if message_id is not None:
        stmt = select(SecurityIncident).where(SecurityIncident.message_id == message_id)
        existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        _merge(existing, rules, model_flagged)
        db.commit()
        return existing
    row = SecurityIncident(
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        question=question[:MAX_QUESTION_LENGTH],
        source=incident_source(rules, model_flagged),
        rules=list(dict.fromkeys(rules)),
        status="open",
    )
    db.add(row)
    db.commit()
    return row


def record_incident(
    db: Session,
    *,
    user_id: str | None,
    conversation_id: str | None,
    message_id: str | None,
    question: str,
    rules: Sequence[str],
    model_flagged: bool,
) -> SecurityIncident | None:
    """Zapisuje incydent albo dopisuje sygnal do incydentu tego samego pytania
    (message_id). Bez trafien heurystyki i bez znacznika nic nie robi (None).

    Wyscig dwoch pierwszych zapisow dla tego samego pytania konczy sie na
    unikalnym message_id - druga proba dopisuje sie do wiersza pierwszej."""
    if incident_source(rules, model_flagged) is None:
        return None
    args = (db, user_id, conversation_id, message_id, question, rules, model_flagged)
    try:
        return _record_once(*args)
    except IntegrityError:
        db.rollback()
    return _record_once(*args)


# --- zarzad ---------------------------------------------------------------------------

def list_incidents(
    db: Session, status: ReportStatus | None, limit: int, offset: int
) -> tuple[list[tuple[SecurityIncident, User | None]], int]:
    """Strona incydentow od najnowszych (z kontem zglaszanej osoby, jesli
    jeszcze istnieje) i liczba wszystkich pasujacych."""
    filtered = select(SecurityIncident)
    if status is not None:
        filtered = filtered.where(SecurityIncident.status == status)
    total = db.execute(select(func.count()).select_from(filtered.subquery())).scalar_one()

    stmt = select(SecurityIncident, User).outerjoin(User, User.id == SecurityIncident.user_id)
    if status is not None:
        stmt = stmt.where(SecurityIncident.status == status)
    page = (
        stmt.order_by(SecurityIncident.created_at.desc(), SecurityIncident.id)
        .limit(limit)
        .offset(offset)
    )
    return [(row, user) for row, user in db.execute(page).tuples()], int(total)


def review_incident(
    db: Session,
    incident_id: str,
    reviewer_id: str,
    status: ReportStatus,
    admin_note: str | None,
    sets_note: bool,
) -> tuple[SecurityIncident, User | None]:
    """Zmienia status incydentu (i ewentualnie notatke zarzadu).

    Raises:
        IncidentNotFound: brak incydentu o tym id.
    """
    row = db.get(SecurityIncident, incident_id)
    if row is None:
        raise IncidentNotFound(incident_id)
    row.status = status
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
    user = db.get(User, row.user_id) if row.user_id is not None else None
    return row, user


def to_admin_item(row: SecurityIncident, user: User | None) -> AdminIncidentItem:
    return AdminIncidentItem(
        id=row.id,
        user_id=row.user_id,
        user=None if user is None else IncidentUser(
            id=user.id, name=user.name, username=user.username, email=user.email
        ),
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        question=row.question,
        source=row.source,
        rules=list(row.rules or []),
        status=row.status,
        admin_note=row.admin_note,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --- sprzatanie -------------------------------------------------------------------------

def purge_old_incidents(db: Session, retention_days: int = INCIDENT_RETENTION_DAYS) -> int:
    """Kasuje incydenty starsze niz retention_days (niezaleznie od statusu)."""
    cutoff = utcnow() - timedelta(days=retention_days)
    result = db.execute(delete(SecurityIncident).where(SecurityIncident.created_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)
