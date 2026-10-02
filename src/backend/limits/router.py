"""Endpoint stanu dziennego limitu i odpowiedz 429 po jego wyczerpaniu.

Za nginxem jest pod /api/* (nginx obcina /api).

    GET /usage -> {used, limit (null = bez limitu), reset_at}
"""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..auth.dependencies import require_member
from ..database import get_db
from ..models import User
from .schemas import UsageResponse
from .usage import Clock, LimitExceeded, get_clock, usage_status

RATE_LIMITED = "rate_limited"

router = APIRouter(tags=["limits"])


@router.get("/usage", response_model=UsageResponse)
def get_usage(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
    clock: Clock = Depends(get_clock),
) -> UsageResponse:
    """Dzienny limit pytan biezacego uzytkownika (podpowiedz w sidebarze)."""
    response.headers["Cache-Control"] = "no-store"
    status = usage_status(db, user.id, clock())
    return UsageResponse(used=status.used, limit=status.limit, reset_at=status.reset_at)


def rate_limited_response(exc: LimitExceeded) -> JSONResponse:
    """429 z kodem rate_limited, limitem i chwila odnowienia; Retry-After w
    sekundach do polnocy czasu polskiego (co najmniej 1)."""
    seconds = (exc.reset_at - exc.checked_at).total_seconds()
    retry_after = max(1, math.ceil(seconds))
    return JSONResponse(
        status_code=429,
        content={
            "detail": {
                "code": RATE_LIMITED,
                "message": f"Wykorzystano dzienny limit pytań ({exc.limit}). Limit odnowi się o północy.",
                "limit": exc.limit,
                "reset_at": exc.reset_at.isoformat(),
            }
        },
        headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
    )


async def limit_exceeded_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handler wyjatku LimitExceeded dla calej aplikacji (/chat i /chat/stream)."""
    if not isinstance(exc, LimitExceeded):
        raise exc
    return rate_limited_response(exc)
