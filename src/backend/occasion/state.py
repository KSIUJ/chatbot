"""Aktualny motyw okazjonalny: odswiezanie z ksi.sh w tle i stan w pamieci.

Petla w tle (start w lifespan aplikacji, jeden worker) co
OCCASION_REFRESH_SECONDS pyta API ksi.sh, ktora okazja trwa (z tokenem
OCCASION_API_TOKEN), a przy aktywnej okazji pobiera strone glowna (kolory),
modul wejsciowy i fasade. Bez tokenu albo gdy API nie odpowiada o tym, czy
okazja trwa, decyduje sama strona glowna. Okazja z API znika w chwili jej
konca, nawet miedzy odswiezeniami. Pliki z /assets/ maja hash w nazwie, wiec raz pobrane
(albo raz odrzucone) nie sa pobierane ponownie. Gdy strona nie odpowiada,
zostaje ostatni znany stan, ale najwyzej STALE_AFTER_SECONDS - potem czat
wraca do zwyklego wygladu.

W repozytorium (publicznym) nie ma zadnych motywow ani terminow: wszystko
przychodzi z ksi.sh w chwili, gdy motyw jest juz widoczny na stronie.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urljoin

import httpx

from .landing import (
    ApiOccasion,
    ApiResponseError,
    FacadePaths,
    LandingPage,
    parse_api_occasion,
    parse_facade_paths,
    parse_landing_page,
)
from .svg import MAX_SVG_BYTES, UnsafeSvg, for_scheme, validate_svg

logger = logging.getLogger(__name__)

USER_AGENT = "KSI-Chatbot/1.0 (+https://chat.ksi.sh)"
REQUEST_TIMEOUT_SECONDS = 5.0
# cale odswiezenie (strona + modul + 2 fasady), takze przy powolnym przesylaniu
REFRESH_DEADLINE_SECONDS = 30.0
MAX_PAGE_BYTES = 2_000_000
MAX_MODULE_BYTES = 512_000
MAX_API_BYTES = 16_000
API_PATH = "/api/occasion"
STALE_AFTER_SECONDS = 30 * 60
VERSION_LENGTH = 16


class LandingError(Exception):
    """Strona glowna odpowiedziala inaczej niz 200 albo za duzo."""


@dataclass(frozen=True)
class Facade:
    # skrot tresci: adres grafiki zmienia sie razem z nia (dluga pamiec przegladarki)
    version: str
    svg: str
    # wersje dla motywu czatu, liczone raz (endpoint tylko je podaje)
    light: str = field(init=False, repr=False, compare=False)
    dark: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "light", for_scheme(self.svg, "light"))
        object.__setattr__(self, "dark", for_scheme(self.svg, "dark"))


@dataclass(frozen=True)
class OccasionSnapshot:
    """Aktywna okazja. Brak okazji to None, nie pusty obiekt."""

    # strona wymusza ciemny motyw (ma data-color)
    dark: bool
    theme_color: str | None
    palette: Mapping[str, str] = field(default_factory=dict)
    # "pl"/"en" -> fasada (obie moga byc ta sama); pusto = bez fasady
    facades: Mapping[str, Facade] = field(default_factory=dict)
    # sekundy od pobrania do konca okazji wg API (None = nieznany koniec);
    # tylko w backendzie - repr=False, zeby nie trafil do logu
    ends_in: float | None = field(default=None, repr=False)


class _ApiUnavailable:
    """API ksi.sh nie powiedzialo nic pewnego - decyduje strona glowna."""


API_UNAVAILABLE = _ApiUnavailable()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def facade_version(svg: str) -> str:
    return hashlib.sha256(svg.encode("utf-8")).hexdigest()[:VERSION_LENGTH]


class LandingClient:
    """Pobiera stan okazji ze strony glownej; pamieta zasoby z /assets/."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        source_url: str,
        api_token: str | None = None,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.http = http
        self.source_url = source_url
        self.api_token = api_token
        self._now = now
        # niedzialajace API logujemy raz na proces: wpis przy kazdej zmianie
        # zdradzalby w logach, kiedy okazje sie zaczynaja i koncza
        self._api_failure_logged = False
        # (modul, okazja) -> sciezki fasady; None = modul bez rozpoznawalnej fasady
        self._modules: dict[tuple[str, str], FacadePaths | None] = {}
        # sciezka -> fasada; None = plik odrzucony przez validate_svg
        self._facades: dict[str, Facade | None] = {}

    async def _get(self, url: str, limit: int, token: str | None = None) -> str:
        """Tresc odpowiedzi 200 najwyzej `limit` bajtow; bez przekierowan (token
        nie poleci pod inny adres)."""
        # identity: limit liczy bajty odpowiedzi, a skompresowana bomba
        # rozpakowalaby sie przed sprawdzeniem
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        async with self.http.stream(
            "GET", url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False
        ) as response:
            if response.status_code != 200:
                raise LandingError(f"HTTP {response.status_code}")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise LandingError("odpowiedz za duza")
                chunks.append(chunk)
        # zawsze UTF-8 (strona jest w UTF-8): kodowanie z naglowka nie decyduje
        return b"".join(chunks).decode("utf-8", errors="replace")

    async def _api_occasion(self) -> ApiOccasion | None | _ApiUnavailable:
        """Okazja wg API ksi.sh: trwajaca, None (zadna) albo API_UNAVAILABLE
        (brak tokenu, blad, 404 przy zlym tokenie, nieznany ksztalt)."""
        if self.api_token is None:
            return API_UNAVAILABLE
        try:
            body = await self._get(urljoin(self.source_url, API_PATH), MAX_API_BYTES, token=self.api_token)
            return await asyncio.to_thread(parse_api_occasion, body, self._now())
        except (httpx.HTTPError, LandingError, ApiResponseError) as error:
            if not self._api_failure_logged:
                self._api_failure_logged = True
                logger.warning("occasion: ksi.sh API not used (%s), reading the landing page instead", error)
            return API_UNAVAILABLE

    def _asset_url(self, path: str) -> str:
        # sciezki sa sprawdzone wzorcem /assets/..., wiec zostaja na hoscie strony
        return urljoin(self.source_url, path)

    async def _facade_paths(self, page: LandingPage) -> FacadePaths | None:
        if page.entry_module is None or page.occasion is None:
            logger.warning("occasion: no entry module on the landing page, showing colours only")
            return None
        key = (page.entry_module, page.occasion)
        if key in self._modules:
            return self._modules[key]
        try:
            module = await self._get(self._asset_url(page.entry_module), MAX_MODULE_BYTES)
        except (httpx.HTTPError, LandingError) as error:
            logger.warning("occasion: entry module not fetched (%s), retrying next time", error)
            return None
        paths = await asyncio.to_thread(parse_facade_paths, module, page.occasion)
        if paths is None:
            logger.warning("occasion: no facade found in the entry module, showing colours only")
        self._modules[key] = paths
        return paths

    async def _facade(self, path: str) -> Facade | None:
        if path in self._facades:
            return self._facades[path]
        try:
            svg = await self._get(self._asset_url(path), MAX_SVG_BYTES)
        except (httpx.HTTPError, LandingError) as error:
            logger.warning("occasion: facade not fetched (%s), retrying next time", error)
            return None
        try:
            clean = await asyncio.to_thread(validate_svg, svg)
            facade: Facade | None = Facade(version=facade_version(clean), svg=clean)
        except UnsafeSvg as error:
            logger.warning("occasion: facade rejected: %s", error)
            facade = None
        self._facades[path] = facade
        return facade

    async def _facades_for(self, paths: FacadePaths | None) -> dict[str, Facade]:
        if paths is None:
            return {}
        pl = await self._facade(paths.pl)
        en = pl if paths.en == paths.pl else await self._facade(paths.en)
        # brakujaca wersja jezykowa zastepuje druga
        pl, en = pl or en, en or pl
        return {"pl": pl, "en": en} if pl is not None and en is not None else {}

    def _forget_except(self, paths: FacadePaths | None) -> None:
        """Pamiec tylko zasobow biezacej okazji (nie rosnie przez caly rok)."""
        used = {paths.pl, paths.en} if paths else set()
        self._facades = {path: facade for path, facade in self._facades.items() if path in used}

    async def fetch(self) -> OccasionSnapshot | None:
        """Biezaca okazja albo None.

        Raises:
            LandingError, httpx.HTTPError: strona glowna niedostepna.
        """
        api = await self._api_occasion()
        if api is None:
            # API: zadna okazja nie trwa - strony nie trzeba pobierac
            page = LandingPage(occasion=None)
        else:
            # parsowanie cudzej tresci poza petla zdarzen: nawet przypadek
            # patologiczny nie zatrzyma czatu (backend ma jednego workera)
            html = await self._get(self.source_url, MAX_PAGE_BYTES)
            page = await asyncio.to_thread(parse_landing_page, html)
            if isinstance(api, ApiOccasion) and page.occasion != api.occasion:
                # strona jeszcze (albo juz) pokazuje co innego niz API, np. z
                # pamieci CDN - bez motywu, az obie sie zgodza
                page = LandingPage(occasion=None)
        if page.occasion is None:
            self._modules.clear()
            self._forget_except(None)
            return None
        paths = await self._facade_paths(page)
        facades = await self._facades_for(paths)
        self._modules = {key: value for key, value in self._modules.items() if key[1] == page.occasion}
        self._forget_except(paths)
        return OccasionSnapshot(
            dark=page.color is not None,
            theme_color=page.color,
            palette=dict(page.palette),
            facades=facades,
            ends_in=api.ends_in if isinstance(api, ApiOccasion) else None,
        )


