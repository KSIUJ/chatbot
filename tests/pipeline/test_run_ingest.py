"""
Testy pipeline/ingest/run_ingest.py na atrapach vectorstore i indeksu FTS
(bez ChromaDB i modelu embeddingowego).
"""

from pipeline.ingest.run_ingest import run_ingest
from src.backend.rag.schema import Document


def _doc(id_: str, source: str = "usos") -> Document:
    return Document(id=id_, source=source, embed_text=id_, content_type="text", value=id_)


class FakeIndex:
    """Wspolna atrapa VectorStore/LexicalIndex: slownik id -> Document."""

    def __init__(self, documents: list[Document] | None = None):
        self.docs = {d.id: d for d in documents or []}

    def add_documents(self, documents: list[Document]) -> None:
        self.docs.update({d.id: d for d in documents})

    def filter_new(self, documents: list[Document]) -> list[Document]:
        return [d for d in documents if d.id not in self.docs]

    def delete_source(self, source: str) -> int:
        removed = [i for i, d in self.docs.items() if d.source == source]
        for doc_id in removed:
            del self.docs[doc_id]
        return len(removed)


def _run(loaders, existing=(), **kwargs):
    store, lexical = FakeIndex(list(existing)), FakeIndex(list(existing))
    summary = run_ingest(store=store, lexical=lexical, loaders=loaders, **kwargs)
    return summary, store, lexical


def test_summary_counts_only_added_documents():
    loaders = {"usos": lambda: [_doc("usos_1"), _doc("usos_2")]}

    summary, store, lexical = _run(loaders, existing=[_doc("usos_1")])

    assert summary == {"usos": 1}
    assert set(store.docs) == set(lexical.docs) == {"usos_1", "usos_2"}


def test_purge_replaces_source_and_counts_all_loaded():
    loaders = {"usos": lambda: [_doc("usos_new")]}

    summary, store, _ = _run(loaders, existing=[_doc("usos_old"), _doc("strony_1", "strony")], purge=True)

    assert summary == {"usos": 1}
    assert set(store.docs) == {"usos_new", "strony_1"}


def test_purge_keeps_existing_data_when_loader_returns_nothing(capsys):
    loaders = {"usos": lambda: []}

    summary, store, lexical = _run(loaders, existing=[_doc("usos_old")], purge=True)

    assert summary == {"usos": 0}
    assert set(store.docs) == set(lexical.docs) == {"usos_old"}
    assert "UWAGA" in capsys.readouterr().out


def test_ingests_only_selected_sources_in_batches():
    called = []

    def mordor_loader():
        called.append("mordor")
        return [_doc(f"mordor_{i}", "mordor") for i in range(5)]

    loaders = {"mordor": mordor_loader, "usos": lambda: called.append("usos") or []}

    summary, store, _ = _run(loaders, sources=["mordor"], batch_size=2)

    assert called == ["mordor"]
    assert summary == {"mordor": 5}
    assert len(store.docs) == 5
