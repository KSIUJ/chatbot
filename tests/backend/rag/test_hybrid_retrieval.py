"""
Testy hybrydowego retrievalu w core/retrieval.py - fuzja RRF trafien BM25
i wektorowych, prog trafnosci, wybor fragmentow (dokumenty, sklejanie
sasiednich chunkow, budzet) oraz filtr tokenow po czestosci w indeksie
leksykalnym.
"""

from src.backend.rag.core.documents import Document
from src.backend.rag.core.lexical import LexicalIndex
from src.backend.rag.core.retrieval import (
    NO_THRESHOLD,
    Candidate,
    Relevance,
    Retriever,
    document_key,
    fuse,
    hit_ids,
    join_chunks,
    select,
)
from src.backend.rag.core.vectorstore import VectorStore
from src.backend.rag.registry import MORDOR_HEADER, OFFICIAL_HEADER, Pool


def _pools(k_other=5, k_mordor=5):
    return (
        Pool("official", ("strony", "usos"), k=k_other, header=OFFICIAL_HEADER),
        Pool("student", ("mordor",), k=k_mordor, header=MORDOR_HEADER),
    )


def _groups(retriever, query):
    """Trafienia pul: {"mordor": [...], "other": [...]}."""
    sections = {s.header: s.hits for s in retriever.retrieve(query)}
    return {"mordor": sections[MORDOR_HEADER], "other": sections[OFFICIAL_HEADER]}


def _doc(id_, source, text, metadata=None):
    return Document(
        id=id_, source=source, embed_text=text, content_type="text", value=text, metadata=metadata or {}
    )


def _make_retriever(tmp_path, encoder, documents, relevance=NO_THRESHOLD, pools=None):
    store = VectorStore(persist_dir=str(tmp_path / "vectorstore"), encoder=encoder)
    lexical = LexicalIndex(db_path=str(tmp_path / "lexical.db"))
    store.add_documents(documents)
    lexical.add_documents(documents)
    return Retriever(
        encoder=encoder,
        vectorstore=store,
        lexical=lexical,
        pools=pools or _pools(k_other=0, k_mordor=3),
        relevance=relevance,
    )


def _page(id_, url, index, value, source="uj_pages"):
    return {"id": id_, "source": source, "content_type": "text", "value": value,
            "metadata": {"url": url, "chunk_index": index}}


POOL = Pool("official", ("uj_pages",), k=5, header=OFFICIAL_HEADER, budget=10_000)


# --- fuzja RRF ----------------------------------------------------------------


def test_fuse_ranks_hits_found_by_both_lists_first():
    vector = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    lexical = [{"id": "c"}, {"id": "d"}]

    fused = fuse(vector, lexical, rrf_k=60)

    assert [c.hit["id"] for c in fused] == ["c", "a", "b", "d"]
    assert (fused[0].vector_rank, fused[0].lexical_rank) == (3, 1)
    assert fused[0].score == 1 / 63 + 1 / 61


def test_fuse_ties_keep_vector_order_first_and_ignore_duplicates():
    fused = fuse([{"id": "v"}, {"id": "v"}], [{"id": "l"}], rrf_k=60)

    assert [c.hit["id"] for c in fused] == ["v", "l"]
    assert fused[0].vector_rank == 1


def test_fuse_of_empty_lists_is_empty():
    assert fuse([], []) == []


# --- prog trafnosci -------------------------------------------------------------


RELEVANCE = Relevance(min_similarity=0.78, max_gap=0.03)


def _ids(candidates):
    return [c.hit["id"] for c in candidates]


def test_relevance_drops_candidates_below_the_floor():
    candidates = [Candidate({"id": "a"}, similarity=0.79), Candidate({"id": "b"}, similarity=0.77)]

    assert _ids(RELEVANCE.filter(candidates)) == ["a"]


