"""
Testy hybrydowego retrievalu w retriever.py - przeplatanie trafien BM25
i wektorowych oraz filtr tokenow po czestosci w indeksie leksykalnym.
"""

from RAG.ingest.schema import Document
from RAG.lexical import LexicalIndex
from RAG.retriever import Retriever
from RAG.vectorstore import VectorStore


def _doc(id_, source, text):
    return Document(
        id=id_, source=source, embed_text=text, content_type="text", value=text, metadata={}
    )


def _make_retriever(tmp_path, encoder, documents):
    store = VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=encoder)
    lexical = LexicalIndex(db_path=str(tmp_path / "lexical.db"))
    store.add_documents(documents)
    lexical.add_documents(documents)
    return Retriever(encoder=encoder, vectorstore=store, lexical=lexical, staff=None)


def test_interleave_reserves_half_the_slots_for_lexical():
    vector = [{"id": f"v{i}"} for i in range(5)]
    lexical = [{"id": f"l{i}"} for i in range(5)]

    merged = Retriever._interleave(vector, lexical, 5)

    assert [h["id"] for h in merged] == ["l0", "l1", "l2", "v0", "v1"]


def test_interleave_dedupes_and_respects_k():
    vector = [{"id": "a"}, {"id": "b"}]
    lexical = [{"id": "a"}, {"id": "c"}]

    merged = Retriever._interleave(vector, lexical, 3)

    assert [h["id"] for h in merged] == ["a", "c", "b"]


def test_interleave_returns_empty_for_zero_k():
    assert Retriever._interleave([{"id": "a"}], [{"id": "b"}], 0) == []


def test_retrieve_split_surfaces_exact_token_match(tmp_path, fake_encoder):
    documents = [
        _doc("mordor_1", "mordor", "Sortowanie szybkie quicksort dzielenie tablicy pivot"),
    ] + [
        _doc(f"mordor_pad_{i}", "mordor", f"zupelnie inny material numer {i} o calkach")
        for i in range(10)
    ]
    retriever = _make_retriever(tmp_path, fake_encoder, documents)

    hits = retriever.retrieve_split("quicksort", k_mordor=3, k_other=0)["mordor"]

    assert "mordor_1" in [h["id"] for h in hits]


def test_selective_tokens_drops_very_common_ones(tmp_path, fake_encoder):
    documents = [_doc(f"strony_{i}", "strony", "jak dziala ta strona") for i in range(100)]
    documents.append(_doc("strony_rzadki", "strony", "jak dziala kwantyzacja"))
    lexical = LexicalIndex(db_path=str(tmp_path / "lexical.db"))
    lexical.add_documents(documents)

    assert lexical.selective_tokens(["jak", "dziala", "kwantyzacja"]) == ["kwantyzacja"]


def test_selective_tokens_keeps_all_when_every_token_is_common(tmp_path, fake_encoder):
    documents = [_doc(f"strony_{i}", "strony", "jak dziala ta strona") for i in range(100)]
    lexical = LexicalIndex(db_path=str(tmp_path / "lexical.db"))
    lexical.add_documents(documents)

    assert lexical.selective_tokens(["jak", "dziala"]) == ["jak", "dziala"]