class OccasionStore:
    """Ostatni znany stan okazji, czytany przez endpointy (watki puli)."""

    def __init__(
        self, clock: Callable[[], float] = time.monotonic, stale_after: float = STALE_AFTER_SECONDS
    ) -> None:
        self._clock = clock
        self._stale_after = stale_after
        self._lock = threading.Lock()
        self._succeeded = False
        self._first_failure_at: float | None = None
        self._snapshot: OccasionSnapshot | None = None
        self._updated_at = 0.0

    @property
    def known(self) -> bool:
        """False do pierwszego udanego odswiezenia - przegladarki zostaja wtedy
        przy swoim ostatnim stanie (restart backendu w chwili, gdy ksi.sh nie
        odpowiada, nie gasi trwajacego motywu). Gdy strona nie odpowiada
        dluzej niz stale_after od startu, stan jest znany: brak okazji."""
        with self._lock:
            if self._succeeded:
                return True
            return self._first_failure_at is not None and self._clock() - self._first_failure_at > self._stale_after

    def set(self, snapshot: OccasionSnapshot | None) -> None:
        with self._lock:
            self._succeeded = True
            self._snapshot = snapshot
            self._updated_at = self._clock()

    def failed(self) -> None:
        """Nieudane odswiezenie: stan zostaje, ale z czasem sie przeterminuje."""
        with self._lock:
            if not self._succeeded and self._first_failure_at is None:
                self._first_failure_at = self._clock()

    def current(self) -> OccasionSnapshot | None:
        with self._lock:
            snapshot = self._snapshot
            if snapshot is None:
                return None
            age = self._clock() - self._updated_at
            if age > self._stale_after or (snapshot.ends_in is not None and age >= snapshot.ends_in):
                return None
            return snapshot

    def facade(self, version: str) -> Facade | None:
        """Fasada biezacej okazji o tej wersji (stare wersje juz nie sa podawane)."""
        snapshot = self.current()
        if snapshot is None:
            return None
        return next((f for f in snapshot.facades.values() if f.version == version), None)


