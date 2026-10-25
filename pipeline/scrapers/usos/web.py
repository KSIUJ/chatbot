"""
Klient stron USOSweb UJ (https://www.usosweb.uj.edu.pl) - strony informacyjne
dostepne bez logowania (Dokumenty, Kontakt).

USOSweb przy kazdym wejsciu odsyla przegladarke przez CAS w trybie "gateway"
(cas.uj.edu.pl/cas/login?...&gateway=true) i z powrotem; bez ciasteczek
(PHPSESSID) zapetla sie w przekierowaniach. Dlatego klient trzyma ciasteczka
w requests.Session i sam prowadzi przekierowania: dozwolone sa tylko skoki
w obrebie www.usosweb.uj.edu.pl i przez CAS w trybie gateway, a strona
koncowa musi byc na www.usosweb.uj.edu.pl. Adresy innych hostow sa odrzucane
(np. usosownia.uj.edu.pl - jej robots.txt nie pozwala na roboty).

Zapytania sa wysylane nie czesciej niz co `delay` sekund, a bledy chwilowe
(429, 5xx, zerwane polaczenie) ponawiane z rosnacym odstepem (common/throttle.py,
Retry-After najwyzej 300 s).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from ..common.throttle import Throttle, backoff_seconds
from .api import USER_AGENT

logger = logging.getLogger(__name__)

HOST = "www.usosweb.uj.edu.pl"
BASE_URL = f"https://{HOST}/kontroler.php"
CAS_HOST = "cas.uj.edu.pl"
TIMEOUT = 30
DEFAULT_DELAY = 1.0
RETRIES = 3
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_REDIRECTS = 6
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class UsosWebError(RuntimeError):
    """Blad pobierania strony USOSweb."""


class HostNotAllowed(UsosWebError):
    """Adres (albo przekierowanie) poza www.usosweb.uj.edu.pl."""


class LoginRequired(UsosWebError):
    """Strona wymaga zalogowania (przekierowanie do CAS bez trybu gateway)."""


def is_usosweb_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "").lower() == HOST


def _is_cas_gateway(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() != CAS_HOST:
        return False
    return parse_qs(parts.query).get("gateway") == ["true"]


def _is_cas(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower() == CAS_HOST


class UsosWeb:
    def __init__(
        self,
        *,
        delay: float = DEFAULT_DELAY,
        session: requests.Session | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._sleep = sleep
        self._throttle = Throttle(delay, sleep, clock)
        # statystyki przebiegu (raport na koncu); skoki przekierowan sie licza
        self.requests = 0
        self.errors = 0

    @property
    def delay(self) -> float:
        return self._throttle.delay

    def get(self, url: str) -> str:
        """HTML strony USOSweb (po przekierowaniach).

        Raises:
            HostNotAllowed: adres albo przekierowanie poza dozwolonymi hostami.
            LoginRequired: strona wymaga logowania.
            UsosWebError: inny blad (po wyczerpaniu ponowien dla bledow chwilowych).
        """
        if not is_usosweb_url(url):
            raise HostNotAllowed(f"{url}: dozwolone tylko https://{HOST}/")
        for attempt in range(RETRIES + 1):
            self._throttle.wait()
            try:
                response = self._follow(url)
            except requests.RequestException as error:
                if attempt == RETRIES:
                    self.errors += 1
                    raise UsosWebError(f"{url}: {error}") from error
                self._backoff(url, attempt, None, str(error))
                continue
            if response.status_code == 200:
                return _text(response)
            if response.status_code in RETRY_STATUSES and attempt < RETRIES:
                self._backoff(url, attempt, response.headers.get("Retry-After"), f"HTTP {response.status_code}")
                continue
            self.errors += 1
            raise UsosWebError(f"{url}: HTTP {response.status_code}")
        raise AssertionError("unreachable")

    def _follow(self, url: str) -> requests.Response:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            self.requests += 1
            response = self.session.get(current, allow_redirects=False, timeout=TIMEOUT)
            if response.status_code not in REDIRECT_STATUSES:
                if not is_usosweb_url(current):
                    self.errors += 1
                    raise LoginRequired(f"{url}: strona koncowa poza USOSweb ({urlsplit(current).hostname})")
                return response
            location = (response.headers.get("Location") or "").strip()
            if not location:
                self.errors += 1
                raise UsosWebError(f"{url}: przekierowanie bez adresu")
            target = urljoin(current, location)
            if not (is_usosweb_url(target) or _is_cas_gateway(target)):
                self.errors += 1
                if _is_cas(target):
                    raise LoginRequired(f"{url}: strona wymaga logowania")
                raise HostNotAllowed(f"{url}: przekierowanie poza USOSweb ({urlsplit(target).hostname})")
            current = target
        self.errors += 1
        raise UsosWebError(f"{url}: za duzo przekierowan (>{MAX_REDIRECTS})")

    def _backoff(self, url: str, attempt: int, retry_after: str | None, reason: str) -> None:
        wait = backoff_seconds(attempt, retry_after)
        logger.warning("%s: %s, ponawiam za %.0f s", url, reason, wait)
        self._sleep(wait)


def _text(response: requests.Response) -> str:
    # bez charsetu w naglowku requests zaklada ISO-8859-1; USOSweb pisze w UTF-8
    if "charset" not in (response.headers.get("Content-Type") or "").lower():
        response.encoding = "utf-8"
    return response.text


# --- czas wzgledny ("ok. 19 godzin temu") ----------------------------------------------

_UNITS: tuple[tuple[str, timedelta], ...] = (
    (r"sekund", timedelta(seconds=1)),
    (r"minut", timedelta(minutes=1)),
    (r"godzin", timedelta(hours=1)),
    (r"(?:dni|dzie[nń]|dnia)", timedelta(days=1)),
    (r"tydzie[nń]|tygodn", timedelta(weeks=1)),
    (r"miesi[aą]c|miesi[eę]c", timedelta(days=30)),
    (r"(?:rok|roku|lat)", timedelta(days=365)),
)
_RELATIVE = re.compile(
    r"(?:ok(?:\.|oło)?\s*)?(?:(\d+)\s*)?\b(" + "|".join(f"(?:{u})" for u, _ in _UNITS) + r")\w*\s+temu",
    re.IGNORECASE,
)
_JUST_NOW = re.compile(r"przed chwil[aą]|chwil[eę] temu|teraz", re.IGNORECASE)
_YESTERDAY = re.compile(r"wczoraj", re.IGNORECASE)


def parse_relative(text: str, now: datetime) -> tuple[datetime, timedelta] | None:
    """Czas z opisu wzglednego ("ok. 19 godzin temu", "2 dni temu", "godzinę
    temu", "wczoraj") i jego dokladnosc (jednostka); None, gdy nie rozpoznany."""
    text = " ".join(text.split())
    match = _RELATIVE.search(text)
    if match:
        count = int(match.group(1)) if match.group(1) else 1
        word = match.group(2)
        for pattern, unit in _UNITS:
            if re.match(pattern, word, re.IGNORECASE):
                return now - count * unit, unit
    if _YESTERDAY.search(text):
        return now - timedelta(days=1), timedelta(days=1)
    if _JUST_NOW.search(text):
        return now, timedelta(minutes=1)
    return None


def _page_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(("script", "style", "noscript", "template")):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def _note(html: str, label: str) -> str | None:
    text = _page_text(html)
    match = re.search(re.escape(label) + r"\s*:?\s*(.{0,60}?(?:temu|wczoraj|przed chwil\w+|teraz))", text, re.IGNORECASE)
    return match.group(1) if match else None


def parse_last_migration(html: str, now: datetime) -> datetime | None:
    """Przyblizony czas ostatniej migracji danych z USOS do USOSweb, z notki
    strony ("ostatnia migracja danych: ok. 19 godzin temu"); None, gdy brak."""
    note = _note(html, "ostatnia migracja danych")
    parsed = parse_relative(note, now) if note else None
    return parsed[0] if parsed else None


_MONTH = timedelta(days=28)
_YEAR = timedelta(days=365)


def parse_last_modified(html: str, now: datetime) -> datetime | None:
    """Przyblizony czas zmiany dokumentu ("ostatnia modyfikacja tego dokumentu:
    8 dni temu"), zaokraglony do dokladnosci opisu, zeby kolejne codzienne
    przebiegi dawaly ten sam wynik: lata -> 1 stycznia tego roku, miesiace ->
    1. dzien miesiaca (liczone kalendarzowo), dni i tygodnie -> polnoc,
    godziny i minuty -> pelna godzina; None, gdy brak."""
    note = _note(html, "ostatnia modyfikacja tego dokumentu")
    parsed = parse_relative(note, now) if note else None
    if not parsed:
        return None
    when, unit = parsed
    midnight = {"hour": 0, "minute": 0, "second": 0, "microsecond": 0}
    if unit >= _YEAR:
        years = round((now - when) / _YEAR)
        return now.replace(year=now.year - years, month=1, day=1, **midnight)
    if unit >= _MONTH:
        months = now.year * 12 + now.month - 1 - round((now - when) / unit)
        return now.replace(year=months // 12, month=months % 12 + 1, day=1, **midnight)
    if unit >= timedelta(days=1):
        return when.replace(**midnight)
    return when.replace(minute=0, second=0, microsecond=0)


# --- tresc glowna strony -------------------------------------------------------------

# obszar tresci w ukladzie USOSweb: <main id="layout-main-content" slot="page-body">
_MAIN_START = re.compile(r"<main\b[^>]*\bid\s*=\s*[\"']?layout-main-content\b[^>]*>", re.IGNORECASE)
_MAIN_END = re.compile(r"</main\s*>", re.IGNORECASE)
# elementy ukladu strony - na wypadek, gdyby trafily do wycinka
_CHROME = (
    "usos-footer", "usos-copyright", "menu-left", "menu-top", "app-header", "cas-bar",
    "skip-links", "top-scroller", "nav", "footer", "header",
)
# elementy, ktore nie sa trescia (osadzone w tresci dokumenty maja wlasne <html><head>)
_DROP = ("script", "style", "noscript", "template", "link", "meta", "title", "head", "iframe", "form")
_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_PSEUDO_HEADING_MAX = 120
_NEWLINES = re.compile(r"\s*\n\s*")


def _main_fragment(html: str) -> str | None:
    """Surowy HTML miedzy <main id="layout-main-content"> a ostatnim </main>.

    Wycinek z tekstu, nie z drzewa: parser lxml nie zna <main> i przy
    niedomknietych znacznikach w tresci (np. <p> z listami na stronie
    Kontakt) wciaga do niego stopke strony."""
    start = _MAIN_START.search(html)
    if not start:
        return None
    ends = list(_MAIN_END.finditer(html, start.end()))
    if not ends:
        return None
    return html[start.end():ends[-1].start()]


def main_content(html: str) -> str | None:
    """HTML samej tresci strony (bez naglowka, menu, stopki, paska CAS i notek
    "ostatnia migracja danych" / "ostatnia modyfikacja"); None, gdy strona nie
    ma obszaru tresci (inny uklad - lepiej pominac niz zapisac menu).

    Porzadkuje tez tresc pod html_to_markdown: elementy niestandardowe
    (<usos-frame> itp.) zamienia na <div>, laczy linie zlamane w zrodle,
    linki i pogrubienia lezace wprost w akapicie owija w <span> (inaczej
    konwerter gubi adres linku), a gdy strona nie ma zadnych naglowkow,
    akapity z samym pogrubieniem (<p><strong>Termin ważności</strong></p>)
    zamienia na <h2>.
    """
    fragment = _main_fragment(html)
    if fragment is None:
        return None
    soup = BeautifulSoup(f"<div>{fragment}</div>", "lxml")
    root = soup.body.find("div") if soup.body else None
    if root is None:
        return None
    for comment in root.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for tag in root.find_all(_DROP + _CHROME):
        tag.decompose()
    # notki USOSweb (migracja danych, modyfikacja dokumentu) w tabelkach .grey
    for note in root.select("span.note"):
        holder = note.find_parent("table") or note
        holder.decompose()
    for tag in root.find_all(True):
        if "-" in tag.name or tag.name in ("html", "body", "main"):
            tag.name = "div"
    for link in root.find_all("a"):
        if not link.get_text(strip=True):
            alt = next((img["alt"].strip() for img in link.find_all("img") if img.get("alt", "").strip()), "")
            if alt:
                link.append(alt)
    for text in root.find_all(string=True):
        if "\n" in text and not text.find_parent("pre"):
            text.replace_with(_NEWLINES.sub(" ", str(text)))
    for br in root.find_all("br"):
        after = br.next_sibling
        if isinstance(after, NavigableString) and after != after.lstrip():
            after.replace_with(after.lstrip())
    if not root.find(_HEADINGS):
        for paragraph in root.find_all("p"):
            text = _pseudo_heading(paragraph)
            if text:
                paragraph.clear()
                paragraph.append(text)
                paragraph.name = "h2"
    for tag in root.find_all(("a", "strong", "b")):
        parent = tag.parent
        if parent is not None and parent.name not in ("a", "strong", "b", "span", "em", "i", "u") and parent.name not in _HEADINGS:
            tag.wrap(soup.new_tag("span"))
    return str(root)


def _pseudo_heading(paragraph: Tag) -> str:
    children = [c for c in paragraph.children if not (isinstance(c, NavigableString) and not c.strip())]
    if len(children) != 1 or not isinstance(children[0], Tag) or children[0].name not in ("strong", "b"):
        return ""
    text = " ".join(children[0].get_text(" ").split())
    return text if len(text) <= _PSEUDO_HEADING_MAX else ""