def test_relevance_drops_candidates_far_below_the_best_one():
    candidates = [
        Candidate({"id": "a"}, similarity=0.85),
        Candidate({"id": "b"}, similarity=0.83),
        Candidate({"id": "c"}, similarity=0.81),
    ]

    assert _ids(RELEVANCE.filter(candidates)) == ["a", "b"]


def test_relevance_keeps_candidates_without_a_vector():
    candidates = [Candidate({"id": "a"}), Candidate({"id": "b"}, similarity=0.5)]

    assert _ids(RELEVANCE.filter(candidates)) == ["a"]
    assert _ids(NO_THRESHOLD.filter(candidates)) == ["a", "b"]


def test_threshold_drops_unrelated_documents(tmp_path, fake_encoder):
    documents = [
        _doc("mordor_1", "mordor", "sortowanie szybkie quicksort pivot"),
        _doc("mordor_2", "mordor", "calki oznaczone i nieoznaczone"),
    ]
    strict = Relevance(min_similarity=0.7, max_gap=1.0)
    retriever = _make_retriever(tmp_path, fake_encoder, documents, relevance=strict)

    hits = _groups(retriever, "sortowanie szybkie quicksort")["mordor"]

    assert [h["id"] for h in hits] == ["mordor_1"]


# --- wybor fragmentow -------------------------------------------------------------


def test_document_key_per_source():
    assert document_key(_page("x", "https://a.pl/s", 0, "")) == "uj_pages|https://a.pl/s"
    note = {"id": "k", "source": "ksi", "metadata": {"note": "dolacz", "url": "https://ksi.pl"}}
    assert document_key(note) == "ksi|note|dolacz"
    mordor = {"id": "m", "source": "mordor", "metadata": {"directory": "data/mordor/AM", "source_file": "a.pdf"}}
    assert document_key(mordor) == "mordor|data/mordor/AM/a.pdf"
    assert document_key({"id": "usos_1", "source": "usos", "metadata": {"employee_name": "Jan"}}) == "usos_1"


def test_join_chunks_removes_the_overlap():
    first = "Pierwsze zdanie. Wspolna zakladka obu chunkow."
    second = "Wspolna zakladka obu chunkow. Dalszy ciag."

    assert join_chunks(first, second) == "Pierwsze zdanie. Wspolna zakladka obu chunkow. Dalszy ciag."
    assert join_chunks("abc", "def") == "abc\ndef"


def test_select_limits_chunks_of_one_document():
    hits = [_page(f"p{i}", "https://a.pl/s", i * 2, f"tekst {i}") for i in range(4)]
    hits.append(_page("q", "https://a.pl/inna", 0, "inna strona"))

    selected = select(hits, POOL)

    assert [h["id"] for h in selected] == ["p0", "p1", "q"]


def test_select_merges_adjacent_chunks_into_one_fragment():
    hits = [
        _page("p3", "https://a.pl/s", 3, "wspolny srodek strony. koniec"),
        _page("q", "https://a.pl/inna", 0, "inna strona"),
        _page("p2", "https://a.pl/s", 2, "poczatek strony. wspolny srodek strony."),
    ]

    selected = select(hits, POOL)

    assert [h["id"] for h in selected] == ["p3", "q"]
    assert selected[0]["value"] == "poczatek strony. wspolny srodek strony. koniec"
    assert hit_ids(selected[0]) == ["p3", "p2"]
    assert hit_ids(selected[1]) == ["q"]


def test_select_stops_when_the_budget_is_used_but_keeps_min_hits():
    hits = [_page(f"p{i}", f"https://a.pl/{i}", 0, "x" * 600) for i in range(4)]

    small = Pool("official", ("uj_pages",), k=5, header=OFFICIAL_HEADER, budget=1300)
    assert [h["id"] for h in select(hits, small)] == ["p0", "p1"]

    tiny = Pool("official", ("uj_pages",), k=5, header=OFFICIAL_HEADER, budget=100, min_hits=1)
    assert [h["id"] for h in select(hits, tiny)] == ["p0"]


