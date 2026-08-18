"""
Testy context_builder.py - publiczny interfejs dla src/backend/llm/.
Uzywa fake'owego retrievera (bez encodera/vectorstore), zeby izolowac tylko
logike formatowania promptu i wyodrebniania sciezek do obrazow.
"""

from RAG.context_builder import build_context


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits
        self.last_query = None
        self.last_top_k = None

    def retrieve(self, query, top_k=5):
        self.last_query = query
        self.last_top_k = top_k
        return self.hits


def test_build_context_joins_text_fragments_with_source_label():
    hits = [
        {
            "id": "mordor_1",
            "value": "Zaliczenie wymaga 60% punktow.",
            "content_type": "text",
            "source": "mordor",
            "metadata": {"source_file": "regulamin.pdf"},
        },
        {
            "id": "strony_1",
            "value": "Dziekanat czynny pon-pt 8-15.",
            "content_type": "text",
            "source": "strony",
            "metadata": {"url": "https://matinf.uj.edu.pl/dziekanat"},
        },
    ]
    retriever = FakeRetriever(hits)

    prompt, images = build_context("zasady zaliczenia", top_k=2, retriever=retriever)

    assert "[mordor: regulamin.pdf]" in prompt
    assert "Zaliczenie wymaga 60% punktow." in prompt
    assert "[strony: https://matinf.uj.edu.pl/dziekanat]" in prompt
    assert "Dziekanat czynny pon-pt 8-15." in prompt
    assert images == []
    assert retriever.last_query == "zasady zaliczenia"
    assert retriever.last_top_k == 2


def test_build_context_separates_image_paths_from_prompt():
    hits = [
        {
            "id": "mordor_img_1",
            "value": "data/mordor/mapy/plan_budynku.png",
            "content_type": "image",
            "source": "mordor",
            "metadata": {"file_name": "plan_budynku.png"},
        },
        {
            "id": "usos_1",
            "value": "Jan Kowalski, pokoj 101.",
            "content_type": "text",
            "source": "usos",
            "metadata": {"employee_name": "Jan Kowalski"},
        },
    ]
    retriever = FakeRetriever(hits)

    prompt, images = build_context("gdzie jest pokoj Jana Kowalskiego", retriever=retriever)

    assert images == ["data/mordor/mapy/plan_budynku.png"]
    assert "plan_budynku.png" not in prompt
    assert "Jan Kowalski, pokoj 101." in prompt


def test_build_context_returns_empty_when_no_hits():
    retriever = FakeRetriever([])

    prompt, images = build_context("cokolwiek", retriever=retriever)

    assert prompt == ""
    assert images == []
