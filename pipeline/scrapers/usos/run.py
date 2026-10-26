"""
Przebieg scrapera USOS: kolektory po kolei -> zbior data/usos/ (manifest.json
+ records.jsonl, format z src/backend/rag/DATASETS.md).

Kazdy rekord jest sprawdzany modelem formatu przed zapisem. Zbior jest
zastepowany tylko tym, co tym razem zebrano z powodzeniem - inaczej sync
indeksu usunalby z niego wszystko, czego nie udalo sie pobrac:
- blad albo pominiecie kolektora (brak klucza, nieudana zaleznosc) wstrzymuje
  zapis; z --partial zbior jest zapisywany, a rodzaje rekordow tego kolektora
  zostaja z poprzedniego zbioru,
- --only zbiera wybrane kolektory (z ich zaleznosciami) i podmienia tylko ich
  rodzaje rekordow - reszta zostaje z poprzedniego zbioru,
- rodzaj rekordow, ktorych jest nagle o ponad polowe mniej niz poprzednio
  (np. pusta odpowiedz API), wstrzymuje zapis bez --force.
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from src.backend.rag.core.datasets import DatasetError, Record, read_dataset, write_dataset
from src.backend.rag.sources.usos.dataset import USOS_RECORD, StaffRecord
from src.backend.security.injection import detect_injection

from .api import ConsumerRequired
from .collectors import calendar, courses, news, pages, places, programmes, registrations, staff, units
from .context import Context

logger = logging.getLogger("usos")

SOURCE = "usos"
# kolejnosc ma znaczenie: kalendarz ustala aktywne cykle, jednostki - liste
# jednostek wydzialu, pracownicy - prowadzacych i ich edycje przedmiotow,
# przedmioty - budynki z zajeciami (sale w places)
COLLECTORS: tuple[ModuleType, ...] = (
    calendar, units, staff, courses, programmes, registrations, news, places, pages,
)
COLLECTOR_NAMES = tuple(module.NAME for module in COLLECTORS)
# rodzaje rekordow kazdego kolektora - przy czesciowym przebiegu reszta zostaje
# z poprzedniego zbioru
KINDS: dict[str, tuple[str, ...]] = {
    "calendar": ("calendar",),
    "units": ("unit",),
    "staff": ("staff",),
    "courses": ("course", "lecturer"),
    "programmes": ("programme",),
    "registrations": ("registration",),
    "news": ("news",),
    "places": ("building", "dormitory"),
    "pages": ("page",),
}
# zaleznosci: kolektor korzysta z tego, co wczesniejsze zapisaly w kontekscie,
# i bez nich zebralby zle albo niepelne dane - wtedy jest pomijany
REQUIRES: dict[str, tuple[str, ...]] = {
    "staff": ("calendar", "units"),
    "courses": ("calendar", "staff"),
    "programmes": ("units",),
    "registrations": ("units",),
    "places": ("units",),
}
# spadek liczby rekordow rodzaju ponizej tej czesci poprzedniej wstrzymuje zapis
MIN_KEPT_RATIO = 0.5
# ... o ile poprzednio bylo ich co najmniej tyle (male rodzaje wahaja sie naturalnie)
MIN_COUNT_FOR_GUARD = 10


@dataclass
class RunResult:
    counts: Counter = field(default_factory=Counter)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    # rodzaje rekordow wziete z poprzedniego zbioru (nie zbierane w tym przebiegu)
    kept: Counter = field(default_factory=Counter)
    # rodzaje z podejrzanym spadkiem liczby rekordow: rodzaj -> (bylo, jest)
    shrunk: dict[str, tuple[int, int]] = field(default_factory=dict)
    # rekordy z tekstem pasujacym do heurystyki prob obejscia promptu: id -> reguly
    # (tylko raport - tresc USOS jest oficjalna, a kontekst i tak jest neutralizowany)
    suspicious: dict[str, list[str]] = field(default_factory=dict)
    written: bool = False


def _record_text(record: Record) -> str:
    if isinstance(record, StaffRecord):
        return "\n".join((record.attributes.office_hours, record.attributes.interests))
    return record.content


def _head_from_git_dir(git_dir: Path) -> str:
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head[5:]
            path = git_dir / ref
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()[:7]
            for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
                if line.endswith(" " + ref):
                    return line[:7]
            return "unknown"
        return head[:7]
    except OSError:
        return "unknown"


def collector_version() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        # obraz bez gita - wersja z .git/HEAD (repozytorium zamontowane w kontenerze)
        sha = _head_from_git_dir(Path(".git"))
    return f"pipeline/scrapers/usos@{sha}"


def _validated(records: Iterable[Record]) -> list[Record]:
    # rekordy z kolektorow to juz modele formatu; ponowna walidacja z JSON-a
    # lapie to, czego konstruktor nie sprawdza (model_construct, zle typy)
    return [USOS_RECORD.validate_json(record.model_dump_json()) for record in records]


def with_dependencies(names: Iterable[str]) -> list[str]:
    """Wybrane kolektory z ich zaleznosciami, w kolejnosci COLLECTORS."""
    needed: set[str] = set()
    stack = list(names)
    while stack:
        name = stack.pop()
        if name not in needed:
            needed.add(name)
            stack.extend(REQUIRES.get(name, ()))
    return [name for name in COLLECTOR_NAMES if name in needed]


def _previous(out_dir: Path) -> list[Record]:
    try:
        dataset = read_dataset(out_dir, SOURCE, USOS_RECORD)
    except DatasetError as error:
        logger.warning("poprzedni zbior nieczytelny - nie da sie zachowac jego czesci (%s)", error)
        return []
    return dataset.records if dataset else []


def run(
    ctx: Context, out_dir: Path, only: Iterable[str] | None = None, partial: bool = False, force: bool = False,
) -> RunResult:
    selected = with_dependencies(only) if only is not None else list(COLLECTOR_NAMES)
    result = RunResult()
    records: dict[str, Record] = {}
    succeeded: list[str] = []
    for module in COLLECTORS:
        if module.NAME not in selected:
            continue
        missing = [dep for dep in REQUIRES.get(module.NAME, ()) if dep not in succeeded]
        if missing:
            ctx.warn(f"{module.NAME}: pominiety - nie zadzialaly zaleznosci: {', '.join(missing)}")
            result.skipped.append(module.NAME)
            continue
        if module.NEEDS_CONSUMER and not ctx.api.has_consumer:
            ctx.warn(f"{module.NAME}: pominiety - wymaga klucza aplikacji (USOS_CONSUMER_KEY/SECRET)")
            result.skipped.append(module.NAME)
            continue
        started = time.monotonic()
        requests_before = ctx.api.requests
        try:
            got = _validated(module.collect(ctx))
        except ConsumerRequired as error:
            ctx.warn(f"{module.NAME}: pominiety - {error.method} wymaga klucza aplikacji")
            result.skipped.append(module.NAME)
            continue
        except Exception as error:  # jeden kolektor nie przerywa reszty
            logger.exception("%s: blad", module.NAME)
            ctx.warn(f"{module.NAME}: blad - {error}")
            result.failed.append(module.NAME)
            continue
        succeeded.append(module.NAME)
        for record in got:
            if record.id in records:
                ctx.warn(f"{module.NAME}: powtorzone id {record.id!r} - zostaje pierwszy rekord")
                continue
            records[record.id] = record
            result.counts[record.kind] += 1
            rules = detect_injection(_record_text(record))
            if rules:
                result.suspicious[record.id] = rules
        logger.info(
            "%s: %d rekordow, %d zapytan, %.0f s",
            module.NAME, len(got), ctx.api.requests - requests_before, time.monotonic() - started,
        )

    if result.suspicious:
        ctx.warn(
            f"tresc {len(result.suspicious)} rekordow wyglada na probe obejscia promptu: "
            + ", ".join(f"{rid} ({', '.join(rules)})" for rid, rules in sorted(result.suspicious.items())[:20])
        )
    incomplete = result.failed + result.skipped
    if incomplete and not partial:
        logger.error("nie zapisuje zbioru - niezebrane: %s (--partial zapisze mimo to)", ", ".join(incomplete))
        return result

    # rodzaje zebrane teraz zastepuja poprzednie, pozostale zostaja ze starego zbioru;
    # przy --only tylko wybrane kolektory - zaleznosci dzialaja dla kontekstu, ale ich
    # rekordy zostaja z poprzedniego zbioru (np. pracownicy z adresami e-mail)
    requested = set(only) if only is not None else set(COLLECTOR_NAMES)
    fresh_kinds = {kind for name in succeeded if name in requested for kind in KINDS[name]}
    for record_id in [rid for rid, record in records.items() if record.kind not in fresh_kinds]:
        result.counts[records.pop(record_id).kind] -= 1
    result.counts += Counter()  # bez zer
    previous = _previous(out_dir)
    before = Counter(record.kind for record in previous)
    for record in previous:
        if record.kind not in fresh_kinds and record.id not in records:
            records[record.id] = record
            result.kept[record.kind] += 1
    for kind in fresh_kinds:
        old, new = before.get(kind, 0), result.counts.get(kind, 0)
        if old >= MIN_COUNT_FOR_GUARD and new < old * MIN_KEPT_RATIO:
            result.shrunk[kind] = (old, new)
    if result.shrunk and not force:
        logger.error(
            "nie zapisuje zbioru - podejrzanie malo rekordow: %s (--force zapisze mimo to)",
            ", ".join(f"{kind} {old} -> {new}" for kind, (old, new) in sorted(result.shrunk.items())),
        )
        return result

    write_dataset(out_dir, SOURCE, records.values(), collector=collector_version())
    result.written = True
    logger.info(
        "zapisano %d rekordow do %s: nowe %s, z poprzedniego zbioru %s",
        len(records), out_dir, dict(result.counts), dict(result.kept),
    )
    return result
