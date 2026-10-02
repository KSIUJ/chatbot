"""
Prompt systemowy: data i rok akademicki (czas Europe/Warsaw), jezyk odpowiedzi,
13 zasad w osobnych liniach i blok KONTEKST w wiadomosci uzytkownika.
"""

from datetime import date, datetime, timezone

import pytest

from src.backend.llm import dates, generate
from src.backend.llm.language import LANGUAGE_NAMES, LANGUAGES
from src.backend.rag.context_builder import RagContext, STAFF_HEADER

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)


# --- data po polsku --------------------------------------------------------------

@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 2), "2 października 2026 (piątek)"),
        (date(2026, 1, 1), "1 stycznia 2026 (czwartek)"),
        (date(2026, 2, 28), "28 lutego 2026 (sobota)"),
        (date(2026, 3, 15), "15 marca 2026 (niedziela)"),
        (date(2026, 4, 6), "6 kwietnia 2026 (poniedziałek)"),
        (date(2026, 5, 5), "5 maja 2026 (wtorek)"),
        (date(2026, 6, 10), "10 czerwca 2026 (środa)"),
        (date(2026, 7, 9), "9 lipca 2026 (czwartek)"),
        (date(2026, 8, 31), "31 sierpnia 2026 (poniedziałek)"),
        (date(2026, 9, 30), "30 września 2026 (środa)"),
        (date(2026, 11, 11), "11 listopada 2026 (środa)"),
        (date(2026, 12, 24), "24 grudnia 2026 (czwartek)"),
    ],
)
def test_polish_date_uses_genitive_month_and_weekday(day, expected):
    assert dates.polish_date(day) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 30), "2025/2026"),
        (date(2026, 10, 1), "2026/2027"),
        (date(2027, 1, 15), "2026/2027"),
        (date(2027, 6, 30), "2026/2027"),
        (date(2026, 12, 31), "2026/2027"),
    ],
)
def test_academic_year_starts_on_first_of_october(day, expected):
    assert dates.academic_year(day) == expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        # czas letni (CEST, UTC+2): 22:30 UTC 30.09 to juz 1.10 w Krakowie
        (datetime(2026, 9, 30, 22, 30, tzinfo=timezone.utc), date(2026, 10, 1)),
        (datetime(2026, 9, 30, 21, 59, tzinfo=timezone.utc), date(2026, 9, 30)),
        # czas zimowy (CET, UTC+1)
        (datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc), date(2027, 1, 1)),
        (datetime(2026, 12, 31, 22, 30, tzinfo=timezone.utc), date(2026, 12, 31)),
    ],
)
def test_warsaw_date_follows_local_time(moment, expected):
    assert dates.warsaw_now(moment).date() == expected


@pytest.mark.parametrize(
    ("moment", "offset_hours"),
    [
        # zmiana czasu: ostatnia niedziela marca i pazdziernika, 01:00 UTC
        (datetime(2026, 3, 29, 0, 59, tzinfo=timezone.utc), 1),
        (datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc), 2),
        (datetime(2026, 10, 25, 0, 59, tzinfo=timezone.utc), 2),
        (datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc), 1),
        (datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc), 2),
        (datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc), 1),
    ],
)
def test_eu_rule_offset_matches_cet_cest(moment, offset_hours):
    assert dates.eu_warsaw_offset(moment).total_seconds() == offset_hours * 3600


def test_naive_datetime_is_treated_as_utc():
    assert dates.warsaw_now(datetime(2026, 9, 30, 22, 30)).date() == date(2026, 10, 1)


# --- prompt systemowy ----------------------------------------------------------------

def test_prompt_contains_date_academic_year_and_language():
    prompt = generate.system_prompt("pl", now=NOW)

    assert prompt.startswith(
        "Jesteś asystentem Koła Studentów Informatyki UJ (KSI) dla jego członków. "
        "Dzisiaj jest 2 października 2026 (piątek), trwa rok akademicki 2026/2027.\n"
    )
    assert "Odpowiadasz po polsku." in prompt
    assert "{" not in prompt and "}" not in prompt


