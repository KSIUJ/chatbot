"""
Format zbiorow danych zrodel (kontrakt dla scraperow) - patrz DATASETS.md.

Kazde zrodlo ma katalog data/<zrodlo>/ z plikiem manifest.json i plikami
JSONL (jeden rekord na linie). Rekord ma wspolna koperte (Record) i pola
wlasne zrodla w `attributes`; kazde zrodlo zaweza ja swoim modelem
(sources/<zrodlo>/dataset.py). Wczytanie sprawdza manifest i kazdy rekord,
a blad wskazuje plik i linie - scraper dowiaduje sie od razu, co poprawic.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from .citations import http_url

FORMAT_VERSION = 1
MANIFEST = "manifest.json"


class DatasetError(ValueError):
    """Zbior danych niezgodny z formatem (z plikiem i linia, gdy dotyczy rekordu)."""


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    format_version: int
    # kiedy dane zostaly zebrane (czas UTC ze strefa)
    collected_at: datetime
    # kto je zebral: scraper i jego wersja, np. "pipeline/scrapers/usos@abc123"
    collector: str = ""
    # pliki JSONL z rekordami, wzgledem katalogu zbioru
    files: list[str] = Field(min_length=1)

    @field_validator("collected_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("collected_at musi miec strefe czasowa")
        return value

    @field_validator("files")
    @classmethod
    def _relative(cls, files: list[str]) -> list[str]:
        for name in files:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or path.suffix != ".jsonl":
                raise ValueError(f"plik {name!r}: tylko wzgledna sciezka .jsonl wewnatrz zbioru")
        return files


class Record(BaseModel):
    """Wspolna koperta rekordu; zrodla zawezaja `kind` i `attributes`."""

    model_config = ConfigDict(extra="forbid")

    # staly identyfikator w obrebie zrodla (adres, id z USOS, sciezka pliku)
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    title: str = ""
    url: str | None = None
    # jezyk tresci (pl, en); None = nieznany
    lang: str | None = None
    # data zmiany w zrodle, jesli zrodlo ja podaje
    updated_at: datetime | None = None
    # tresc w Markdownie (naglowki #, listy, tabele); pusto dla rekordow bez tekstu
    content: str = ""

    @field_validator("url")
    @classmethod
    def _http(cls, value: str | None) -> str | None:
        if value is not None and http_url(value) is None:
            raise ValueError("url musi byc adresem http(s)")
        return value


R = TypeVar("R", bound=Record)

# Model rekordu zrodla: klasa rekordu albo TypeAdapter unii rekordow rozroznianych
# po `kind` (zrodlo z kilkoma rodzajami rekordow o roznych `attributes`, np. usos).
RecordModel = type[Record] | TypeAdapter[Any]


def record_adapter(model: RecordModel) -> TypeAdapter[Any]:
    return model if isinstance(model, TypeAdapter) else TypeAdapter(model)


@dataclass(frozen=True)
class Dataset(Generic[R]):
    directory: Path
    manifest: Manifest
    records: list[R]


def _validation_message(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '(rekord)'}: {e['msg']}" for e in error.errors()
    )


def read_dataset(directory: Path, source: str, record_model: RecordModel) -> Dataset[Any] | None:
    """Zbior z katalogu; None, gdy nie ma manifestu (zrodlo bez danych).

    Raises:
        DatasetError: manifest albo rekord niezgodny z formatem, zle zrodlo
            lub wersja formatu, powtorzone id.
    """
    manifest_path = directory / MANIFEST
    if not manifest_path.is_file():
        return None
    try:
        manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except ValidationError as error:
        raise DatasetError(f"{manifest_path}: {_validation_message(error)}") from None
    if manifest.source != source:
        raise DatasetError(f"{manifest_path}: zbior zrodla {manifest.source!r}, oczekiwano {source!r}")
    if manifest.format_version != FORMAT_VERSION:
        raise DatasetError(
            f"{manifest_path}: wersja formatu {manifest.format_version}, obslugiwana {FORMAT_VERSION}"
        )

    adapter = record_adapter(record_model)
    records: list[Record] = []
    seen: set[str] = set()
    for name in manifest.files:
        path = directory / name
        if not path.is_file():
            raise DatasetError(f"{path}: brak pliku wymienionego w manifescie")
        # tylko "\n" konczy rekord - splitlines() dzielilby tez na U+2028 i NEL,
        # ktore JSON dopuszcza wewnatrz napisow
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
            if not line.strip():
                continue
            try:
                record = adapter.validate_json(line)
            except ValidationError as error:
                raise DatasetError(f"{path}:{number}: {_validation_message(error)}") from None
            if record.id in seen:
                raise DatasetError(f"{path}:{number}: powtorzone id {record.id!r}")
            seen.add(record.id)
            records.append(record)
    return Dataset(directory, manifest, records)


def write_dataset(
    directory: Path,
    source: str,
    records: Iterable[Record],
    collector: str = "",
    collected_at: datetime | None = None,
    file_name: str = "records.jsonl",
) -> Manifest:
    """Zapisuje zbior (manifest + jeden plik JSONL); dla scraperow w Pythonie
    i adapterow starych formatow."""
    directory.mkdir(parents=True, exist_ok=True)
    # najpierw pliki tymczasowe, potem podmiana (os.replace jest atomowe) - zapis
    # przerwany w trakcie zostawia poprzedni zbior bez zmian
    records_path = directory / file_name
    records_tmp = records_path.with_name(records_path.name + ".tmp")
    with records_tmp.open("w", encoding="utf-8") as out:
        for record in records:
            out.write(record.model_dump_json(exclude_defaults=True) + "\n")
    manifest = Manifest(
        source=source,
        format_version=FORMAT_VERSION,
        collected_at=collected_at or datetime.now(timezone.utc),
        collector=collector,
        files=[file_name],
    )
    manifest_tmp = directory / (MANIFEST + ".tmp")
    manifest_tmp.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(records_tmp, records_path)
    os.replace(manifest_tmp, directory / MANIFEST)
    return manifest


def json_schemas(models: Sequence[tuple[str, RecordModel]]) -> dict[str, dict]:
    """Schematy JSON (manifest i rekord kazdego zrodla) dla scraperow w innych jezykach."""
    schemas = {"manifest": Manifest.model_json_schema()}
    for name, model in models:
        schemas[name] = record_adapter(model).json_schema()
    return schemas
