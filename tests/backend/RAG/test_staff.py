"""
Testy staff.py - wyszukiwarka pracownikow (BM25 zawezony do zrodla usos)
wraz z bramka slownikowa decydujaca, czy zapytanie dotyczy pracownika.
"""

from RAG.ingest.schema import Document
from RAG.lexical import LexicalIndex
from RAG.staff import StaffIndex

PEOPLE = {
    "usos_kawa": ("Rafał Kawa", "dr Rafał Kawa\nStanowisko: starszy wykladowca\nPokoj: 2168"),
    "usos_ulas": ("Maciej Ulas", "dr hab. Maciej Ulas\nStanowisko: profesor uczelni\nPokoj: 3121"),
    "usos_klis": ("Kamila Kliś-Garlicka", "dr Kamila Kliś-Garlicka\nStanowisko: adiunkt"),
    "usos_micek": ("Piotr Micek", "dr hab. Piotr Micek\nStanowisko: profesor uczelni"),
    "usos_krawiec": ("Miłosz Krawiec", "mgr Miłosz Krawiec\nStanowisko: doktorant"),
}


def _make_staff(tmp_path):
    index = LexicalIndex(db_path=str(tmp_path / "lexical.db"))
    index.add_documents(
        [
            Document(
                id=doc_id, source="usos", embed_text=text, content_type="text",
                value=text, metadata={"employee_name": name},
            )
            for doc_id, (name, text) in PEOPLE.items()
        ]
    )
    index.add_documents(
        [
            Document(
                id="mordor_1", source="mordor",
                embed_text="Kolokwium z analizy, prowadzi Rafał Kawa, sala 0004",
                content_type="text", value="...", metadata={},
            )
        ]
    )
    return StaffIndex([name for name, _ in PEOPLE.values()], index)


def test_lookup_finds_employee_by_full_name(tmp_path):
    assert _make_staff(tmp_path).lookup("Rafał Kawa") == ["usos_kawa"]


def test_lookup_ignores_surrounding_question_words(tmp_path):
    staff = _make_staff(tmp_path)

    assert staff.lookup("jakie dyzury ma Rafał Kawa")[0] == "usos_kawa"
    assert staff.lookup("gdzie jest pokoj Macieja Ulasa")[0] == "usos_ulas"


def test_lookup_works_without_polish_letters(tmp_path):
    assert _make_staff(tmp_path).lookup("rafal kawa") == ["usos_kawa"]


def test_lookup_handles_hyphenated_surname(tmp_path):
    assert _make_staff(tmp_path).lookup("Kamila Kliś-Garlicka")[0] == "usos_klis"


def test_gate_returns_nothing_for_unrelated_question(tmp_path):
    staff = _make_staff(tmp_path)

    assert staff.lookup("kiedy zaczyna sie sesja egzaminacyjna") == []
    assert staff.lookup("Zasady przyznawania miejsc w domach studenckich") == []
    assert staff.lookup("co to jest rekurencja") == []


def test_lookup_never_returns_documents_from_other_sources(tmp_path):
    assert "mordor_1" not in _make_staff(tmp_path).lookup("Rafał Kawa", limit=5)


def test_lookup_handles_declension_by_suffix(tmp_path):
    staff = _make_staff(tmp_path)

    assert staff.lookup("dyzury Ulasa")[0] == "usos_ulas"
    assert staff.lookup("kontakt z Kawą")[0] == "usos_kawa"


def test_lookup_handles_fleeting_e_declension(tmp_path):
    staff = _make_staff(tmp_path)

    assert staff.lookup("gabinet Micka")[0] == "usos_micek"
    assert staff.lookup("rozmowa z Krawcem")[0] == "usos_krawiec"
