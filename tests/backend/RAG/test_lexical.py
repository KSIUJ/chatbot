"""
Testy lexical.py - indeks BM25 (SQLite FTS5) uzywany rownolegle z vectorstore.
"""

from RAG.ingest.schema import Document
from RAG.lexical import LexicalIndex, fold, tokenize


def _doc(id_, source, text):
    return Document(
        id=id_, source=source, embed_text=text, content_type="text", value=text, metadata={}
    )


def _make_index(tmp_path):
    return LexicalIndex(db_path=str(tmp_path / "lexical.db"))


def test_fold_maps_polish_letters_including_l():
    assert fold("Sławomir Kołodziej") == "Slawomir Kolodziej"
    assert tokenize("Rafał KAWA") == ["rafal", "kawa"]


def test_search_finds_document_by_rare_token(tmp_path):
    index = _make_index(tmp_path)
    index.add_documents(
        [
            _doc("usos_1", "usos", "dr Rafał Kawa\nStanowisko: starszy wykladowca"),
            _doc("usos_2", "usos", "dr Jan Kowalski\nStanowisko: adiunkt"),
        ]
    )

    assert index.search(["kawa"], ("usos",), limit=5) == ["usos_1"]


def test_search_matches_without_polish_letters(tmp_path):
    index = _make_index(tmp_path)
    index.add_documents([_doc("usos_1", "usos", "dr Sławomir Kołodziej\nStanowisko: profesor")])

    assert index.search(tokenize("Slawomir Kolodziej"), ("usos",), limit=5) == ["usos_1"]


def test_search_respects_source_filter(tmp_path):
    index = _make_index(tmp_path)
    index.add_documents(
        [
            _doc("usos_1", "usos", "dr Rafał Kawa\nStanowisko: starszy wykladowca"),
            _doc("mordor_1", "mordor", "Wstep do informatyki, Rafał Kawa, zadanie 5"),
        ]
    )

    assert index.search(["kawa"], ("usos",), limit=5) == ["usos_1"]
    assert index.search(["kawa"], ("mordor",), limit=5) == ["mordor_1"]
    assert len(index.search(["kawa"], ("usos", "mordor"), limit=5)) == 2


def test_title_column_outranks_match_buried_in_body(tmp_path):
    index = _make_index(tmp_path)
    filler = "tekst wypelniajacy akapit " * 40
    index.add_documents(
        [
            _doc("usos_1", "usos", "dr hab. Maciej Ulas\nStanowisko: profesor uczelni\n" + filler),
            _doc("strony_1", "strony", "Regulamin studiow\n" + filler + " tutor: Maciej Ulas " + filler),
        ]
    )

    assert index.search(["maciej", "ulas"], ("usos", "strony"), limit=5)[0] == "usos_1"


def test_add_documents_is_idempotent(tmp_path):
    index = _make_index(tmp_path)
    doc = _doc("usos_1", "usos", "dr Rafał Kawa\nStanowisko: starszy wykladowca")

    index.add_documents([doc])
    index.add_documents([doc])

    assert index.count() == 1
    assert index.count("usos") == 1
    assert index.count("mordor") == 0