def test_select_respects_k():
    hits = [_page(f"p{i}", f"https://a.pl/{i}", 0, "tekst") for i in range(6)]

    assert len(select(hits, Pool("official", ("uj_pages",), k=3, header=OFFICIAL_HEADER))) == 3


def test_image_hits_do_not_use_the_budget():
    image = {"id": "img", "source": "mordor", "content_type": "image", "value": "data/mordor/a.png", "metadata": {}}
    text = _page("p", "https://a.pl/s", 0, "x" * 900)
    pool = Pool("student", ("mordor",), k=5, header=MORDOR_HEADER, budget=1000)

    assert [h["id"] for h in select([image, text], pool)] == ["img", "p"]


# --- pule na realnych indeksach -------------------------------------------------------


def test_pool_surfaces_exact_token_match(tmp_path, fake_encoder):
    documents = [
        _doc("mordor_1", "mordor", "Sortowanie szybkie quicksort dzielenie tablicy pivot"),
    ] + [
        _doc(f"mordor_pad_{i}", "mordor", f"zupelnie inny material numer {i} o calkach")
        for i in range(10)
    ]
    retriever = _make_retriever(tmp_path, fake_encoder, documents)

    hits = _groups(retriever, "quicksort")["mordor"]

    assert "mordor_1" in [h["id"] for h in hits]


def test_pool_merges_adjacent_chunks_of_a_page(tmp_path, fake_encoder):
    url = "https://a.pl/regulamin"
    documents = [
        _doc("strony_0", "strony", "regulamin studiow egzamin poprawkowy termin", {"url": url, "chunk_index": 0}),
        _doc("strony_1", "strony", "egzamin poprawkowy termin wrzesien regulamin", {"url": url, "chunk_index": 1}),
        _doc("strony_x", "strony", "stypendium rektora dla najlepszych", {"url": "https://a.pl/x", "chunk_index": 0}),
    ]
    retriever = _make_retriever(tmp_path, fake_encoder, documents, pools=_pools(k_other=5, k_mordor=0))

    hits = _groups(retriever, "egzamin poprawkowy regulamin")["other"]

    assert sorted(hit_ids(hits[0])) == ["strony_0", "strony_1"]
    assert "strony_0" not in [i for h in hits[1:] for i in hit_ids(h)]


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


# --- reranker -------------------------------------------------------------------


class FakeReranker:
    """Ocena = czy tekst zawiera slowo "wazne" (bez modelu)."""

    def __init__(self):
        self.calls = []

    def scores(self, query, texts):
        self.calls.append((query, texts))
        return [1.0 if "wazne" in t else 0.0 for t in texts]


def test_reranker_reorders_pool_candidates(tmp_path, fake_encoder):
    documents = [
        _doc("mordor_1", "mordor", "egzamin analiza terminy"),
        _doc("mordor_2", "mordor", "egzamin analiza wazne informacje"),
    ]
    retriever = _make_retriever(tmp_path, fake_encoder, documents)
    retriever.reranker = FakeReranker()

    hits = _groups(retriever, "egzamin analiza terminy")["mordor"]

    assert [h["id"] for h in hits] == ["mordor_2", "mordor_1"]
    assert retriever.reranker.calls[0][0] == "egzamin analiza terminy"


def test_reranker_min_score_drops_weak_candidates(tmp_path, fake_encoder):
    documents = [
        _doc("mordor_1", "mordor", "egzamin analiza terminy"),
        _doc("mordor_2", "mordor", "egzamin analiza wazne informacje"),
    ]
    retriever = _make_retriever(tmp_path, fake_encoder, documents)
    retriever.reranker = FakeReranker()
    retriever.reranker.min_score = 0.5

    hits = _groups(retriever, "egzamin analiza terminy")["mordor"]

    assert [h["id"] for h in hits] == ["mordor_2"]


def test_reranker_is_off_without_env(monkeypatch):
    from src.backend.rag.core import rerank

    monkeypatch.delenv(rerank.MODEL_ENV, raising=False)

    assert rerank.default_reranker() is None
