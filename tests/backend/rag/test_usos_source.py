"""
Zrodlo usos z rekordami wielu rodzajow (sources/usos/): wczytanie zbioru
z unia rodzajow, fragmenty z linia kontekstu, podpisy i zrodla odpowiedzi,
a wyszukiwanie pracownika zwraca tylko karty.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from src.backend.rag.core.datasets import DatasetError, read_dataset, write_dataset
from src.backend.rag.sources.usos import UsosSource
from src.backend.rag.sources.usos.dataset import (
    USOS_RECORD,
    CourseAttributes,
    CourseRecord,
    NewsAttributes,
    NewsRecord,
    PageAttributes,
    PageRecord,
    StaffAttributes,
    StaffRecord,
)
from src.backend.rag.sources.usos.staff import StaffIndex

COURSE = CourseRecord(
    id="course:WMI.II-AM1-O",
    kind="course",
    title="Analiza matematyczna 1 (WMI.II-AM1-O)",
    url="https://www.usosweb.uj.edu.pl/kontroler.php?_action=katalog2/przedmioty/pokazPrzedmiot&prz_kod=WMI.II-AM1-O",
    content=(
        "# Analiza matematyczna 1 (WMI.II-AM1-O)\n\n## Informacje\n\n- Punkty ECTS: 8\n\n"
        "## Zajęcia: Semestr zimowy 2026/2027\n\n### Wykład\n\n- grupa 1: dr Jan Kowalski; wtorek 10:00–12:00"
    ),
    attributes=CourseAttributes(
        course_id="WMI.II-AM1-O", term_ids=["26/27Z"], ects=8.0, lecturers=["dr Jan Kowalski"]
    ),
)
NEWS = NewsRecord(
    id="news:77",
    kind="news",
    title="Wnioski o stypendium rektora",
    url="https://www.usosweb.uj.edu.pl/kontroler.php?_action=news/default",
    updated_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    content="# Wnioski o stypendium rektora\n\nOpublikowano: 01.10.2026\n\nWnioski do 15 października.",
    attributes=NewsAttributes(news_id="77", category="Stypendia", expiry_date=date(2026, 10, 15)),
)
PAGE = PageRecord(
    id="https://www.usosweb.uj.edu.pl/kontroler.php?_action=news/kontakt",
    kind="page",
    url="https://www.usosweb.uj.edu.pl/kontroler.php?_action=news/kontakt",
    title="Kontakt z administratorem USOSweb",
    content="# Kontakt z administratorem USOSweb\n\nAdres e-mail: usosweb@uj.edu.pl",
    attributes=PageAttributes(site="www.usosweb.uj.edu.pl", section="usosweb", breadcrumbs=["Kontakt"]),
)
STAFF = StaffRecord(
    id="12345",
    kind="staff",
    title="Jan Kowalski",
    attributes=StaffAttributes(usos_id="12345", first_name="Jan", last_name="Kowalski"),
)


def _write(tmp_path, records):
    write_dataset(tmp_path / "usos", "usos", records, collector="test@1")


def test_dataset_with_many_kinds_round_trips(tmp_path):
    _write(tmp_path, [STAFF, COURSE, NEWS, PAGE])

    dataset = read_dataset(tmp_path / "usos", "usos", USOS_RECORD)

    assert [type(r) for r in dataset.records] == [StaffRecord, CourseRecord, NewsRecord, PageRecord]
    assert dataset.records[1] == COURSE


def test_unknown_kind_and_kind_specific_fields_are_errors(tmp_path):
    _write(tmp_path, [STAFF])
    lines = [
        json.dumps({"id": "x", "kind": "exam", "content": "a", "attributes": {}}),
        # pole przedmiotu w artykule
        json.dumps({"id": "news:1", "kind": "news", "content": "a", "attributes": {"news_id": "1", "ects": 5}}),
        # rekord z trescia bez tresci
        json.dumps({"id": "course:A", "kind": "course", "attributes": {"course_id": "A"}}),
    ]
    for line in lines:
        (tmp_path / "usos" / "records.jsonl").write_text(line + "\n", encoding="utf-8")
        with pytest.raises(DatasetError, match="records.jsonl:1"):
            read_dataset(tmp_path / "usos", "usos", USOS_RECORD)


def test_entry_documents_carry_kind_context_and_metadata(tmp_path):
    _write(tmp_path, [STAFF, COURSE, NEWS])

    documents = UsosSource().load_documents(tmp_path)

    staff, *course, news = documents
    assert staff.metadata["kind"] == "staff"
    assert {d.metadata["kind"] for d in course} == {"course"}
    # male sekcje sa laczone w jeden fragment - naglowki zostaja w tekscie
    assert course[0].value.startswith("USOS › Przedmiot › Analiza matematyczna 1 (WMI.II-AM1-O)\n")
    assert "Zajęcia: Semestr zimowy 2026/2027" in course[0].value
    assert course[0].metadata["course_id"] == "WMI.II-AM1-O"
    assert course[0].metadata["lecturers"] == "dr Jan Kowalski"
    assert course[0].metadata["ects"] == 8.0
    assert news.metadata["expiry_date"] == "2026-10-15"
    assert news.metadata["updated_at"].startswith("2026-10-01")
    # metadane indeksu sa plaskie - bez list i None
    for document in documents:
        assert all(isinstance(v, (str, int, float, bool)) for v in document.metadata.values())
    # stabilne id: ponowny ingest nadpisuje zamiast duplikowac
    assert [d.id for d in documents] == [d.id for d in UsosSource().load_documents(tmp_path)]


def test_label_and_citation_per_kind(tmp_path):
    _write(tmp_path, [STAFF, PAGE])
    source = UsosSource()
    staff, page = ({"metadata": d.metadata} for d in source.load_documents(tmp_path))

    assert source.label(staff) == "Jan Kowalski"
    assert source.label(page) == "Kontakt z administratorem USOSweb"
    assert source.cite(page) == {"kind": "usos", "title": "Kontakt z administratorem USOSweb", "url": PAGE.url}
    # stary indeks: karty bez "kind"
    assert source.label({"metadata": {"employee_name": "Anna Nowak"}}) == "Anna Nowak"
    assert source.cite({"metadata": {"kind": "course"}}) is None


class _Lexical:
    def __init__(self, ids):
        self.ids = ids

    def search(self, tokens, sources, limit=5):
        return self.ids[:limit]


def test_staff_lookup_returns_only_staff_cards():
    index = StaffIndex(["Jan Kowalski"], _Lexical(["course_doc", "news_doc", "staff_doc"]), staff_ids={"staff_doc"})

    assert index.lookup("dyżury Jana Kowalskiego") == ["staff_doc"]


def test_staff_index_from_collection_skips_other_kinds():
    class Collection:
        def get(self, where, include):
            return {
                "ids": ["a", "b", "c"],
                "metadatas": [
                    {"kind": "staff", "employee_name": "Jan Kowalski"},
                    {"kind": "course", "title": "Analiza", "lecturers": "Anna Nowak"},
                    # indeks sprzed rodzajow - same karty
                    {"employee_name": "Ewa Cygan"},
                ],
            }

    index = StaffIndex.from_collection(Collection(), _Lexical([]))

    assert index.staff_ids == {"a", "c"}
    assert "nowak" not in index.surnames


def test_line_separators_inside_content_do_not_split_records(tmp_path):
    news = NEWS.model_copy(update={"content": "# Tytuł\n\nraz\u2028dwa\u2029trzy\x85cztery"})
    _write(tmp_path, [news])

    (record,) = read_dataset(tmp_path / "usos", "usos", USOS_RECORD).records

    assert record.content == news.content
    assert not list((tmp_path / "usos").glob("*.tmp"))
