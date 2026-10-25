"""
Zbiory danych zrodel (core/datasets.py, rag/DATASETS.md): format i jego
sprawdzanie, adaptery starych wyjsc scraperow (sources/*/legacy.py),
rekordy -> dokumenty indeksu i notatki o KSI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.backend.rag import datasets_cli
from src.backend.rag.core import chunking
from src.backend.rag.core.datasets import DatasetError, read_dataset, write_dataset
from src.backend.rag.core.documents import make_id
from src.backend.rag.registry import create_sources
from src.backend.rag.sources.ksi import KsiSource
from src.backend.rag.sources.ksi.notes import read_notes
from src.backend.rag.sources.mordor.dataset import MaterialAttributes, MaterialRecord
from src.backend.rag.sources.mordor.documents import material_documents
from src.backend.rag.sources.uj_pages import legacy as uj_legacy
from src.backend.rag.sources.uj_pages.dataset import PageAttributes, PageRecord
from src.backend.rag.sources.uj_pages.documents import page_documents
from src.backend.rag.sources.usos.dataset import Position, Room, StaffAttributes, StaffRecord
from src.backend.rag.sources.usos.documents import staff_document

REPO = Path(__file__).resolve().parents[3]

SCRAPED = (
    "\n\nURL: https://matinf.uj.edu.pl/a\n\nDziekanat czynny pon-pt."
    "\n\nURL: https://matinf.uj.edu.pl/pusta\n\n   "
    "\n\nURL: https://nkr.si/b\n\nKolo naukowe."
    "\n\nURL: https://matinf.uj.edu.pl/documents/41633/1/urlop+dzieka%C5%84ski.pdf/abc\n\nWniosek o urlop."
    "\n\nURL: https://kmsuj.matinf.uj.edu.pl/workshop/contact/en\n\nContact."
)


def _page(url="https://matinf.uj.edu.pl/a", content="Tresc."):
    return PageRecord(
        id=url, kind="page", url=url, content=content,
        attributes=PageAttributes(site="matinf.uj.edu.pl", category="faculty"),
    )


def test_splitter_keeps_chunk_parameters():
    splitter = chunking.make_splitter()

    assert (chunking.CHUNK_SIZE, chunking.CHUNK_OVERLAP) == (1000, 200)
    assert all(len(chunk) <= 1000 for chunk in splitter.split_text("slowo " * 1000))


# --- format -----------------------------------------------------------------------

def test_dataset_round_trip(tmp_path):
    collected = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    write_dataset(tmp_path, "uj_pages", [_page()], collector="test", collected_at=collected)

    dataset = read_dataset(tmp_path, "uj_pages", PageRecord)

    assert dataset is not None
    assert dataset.manifest.collected_at == collected
    assert dataset.records == [_page()]


def test_missing_dataset_is_none(tmp_path):
    assert read_dataset(tmp_path, "uj_pages", PageRecord) is None


def _manifest(tmp_path, **changes):
    manifest = {"source": "uj_pages", "format_version": 1, "collected_at": "2026-10-11T08:00:00Z", "files": ["records.jsonl"]}
    manifest.update(changes)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source": "usos"}, "oczekiwano 'uj_pages'"),
        ({"format_version": 2}, "wersja formatu 2"),
        ({"collected_at": "2026-10-11T08:00:00"}, "strefe"),
        ({"files": ["../poza.jsonl"]}, "wzgledna"),
        ({"files": ["brak.jsonl"]}, "brak pliku"),
        ({"extra": 1}, "extra"),
    ],
)
def test_invalid_manifest_is_rejected(tmp_path, changes, message):
    (tmp_path / "records.jsonl").write_text("", encoding="utf-8")
    _manifest(tmp_path, **changes)

    with pytest.raises(DatasetError, match=message):
        read_dataset(tmp_path, "uj_pages", PageRecord)


def test_invalid_record_points_at_file_and_line(tmp_path):
    good = _page().model_dump_json()
    bad = json.loads(_page("https://a.pl/b").model_dump_json())
    bad["attributes"]["category"] = "blog"
    (tmp_path / "records.jsonl").write_text(f"{good}\n\n{json.dumps(bad)}\n", encoding="utf-8")
    _manifest(tmp_path)

    with pytest.raises(DatasetError, match=r"records.jsonl:3: attributes.category"):
        read_dataset(tmp_path, "uj_pages", PageRecord)


@pytest.mark.parametrize(
    "change",
    [{"url": "javascript:alert(1)"}, {"surprise": True}, {"id": ""}, {"kind": "video"}],
)
def test_record_rules(tmp_path, change):
    record = json.loads(_page().model_dump_json()) | change
    (tmp_path / "records.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    _manifest(tmp_path)

    with pytest.raises(DatasetError):
        read_dataset(tmp_path, "uj_pages", PageRecord)


def test_duplicate_ids_are_rejected(tmp_path):
    line = _page().model_dump_json()
    (tmp_path / "records.jsonl").write_text(f"{line}\n{line}\n", encoding="utf-8")
    _manifest(tmp_path)

    with pytest.raises(DatasetError, match="powtorzone id"):
        read_dataset(tmp_path, "uj_pages", PageRecord)


# --- uj_pages ---------------------------------------------------------------------

def test_legacy_pages_become_records(tmp_path):
    (tmp_path / "strony").mkdir()
    (tmp_path / "strony" / "website_data.txt").write_text(SCRAPED, encoding="utf-8")

    records = {r.url: r for r in uj_legacy.convert(tmp_path)}

    assert list(records) == [
        "https://matinf.uj.edu.pl/a",
        "https://nkr.si/b",
        "https://matinf.uj.edu.pl/documents/41633/1/urlop+dzieka%C5%84ski.pdf/abc",
        "https://kmsuj.matinf.uj.edu.pl/workshop/contact/en",
    ]
    page = records["https://matinf.uj.edu.pl/a"]
    assert (page.kind, page.attributes.category, page.lang, page.content) == ("page", "faculty", "pl", "Dziekanat czynny pon-pt.")
    assert (page.title, page.attributes.breadcrumbs) == ("A", ["A"])
    group = records["https://nkr.si/b"]
    assert (group.attributes.category, group.attributes.breadcrumbs) == ("student_group", ["nkr.si", "B"])
    pdf = records["https://matinf.uj.edu.pl/documents/41633/1/urlop+dzieka%C5%84ski.pdf/abc"]
    assert (pdf.kind, pdf.attributes.media_type, pdf.title) == ("document", "application/pdf", "Urlop dziekański")
    workshop = records["https://kmsuj.matinf.uj.edu.pl/workshop/contact/en"]
    assert (workshop.lang, workshop.attributes.breadcrumbs) == ("en", ["kmsuj.matinf.uj.edu.pl", "Workshop", "Contact"])


def test_legacy_pages_old_file_name_duplicates_and_missing(tmp_path):
    assert uj_legacy.convert(tmp_path) is None

    (tmp_path / "strony").mkdir()
    (tmp_path / "strony" / "webiste_data.txt").write_text(
        "\n\nURL: https://a.uj.edu.pl/x\n\nstara\n\nURL: https://a.uj.edu.pl/x\n\nnowa", encoding="utf-8"
    )

    (record,) = uj_legacy.convert(tmp_path)
    assert record.content == "nowa"
    assert record.attributes.category == "uj"


def test_page_documents_keep_ids_and_metadata():
    (document,) = page_documents("uj_pages", [_page(content="Dziekanat czynny pon-pt.")])

    assert document.id == make_id("uj_pages", "https://matinf.uj.edu.pl/a", "0")
    assert document.value == document.embed_text == "Dziekanat czynny pon-pt."
    assert document.metadata == {
        "url": "https://matinf.uj.edu.pl/a", "domain": "matinf.uj.edu.pl", "category": "faculty", "title": "",
        "section": "", "chunk_index": 0,
    }


def test_page_documents_start_with_breadcrumbs_title_and_section():
    url = "https://matinf.uj.edu.pl/o-nas/biblioteka"
    record = PageRecord(
        id=url, kind="page", url=url, title="Biblioteka",
        content="Wstep.\n\n## Godziny otwarcia\n\npon-pt 9-17\n\n## Kontakt\n\n" + "tel. 12 664 " * 120,
        attributes=PageAttributes(site="matinf.uj.edu.pl", category="faculty", breadcrumbs=["O nas", "Biblioteka"]),
    )

    documents = page_documents("uj_pages", [record])

    first, *rest = documents
    assert first.value == first.embed_text
    assert first.value.startswith("O nas › Biblioteka\nWstep.")
    assert "## Godziny otwarcia\n\npon-pt 9-17" in first.value
    assert rest and all(d.value.startswith("O nas › Biblioteka › Kontakt\ntel.") for d in rest)
    assert [d.metadata["section"] for d in documents] == ["", *["Kontakt"] * len(rest)]
    assert [d.metadata["chunk_index"] for d in documents] == list(range(len(documents)))


# --- usos --------------------------------------------------------------------------

EMPLOYEE = StaffRecord(
    id="12345",
    kind="staff",
    title="Jan Kowalski",
    url="https://usosweb.uj.edu.pl/kontroler.php?_action=katalog2/osoby/pokazOsobe&os_id=12345",
    attributes=StaffAttributes(
        usos_id="12345",
        first_name="Jan",
        last_name="Kowalski",
        titles_before="dr hab.",
        titles_after="prof. UJ",
        positions=[Position(name="adiunkt", unit="WMiI"), Position(name="kierownik")],
        room=Room(number="2144", building="Łojasiewicza 6"),
        office_hours="wtorek 10-12",
        interests="analiza",
        phones=["12 664 00 00"],
    ),
)


def test_staff_card_text():
    document = staff_document("usos", EMPLOYEE)

    # ten sam tekst karty co przed zmiana formatu; do wyszukiwania z dopelniaczem
    card = (
        "dr hab. prof. UJ Jan Kowalski\n"
        "Stanowisko: adiunkt (WMiI); kierownik\n"
        "Pokoj: pokój 2144, Łojasiewicza 6\n"
        "Dyzury: wtorek 10-12\n"
        "E-mail: brak danych w USOS\n"
        "Telefon: 12 664 00 00\n"
        "Zainteresowania: analiza"
    )
    assert document.value == card
    assert document.embed_text == card + "\nOdmiana: Jana Kowalskiego"
    assert document.id == make_id("usos", "12345")
    assert document.metadata["employee_name"] == "Jan Kowalski"
    assert document.metadata["kind"] == "staff"
    assert document.metadata["profile_url"] == EMPLOYEE.url


def test_usos_has_no_legacy_format(tmp_path):
    staff_dir = tmp_path / "usos" / "staff"
    staff_dir.mkdir(parents=True)
    (staff_dir / "staff_UJ.WMI_20260906T102458Z.json").write_text("[]", encoding="utf-8")

    assert create_sources()["usos"].convert_legacy(tmp_path) is None


# --- mordor ------------------------------------------------------------------------

def _material(path, kind, content=""):
    file_type = path.rsplit(".", 1)[1]
    return MaterialRecord(id=path, kind=kind, content=content, attributes=MaterialAttributes(path=path, file_type=file_type))


def test_material_documents(tmp_path):
    directory = tmp_path / "mordor"
    image, text = material_documents(
        "mordor", directory, [_material("mapy/plan_budynku-A.png", "image"), _material("Analiza/notatki.pdf", "text", "Calki.")]
    )

    assert image.embed_text == "mapy plan budynku A"
    assert image.value == (directory / "mapy/plan_budynku-A.png").as_posix()
    assert image.content_type == "image"
    assert (text.value, text.metadata["source_file"], text.metadata["file_type"]) == ("notatki.pdf\nCalki.", "notatki.pdf", ".pdf")


@pytest.mark.parametrize("path", ["/etc/passwd", "../poza.pdf", "a\\b.pdf"])
def test_material_paths_stay_inside_the_dataset(path):
    with pytest.raises(ValueError):
        MaterialAttributes(path=path, file_type="pdf")


# --- ksi ---------------------------------------------------------------------------

NOTE = """---
title: Jak dołączyć do KSI
updated: 2026-10-01
tags: [członkostwo]
url: https://ksi.ii.uj.edu.pl/
---

