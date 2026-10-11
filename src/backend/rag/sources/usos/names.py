"""
Odmiana polskich imion i nazwisk pracownikow - dla dokladnego wyszukiwania
(staff.py) i karty pracownika (documents.py).

- inflected_forms: formy przypadkow zaleznych tokenu (male litery, bez
  polskich znakow - jak lexical.tokenize), z nadmiarem: generujemy formy
  meskie i zenskie, z e ruchomym i bez, bo plec i pochodzenie nazwiska nie
  sa znane. Formy sa porownywane tylko ze slowami zapytania, wiec nieistniejaca
  forma niczego nie psuje.
- genitive: dopelniacz imienia i nazwiska ("Jacka Cyranki") - jedna,
  najbardziej prawdopodobna forma do tekstu wyszukiwania karty.
"""

from __future__ import annotations

VOWELS = set("aeiouy")
MIN_FORM = 4

# miekkie zakonczenia, po ktorych miejscownik ma -u (a nie -e z oboczna)
_LOCATIVE_U = ("k", "g", "ch", "h", "j", "c", "cz", "sz", "rz", "z", "dz", "l")
# oboczne w celowniku/miejscowniku: "-ie"/"-e" po twardej spolglosce
_ALTERNATION = {
    "st": "scie", "sl": "sle", "zd": "zdzie", "sn": "snie", "ch": "sze",
    "k": "ce", "g": "dze", "h": "sze", "d": "dzie", "t": "cie", "r": "rze", "l": "le",
    "n": "nie", "s": "sie", "z": "zie", "w": "wie", "m": "mie", "b": "bie", "p": "pie", "f": "fie",
}
# imiona meskie zakonczone na -a (odmiana jak imiona zenskie, ale plec meska)
MALE_NAMES_IN_A = {"kuba", "barnaba", "bonawentura", "kosma", "jarema"}
# czeste slowa, ktore sa tez nazwiskiem albo jego forma (Tutaj-Gasinska,
# Wiek -> "wieku", Ksiazek -> "ksiazka"): forma odmieniona odpada, a samo
# nazwisko wymaga sladu osoby (staff.py)
COMMON_WORDS = {
    "tutaj", "pogoda", "polak", "kawa", "niemiec", "wiek", "roman", "wrona", "sroka", "miska",
    "mnich", "chmiel", "tabor", "mazur", "burek", "kulig", "duda", "kania", "palka", "cynk",
    "wieku", "sali", "gronie", "ksiazka", "ksiazki", "ksiazce", "ksiazke", "pogody", "pogodzie",
    "kawy", "kawie", "kawe", "roku", "planu", "domu", "polaka", "polakiem", "niemca", "niemcy",
}


def _alternate(stem: str) -> set[str]:
    """Formy celownika/miejscownika z oboczna: "cyrank" -> "cyrance"."""
    forms = set()
    for ending, replacement in _ALTERNATION.items():
        if stem.endswith(ending):
            forms.add(stem[: -len(ending)] + replacement)
            break
    if stem.endswith(_LOCATIVE_U):
        forms.add(stem + "u")
    return forms


def _feminine_a(token: str) -> set[str]:
    """Rzeczownik na -a (Ewa, Cyranka, Duda, Zawisza): -y/-i, -e (biernik),
    -ie z oboczna (celownik, miejscownik), -a (narzednik)."""
    stem = token[:-1]
    forms = {stem + "y", stem + "e"} | _alternate(stem)
    if stem.endswith(("k", "g", "j", "l")):
        forms.add(stem + "i")
    return forms


def _consonant_stems(token: str) -> list[str]:
    """Temat odmiany z e ruchomym i bez: micek -> mick, krawiec -> krawc,
    pawel -> pawl, stepien -> stepn."""
    stems = [token]
    for ending, replacement in (("iec", "c"), ("ien", "n"), ("ek", "k"), ("ec", "c"), ("el", "l")):
        if token.endswith(ending) and len(token) - len(ending) >= 2:
            stems.append(token[: -len(ending)] + replacement)
            break
    return stems


