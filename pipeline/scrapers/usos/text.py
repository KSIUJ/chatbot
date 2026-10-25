"""Pomocnicze funkcje tekstu dla rekordow USOS: slowniki jezykowe USOS API,
daty i godziny po polsku, tabele Markdownu."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from html import escape
from datetime import date, datetime
from typing import Any

from ..common.markdown import html_to_markdown, text_of

WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
_HTML_TAG = re.compile(r"<\/?[a-zA-Z][^>]*>")
FREQUENCIES = {
    "every_week": "co tydzień",
    "every_two_weeks": "co dwa tygodnie",
    "every_two_weeks_odd": "co dwa tygodnie (tygodnie nieparzyste)",
    "every_two_weeks_even": "co dwa tygodnie (tygodnie parzyste)",
    "once": "jednorazowo",
}


def pick(value: Any, lang: str = "pl") -> str:
    """Tekst ze slownika jezykowego USOS ({"pl": ..., "en": ...}); gdy brak
    wersji w `lang`, druga wersja. Zwykly napis zwraca bez zmian."""
    if isinstance(value, dict):
        for key in (lang, "pl", "en"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
        return ""
    return value.strip() if isinstance(value, str) else ""


def pick_markdown(value: Any, lang: str = "pl", heading_offset: int = 2) -> str:
    """Pole opisowe USOS (HTML albo zwykly tekst w slowniku jezykowym) jako Markdown.
    W zwyklym tekscie nowe linie sa czescia tresci (akapity, wyliczenia) - staja sie
    akapitami i <br>, zanim konwerter zamieni zawiniecia wierszy na spacje."""
    text = pick(value, lang)
    if text and not _HTML_TAG.search(text):
        paragraphs = re.split(r"\n\s*\n", text.replace("\r", ""))
        text = "".join("<p>" + escape(p).replace("\n", "<br>") + "</p>" for p in paragraphs)
    return html_to_markdown(text, heading_offset=heading_offset)


def pick_text(value: Any, lang: str = "pl") -> str:
    """Krotkie pole USOS (moze zawierac HTML) jako jedna linia tekstu."""
    return text_of(pick(value, lang))


def parse_datetime(value: Any) -> datetime | None:
    """Data i czas z USOS API ("2026-10-27 14:00:00" albo "2026-10-27")."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    # czasy USOS sa lokalne (Europe/Warsaw), bez strefy
    return parsed.replace(tzinfo=None)


def parse_date(value: Any) -> date | None:
    parsed = parse_datetime(value)
    return parsed.date() if parsed else None


def format_date(value: date | datetime | None) -> str:
    """"27.10.2026" (z godzina, gdy podana i niezerowa: "27.10.2026, 14:00")."""
    if value is None:
        return ""
    if isinstance(value, datetime) and (value.hour or value.minute):
        return value.strftime("%d.%m.%Y, %H:%M")
    return value.strftime("%d.%m.%Y")


def format_period(start: date | datetime | None, end: date | datetime | None) -> str:
    if start and end:
        return f"{format_date(start)} – {format_date(end)}"
    if start:
        return f"od {format_date(start)}"
    if end:
        return f"do {format_date(end)}"
    return ""


def weekday(value: date) -> str:
    return WEEKDAYS[value.weekday()]


def frequency(value: Any) -> str:
    return FREQUENCIES.get(value, "") if isinstance(value, str) else ""


def table(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Tabela Markdownu; pusty napis, gdy nie ma wierszy."""
    body = [[_cell(c) for c in row] for row in rows]
    if not body:
        return ""
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.split()).replace("|", "\\|")


def join_nonempty(parts: Iterable[str], sep: str = ", ") -> str:
    return sep.join(p for p in parts if p)


def section(title: str, body: str, level: int = 2) -> str:
    """Sekcja Markdownu; pusty napis, gdy nie ma tresci."""
    body = body.strip()
    return f"{'#' * level} {title}\n\n{body}" if body else ""


def document(*sections: str) -> str:
    return "\n\n".join(s for s in sections if s and s.strip()).strip() + "\n"
