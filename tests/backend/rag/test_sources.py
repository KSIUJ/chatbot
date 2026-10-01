"""
Testy sources.py - lista zrodel odpowiedzi (strony, USOS, mordor) budowana z
trafien RAG-a, ktore trafily do kontekstu.
"""

from src.backend.rag.sources import collect_sources, source_from_hit


def _hit(source: str, metadata: dict, content_type: str = "text", value: str = "tresc") -> dict:
    return {"id": f"{source}-{len(metadata)}", "source": source, "content_type": content_type,
            "value": value, "metadata": metadata}


def test_strony_hit_gets_short_title_and_full_url():
    hit = _hit("strony", {"url": "https://matinf.uj.edu.pl/wydzial/dziekanat/"})

    assert source_from_hit(hit) == {
        "kind": "strony",
        "title": "matinf.uj.edu.pl/wydzial/dziekanat",
        "url": "https://matinf.uj.edu.pl/wydzial/dziekanat/",
    }


def test_strony_title_is_url_decoded():
    hit = _hit("strony", {"url": "https://matinf.uj.edu.pl/o%C5%9Brodek"})

    assert source_from_hit(hit)["title"] == "matinf.uj.edu.pl/ośrodek"


def test_usos_hit_uses_employee_name_and_profile_url():
    hit = _hit("usos", {"employee_name": "Jan Kowalski", "profile_url": "https://usosweb.uj.edu.pl/x"})

    assert source_from_hit(hit) == {
        "kind": "usos",
        "title": "Jan Kowalski",
        "url": "https://usosweb.uj.edu.pl/x",
    }


def test_non_http_urls_are_dropped():
    usos = _hit("usos", {"employee_name": "Jan Kowalski", "profile_url": "javascript:alert(1)"})
    empty = _hit("usos", {"employee_name": "Anna Nowak", "profile_url": ""})
    strony = _hit("strony", {"url": "file:///etc/passwd"})

    assert source_from_hit(usos)["url"] is None
    assert source_from_hit(empty)["url"] is None
    assert source_from_hit(strony) is None


def test_mordor_text_and_image_hits_use_file_names_without_url():
    text = _hit("mordor", {"source_file": "regulamin.pdf"})
    image = _hit("mordor", {"file_name": "plan.png"}, content_type="image", value="data/mordor/mapy/plan.png")
    bare_image = _hit("mordor", {}, content_type="image", value="data/mordor/mapy/sala.jpg")

    assert source_from_hit(text) == {"kind": "mordor", "title": "regulamin.pdf", "url": None}
    assert source_from_hit(image) == {"kind": "mordor", "title": "plan.png", "url": None}
    assert source_from_hit(bare_image)["title"] == "sala.jpg"


def test_unknown_source_or_missing_title_is_skipped():
    assert source_from_hit(_hit("inne", {"url": "https://x.pl"})) is None
    assert source_from_hit(_hit("usos", {"profile_url": "https://usosweb.uj.edu.pl/x"})) is None
    assert source_from_hit(_hit("mordor", {})) is None


def test_collect_sources_deduplicates_and_keeps_order():
    hits = [
        _hit("usos", {"employee_name": "Jan Kowalski", "profile_url": "https://usosweb.uj.edu.pl/x"}),
        _hit("strony", {"url": "https://matinf.uj.edu.pl/dziekanat", "chunk_index": 0}),
        _hit("strony", {"url": "https://matinf.uj.edu.pl/dziekanat", "chunk_index": 1}),
        _hit("mordor", {"source_file": "regulamin.pdf", "chunk_index": 0}),
        _hit("mordor", {"source_file": "regulamin.pdf", "chunk_index": 3}),
        _hit("inne", {}),
    ]

    sources = collect_sources(hits)

    assert [(s["kind"], s["title"]) for s in sources] == [
        ("usos", "Jan Kowalski"),
        ("strony", "matinf.uj.edu.pl/dziekanat"),
        ("mordor", "regulamin.pdf"),
    ]