def test_prompt_on_academic_year_boundary():
    last_day = generate.system_prompt("pl", now=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc))
    first_day = generate.system_prompt("pl", now=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))
    # 30.09 22:30 UTC = 1.10 00:30 w Krakowie
    local_midnight = generate.system_prompt("pl", now=datetime(2026, 9, 30, 22, 30, tzinfo=timezone.utc))

    assert "Dzisiaj jest 30 września 2026 (środa), trwa rok akademicki 2025/2026." in last_day
    assert "Dzisiaj jest 1 października 2026 (czwartek), trwa rok akademicki 2026/2027." in first_day
    assert "Dzisiaj jest 1 października 2026 (czwartek), trwa rok akademicki 2026/2027." in local_midnight


@pytest.mark.parametrize("language", LANGUAGES)
def test_prompt_language_comes_from_language_names(language):
    prompt = generate.system_prompt(language, now=NOW)

    assert f"Odpowiadasz {LANGUAGE_NAMES[language]}." in prompt


@pytest.mark.parametrize("language", LANGUAGES)
def test_prompt_rules_1_to_13_are_separate_lines(language):
    lines = generate.system_prompt(language, now=NOW).splitlines()

    for number in range(1, 14):
        assert sum(line.startswith(f"{number}. ") for line in lines) == 1
    assert not any(line.startswith("14. ") for line in lines)


def test_prompt_keeps_sections_marker_and_diacritics():
    lines = generate.system_prompt("pl", now=NOW).splitlines()

    for header in ("ZAKRES", "ŹRÓDŁA I PRAWDA", "BEZPIECZEŃSTWO", "FORMA"):
        assert header in lines
    text = "\n".join(lines)
    assert "zaczynasz odpowiedź od znacznika [[NARUSZENIE]]." in text
    assert "Zwracasz się do użytkownika na „ty”" in text
    assert "z KONTEKSTU dołączonego do pytania" in text
    assert "tylko z sekcji PRACOWNIK" in text


def test_prompt_uses_current_time_by_default(monkeypatch):
    monkeypatch.setattr(generate, "utc_now", lambda: datetime(2027, 2, 14, 9, 0, tzinfo=timezone.utc))

    assert "Dzisiaj jest 14 lutego 2027 (niedziela), trwa rok akademicki 2026/2027." in generate.system_prompt()


# --- wiadomosc uzytkownika: blok KONTEKST ------------------------------------------------

def _capture_chat(monkeypatch, rag: RagContext) -> dict:
    monkeypatch.setattr(generate, "condense", lambda query, history: query)
    monkeypatch.setattr(generate, "retrieve_context", lambda query, k_mordor, k_other: rag)
    monkeypatch.setattr(generate, "utc_now", lambda: NOW)
    seen: dict = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr(generate, "_resolve_chat_fn", lambda: fake_chat)
    return seen


def test_user_message_wraps_context_in_labelled_block(monkeypatch):
    context = f"{STAFF_HEADER}\n\n[usos: Jan Kowalski]\nPokoj: 1234"
    seen = _capture_chat(monkeypatch, RagContext(context, ["mordor/analiza/skan.png"], []))

    generate.answer("gdzie siedzi Jan Kowalski?")

    user = seen["user"]
    assert user.startswith("KONTEKST:\n")
    assert "PRACOWNIK" in user
    assert user.index("KONTEKST:") < user.index("KONIEC KONTEKSTU") < user.index("PYTANIE: gdzie siedzi")
    assert "- skan.png (folder: analiza)" in user
    assert user.index("skan.png") < user.index("KONIEC KONTEKSTU")
    assert user.endswith("Odpowiedz po polsku.")
    assert "KONTEKST TEKSTOWY" not in user
    assert "PASUJACE PLIKI" not in user
    assert "Dzisiaj jest 2 października 2026 (piątek)" in seen["system"]


def test_user_message_says_when_context_is_empty(monkeypatch):
    seen = _capture_chat(monkeypatch, RagContext("", [], []))

    generate.answer("co to jest?", language="en")

    assert seen["user"].startswith("KONTEKST:\n(Brak pasujacych materialow w bazie.)\nKONIEC KONTEKSTU")
    assert seen["user"].endswith("Answer in English.")
