"""Endpointy motywu okazjonalnego. Za nginxem sa pod /api/* (nginx obcina /api).

    GET /occasion -> {active, dark, theme_color, palette, facade: {pl, en} | null}
        Publiczny (ekran logowania tez zmienia wyglad), bez nazwy i terminow
        okazji - tylko to, co ksi.sh i tak teraz pokazuje. 503
        occasion_unknown do pierwszego udanego odswiezenia po starcie
        (najwyzej STALE_AFTER_SECONDS): przegladarka zostaje wtedy przy swoim
        ostatnim stanie.
    GET /occasion/facade/{wersja}?scheme=light|dark -> fasada SVG biezacej
        okazji (zweryfikowana w svg.py), z CSP bez skryptow.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel

from .state import VERSION_LENGTH, OccasionStore, get_occasion_store

OCCASION_UNKNOWN = "occasion_unknown"
UNKNOWN_RETRY_SECONDS = 5
# SVG otwarty bezposrednio (nie jako <img>) nie moze wykonac niczego w naszym originie.
FACADE_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'"
# private: wspoldzielone cache (Cloudflare, proxy VM) nie trzymaja grafiki po
# koncu okazji; krotko, bo po koncu backend i tak juz jej nie podaje (404)
FACADE_CACHE = "private, max-age=600"

router = APIRouter(prefix="/occasion", tags=["occasion"])


class FacadeVersions(BaseModel):
    pl: str
    en: str


class OccasionResponse(BaseModel):
    active: bool
    # czat ma byc ciemny niezaleznie od ustawienia uzytkownika
    dark: bool
    theme_color: str | None
    # zmienne palety ksi.sh (night-950 ... night-100, accent, accent-hover, accent-light)
    palette: dict[str, str]
    facade: FacadeVersions | None


INACTIVE = OccasionResponse(active=False, dark=False, theme_color=None, palette={}, facade=None)


@router.get("", response_model=OccasionResponse)
def get_occasion(response: Response, store: OccasionStore = Depends(get_occasion_store)) -> OccasionResponse:
    """Biezacy motyw okazjonalny ksi.sh."""
    if not store.known:
        raise HTTPException(
            status_code=503,
            detail={"code": OCCASION_UNKNOWN, "message": "Stan motywu jeszcze nieznany."},
            headers={"Retry-After": str(UNKNOWN_RETRY_SECONDS)},
        )
    response.headers["Cache-Control"] = "no-cache"
    snapshot = store.current()
    if snapshot is None:
        return INACTIVE
    pl, en = snapshot.facades.get("pl"), snapshot.facades.get("en")
    return OccasionResponse(
        active=True,
        dark=snapshot.dark,
        theme_color=snapshot.theme_color,
        palette=dict(snapshot.palette),
        facade=FacadeVersions(pl=pl.version, en=en.version) if pl and en else None,
    )


@router.get("/facade/{version}")
def get_facade(
    version: str = Path(pattern=rf"^[0-9a-f]{{{VERSION_LENGTH}}}$"),
    scheme: Literal["light", "dark"] = Query("light"),
    store: OccasionStore = Depends(get_occasion_store),
) -> Response:
    """Fasada biezacej okazji w wersji dla motywu czatu."""
    facade = store.facade(version)
    if facade is None:
        raise HTTPException(status_code=404, detail="facade not found")
    return Response(
        content=facade.dark if scheme == "dark" else facade.light,
        # jawne kodowanie: przegladarka nie zgaduje go z tresci pliku
        media_type="image/svg+xml; charset=utf-8",
        headers={
            "Content-Security-Policy": FACADE_CSP,
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Cache-Control": FACADE_CACHE,
        },
    )
