"""Incydenty bezpieczenstwa dla zarzadu (OIDC_ADMIN_GROUP).

Za nginxem sa pod /api/* (nginx obcina /api).

    GET   /admin/incidents       -> lista od najnowszych (z danymi osoby)
    PATCH /admin/incidents/{id}  -> obsluga incydentu (status + notatka)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth.dependencies import require_admin
from ..database import get_db
from ..feedback.schemas import AdminReviewRequest, ReportStatus
from ..models import User
from .incidents import IncidentNotFound, list_incidents, review_incident, to_admin_item
from .schemas import AdminIncidentItem, AdminIncidentPage

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# Odpowiedzi zawieraja tresc pytan i dane osob - nie moga zostac w cache.
_NO_STORE = {"Cache-Control": "no-store"}

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/incidents", response_model=AdminIncidentPage)
def admin_list_incidents(
    response: Response,
    status: ReportStatus | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminIncidentPage:
    """Incydenty od najnowszych; status filtruje (open/resolved/dismissed)."""
    response.headers.update(_NO_STORE)
    rows, total = list_incidents(db, status, limit, offset)
    return AdminIncidentPage(
        items=[to_admin_item(row, user) for row, user in rows], total=total, limit=limit, offset=offset
    )


@admin_router.patch("/incidents/{incident_id}", response_model=AdminIncidentItem)
def admin_review_incident(
    incident_id: str,
    payload: AdminReviewRequest,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminIncidentItem:
    """Oznacza incydent jako resolved/dismissed (albo z powrotem open), z
    opcjonalna notatka (pominieta = bez zmian, null/pusta = skasowana)."""
    response.headers.update(_NO_STORE)
    try:
        row, user = review_incident(db, incident_id, admin.id, payload.status, payload.admin_note, payload.sets_note)
    except IncidentNotFound:
        raise HTTPException(status_code=404, detail="incident not found") from None
    return to_admin_item(row, user)
