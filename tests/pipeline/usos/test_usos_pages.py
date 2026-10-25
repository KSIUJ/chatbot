"""
pipeline/scrapers/usos/web.py i collectors/pages.py: strony informacyjne
USOSweb (Dokumenty, Kontakt) jako rekordy `page` - bez sieci (falszywa sesja
HTTP i strony przyciete z prawdziwego USOSweb w fixtures/).
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from pipeline.scrapers.usos.collectors import pages
from pipeline.scrapers.usos.context import Context
from pipeline.scrapers.usos.web import (
    HostNotAllowed,
    LoginRequired,
    UsosWeb,
    UsosWebError,
    main_content,
    parse_last_migration,
    parse_last_modified,
)
from src.backend.rag.sources.usos.dataset import USOS_RECORD, PageRecord

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 25, 12, 30, tzinfo=timezone.utc)
BASE = "https://www.usosweb.uj.edu.pl/kontroler.php"
HOME = f"{BASE}?_action=news/default"
KONTAKT = f"{BASE}?_action=news/kontakt"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def doc_url(name: str) -> str:
    return f"{BASE}?_action=news/default&panel=DOMYSLNY&file={name}"


class FakeResponse:
    def __init__(self, status: int = 200, text: str = "", headers: dict | None = None):
        self.status_code = status
        self.text = text
        self.headers = {"Content-Type": "text/html; charset=utf-8", **(headers or {})}
        self.encoding = None


class FakeSession:
    """Odpowiedzi wg adresu: FakeResponse, lista (kolejne proby) albo wyjatek."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []

    def get(self, url, allow_redirects=True, timeout=None):
        assert allow_redirects is False
        assert timeout
        self.calls.append(url)
        if url not in self.routes:
            return FakeResponse(404, "nie ma")
        got = self.routes[url]
        if isinstance(got, list):
            got = got.pop(0) if len(got) > 1 else got[0]
        if isinstance(got, Exception):
            raise got
        return got


def make_web(routes: dict) -> tuple[UsosWeb, FakeSession, list[float]]:
    session = FakeSession(routes)
    sleeps: list[float] = []
    web = UsosWeb(session=session, sleep=sleeps.append, clock=lambda: 0.0)
    return web, session, sleeps


def site_routes() -> dict:
    return {
        HOME: FakeResponse(text=fixture("usosweb_home.html")),
        doc_url("index.html"): FakeResponse(text=fixture("usosweb_home.html")),
        doc_url("newsy.html"): FakeResponse(text=fixture("usosweb_spa.html")),
        doc_url("legitymacje_dr.html"): FakeResponse(text=fixture("usosweb_legitymacje_dr.html")),
        doc_url("mlegitymacja.html"): FakeResponse(text=fixture("usosweb_mlegitymacja.html")),
        doc_url("pierwsze-kroki.html"): FakeResponse(text=fixture("usosweb_legitymacje_dr.html")),
        KONTAKT: FakeResponse(text=fixture("usosweb_kontakt.html")),
    }


def ctx() -> Context:
    return Context(api=None)


# --- tresc glowna ----------------------------------------------------------------------

CHROME = (
    "Centralny System Uwierzytelniania", "DOKUMENTY", "DEKLARACJA", "Unia Europejska", "POMOC",
    "Gołębia 24", "USOSweb 7.3.1.0", "mapa serwisu", "ostatnia migracja", "ostatnia modyfikacja",
    "usosweb_status_ok", "Panel boczny",
)


@pytest.mark.parametrize(
    "name", ["usosweb_home.html", "usosweb_kontakt.html", "usosweb_legitymacje_dr.html", "usosweb_mlegitymacja.html"]
)
def test_main_content_drops_layout_chrome(name):
    from pipeline.scrapers.common.markdown import html_to_markdown

    markdown = html_to_markdown(main_content(fixture(name)), base_url=HOME)

    assert markdown
    for text in CHROME:
        assert text not in markdown, text


