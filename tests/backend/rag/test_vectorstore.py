"""
Testy vectorstore.py. Uzywa FakeEncoder (fixture fake_encoder, patrz
conftest.py) - realna ChromaDB, ale bez pobierania modelu embeddingowego -
oraz tymczasowego katalogu na dane.
"""

from src.backend.rag.schema import Document
from src.backend.rag.vectorstore import VectorStore


def _make_store(tmp_path, encoder):
    return VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=encoder)


def test_add_and_search_split_returns_matching_document(tmp_path, fake_encoder):
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

    hits = store.search_split("regulamin studiow zaliczenia", k_mordor=1, k_other=0)["mordor"]

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
    hits = store.search_split("nowa tresc", k_mordor=0, k_other=1)["other"]
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

    hits = store.search_split("plan budynku", k_mordor=1, k_other=0)["mordor"]

    assert hits[0]["content_type"] == "image"
    assert hits[0]["value"] == "data/mordor/mapy/plan_budynku.png"


def test_search_split_gives_each_group_its_own_slots(tmp_path, fake_encoder):
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

    groups = store.search_split("regulamin zaliczenia", k_mordor=2, k_other=2)

    assert len(groups["mordor"]) == 2
    assert all(h["source"] == "mordor" for h in groups["mordor"])
    assert len(groups["other"]) == 1
    assert groups["other"][0]["value"] == "Jan Kowalski, pokoj 101."


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
