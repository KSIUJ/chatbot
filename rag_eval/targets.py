"""
Cele w zbiorze pytan: co powinno trafic do kontekstu, zapisane niezaleznie od
budowy RAG-a (stary i nowy RAG sa mierzone tym samym zbiorem).

    page:<adres>      strona albo plik ze stron (bez schematu, "/" na koncu
                      bez znaczenia, %xx rozkodowane); "*" na koncu = prefiks
    staff:<imie nazwisko>   pracownik z USOS (bez rozrozniania wielkosci liter)
    mordor:<fragment> plik z Mordoru, ktorego sciezka zawiera fragment
    ksi:<fragment>    informacja o KSI (strony KSI, pliki pisane recznie);
                      "ksi:*" = dowolna
    usos:<id rekordu> rekord USOS inny niz pracownik (przedmiot, kalendarz,
                      rejestracja, budynek...), np. usos:course:WMI.II-WMD-2MK;
                      "*" na koncu = prefiks (usos:registration:*)

System pod testem zamienia kazde trafienie na zbior celow (hit_targets
w adapterze), a expected_rank szuka pierwszego trafienia, ktore pasuje do
ktoregokolwiek oczekiwanego celu.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from urllib.parse import unquote, urlsplit

KINDS = ("page", "staff", "mordor", "ksi", "usos")


def normalize_url(url: str) -> str:
    """Adres do porownan: bez schematu, z rozkodowanymi %xx, bez "/" na koncu."""
    url = unquote(url.strip())
    parts = urlsplit(url if "://" in url else f"https://{url}")
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.netloc.lower()}{path}{query}"


def page(url: str) -> str:
    return f"page:{normalize_url(url)}"


def staff(name: str) -> str:
    return f"staff:{' '.join(name.split()).casefold()}"


def mordor(path: str) -> str:
    return f"mordor:{path.replace(chr(92), '/').casefold()}"


def ksi(key: str) -> str:
    return f"ksi:{key.casefold()}"


def usos(record_id: str) -> str:
    return f"usos:{record_id.casefold()}"


def _split(target: str) -> tuple[str, str]:
    kind, sep, value = target.partition(":")
    if not sep or kind not in KINDS or not value:
        raise ValueError(f"nieprawidlowy cel {target!r} (rodzaje: {', '.join(KINDS)})")
    return kind, value


def validate(target: str) -> None:
    _split(target)


def matches(expected: str, actual: str) -> bool:
    """Czy cel trafienia (`actual`, z adaptera) spelnia cel oczekiwany."""
    kind, value = _split(expected)
    actual_kind, actual_value = _split(actual)
    if kind != actual_kind:
        return False
    if kind == "page":
        if value.endswith("*"):
            return actual_value.startswith(normalize_url(value[:-1]))
        return actual_value == normalize_url(value)
    if kind == "staff":
        return actual_value == " ".join(value.split()).casefold()
    if kind == "usos":
        value = value.casefold()
        return actual_value.startswith(value[:-1]) if value.endswith("*") else actual_value == value
    # mordor, ksi: fragment sciezki/klucza; "*" = cokolwiek tego rodzaju
    return value == "*" or value.casefold() in actual_value


def expected_rank(expected: Sequence[str], hits: Iterable[Iterable[str]]) -> int | None:
    """Pozycja (od 1) pierwszego trafienia pasujacego do ktoregos celu; None = brak."""
    for rank, targets in enumerate(hits, start=1):
        if any(matches(e, t) for e in expected for t in targets):
            return rank
    return None