def test_main_content_keeps_frames_links_and_bold():
    from pipeline.scrapers.common.markdown import html_to_markdown

    markdown = html_to_markdown(main_content(fixture("usosweb_home.html")), base_url=HOME)

    # <usos-frame> to blok, a jego <h2 slot="title"> - naglowek
    assert "## Obowiązek podpięć przedmiotów realizowanych w roku akademickim 2026/2027" in markdown
    assert "## Pierwsze kroki w USOSweb" in markdown
    # ukryta ramka i zakomentowane ogloszenie pominiete
    assert "Ogłoszenia jednostek" not in markdown
    assert "Zakomentowane" not in markdown
    # link wprost w akapicie zachowuje adres, a linia zlamana w zrodle jest sklejona
    assert (
        "[obowiązkiem informacyjnym wynikającym z art. 13 RODO]"
        f"({BASE}?_action=news/default&panel=DOMYSLNY&file=newsy.html#rodo)"
    ) in markdown
    assert f"['Domyślny program']({BASE}?_action=dla_stud/studia/podpiecia/domyslnyProgram)" in markdown
    assert "**wszystkie przedmioty muszą zostać podpięte" in markdown


def test_main_content_kontakt_without_footer_leak():
    # niedomkniete <p>/<li> - lxml wciagalby stopke do <main>
    from pipeline.scrapers.common.markdown import html_to_markdown

    markdown = html_to_markdown(main_content(fixture("usosweb_kontakt.html")), base_url=KONTAKT)

    assert "usosweb@uj.edu.pl" in markdown
    assert "#### Odzyskiwanie hasła SMS" in markdown
    assert "https://passwordreset.uj.edu.pl" in markdown
    assert "[INSTRUKCJA LOGOWANIA](https://usosownia.uj.edu.pl/usosweb/ogolne/dostep-do-systemu)" in markdown
    assert "stary@example.com" not in markdown
    assert "Gołębia" not in markdown


def test_main_content_pseudo_headings_only_without_real_headings():
    from pipeline.scrapers.common.markdown import html_to_markdown

    plain = html_to_markdown(main_content(fixture("usosweb_legitymacje_dr.html")))
    assert "## Legitymacja doktoranta" in plain
    assert "## Termin ważności" in plain
    assert "twój status doktoranta" in plain

    with_headings = html_to_markdown(main_content(fixture("usosweb_kontakt.html")))
    assert "## W przypadku potrzeby" not in with_headings
    assert "**W przypadku potrzeby kontaktu" in with_headings


def test_main_content_none_without_content_area():
    assert main_content("<html><body><menu-left><a href='x'>menu</a></menu-left></body></html>") is None


# --- odkrywanie stron ------------------------------------------------------------------

def test_discover_documents_from_menu_and_content_links():
    links = pages.discover_documents(fixture("usosweb_home.html"))

    # newsy.html (archiwum aktualnosci) pominiete mimo linku w menu
    assert [link.url for link in links] == [
        doc_url("index.html"),
        doc_url("legitymacje_dr.html"),
        doc_url("mlegitymacja.html"),
        doc_url("pierwsze-kroki.html"),
    ]
    by_url = {link.url: link for link in links}
    # nazwa z menu bocznego, nie z linku w tresci ("aktualności" w obu)
    assert by_url[doc_url("legitymacje_dr.html")].breadcrumbs == ("Dokumenty", "Legitymacje doktoranckie")
    assert by_url[doc_url("mlegitymacja.html")].breadcrumbs == ("Dokumenty", "mLegitymacja")
    assert by_url[doc_url("pierwsze-kroki.html")].label == "Pierwsze kroki"


