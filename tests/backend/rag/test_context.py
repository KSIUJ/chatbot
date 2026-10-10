"""
Testy core/context.py - publiczny interfejs dla src/backend/llm/. Uzywa
fake'owego retrievera (gotowe sekcje, bez encodera/vectorstore), zeby izolowac
formatowanie promptu, obrazy i zrodla odpowiedzi.
"""

from src.backend.rag.core.context import retrieve_context
from src.backend.rag.core.retrieval import Section
from src.backend.rag.registry import MORDOR_HEADER, OFFICIAL_HEADER, create_sources
from src.backend.rag.sources.usos import STAFF_HEADER


class FakeRetriever:
    """Sekcje jak z Retriever.retrieve: pracownik (gdy sa trafienia), oficjalne, Mordor."""

    def __init__(self, hits, staff_hits=None):
        self.hits = hits
        self.staff_hits = staff_hits or []
        self.sources = create_sources()
        self.last_query = None

    def retrieve(self, query):
        self.last_query = query
        staff_ids = {h["id"] for h in self.staff_hits}
        return [
            Section(STAFF_HEADER, self.staff_hits),
            Section(OFFICIAL_HEADER, [h for h in self.hits if h["source"] != "mordor" and h["id"] not in staff_ids]),
            Section(MORDOR_HEADER, [h for h in self.hits if h["source"] == "mordor"]),
        ]


def _hit(id_, source, value, metadata, content_type="text"):
    return {"id": id_, "value": value, "content_type": content_type, "source": source, "metadata": metadata}


KOWALSKI = _hit("usos_1", "usos", "Jan Kowalski, pokoj 101.", {"employee_name": "Jan Kowalski"})
DZIEKANAT = _hit("uj_pages_1", "uj_pages", "Dziekanat czynny pon-pt 8-15.", {"url": "https://matinf.uj.edu.pl/dziekanat"})
NOTATKA = _hit("mordor_1", "mordor", "Notatka ze studenckich materialow.", {"source_file": "notatka.pdf"})
PLAN = _hit(
    "mordor_img_1", "mordor", "data/mordor/mapy/plan_budynku.png", {"file_name": "plan_budynku.png"}, content_type="image"
)


def test_fragments_are_labelled_with_their_source():
    retriever = FakeRetriever([NOTATKA, DZIEKANAT])

    prompt = retrieve_context("zasady zaliczenia", retriever=retriever).prompt

    assert "[mordor: notatka.pdf]\nNotatka ze studenckich materialow." in prompt
    assert "[uj_pages: https://matinf.uj.edu.pl/dziekanat]\nDziekanat czynny pon-pt 8-15." in prompt
    assert retriever.last_query == "zasady zaliczenia"


def test_official_sources_come_before_mordor():
    prompt = retrieve_context("gdzie siedzi Jan Kowalski", retriever=FakeRetriever([NOTATKA, KOWALSKI])).prompt

    assert prompt.index(OFFICIAL_HEADER) < prompt.index(MORDOR_HEADER)
    assert prompt.index("Jan Kowalski, pokoj 101.") < prompt.index("Notatka ze studenckich materialow.")


def test_image_hits_are_files_not_prompt_text():
    result = retrieve_context("gdzie jest pokoj", retriever=FakeRetriever([PLAN, KOWALSKI]))

    assert result.image_paths == ["data/mordor/mapy/plan_budynku.png"]
    assert "plan_budynku.png" not in result.prompt
    assert "Jan Kowalski, pokoj 101." in result.prompt


def test_no_hits_give_an_empty_context():
    assert retrieve_context("cokolwiek", retriever=FakeRetriever([])) == ("", [], [])


def test_staff_section_comes_first_and_empty_sections_are_skipped():
    prompt = retrieve_context("pokoj Kowalskiego", retriever=FakeRetriever([KOWALSKI, DZIEKANAT], [KOWALSKI])).prompt

    assert prompt.index(STAFF_HEADER) < prompt.index(OFFICIAL_HEADER)
    assert prompt.count("Jan Kowalski, pokoj 101.") == 1
    assert MORDOR_HEADER not in prompt

    assert STAFF_HEADER not in retrieve_context("dziekanat", retriever=FakeRetriever([DZIEKANAT])).prompt


def test_citations_cover_text_and_image_hits():
    staff = _hit("usos_1", "usos", "dr Jan Kowalski", {"employee_name": "Jan Kowalski", "profile_url": "https://usosweb.uj.edu.pl/jk"})

    result = retrieve_context("gdzie siedzi Jan Kowalski", retriever=FakeRetriever([staff, DZIEKANAT, PLAN], [staff]))

    assert result.citations == [
        {"kind": "usos", "title": "Jan Kowalski", "url": "https://usosweb.uj.edu.pl/jk"},
        {"kind": "uj_pages", "title": "matinf.uj.edu.pl/dziekanat", "url": "https://matinf.uj.edu.pl/dziekanat"},
        {"kind": "mordor", "title": "plan_budynku.png", "url": None},
    ]


def test_hits_of_unknown_sources_get_a_plain_label_and_no_citation():
    retriever = FakeRetriever([_hit("x_1", "inne", "Tresc.", {})])

    result = retrieve_context("pytanie", retriever=retriever)

    assert "[inne: inne]\nTresc." in result.prompt
    assert result.citations == []
