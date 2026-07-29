"""
Testy retriever.py - sklejenie Encoder + VectorStore. Uzywa FakeEncoder,
zeby nie pobierac realnego modelu.
"""

from conftest import FakeEncoder

from RAG.ingest.schema import Document
from RAG.retriever import Retriever
from RAG.vectorstore import VectorStore


def _make_retriever(tmp_path):
    encoder = FakeEncoder()
    vectorstore = VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=encoder)
    return Retriever(encoder=encoder, vectorstore=vectorstore)


def test_retrieve_delegates_to_vectorstore_search(tmp_path):
    retriever = _make_retriever(tmp_path)
    retriever.vectorstore.add_documents(
        [
            Document(
                id="strony_1",
                source="strony",
                embed_text="godziny otwarcia dziekanatu wydzialu",
                content_type="text",
                value="Dziekanat czynny pon-pt 8-15.",
                metadata={"url": "https://matinf.uj.edu.pl/dziekanat"},
            )
        ]
    )

    hits = retriever.retrieve("godziny otwarcia dziekanatu", top_k=3)

    assert len(hits) == 1
    assert hits[0]["source"] == "strony"
    assert hits[0]["value"] == "Dziekanat czynny pon-pt 8-15."


def test_retrieve_respects_top_k(tmp_path):
    retriever = _make_retriever(tmp_path)
    documents = [
        Document(
            id=f"usos_{i}",
            source="usos",
            embed_text=f"pracownik numer {i} dyzury",
            content_type="text",
            value=f"Pracownik {i}",
            metadata={},
        )
        for i in range(5)
    ]
    retriever.vectorstore.add_documents(documents)

    hits = retriever.retrieve("pracownik dyzury", top_k=2)

    assert len(hits) == 2


def test_retrieve_returns_empty_list_when_store_empty(tmp_path):
    retriever = _make_retriever(tmp_path)

    hits = retriever.retrieve("cokolwiek", top_k=5)

    assert hits == []