def test_discover_ignores_other_actions_and_hosts():
    html = """
    <a href="https://usosownia.uj.edu.pl/kontroler.php?_action=news/default&file=a.html">obcy host</a>
    <a href="kontroler.php?_action=dla_stud/studia/oceny/index&file=b.html">logowanie</a>
    <a href="kontroler.php?_action=news/default&panel=INNY&file=c.html">inny panel</a>
    <a href="kontroler.php?_action=news/default&file=../d.html">zla nazwa</a>
    <a href="kontroler.php?_action=news/default&panel=DOMYSLNY&file=ok.html&PHPSESSID=abc#x">ok</a>
    """
    links = pages.discover_documents(html)

    assert [link.url for link in links] == [doc_url("ok.html")]


# --- rekordy ---------------------------------------------------------------------------

def test_collect_records_validate_against_model():
    web, session, _ = make_web(site_routes())
    context = ctx()

    records = list(pages.collect(context, web=web, now=NOW))

    by_url = {r.url: r for r in records}
    # newsy.html (SKIPPED_FILES) w ogole nie pobierane
    assert doc_url("newsy.html") not in session.calls
    assert set(by_url) == {
        doc_url("index.html"), doc_url("legitymacje_dr.html"), doc_url("mlegitymacja.html"),
        doc_url("pierwsze-kroki.html"), KONTAKT,
    }
    assert context.warnings == []
    for record in records:
        assert isinstance(record, PageRecord)
        again = USOS_RECORD.validate_json(record.model_dump_json())
        assert again == record
        assert record.id == record.url
        assert record.kind == "page"
        assert record.lang == "pl"
        assert record.attributes.site == "www.usosweb.uj.edu.pl"
        assert record.attributes.section == "usosweb"
        assert record.content.startswith(f"# {record.title}\n\n")
        assert "ostatnia migracja" not in record.content

    home = by_url[doc_url("index.html")]
    # tytul zapasowy to sama nazwa z menu (linia kontekstu zaczyna sie od "USOSweb")
    assert home.title == "Strona główna"
    assert home.attributes.breadcrumbs == ["Dokumenty", "Strona główna"]
    # "8 dni temu" -> data obcieta do polnocy
    assert home.updated_at == datetime(2026, 10, 17, tzinfo=timezone.utc)

    dr = by_url[doc_url("legitymacje_dr.html")]
    assert dr.title == "Legitymacje doktoranckie"
    assert "\n## Legitymacja doktoranta\n" in dr.content

    mleg = by_url[doc_url("mlegitymacja.html")]
    # tytul z h1; drugi h1 i h2 przesuniete pod tytul
    assert mleg.title == "mLegitymacja"
    assert mleg.content.count("\n# ") == 0
    assert "\n## Pytania\n" in mleg.content
    assert "\n### Instrukcja Aktywacji:\n" in mleg.content
    assert "mLegitymacja UJ" not in mleg.content

    kontakt = by_url[KONTAKT]
    assert kontakt.title == "Kontakt z administratorem USOSweb"
    assert kontakt.attributes.breadcrumbs == ["Kontakt"]
    assert kontakt.updated_at is None


def test_failing_page_warns_and_continues():
    routes = site_routes()
    routes[doc_url("mlegitymacja.html")] = FakeResponse(500, "blad")
    routes[doc_url("legitymacje_dr.html")] = requests.ConnectionError("zerwane")
    web, session, sleeps = make_web(routes)
    context = ctx()

    records = list(pages.collect(context, web=web, now=NOW))

    urls = {r.url for r in records}
    assert doc_url("mlegitymacja.html") not in urls
    assert doc_url("legitymacje_dr.html") not in urls
    assert KONTAKT in urls
    assert len(context.warnings) == 2
    assert any("mlegitymacja.html" in w and "HTTP 500" in w for w in context.warnings)
    # bledy chwilowe ponawiane (1 + RETRIES prob) z rosnacym odstepem
    assert session.calls.count(doc_url("mlegitymacja.html")) == 4
    assert [s for s in sleeps if s >= 2] == [2.0, 4.0, 8.0, 2.0, 4.0, 8.0]