@lru_cache(maxsize=1)
def get_occasion_store() -> OccasionStore:
    """Wspolny stan procesu. Dependency FastAPI - testy podmieniaja ja
    przez app.dependency_overrides."""
    return OccasionStore()


async def refresh_once(store: OccasionStore, client: LandingClient) -> None:
    """Jedno odswiezenie; niedostepna strona to wpis w logu, nie wyjatek."""
    try:
        async with asyncio.timeout(REFRESH_DEADLINE_SECONDS):
            snapshot = await client.fetch()
    except (httpx.HTTPError, LandingError, TimeoutError) as error:
        logger.warning("occasion: landing page not read: %s", error or type(error).__name__)
        store.failed()
        return
    was_active = store.current() is not None
    if was_active != (snapshot is not None):
        # DEBUG: logi z calego roku odtworzylyby terminy motywow (konkurs)
        logger.debug("occasion theme %s", "on" if snapshot is not None else "off")
    store.set(snapshot)


async def refresh_loop(
    store: OccasionStore, source_url: str, interval_seconds: int, api_token: str | None = None
) -> None:
    """Odswieza stan przy starcie i potem co interval_seconds (do anulowania)."""
    async with httpx.AsyncClient(follow_redirects=False) as http:
        client = LandingClient(http, source_url, api_token)
        while True:
            try:
                await refresh_once(store, client)
            except Exception:
                # petla w tle ma przetrwac nieprzewidziany blad parsera
                logger.exception("occasion: refresh failed")
                store.failed()
            await asyncio.sleep(interval_seconds)
