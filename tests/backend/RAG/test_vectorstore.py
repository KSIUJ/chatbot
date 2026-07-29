"""
Testy vectorstore.py. Uzywa FakeEncoder (patrz conftest.py) - realna ChromaDB,
ale bez pobierania modelu embeddingowego - oraz tymczasowego katalogu na dane.
"""

from conftest import FakeEncoder

from RAG.ingest.schema import Document
from RAG.vectorstore import VectorStore


def _make_store(tmp_path):
    return VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=FakeEncoder())


def test_add_and_search_returns_matching_document(tmp_path):
    store = _make_store(tmp_path)
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

    hits = store.search("regulamin studiow zaliczenia", top_k=1)

    assert len(hits) == 1
    assert hits[0]["id"] == "mordor_1"
    assert hits[0]["source"] == "mordor"
    assert hits[0]["content_type"] == "text"
    assert hits[0]["metadata"]["source_file"] == "regulamin.pdf"


def test_add_documents_with_empty_list_is_noop(tmp_path):
    store = _make_store(tmp_path)
    store.add_documents([])
    assert store.count() == 0


def test_upsert_overwrites_existing_id(tmp_path):
    store = _make_store(tmp_path)
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
    hits = store.search("nowa tresc", top_k=1)
    assert hits[0]["value"] == "nowa tresc"


def test_search_includes_image_content_type(tmp_path):
    store = _make_store(tmp_path)
    image_doc = Document(
        id="mordor_img_1",
        source="mordor",
        embed_text="plan budynku wydzialu",
        content_type="image",
        value="data/mordor/mapy/plan_budynku.png",
        metadata={"file_name": "plan_budynku.png"},
    )
    store.add_documents([image_doc])

    hits = store.search("plan budynku", top_k=1)

    assert hits[0]["content_type"] == "image"
    assert hits[0]["value"] == "data/mordor/mapy/plan_budynku.png"