def test_home_unavailable_uses_fallback_list():
    routes = {KONTAKT: FakeResponse(text=fixture("usosweb_kontakt.html"))}
    web, _, _ = make_web(routes)
    context = ctx()

    records = list(pages.collect(context, web=web, now=NOW))

    assert [r.url for r in records] == [KONTAKT]
    assert "lista zapasowa" in context.warnings[0]
    # strona glowna + Dokumenty z listy zapasowej (404) - po ostrzezeniu
    assert len(context.warnings) == 1 + len(pages.FALLBACK_DOCUMENTS)
    assert not any("newsy.html" in w for w in context.warnings)


def test_collect_uses_web_client_and_timezone_from_context(monkeypatch):
    web, session, _ = make_web(site_routes())
    context = ctx()
    context.web = web
    monkeypatch.setattr(pages, "UsosWeb", lambda: pytest.fail("nowy klient mimo ctx.web"))

    records = list(pages.collect(context))

    assert HOME in session.calls
    home = next(r for r in records if r.url == doc_url("index.html"))
    # "8 dni temu" liczone od teraz w strefie kontekstu (Europe/Warsaw)
    assert home.updated_at.tzinfo is context.tz
    assert home.updated_at.hour == 0


def test_all_pages_failing_raises():
    web, _, _ = make_web({})
    context = ctx()

    with pytest.raises(UsosWebError, match="zadnej strony"):
        list(pages.collect(context, web=web, now=NOW))
    assert context.warnings


def test_only_empty_pages_raises():
    routes = {url: FakeResponse(text=fixture("usosweb_spa.html")) for url in site_routes()}
    web, _, _ = make_web(routes)

    with pytest.raises(UsosWebError, match="tresci"):
        list(pages.collect(ctx(), web=web, now=NOW))


# --- klient ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "https://usosownia.uj.edu.pl/usosweb/ogolne/dostep-do-systemu",
        "http://www.usosweb.uj.edu.pl/kontroler.php?_action=news/default",
        "https://www.usosweb.uj.edu.pl.evil.example/kontroler.php",
        "https://cas.uj.edu.pl/cas/login?gateway=true",
    ],
)
def test_host_allowlist(url):
    web, session, _ = make_web({})

    with pytest.raises(HostNotAllowed):
        web.get(url)
    assert session.calls == []


def test_cas_gateway_redirects_followed_with_cookies_session():
    cas = "https://cas.uj.edu.pl/cas/login?service=https%3A%2F%2Fwww.usosweb.uj.edu.pl%2Fkontroler.php&gateway=true"
    back = f"{KONTAKT}&_x=1"
    routes = {
        KONTAKT: FakeResponse(302, headers={"Location": cas}),
        cas: FakeResponse(302, headers={"Location": back}),
        back: FakeResponse(text="<p>ok</p>"),
    }
    web, session, _ = make_web(routes)

    assert web.get(KONTAKT) == "<p>ok</p>"
    assert session.calls == [KONTAKT, cas, back]
    assert session.headers["User-Agent"].startswith("KSI-chatbot-scraper/1.0")


def test_redirect_to_foreign_host_or_login_refused():
    web, _, _ = make_web({KONTAKT: FakeResponse(302, headers={"Location": "https://usosownia.uj.edu.pl/"})})
    with pytest.raises(HostNotAllowed):
        web.get(KONTAKT)

    login = "https://cas.uj.edu.pl/cas/login?service=x"
    web, _, _ = make_web({KONTAKT: FakeResponse(302, headers={"Location": login})})
    with pytest.raises(LoginRequired):
        web.get(KONTAKT)


def test_redirect_loop_bounded():
    web, session, _ = make_web({KONTAKT: FakeResponse(302, headers={"Location": KONTAKT})})

    with pytest.raises(UsosWebError, match="przekierowan"):
        web.get(KONTAKT)
    assert len(session.calls) <= 10


