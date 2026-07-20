"""
Wlasciwy scraper danych pracownikow WMI z USOS API UJ: kontakt i dyzury
("office_hours"), zapisywane jako znormalizowany dataset JSON pod katem
pozniejszego wykorzystania w RAG.
"""

from usos_api import (
    RAW_DATA_DIR,
    UsosApiError,
    save_response,
    usos_call_signed,
)

FAC_ID = "WMI"
STAFF_INDEX_PAGE_SIZE = 100
USER_FIELDS = (
    "id|first_name|last_name|titles|email|phone_numbers|office_hours|"
    "room|profile_url|homepage_url|interests|employment_positions"
)


def flatten_langdict(langdict: dict | None, preferred_lang: str = "pl") -> tuple[dict, str]:
    """Splaszcza pole typu LangDict do (oryginalny slownik, najlepszy tekst).

    Preferuje jezyk `preferred_lang`; jesli go brak lub jest pusty, bierze
    pierwsza niepusta wartosc z dostepnych jezykow. Zwraca ({}, "") dla
    pustego/brakujacego LangDict.
    """
    if not langdict:
        return {}, ""

    preferred_text = langdict.get(preferred_lang)
    if preferred_text:
        return dict(langdict), preferred_text

    for value in langdict.values():
        if value:
            return dict(langdict), value

    return dict(langdict), ""


def normalize_employee(raw: dict) -> dict:
    """Normalizuje surowa odpowiedz services/users/user do plaskiego rekordu."""
    office_hours, office_hours_text = flatten_langdict(raw.get("office_hours"))
    interests, interests_text = flatten_langdict(raw.get("interests"))

    return {
        "id": raw.get("id"),
        "first_name": raw.get("first_name"),
        "last_name": raw.get("last_name"),
        "titles": raw.get("titles"),
        "email": raw.get("email"),
        "phone_numbers": raw.get("phone_numbers") or [],
        "room": raw.get("room"),
        "profile_url": raw.get("profile_url"),
        "homepage_url": raw.get("homepage_url"),
        "office_hours": office_hours,
        "office_hours_text": office_hours_text,
        "interests": interests,
        "interests_text": interests_text,
        "employment_positions": raw.get("employment_positions") or [],
    }
