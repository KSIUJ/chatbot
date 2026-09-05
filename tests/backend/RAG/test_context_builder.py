"""
Testy context_builder.py - publiczny interfejs dla src/backend/llm/.
Uzywa fake'owego retrievera (bez encodera/vectorstore), zeby izolowac tylko
logike formatowania promptu i wyodrebniania sciezek do obrazow.
"""

from RAG.context_builder import MORDOR_HEADER, OFFICIAL_HEADER, STAFF_HEADER, build_context


class FakeRetriever:
    def __init__(self, hits, staff_hits=None):
        self.hits = hits
        self.staff_hits = staff_hits or []
        self.last_query = None
        self.last_k_mordor = None
        self.last_k_other = None

    def retrieve_staff(self, query, limit=2):
        return self.staff_hits[:limit]

    def retrieve_split(self, query, k_mordor=5, k_other=5):
        self.last_query = query
        self.last_k_mordor = k_mordor
        self.last_k_other = k_other
        return {
            "mordor": [h for h in self.hits if h.get("source") == "mordor"][:k_mordor],
            "other": [h for h in self.hits if h.get("source") != "mordor"][:k_other],
        }


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

    prompt, images = build_context(
        "zasady zaliczenia", k_mordor=1, k_other=1, retriever=retriever
    )

    assert "[mordor: regulamin.pdf]" in prompt
    assert "Zaliczenie wymaga 60% punktow." in prompt
    assert "[strony: https://matinf.uj.edu.pl/dziekanat]" in prompt
    assert "Dziekanat czynny pon-pt 8-15." in prompt
    assert images == []
    assert retriever.last_query == "zasady zaliczenia"
    assert retriever.last_k_mordor == 1
    assert retriever.last_k_other == 1


def test_build_context_puts_official_sources_before_mordor():
    hits = [
        {
            "id": "mordor_1",
            "value": "Notatka ze studenckich materialow.",
            "content_type": "text",
            "source": "mordor",
            "metadata": {"source_file": "notatka.pdf"},
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

    prompt, _ = build_context("gdzie siedzi Jan Kowalski", retriever=retriever)

    assert prompt.index(OFFICIAL_HEADER) < prompt.index(MORDOR_HEADER)
    assert prompt.index("Jan Kowalski, pokoj 101.") < prompt.index("Notatka ze studenckich materialow.")


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


def test_build_context_puts_staff_section_first_and_dedupes():
    staff_hit = {
        "id": "usos_1",
        "value": "dr Rafał Kawa, pokoj 2168.",
        "content_type": "text",
        "source": "usos",
        "metadata": {"employee_name": "Rafał Kawa"},
    }
    other_hit = {
        "id": "strony_1",
        "value": "Lista pracownikow wydzialu.",
        "content_type": "text",
        "source": "strony",
        "metadata": {"url": "https://matinf.uj.edu.pl/pracownicy"},
    }
    retriever = FakeRetriever([staff_hit, other_hit], staff_hits=[staff_hit])

    prompt, _ = build_context("gdzie jest pokoj Rafala Kawy", retriever=retriever)

    assert prompt.index(STAFF_HEADER) < prompt.index(OFFICIAL_HEADER)
    assert prompt.count("dr Rafał Kawa, pokoj 2168.") == 1


def test_build_context_skips_staff_section_when_gate_is_silent():
    hit = {
        "id": "strony_1",
        "value": "Dziekanat czynny pon-pt 8-15.",
        "content_type": "text",
        "source": "strony",
        "metadata": {"url": "https://matinf.uj.edu.pl/dziekanat"},
    }
    retriever = FakeRetriever([hit])

    prompt, _ = build_context("kiedy czynny jest dziekanat", retriever=retriever)

    assert STAFF_HEADER not in prompt
    assert OFFICIAL_HEADER in prompt