def test_delay_between_requests():
    times = iter([0.0, 0.25, 0.25])
    session = FakeSession({KONTAKT: FakeResponse(text="x")})
    sleeps: list[float] = []
    web = UsosWeb(session=session, sleep=sleeps.append, clock=lambda: next(times))

    web.get(KONTAKT)
    web.get(KONTAKT)

    assert sleeps == [pytest.approx(0.75)]


def test_retry_after_capped():
    routes = {KONTAKT: [FakeResponse(429, headers={"Retry-After": "86400"}), FakeResponse(text="ok")]}
    web, _, sleeps = make_web(routes)

    assert web.get(KONTAKT) == "ok"
    # backoff nie dluzszy niz 300 s mimo Retry-After (potem zwykly odstep miedzy zapytaniami)
    assert sleeps[0] == 300.0 and max(sleeps) == 300.0


def test_missing_charset_decoded_as_utf8():
    response = FakeResponse(text="x")
    response.headers = {"Content-Type": "text/html"}
    web, _, _ = make_web({KONTAKT: response})

    web.get(KONTAKT)

    assert response.encoding == "utf-8"


# --- notki z czasem wzglednym ---------------------------------------------------------

def _migration(text: str) -> str:
    return f"<table><tr><td><span class='note'>ostatnia migracja danych:\n {text}\n</span></td></tr></table>"


@pytest.mark.parametrize(
    ("text", "delta"),
    [
        ("ok. 19 godzin temu", timedelta(hours=19)),
        ("ok. 5 minut temu", timedelta(minutes=5)),
        ("ok. 2 dni temu", timedelta(days=2)),
        ("ok. 1 dzień temu", timedelta(days=1)),
        ("ok. godzinę temu", timedelta(hours=1)),
        ("21 godzin\n            temu", timedelta(hours=21)),
        ("30 sekund temu", timedelta(seconds=30)),
        ("ok. 3 tygodnie temu", timedelta(weeks=3)),
        ("przed chwilą", timedelta(0)),
    ],
)
def test_parse_last_migration(text, delta):
    assert parse_last_migration(_migration(text), NOW) == NOW - delta


def test_parse_last_migration_on_real_page():
    assert parse_last_migration(fixture("usosweb_home.html"), NOW) == NOW - timedelta(hours=19)


@pytest.mark.parametrize(
    "html",
    [
        "",
        fixture("usosweb_kontakt.html"),
        _migration("brak danych"),
        "<p>ostatnia modyfikacja tego dokumentu: 8 dni temu</p>",
    ],
)
def test_parse_last_migration_absent(html):
    assert parse_last_migration(html, NOW) is None


def _modified(text: str) -> str:
    return f"<span>ostatnia modyfikacja tego dokumentu: {text}</span>"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3 godziny temu", datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)),
        # minuty - tez do pelnej godziny
        ("ok. 40 minut temu", datetime(2026, 10, 25, 11, 0, tzinfo=timezone.utc)),
        ("8 dni temu", datetime(2026, 10, 17, tzinfo=timezone.utc)),
        ("3 miesiące temu", datetime(2026, 7, 1, tzinfo=timezone.utc)),
        ("ok. 10 miesięcy temu", datetime(2025, 12, 1, tzinfo=timezone.utc)),
        ("rok temu", datetime(2025, 1, 1, tzinfo=timezone.utc)),
        ("2 lata temu", datetime(2024, 1, 1, tzinfo=timezone.utc)),
    ],
)
def test_parse_last_modified_rounded_to_unit(text, expected):
    assert parse_last_modified(_modified(text), NOW) == expected


@pytest.mark.parametrize("text", ["2 lata temu", "3 miesiące temu", "ok. 5 lat temu"])
def test_parse_last_modified_stable_across_daily_runs(text):
    tomorrow = NOW + timedelta(days=1)
    assert parse_last_modified(_modified(text), NOW) == parse_last_modified(_modified(text), tomorrow)


def test_parse_last_modified_absent():
    assert parse_last_modified(fixture("usosweb_kontakt.html"), NOW) is None
