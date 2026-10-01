"""Endpointy ocen i zgloszen odpowiedzi.

Za nginxem sa pod /api/* (nginx obcina /api).

    PUT   /messages/{id}/feedback    -> ocena/zgloszenie wlasnej odpowiedzi
    GET   /admin/feedback            -> lista dla zarzadu (OIDC_ADMIN_GROUP)
    GET   /admin/feedback/export.csv -> kopie pytan i odpowiedzi do ewaluacji
    PATCH /admin/feedback/{id}       -> obsluga zgloszenia
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth.dependencies import require_admin, require_member
from ..database import get_db
from ..models import User
from ..response import FeedbackState
from .schemas import (
    AdminFeedbackItem,
    AdminFeedbackPage,
    AdminReviewRequest,
    FeedbackKind,
    FeedbackRequest,
    ReportStatus,
)
from .service import (
    FeedbackNotFound,
    export_rows,
    list_feedback,
    review_report,
    submit_feedback,
    to_admin_item,
    to_csv,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# Odpowiedzi adminow zawieraja tresc rozmow - nie moga zostac w cache.
_NO_STORE = {"Cache-Control": "no-store"}

router = APIRouter(tags=["feedback"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


@router.put("/messages/{message_id}/feedback", response_model=FeedbackState)
def put_feedback(
    message_id: str,
    payload: FeedbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
) -> FeedbackState:
    """Lapka w gore/w dol i/lub zgloszenie odpowiedzi asystenta z wlasnej
    rozmowy. Cudza wiadomosc albo pytanie (nie odpowiedz) -> 404."""
    try:
        return submit_feedback(db, user.id, message_id, payload)
    except FeedbackNotFound:
        raise HTTPException(status_code=404, detail="message not found") from None


@admin_router.get("/feedback", response_model=AdminFeedbackPage)
def admin_list_feedback(
    response: Response,
    kind: FeedbackKind = "reports",
    status: ReportStatus | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminFeedbackPage:
    """Zgloszenia (kind=reports) albo oceny (kind=ratings) od najnowszych.
    status filtruje po statusie zgloszenia."""
    response.headers.update(_NO_STORE)
    rows, total = list_feedback(db, kind, status, limit, offset)
    return AdminFeedbackPage(items=[to_admin_item(r) for r in rows], total=total, limit=limit, offset=offset)


@admin_router.get(
    "/feedback/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV z kopiami pytan i odpowiedzi"}},
)
def admin_export_feedback(
    kind: FeedbackKind | None = None,
    status: ReportStatus | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    """Wszystkie wpisy (albo tylko kind/status) jako CSV - material do zbioru
    ewaluacyjnego. UTF-8 z BOM, zeby Excel poprawnie pokazal polskie znaki."""
    body = to_csv(export_rows(db, kind, status))
    filename = f"feedback-{datetime.now(timezone.utc):%Y%m%d}.csv"
    return Response(
        content="﻿" + body,
        media_type="text/csv; charset=utf-8",
        headers={**_NO_STORE, "Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_router.patch("/feedback/{feedback_id}", response_model=AdminFeedbackItem)
def admin_review_feedback(
    feedback_id: str,
    payload: AdminReviewRequest,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminFeedbackItem:
    """Oznacza zgloszenie jako resolved/dismissed (albo z powrotem open),
    z opcjonalna notatka. Wpis bez zgloszenia (sama ocena) -> 404."""
    response.headers.update(_NO_STORE)
    try:
        row = review_report(db, feedback_id, admin.id, payload.status, payload.admin_note, payload.sets_note)
    except FeedbackNotFound:
        raise HTTPException(status_code=404, detail="report not found") from None
    return to_admin_item(row)