Przyjdź na spotkanie.
"""


def test_notes_are_read_and_drafts_templates_and_readme_skipped(tmp_path):
    (tmp_path / "dolaczanie.md").write_text(NOTE, encoding="utf-8")
    (tmp_path / "szkic.md").write_text("---\ntitle: Szkic\ndraft: true\n---\nTresc", encoding="utf-8")
    (tmp_path / "_szablon.md").write_text("bez naglowka", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Instrukcja", encoding="utf-8")

    (note,) = read_notes(tmp_path)

    assert (note.id, note.title, note.url, note.content) == ("dolaczanie", "Jak dołączyć do KSI", "https://ksi.ii.uj.edu.pl/", "Przyjdź na spotkanie.")
    assert note.updated_at == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert note.attributes.tags == ["członkostwo"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Tresc bez naglowka", "brak naglowka"),
        ("---\ntitle: A\n", "niezamkniety"),
        ("---\ntitle: A\nautor: B\n---\nTresc", "nieznane pola"),
        ("---\nupdated: 2026-01-01\n---\nTresc", "brak tytulu"),
        ("---\ntitle: A\n---\n", "pusta tresc"),
        ("---\ntitle: A\nurl: ftp://x\n---\nTresc", "http"),
    ],
)
def test_invalid_notes_are_rejected(tmp_path, text, message):
    (tmp_path / "notatka.md").write_text(text, encoding="utf-8")

    with pytest.raises(DatasetError, match=message):
        read_notes(tmp_path)


def test_ksi_source_indexes_pages_and_notes(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "dolaczanie.md").write_text(NOTE, encoding="utf-8")
    page = PageRecord(
        id="https://ksi.ii.uj.edu.pl/o-nas", kind="page", url="https://ksi.ii.uj.edu.pl/o-nas", content="O kole.",
        attributes=PageAttributes(site="ksi.ii.uj.edu.pl", category="ksi"),
    )
    write_dataset(tmp_path / "data" / "ksi", "ksi", [page])

    documents = KsiSource(notes_dir=notes).load_documents(tmp_path / "data")

    assert [d.value for d in documents] == ["O kole.", "Jak dołączyć do KSI\nPrzyjdź na spotkanie."]
    assert all(d.source == "ksi" for d in documents)
    assert documents[1].metadata["title"] == "Jak dołączyć do KSI"


def test_repository_notes_are_valid():
    read_notes()


# --- CLI i schematy ----------------------------------------------------------------

def test_convert_writes_datasets_that_ingest_reads(tmp_path):
    (tmp_path / "strony").mkdir()
    (tmp_path / "strony" / "website_data.txt").write_text(SCRAPED, encoding="utf-8")

    summary = datasets_cli.convert(tmp_path, list(create_sources()))

    assert summary == {"uj_pages": 4}
    documents = create_sources()["uj_pages"].load_documents(tmp_path)
    assert {d.metadata["url"] for d in documents} >= {"https://matinf.uj.edu.pl/a", "https://nkr.si/b"}
    assert datasets_cli.check(tmp_path, ["uj_pages", "usos", "mordor"])


def test_check_reports_invalid_datasets(tmp_path):
    (tmp_path / "usos").mkdir()
    (tmp_path / "usos" / "manifest.json").write_text("{}", encoding="utf-8")

    assert not datasets_cli.check(tmp_path, ["usos"])


def test_committed_json_schemas_match_the_models(tmp_path):
    datasets_cli.schemas(tmp_path)

    committed = REPO / "docs" / "datasets"
    generated = sorted(p.name for p in tmp_path.iterdir())
    assert generated == sorted(p.name for p in committed.glob("*.schema.json"))
    for name in generated:
        assert (tmp_path / name).read_text(encoding="utf-8") == (committed / name).read_text(encoding="utf-8"), name
