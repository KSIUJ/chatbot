"""
Testy vectorstore.py. Uzywa FakeEncoder (fixture fake_encoder, patrz
conftest.py) - realna ChromaDB, ale bez pobierania modelu embeddingowego -
oraz tymczasowego katalogu na dane.
"""

from src.backend.rag.core.documents import Document
import pytest

from src.backend.rag.core.vectorstore import VectorStore, document_hash


def _make_store(tmp_path, encoder):
    return VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=encoder)


def _search(store, query, k, *sources):
    return store.query(store.encoder.embed_query(query), k, sources)


def test_add_and_query_returns_matching_document(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    documents = [
        Document(
            id="mordor_1",
            source="mordor",
            embed_text="regulamin studiow zaliczenia egzamin",
            content_type="text",
            value="Tresc regulaminu studiow.",
            metadata={"source_file": "regulamin.pdf"},
        ),
        Document(
            id="usos_1",
            source="usos",
            embed_text="Jan Kowalski dyzury pokoj 101",
            content_type="text",
            value="Jan Kowalski, pokoj 101, dyzury: wtorek 10-12.",
            metadata={"employee_name": "Jan Kowalski"},
        ),
    ]

    store.add_documents(documents)
    assert store.count() == 2

    hits = _search(store, "regulamin studiow zaliczenia", 1, "mordor")

    assert len(hits) == 1
    assert hits[0]["id"] == "mordor_1"
    assert hits[0]["source"] == "mordor"
    assert hits[0]["content_type"] == "text"
    assert hits[0]["metadata"]["source_file"] == "regulamin.pdf"


def test_add_documents_with_empty_list_is_noop(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    store.add_documents([])
    assert store.count() == 0


def test_upsert_overwrites_existing_id(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    doc_v1 = Document(
        id="strony_1", source="strony", embed_text="stara tresc",
        content_type="text", value="stara tresc", metadata={"url": "https://a"},
    )
    doc_v2 = Document(
        id="strony_1", source="strony", embed_text="nowa tresc",
        content_type="text", value="nowa tresc", metadata={"url": "https://a"},
    )

    store.add_documents([doc_v1])
    store.add_documents([doc_v2])

    assert store.count() == 1
    hits = _search(store, "nowa tresc", 1, "strony", "usos")
    assert hits[0]["value"] == "nowa tresc"


def test_search_includes_image_content_type(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    image_doc = Document(
        id="mordor_img_1",
        source="mordor",
        embed_text="plan budynku wydzialu",
        content_type="image",
        value="data/mordor/mapy/plan_budynku.png",
        metadata={"file_name": "plan_budynku.png"},
    )
    store.add_documents([image_doc])

    hits = _search(store, "plan budynku", 1, "mordor")

    assert hits[0]["content_type"] == "image"
    assert hits[0]["value"] == "data/mordor/mapy/plan_budynku.png"


def test_query_is_limited_to_the_given_sources(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    documents = [
        Document(
            id=f"mordor_{i}",
            source="mordor",
            embed_text="regulamin studiow zaliczenia przedmiotu",
            content_type="text",
            value=f"Notatka {i}",
            metadata={"source_file": f"notatka_{i}.pdf"},
        )
        for i in range(3)
    ]
    documents.append(
        Document(
            id="usos_1",
            source="usos",
            embed_text="regulamin studiow zaliczenia przedmiotu",
            content_type="text",
            value="Jan Kowalski, pokoj 101.",
            metadata={"employee_name": "Jan Kowalski"},
        )
    )
    store.add_documents(documents)

    mordor = _search(store, "regulamin zaliczenia", 2, "mordor")
    other = _search(store, "regulamin zaliczenia", 2, "strony", "usos")

    assert len(mordor) == 2
    assert all(h["source"] == "mordor" for h in mordor)
    assert len(other) == 1
    assert other[0]["value"] == "Jan Kowalski, pokoj 101."
    assert _search(store, "regulamin", 0, "mordor") == []
    assert _search(store, "regulamin", 3) == []


def test_get_by_ids_keeps_requested_order_and_skips_missing(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    store.add_documents(
        [
            Document(
                id=f"strony_{i}", source="strony", embed_text=f"tresc {i}",
                content_type="text", value=f"tresc {i}", metadata={"url": f"https://{i}"},
            )
            for i in range(3)
        ]
    )

    hits = store.get_by_ids(["strony_2", "brak", "strony_0"])

    assert [h["id"] for h in hits] == ["strony_2", "strony_0"]
    assert hits[0]["metadata"]["url"] == "https://2"
    assert hits[0]["distance"] is None
    assert store.get_by_ids([]) == []


def test_filter_new_and_delete_source(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    old = Document(id="usos_1", source="usos", embed_text="a", content_type="text", value="a")
    new = Document(id="usos_2", source="usos", embed_text="b", content_type="text", value="b")
    store.add_documents([old])

    assert store.filter_new([old, new]) == [new]
    assert store.delete_source("usos") == 1
    assert store.count() == 0


def test_query_is_exact_and_independent_of_previous_queries(tmp_path):
    """Wyszukiwanie liczy odleglosc do wszystkich wektorow wybranych zrodel:
    wynik = ranking brute-force, niezaleznie od wczesniejszych zapytan i k
    (HNSW Chromy z filtrem po zrodle gubil czasem blizszego sasiada)."""
    import numpy as np

    rng = np.random.default_rng(7)
    vectors = rng.normal(size=(600, 16)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    sources = ["mordor" if i % 3 else "usos" for i in range(len(vectors))]

    class TableEncoder:
        def embed_batch(self, texts):
            return [vectors[int(t)].tolist() for t in texts]

    store = VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=TableEncoder())
    store.add_documents(
        [
            Document(id=f"d{i:04d}", source=s, embed_text=str(i), content_type="text", value=str(i))
            for i, s in enumerate(sources)
        ]
    )

    def brute(query, k, wanted):
        rows = [i for i, s in enumerate(sources) if s in wanted]
        distances = ((vectors[rows] - query) ** 2).sum(axis=1)
        return [f"d{rows[i]:04d}" for i in np.argsort(distances, kind="stable")[:k]]

    queries = rng.normal(size=(20, 16)).astype(np.float32)
    first = [[h["id"] for h in store.query(q.tolist(), 10, ("usos",))] for q in queries]
    # inne zapytania (duze k, inne zrodla) nie zmieniaja kolejnych wynikow
    for q in queries:
        store.query(q.tolist(), 300, ("usos", "mordor"))
    again = [[h["id"] for h in store.query(q.tolist(), 10, ("usos",))] for q in queries]
    # nowy obiekt na tym samym katalogu (np. restart backendu) - te same wyniki
    reopened = VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=TableEncoder())
    after_restart = [[h["id"] for h in reopened.query(q.tolist(), 10, ("usos",))] for q in queries]

    assert first == again == after_restart == [brute(q, 10, {"usos"}) for q in queries]
    hit = store.query(queries[0].tolist(), 1, ("usos",))[0]
    expected = float(((vectors[int(hit["value"])] - queries[0]) ** 2).sum())
    assert hit["distance"] == pytest.approx(expected, abs=1e-4)


def test_document_hash_tracks_text_value_and_metadata():
    base = Document(id="u", source="usos", embed_text="a", content_type="text", value="b", metadata={"x": 1})

    def changed(**fields):
        return document_hash(Document(**{**base.__dict__, **fields})) != document_hash(base)

    assert not changed()
    assert changed(embed_text="a2") and changed(value="b2") and changed(metadata={"x": 2})


def test_written_entries_carry_content_hash(tmp_path, fake_encoder):
    store = _make_store(tmp_path, fake_encoder)
    doc = Document(id="usos_1", source="usos", embed_text="a", content_type="text", value="a")
    store.add_documents([doc])

    assert store.source_hashes("usos") == {"usos_1": document_hash(doc)}
    store.delete_ids(["usos_1"])
    assert store.count() == 0
