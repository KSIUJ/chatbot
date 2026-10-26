"""Odpowiedzi endpointow /usos/* - bez tokenow i sekretow."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UsosStatusResponse(BaseModel):
    # false = funkcja wylaczona (frontend chowa pozycje w ustawieniach)
    available: bool
    # polaczenie jest i dziala
    connected: bool
    # polaczenie jest, ale USOS odrzucil token - trzeba polaczyc sie ponownie
    needs_reconnect: bool
    # imie i nazwisko z USOS
    name: str | None
    connected_at: datetime | None
    scopes: list[str]


class UsosConnectResponse(BaseModel):
    # strona zgody w USOS - frontend przechodzi na nia (window.location)
    authorize_url: str
