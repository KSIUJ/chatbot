"""
Testy retriever.py - retrieve_split/retrieve_staff na realnej ChromaDB i FTS5,
z FakeEncoder (fixture fake_encoder, patrz conftest.py) zamiast modelu.
"""

from src.backend.rag.lexical import LexicalIndex
from src.backend.rag.retriever import Retriever
from src.backend.rag.schema import Document
from src.backend.rag.vectorstore import VectorStore


def _doc(id_, source, text, value=None, metadata=None):
    return Document(
        id=id_,
        source=source,
        embed_text=text,
        content_type="text",
        value=value or text,
        metadata=metadata or {},
    )


def _make_store(tmp_path, encoder):
    return VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=encoder)


def test_retrieve_split_returns_matching_official_document(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    store.add_documents(
        [
            _doc(
                "strony_1",
                "strony",
                "godziny otwarcia dziekanatu wydzialu",
                value="Dziekanat czynny pon-pt 8-15.",
                metadata={"url": "https://matinf.uj.edu.pl/dziekanat"},
            )
        ]
    )
    retriever = Retriever(encoder=fake_encoder, vectorstore=store, lexical=LexicalIndex(str(tmp_path / "lex.db")))

    groups = retriever.retrieve_split("godziny otwarcia dziekanatu", k_mordor=3, k_other=3)

    assert groups["mordor"] == []
    assert len(groups["other"]) == 1
    assert groups["other"][0]["source"] == "strony"
    assert groups["other"][0]["value"] == "Dziekanat czynny pon-pt 8-15."


def test_retrieve_split_respects_k(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    store.add_documents([_doc(f"usos_{i}", "usos", f"pracownik numer {i} dyzury") for i in range(5)])
    retriever = Retriever(encoder=fake_encoder, vectorstore=store, lexical=LexicalIndex(str(tmp_path / "lex.db")))

    groups = retriever.retrieve_split("pracownik dyzury", k_mordor=2, k_other=2)

    assert len(groups["other"]) == 2


def test_retrieve_returns_empty_when_store_and_index_empty(tmp_path, fake_encoder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    retriever = Retriever(encoder=fake_encoder, vectorstore=_make_store(tmp_path, fake_encoder))

    assert retriever.retrieve_split("cokolwiek") == {"mordor": [], "other": []}
    assert retriever.retrieve_staff("Rafal Kawa") == []


def _ingest(store, documents):
    store.add_documents(documents)
    LexicalIndex().add_documents(documents)


KAWA = _doc(
    "usos_kawa",
    "usos",
    "dr Rafał Kawa\nStanowisko: starszy wykladowca",
    metadata={"employee_name": "Rafał Kawa"},
)


def test_empty_indexes_are_loaded_once_they_get_data(tmp_path, fake_encoder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = _make_store(tmp_path, fake_encoder)
    retriever = Retriever(encoder=fake_encoder, vectorstore=store, reload_interval=0)

    assert retriever.retrieve_staff("Rafał Kawa") == []

    _ingest(store, [KAWA])

    assert [h["id"] for h in retriever.retrieve_staff("Rafał Kawa")] == ["usos_kawa"]


def test_empty_index_reload_is_throttled(tmp_path, fake_encoder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = _make_store(tmp_path, fake_encoder)
    retriever = Retriever(encoder=fake_encoder, vectorstore=store, reload_interval=3600)

    assert retriever.retrieve_staff("Rafał Kawa") == []
    _ingest(store, [KAWA])

    assert retriever.retrieve_staff("Rafał Kawa") == []