def _masculine_consonant(stem: str) -> set[str]:
    """Rzeczownik meski na spolgloske: -a, -owi, -em/-iem, -u/-ie; po n, s, c,
    z takze formy miekkie (miekkie n, s, c, z znikaja w zapisie bez polskich znakow)."""
    forms = {stem + "a", stem + "owi", stem + ("iem" if stem.endswith(("k", "g")) else "em")}
    forms |= _alternate(stem)
    if stem.endswith(("n", "s", "c", "z")):
        forms |= {stem + "ia", stem + "iowi", stem + "iem", stem + "iu"}
    return forms


def inflected_forms(token: str) -> set[str]:
    """Formy przypadkow zaleznych tokenu imienia lub nazwiska (bez samego
    tokenu); krotsze niz MIN_FORM odpadaja."""
    if len(token) < 3:
        return set()
    forms: set[str] = set()
    if token.endswith("i") and token[-2] in "kg":
        # przymiotnikowe: Blocki, Bakalarski
        forms = {token + "ego", token + "emu", token + "m"}
    elif token.endswith("y") and token[-2] not in VOWELS:
        # przymiotnikowe na -y: Razny
        stem = token[:-1]
        forms = {stem + "ego", stem + "emu", stem + "ym"}
    elif token.endswith("ia"):
        # Leokadia -> Leokadii, Kania -> Kani; biernik -ie
        stem = token[:-1]
        forms = {stem if stem[-2:-1] in ("n", "s", "c", "z") else stem + "i", stem + "e"}
    elif token.endswith("a"):
        forms = _feminine_a(token)
        if token.endswith(("ska", "cka", "dzka")):
            forms.add(token[:-1] + "iej")
    elif token[-1] not in VOWELS:
        for stem in _consonant_stems(token):
            forms |= _masculine_consonant(stem)
    # zakonczone na -o, -e, -u, -i (Zygadlo, Valette, Ugo) - nieodmienne
    forms.discard(token)
    return {form for form in forms if len(form) >= MIN_FORM and form not in COMMON_WORDS}


# --- dopelniacz do karty (z polskimi znakami) ------------------------------------

def _genitive_a(word: str) -> str:
    stem = word[:-1]
    if word.endswith("ia"):
        # Leokadia -> Leokadii, Kania -> Kani
        return stem if stem[-2:-1] in ("n", "s", "c", "z") else stem + "i"
    if stem.endswith(("k", "g", "l", "j")):
        return stem + "i"
    return stem + "y"


def _genitive_masculine(word: str) -> str:
    lower = word.lower()
    if lower.endswith(("ki", "gi")):
        return word + "ego"
    if lower.endswith("y") and lower[-2:-1] not in VOWELS:
        return word[:-1] + "ego"
    if lower.endswith("a"):
        return _genitive_a(word)
    if lower[-1:] in VOWELS:
        return word
    if lower in ("paweł", "gaweł"):
        return word[:-2] + "ła"
    for ending, replacement in (("niec", "ńca"), ("iec", "ca"), ("ień", "nia"), ("ek", "ka"), ("ec", "ca")):
        if lower.endswith(ending):
            return word[: -len(ending)] + replacement
    soft = {"ń": "nia", "ś": "sia", "ć": "cia", "ź": "zia"}
    if lower[-1] in soft:
        return word[:-1] + soft[lower[-1]]
    return word + "a"


def _genitive_feminine(word: str) -> str:
    lower = word.lower()
    if lower.endswith(("ska", "cka", "dzka")):
        return word[:-1] + "iej"
    if lower.endswith("a"):
        return _genitive_a(word)
    # nazwiska zenskie na spolgloske i -o sa nieodmienne
    return word


def _decline(name: str, decline_word) -> str:
    return "-".join(decline_word(part) if part else part for part in name.split("-"))


def is_female(first_name: str) -> bool:
    first = first_name.strip().lower()
    return first.endswith("a") and first not in MALE_NAMES_IN_A


def genitive(first_name: str, last_name: str) -> str:
    """Dopelniacz imienia i nazwiska: "Jacek Cyranka" -> "Jacka Cyranki"."""
    decline_word = _genitive_feminine if is_female(first_name) else _genitive_masculine
    parts = [" ".join(_decline(w, decline_word) for w in part.split()) for part in (first_name, last_name) if part]
    return " ".join(parts)
