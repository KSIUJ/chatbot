"""
Testy staff.py - wyszukiwarka pracownikow (BM25 zawezony do zrodla usos)
wraz z bramka slownikowa decydujaca, czy zapytanie dotyczy pracownika.
"""

import pytest

from src.backend.rag.core.documents import Document
from src.backend.rag.core.lexical import LexicalIndex
from src.backend.rag.sources.usos.staff import StaffIndex

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


# --- odmiana imion i nazwisk (names.py) ------------------------------------------

DECLINED = {
    "usos_cyranka": ("Jacek Cyranka", "dr Jacek Cyranka"),
    "usos_herman": ("Grzegorz Herman", "dr Grzegorz Herman"),
    "usos_czyz": ("Rafał Czyż", "prof. Rafał Czyż"),
    "usos_debecki": ("Jacek Dębecki", "dr Jacek Dębecki"),
    "usos_cygan": ("Ewa Cygan", "dr Ewa Cygan"),
    "usos_bialas": ("Leokadia Białas-Cież", "dr hab. Leokadia Białas-Cież"),
    "usos_zygadlo": ("Jakub Zygadło", "dr Jakub Zygadło"),
    "usos_stepien": ("Kamil Stępień", "mgr Kamil Stępień"),
    "usos_lewandowska": ("Barbara Lewandowska", "dr Barbara Lewandowska"),
    "usos_pogoda": ("Piotr Pogoda", "dr Piotr Pogoda"),
    "usos_tutaj": ("Halszka Tutaj-Gasińska", "dr Halszka Tutaj-Gasińska"),
    "usos_wiek": ("Joanna Świebocka-Więk", "dr Joanna Świebocka-Więk"),
}


def _declined_staff(tmp_path):
    index = LexicalIndex(db_path=str(tmp_path / "lexical.db"))
    index.add_documents(
        [
            Document(id=doc_id, source="usos", embed_text=text, content_type="text", value=text, metadata={})
            for doc_id, (_, text) in DECLINED.items()
        ]
    )
    return StaffIndex([name for name, _ in DECLINED.values()], index)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Kiedy mogę złapać dr. Jacka Cyrankę?", "usos_cyranka"),
        ("rozmawialam z Cyranką", "usos_cyranka"),
        ("Gdzie znajdę dr. Grzegorza Hermana?", "usos_herman"),
        ("o Hermanie mówią, że", "usos_herman"),
        ("dyżury Rafała Czyża", "usos_czyz"),
        ("Dyżury Dębeckiego", "usos_debecki"),
        ("konsultacje u Dębeckiemu", "usos_debecki"),
        ("dyżury Ewy Cygan", "usos_cygan"),
        ("kontakt z Leokadią Białas-Cież", "usos_bialas"),
        ("Gdzie znajdę kierownika studiów, dr. Zygadło?", "usos_zygadlo"),
        ("pokój Kamila Stępnia", "usos_stepien"),
        ("dyżur dr Lewandowskiej", "usos_lewandowska"),
        ("dr Pogoda", "usos_pogoda"),
        ("dr Tutaj-Gasińska", "usos_tutaj"),
    ],
)
def test_lookup_handles_polish_declension(tmp_path, query, expected):
    assert _declined_staff(tmp_path).lookup(query)[0] == expected


@pytest.mark.parametrize(
    "query",
    [
        "jaka jest jutro pogoda",
        "czy tutaj jest biblioteka",
        "w której sali jest egzamin",
        "historia wydziału w XX wieku",
        "gdzie kupić kawę",
        "jak dojechać na kampus",
    ],
)
def test_lookup_ignores_ordinary_words_resembling_names(tmp_path, query):
    assert _declined_staff(tmp_path).lookup(query) == []


def test_female_consonant_surnames_are_indeclinable(tmp_path):
    # "Cygana" to forma nazwiska meskiego - nazwisko Ewy Cygan sie nie odmienia
    assert _declined_staff(tmp_path).lookup("dyżury dr Cygana") == []
