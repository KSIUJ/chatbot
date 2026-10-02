"""Heurystyka prob obejscia promptu systemowego (prompt injection / jailbreak).

detect_injection(tekst) -> nazwy pasujacych regul. Dziala niezaleznie od
modelu na kazdym pytaniu uzytkownika; trafienie niczego nie blokuje (odpowiedz
i tak podlega zasadom z promptu), tylko zaklada incydent dla zarzadu.

Wzorce sa pisane dla tekstu po normalize(): male litery, bez polskich znakow
(takze l zamiast l z kreska), bez znakow niewidocznych. Laczymy slowa z kilku
jezykow w jednej regule - mieszanie jezykow niczego nie psuje, a zwykle
pytania o wydzial nie zawieraja trybu rozkazujacego "zignoruj"/"ignore" razem
z "poprzednie instrukcje". Kazda regula wymaga takiej pary (czasownik +
przedmiot), zeby ograniczyc falszywe alarmy.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from collections.abc import Iterable

# luka miedzy slowami reguly - w obrebie jednego zdania
_SENTENCE_GAP = r"[^.!?\n]{{0,{n}}}"


def _gap(n: int) -> str:
    return _SENTENCE_GAP.format(n=n)


def _words(*alternatives: str) -> str:
    return "(?:" + "|".join(alternatives) + ")"


def _command(verbs: str, qualifiers: str, nouns: str) -> str:
    """Czasownik, potem przedmiot z okreslnikiem w dowolnej kolejnosci
    ("ignore previous instructions", "ignora las instrucciones anteriores")."""
    return (
        rf"\b{verbs}\b{_gap(40)}"
        rf"(?:\b{qualifiers}{_gap(25)}\b{nouns}|\b{nouns}{_gap(25)}\b{qualifiers})"
    )


# --- slowniki (po normalize) -------------------------------------------------------

_IGNORE_VERBS = _words(
    "ignore", "disregard", "forget", "skip", "discard", "abandon", "drop",
    "zignoruj", "ignoruj", "zapomnij", "pomin", "olej", "porzuc", "zlekcewaz", "odrzuc", "anuluj",
    "nie zwazaj", "nie stosuj sie", "nie przestrzegaj", "nie sluchaj", "przestan sluchac",
    "ignoriere", "ignorier", "vergiss", "missachte",
    "ignora", "olvida", "omite", "descarta",
    "oublie", "ignorez", "oubliez", "neglige",
    "dimentica", "ignorate", "dimenticate", "tralascia",
    r"ігнору\w*", "забудь", r"не зважа\w*",
)
_PREVIOUS = _words(
    r"previous", r"prior", r"above", r"earlier", r"preceding", r"all", r"any", r"your", r"system",
    r"original", r"initial", r"these", r"those", r"every",
    r"poprzedn\w*", r"wczesniejsz\w*", r"wszystk\w*", r"powyzsz\w*", r"swoj\w*", r"twoj\w*",
    r"dotychczasow\w*", r"systemow\w*", r"pierwotn\w*", r"oryginaln\w*", r"wyzej",
    r"vorherig\w*", r"bisherig\w*", r"alle", r"obig\w*", r"vorig\w*", r"deine\w*",
    r"anterior\w*", r"previa\w*", r"todas", r"todos", r"tus",
    r"precedent\w*", r"toutes", r"tous", r"tes", r"vos",
    r"tutte", r"tutti", r"tue", r"tuoi",
    r"попередн\w*", r"усі", r"всі", r"сво\w*", r"тво\w*",
)
_INSTRUCTIONS = _words(
    r"instructions?", r"rules?", r"prompts?", r"directives?", r"guidelines?", r"commands?",
    r"constraints?", r"restrictions?",
    r"instrukcj\w*", r"polecen\w*", r"zasad\w*", r"regul\w*", r"wytyczn\w*", r"prompt\w*",
    r"ogranicze\w*", r"zakaz\w*",
    r"anweisung\w*", r"instruktion\w*", r"regeln", r"befehl\w*", r"vorgaben",
    r"instruccion\w*", r"reglas?", r"ordenes", r"indicacion\w*",
    r"consignes?", r"regles?",
    r"istruzion\w*", r"regol\w*", r"indicazion\w*", r"comand\w*",
    r"інструкці\w*", r"правил\w*", r"вказівк\w*", r"команд\w*",
)

_REVEAL_VERBS = _words(
    "reveal", "show", "print", "display", "output", "repeat", "tell me", "give me", "dump", "leak",
    "recite", "paste", "spell out", "share", r"what (?:is|are|was|were)",
    "pokaz", "podaj", "wypisz", "wyswietl", "powtorz", "zdradz", "ujawnij", "wklej", "przytocz",
    "zacytuj", "streszcz", "sparafrazuj", "daj", "jak brzmi", "jaki jest", "jakie sa", "co zawiera",
    r"zeig\w*", "gib", "nenne", "wiederhole", "verrate",
    r"muestra\w*", "dime", r"revela\w*", "repite", "imprime",
    r"montre\w*", r"affiche\w*", r"revele\w*", r"repete\w*", r"donne\w*", r"dis[ -]moi",
    r"mostra\w*", r"rivela\w*", "ripeti", "dimmi", "stampa",
    "покажи", "виведи", "повтори", "розкажи", "напиши",
)
# cel jednoznaczny - "prompt systemowy" po czasowniku wystarczy
_PROMPT_TARGET = _words(
    r"system\s*-?\s*prompt\w*", r"prompt\w* systemow\w*", r"systemow\w* prompt\w*",
    r"instrukcj\w* systemow\w*", r"systemow\w* instrukcj\w*", r"(?:initial|hidden|secret|original) prompt",
    r"pre-?prompt", r"ukryt\w* (?:prompt\w*|instrukcj\w*)", r"poczatkow\w* (?:prompt\w*|instrukcj\w*)",
    r"prompt (?:du )?systeme", r"prompt del sistema", r"prompt di sistema", r"systemanweisung\w*",
    r"системн\w* (?:промпт\w*|інструкці\w*|підказк\w*)",
)
_YOUR = _words(
    # bez hiszpanskiego "tu" - po polsku to "tutaj" ("pokaz tu zasady")
    "your", r"twoj\w*", r"swoj\w*", r"deine\w*", "tus", "tes", "vos", "tue", "tuoi", "tua",
    r"сво\w*", r"тво\w*",
)
_OWN_RULES = _words(
    r"instructions?", r"rules", r"guidelines", r"directives", r"prompt",
    r"instrukcj\w*", r"zasad\w*", r"regul\w*", r"wytyczn\w*", r"polecen\w*",
    r"anweisung\w*", r"regeln", r"instruccion\w*", r"reglas", r"consignes", r"regles",
    r"istruzioni", r"regole", r"інструкці\w*", r"правил\w*",
)

_ROLEPLAY_VERBS = _words(
    "pretend", r"act as", "roleplay", r"role[ -]play", r"behave (?:as|like)", r"imagine (?:you are|you're)",
    "simulate", r"play the role",
    "udawaj", "udaj", r"zachowuj sie jak", r"wciel sie", "odgrywaj", "odegraj", "zagraj", r"graj role",
    r"wyobraz sobie,? ze jestes", "symuluj",
    r"tu so,? als", r"stell dir vor", "finge", r"actua como", r"haz como si",
    r"fais semblant", r"agis comme", r"imagine que tu es", "fingi", r"fai finta", r"comportati come",
    "уяви", "прикинься", r"поводься як",
)
_NO_LIMITS = _words(
    r"without (?:any )?(?:restrictions|rules|limits|limitations|filters|censorship|guidelines)",
    r"no (?:restrictions|rules|limits|filters|guidelines|censorship)",
    "unrestricted", "unfiltered", "uncensored", "evil", r"no longer bound", r"not bound by",
    r"bez (?:zadnych )?(?:ograniczen|zasad|regul|filtrow|cenzury)", r"nieograniczon\w*", r"niecenzurowan\w*",
    r"nie masz (?:zadnych )?(?:zasad|ograniczen|regul)", r"nie obowiazuja cie",
    r"ohne (?:einschrankungen|regeln|filter)", r"sin (?:restricciones|reglas|filtros|censura)",
    r"sans (?:restriction\w*|regle\w*|filtre\w*|censure)", r"senza (?:restrizioni|regole|filtri|censura)",
    r"без (?:обмежень|правил|цензури)",
)

_OVERRIDE_VERBS = _words(
    "override", "bypass", "circumvent", "disable", r"turn off", "deactivate",
    "obejdz", "omin", "wylacz", "dezaktywuj", "nadpisz", "zlam", "uchyl",
    "umgehe", "deaktiviere", "desactiva", "elude", "contourne", "desactive", "aggira", "disattiva",
    "обійди", "вимкни",
)
_OWN = _words(
    "your", "safety", "content", "system", r"swoj\w*", r"twoj\w*", r"systemow\w*",
    r"deine\w*", "tus", "tes", "tue", r"сво\w*", r"тво\w*",
)
_SAFEGUARDS = _words(
    r"rules", r"restrictions", r"filters?", r"safety", r"guardrails", r"guidelines", r"limitations",
    r"censorship", r"safeguards", r"instructions",
    r"zabezpieczen\w*", r"ogranicze\w*", r"cenzur\w*", r"zasad\w*", r"regul\w*", r"instrukcj\w*",
    r"regeln", r"einschrankung\w*", r"restricciones", r"reglas", r"regles", r"restrizioni", r"regole",
    r"обмежен\w*", r"правил\w*",
)
# sam rzeczownik jednoznacznie o zabezpieczeniach modelu
_STRONG_SAFEGUARDS = _words(
    "guardrails", "censorship", r"cenzur\w*", r"safety (?:rules|filters?|guidelines|measures)",
    r"content (?:filters?|policy)", "restrictions",
)


# --- reguly ---------------------------------------------------------------------------

def _compile(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.MULTILINE) for p in patterns)


_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "ignore_instructions": _compile(
        _command(_IGNORE_VERBS, _PREVIOUS, _INSTRUCTIONS),
        rf"\b{_IGNORE_VERBS}\b{_gap(20)}\b(?:everything|all|wszystko|to,? co)?\s*"
        r"(?:above|before this|powyzej|wyzej|powyzsze)\b",
    ),
    "reveal_prompt": _compile(
        rf"\b{_REVEAL_VERBS}\b{_gap(30)}\b{_PROMPT_TARGET}",
        rf"\b{_REVEAL_VERBS}\b{_gap(30)}\b{_YOUR}\b{_gap(15)}\b{_OWN_RULES}\b",
        r"\b(?:jakie|what)\s+(?:instrukcj\w*|polecen\w*|instructions)\s+"
        r"(?:dostal\w*|otrzymal\w*|masz|were you given|did you get|do you have)",
        r"\b(?:repeat|print|output|powtorz|wypisz|przepisz)\b"
        rf"{_gap(20)}\b(?:everything|all|the (?:text|words)|wszystko|caly tekst|tekst|slowa)\b"
        rf"{_gap(20)}\b(?:above|powyzej|wyzej|before)\b",
    ),
    "jailbreak": _compile(r"\bjail-?break\w*", r"\bdo anything now\b"),
    # DAN sprawdzamy na tekscie oryginalnym (wielkie litery) - patrz _matches_dan
    "dan": (),
    "developer_mode": _compile(
        r"\b(?:enable|activate|enter|switch to|turn on|you are (?:now )?in|wlacz\w*|aktywuj\w*|"
        r"przejdz (?:do|w)|przelacz\w*(?: sie)? (?:na|w)|uruchom\w*)\b"
        rf"{_gap(20)}\b(?:developer|dev|god|unrestricted|unfiltered|dan|jailbreak|sudo)[ -]?mode\b",
        r"\b(?:developer|god|dan) mode (?:enabled|on|activated)\b",
        r"\btryb\w* (?:dewelopersk\w*|dewelopera|boga|bez ogranicze\w*|bez cenzury|nieograniczon\w*|"
        r"niecenzurowan\w*|jailbreak\w*|dan)\b",
        r"\bmodo (?:desarrollador|dios|sin restricciones)\b|\bmode (?:developpeur|dieu|sans restriction\w*)\b",
        r"\bmodalita (?:sviluppatore|dio)\b|\bentwicklermodus\b|\bрежим (?:розробника|бога|без обмежень)",
    ),
    "roleplay_bypass": _compile(rf"\b{_ROLEPLAY_VERBS}\b{_gap(60)}\b{_NO_LIMITS}"),
    "role_override": _compile(
        r"\byou are now\b",
        r"\bfrom now on,? you (?:are|will|must)\b",
        r"\byou will now act\b",
        r"\bod (?:teraz|tej chwili|tej pory|dzis),? (?:jestes|bedziesz|masz byc|zachowujesz sie)\b",
        r"\b(?:ab jetzt bist du|du bist jetzt|a partir de ahora eres|ahora eres)\b",
        r"\b(?:a partir de maintenant,? tu es|tu es maintenant|desormais,? tu es|da ora (?:in poi )?sei)\b",
        r"(?:відтепер ти|тепер ти (?:є|будеш))",
    ),
    "override_rules": _compile(
        _command(_OVERRIDE_VERBS, _OWN, _SAFEGUARDS),
        rf"\b{_OVERRIDE_VERBS}\b{_gap(30)}\b{_STRONG_SAFEGUARDS}",
    ),
    "fake_system_message": _compile(
        r"<\|?\s*(?:system|im_start|im_end|endoftext)\s*\|?>",
        r"\[/?(?:system|inst|sys)\]",
        r"<</?sys>>",
        r"#{2,}\s*(?:system|instruction|instrukcj\w*|new rules|nowe zasady)",
        r"^\s*(?:system|assistant|developer)\s*:\s*(?:you |ty |jestes|from now|od teraz|ignore|zignoruj|new |nowe )",
        r"\b(?:new|updated) (?:system )?(?:instructions|rules)\s*:",
        r"\bnowe (?:instrukcje|polecenia|zasady)\s*:",
        r"\b(?:end|koniec) (?:of )?(?:the )?(?:system )?(?:prompt|instrukcj\w*|kontekstu|context)\b",
    ),
    "base64_payload": _compile(
        r"\b(?:decode|zdekoduj|odkoduj|rozkoduj)\b"
        rf"{_gap(40)}\bbase\s?64\b{_gap(60)}\b(?:follow|execute|obey|run|wykonaj|zastosuj|postepuj|zrob)",
        r"\bbase\s?64\b"
        rf"{_gap(40)}\b(?:decode|zdekoduj|odkoduj)\b{_gap(30)}\b(?:follow|execute|obey|wykonaj|zastosuj)",
    ),
}

RULE_NAMES: tuple[str, ...] = tuple(_RULES)

_DAN = re.compile(r"\bDAN\b")

# kandydaci na tekst w base64 (dlugie ciagi bez spacji)
_BASE64_TOKEN = re.compile(r"[A-Za-z0-9+/_-]{20,}={0,2}")
MAX_BASE64_CANDIDATES = 5
# odkodowany tekst musi byc w wiekszosci drukowalny, zeby go sprawdzac
_MIN_PRINTABLE_RATIO = 0.9


def normalize(text: str) -> str:
    """Male litery, bez znakow diakrytycznych i niewidocznych (zero-width),
    spacje/taby zwiniete do jednej spacji; podzial na linie zostaje."""
    decomposed = unicodedata.normalize("NFKD", text)
    kept = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch) and unicodedata.category(ch) != "Cf"
    )
    folded = kept.casefold().replace("ł", "l")
    lines = (" ".join(line.split()) for line in folded.splitlines())
    return "\n".join(line for line in lines if line)


def _matched_rules(normalized: str) -> set[str]:
    return {name for name, patterns in _RULES.items() if any(p.search(normalized) for p in patterns)}


def _decoded_base64(text: str) -> Iterable[str]:
    """Teksty odkodowane z kandydatow na base64 (najwyzej kilka, tylko UTF-8)."""
    for match in list(_BASE64_TOKEN.finditer(text))[:MAX_BASE64_CANDIDATES]:
        token = match.group().replace("-", "+").replace("_", "/")
        token += "=" * (-len(token) % 4)
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8")
        except (binascii.Error, ValueError):
            continue
        printable = sum(ch.isprintable() or ch.isspace() for ch in decoded)
        if decoded and printable / len(decoded) >= _MIN_PRINTABLE_RATIO:
            yield decoded


def detect_injection(text: str) -> list[str]:
    """Nazwy regul (z RULE_NAMES, w tej kolejnosci), do ktorych pasuje tekst.
    Pusta lista = brak sygnalu."""
    if not text or not text.strip():
        return []
    matched = _matched_rules(normalize(text))
    if _DAN.search(text):
        matched.add("dan")
    if any(_matched_rules(normalize(decoded)) for decoded in _decoded_base64(text)):
        matched.add("base64_payload")
    return [name for name in RULE_NAMES if name in matched]
