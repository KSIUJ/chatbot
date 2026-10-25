"""
Reprezentacja danych w indeksie: podzial Markdownu wedlug naglowkow i linia
kontekstu (core/chunking.py), tytuly stron z adresow (uj_pages/titles.py),
odmiana nazwisk do karty pracownika (usos/names.py) i materialy z Mordoru
(sciezki, strony, OCR skanow - mordor/).
"""

from __future__ import annotations

import pytest

from src.backend.rag.core import chunking
from src.backend.rag.core.chunking import chunk_markdown, context_line, split_sections, with_context
from src.backend.rag.sources.mordor import legacy as mordor_legacy
from src.backend.rag.sources.mordor.dataset import MaterialAttributes, MaterialRecord, Page
from src.backend.rag.sources.mordor.documents import material_documents
from src.backend.rag.sources.mordor.paths import academic_year, parse_path
from src.backend.rag.sources.uj_pages.titles import Vocabulary, first_line_title, page_title
from src.backend.rag.sources.usos.names import genitive, inflected_forms

# --- chunking ----------------------------------------------------------------------

def test_sections_follow_heading_levels_and_skip_code_blocks():
    markdown = "Wstep\n# A\ntekst a\n## B\ntekst b\n```\n# to nie naglowek\n```\n#### gleboki\n## C\ntekst c\n# D\ntekst d"

    sections = split_sections(markdown)

    assert [tuple(h.text for h in s.headings) for s in sections] == [(), ("A",), ("A", "B"), ("A", "C"), ("D",)]
    assert "# to nie naglowek" in sections[2].text and "#### gleboki" in sections[2].text


def test_small_sections_are_merged_with_headings_inline():
    (chunk,) = chunk_markdown("# Biblioteka\n## Godziny\npon-pt 9-17\n## Kontakt\ntel. 12 664")

    assert chunk.section == ("Biblioteka",)
    assert chunk.text == "## Godziny\n\npon-pt 9-17\n\n## Kontakt\n\ntel. 12 664"


def test_large_section_is_split_and_every_piece_keeps_its_section():
    chunks = chunk_markdown("## Krotka\nmalo\n## Dluga\n" + "zdanie numer dwa. " * 150)

    assert chunks[0].section == ("Krotka",)
    assert len(chunks) > 2
    assert all(c.section == ("Dluga",) for c in chunks[1:])
    assert all(len(c.text) <= chunking.CHUNK_SIZE for c in chunks)


def test_text_without_headings_is_chunked_as_before():
    text = "slowo " * 500

    assert [c.text for c in chunk_markdown(text)] == chunking.make_splitter().split_text(text)


def test_heading_without_text_does_not_become_a_chunk():
    assert [c.section for c in chunk_markdown("# A\n## B\ntresc")] == [("A", "B")]


def test_context_line_skips_empty_and_repeated_parts():
    assert context_line("O nas", "", "Biblioteka", "biblioteka", "Godziny") == "O nas › Biblioteka › Godziny"
    assert with_context("", "tekst") == "tekst"
    assert with_context("A › B", "tekst") == "A › B\ntekst"


# --- tytuly stron z adresow ----------------------------------------------------------

VOCABULARY = Vocabulary(
    [
        "Siedziba Wydziału jest w Krakowie. Opis siedziby naszego Wydziału.",
        "Rejestracje żetonowe w USOSweb. Informacje ogólne dla studentów.",
        "Rezygnacja ze studiów - wniosek o rezygnację ze studiów.",
    ]
)


@pytest.mark.parametrize(
    ("url", "title", "breadcrumbs"),
    [
        ("https://matinf.uj.edu.pl/o-nas/biblioteka", "Biblioteka", ["O nas", "Biblioteka"]),
        ("https://matinf.uj.edu.pl/o-nas/siedziba-wydzialu/opis", "Opis", ["O nas", "Siedziba Wydziału", "Opis"]),
        (
            "https://usosownia.uj.edu.pl/usosweb/dla-studentow/rejestracje-zetonowe",
            "Rejestracje żetonowe",
            ["USOSweb", "Dla studentów", "Rejestracje żetonowe"],
        ),
        ("https://matinf.uj.edu.pl/en-GB/pracownicy1", "Pracownicy", ["Pracownicy"]),
        ("https://kmsuj.matinf.uj.edu.pl/workshop/contact/pl", "Contact", ["kmsuj.matinf.uj.edu.pl", "Workshop", "Contact"]),
    ],
)
def test_page_title_and_breadcrumbs_come_from_the_url(url, title, breadcrumbs):
    assert page_title(url, "", "faculty" if "kmsuj" not in url else "student_group", False, VOCABULARY) == (title, breadcrumbs)


def test_document_title_is_the_decoded_file_name():
    url = "https://matinf.uj.edu.pl/documents/41633/156734637/rezygnacja+ze+studiow.pdf/87cae808"
    liferay = "https://matinf.uj.edu.pl/documents/41633/146147014/stypendia_2026_a/d086197d"

    assert page_title(url, "", "faculty", True, VOCABULARY).title == "Rezygnacja ze studiów"
    assert page_title(liferay, "", "faculty", True, VOCABULARY).title == "Stypendia 2026 a"


def test_news_page_title_is_its_first_line():
    url = "https://matinf.uj.edu.pl/wydarzenia/-/journal_content/56_INSTANCE_x/758200/42197225"

    title = page_title(url, "III Bieg w dobrej sprawie\nWydzial zaprasza...", "faculty", False, VOCABULARY)

    assert title.title == "III Bieg w dobrej sprawie"
    assert title.breadcrumbs[0] == "Wydarzenia"


def test_long_first_line_is_cut_to_a_sentence_or_word_boundary():
    assert first_line_title("Pierwsze zdanie. " + "Drugie " * 50) == "Pierwsze zdanie."
    long_title = first_line_title("slowo " * 40)
    assert long_title.endswith("…") and len(long_title) <= 101


def test_root_and_wikipedia_titles():
    root = page_title("https://nkr.si/", "Naukowe Koło Robotyki\nKim jesteśmy", "student_group", False, VOCABULARY)
    wiki = page_title(
        "https://pl.wikipedia.org/wiki/Wydzia%C5%82_Matematyki", "", "wikipedia", False, VOCABULARY
    )
    no_title = page_title("https://knmf.im.uj.edu.pl/", "Bardzo dlugi wpis. " * 10, "student_group", False, VOCABULARY)

    assert root == ("Naukowe Koło Robotyki", ["nkr.si", "Naukowe Koło Robotyki"])
    assert wiki == ("Wydział Matematyki", ["Wikipedia", "Wydział Matematyki"])
    assert no_title == ("knmf.im.uj.edu.pl", ["knmf.im.uj.edu.pl"])


# --- odmiana do karty pracownika -----------------------------------------------------

@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [
        ("Jacek", "Cyranka", "Jacka Cyranki"),
        ("Zbigniew", "Błocki", "Zbigniewa Błockiego"),
        ("Ewa", "Cygan", "Ewy Cygan"),
        ("Leokadia", "Białas-Cież", "Leokadii Białas-Cież"),
        ("Barbara", "Lewandowska", "Barbary Lewandowskiej"),
        ("Paweł", "Szafraniec", "Pawła Szafrańca"),
        ("Kamil", "Stępień", "Kamila Stępnia"),
        ("Piotr", "Micek", "Piotra Micka"),
        ("Jakub", "Zygadło", "Jakuba Zygadło"),
        ("Dariusz", "Cichoń", "Dariusza Cichonia"),
        ("Lech", "Duraj", "Lecha Duraja"),
        ("Paweł", "Raźny", "Pawła Raźnego"),
    ],
)
def test_genitive_of_staff_names(first, last, expected):
    assert genitive(first, last) == expected


def test_inflected_forms_cover_cases_and_skip_indeclinable():
    assert {"cyranki", "cyrance", "cyranke"} <= inflected_forms("cyranka")
    assert {"hermana", "hermanowi", "hermanem", "hermanie"} <= inflected_forms("herman")
    assert {"micka", "mickowi", "mickiem", "micku"} <= inflected_forms("micek")
    assert {"blockiego", "blockiemu", "blockim"} <= inflected_forms("blocki")
    assert "lewandowskiej" in inflected_forms("lewandowska")
    assert inflected_forms("zygadlo") == set()
    assert inflected_forms("ugo") == set()


# --- mordor: sciezki ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("path", "course", "year", "kind"),
    [
        ("Informatyka/Rok 2/Bazy danych/Egzaminy/2023-2024/egzamin.pdf", "Bazy danych", "2023/24", "egzamin"),
        ("Analiza 1/2024/kolokwium.pdf", "Analiza 1", "2024/25", "kolokwium"),
        ("Algebra liniowa/23_24/kol1_rozw.pdf", "Algebra liniowa", "2023/24", "kolokwium, rozwiązania"),
        ("Semestr 3/Systemy_operacyjne/notatki z wykladu.docx", "Systemy operacyjne", "", "notatki, wykład"),
        ("Egzaminy/Matematyka dyskretna/egz_2019_20.pdf", "Matematyka dyskretna", "2019/20", "egzamin"),
        ("plan.png", "", "", ""),
    ],
)
def test_course_year_and_kind_from_path(path, course, year, kind):
    assert tuple(parse_path(path)) == (course, year, kind)


@pytest.mark.parametrize(
    ("text", "year"),
    [("2023-2024", "2023/24"), ("2023/24", "2023/24"), ("23_24", "2023/24"), ("2023", "2023/24"), ("12345", ""), ("2023-2025", "2023/24")],
)
def test_academic_year_formats(text, year):
    assert academic_year(text) == year


# --- mordor: dokumenty -------------------------------------------------------------

def _material(path, kind="text", content="", pages=(), **attributes):
    return MaterialRecord(
        id=path, kind=kind, title=path.rsplit("/", 1)[-1], content=content,
        attributes=MaterialAttributes(path=path, file_type=path.rsplit(".", 1)[1], pages=list(pages), **attributes),
    )


def test_material_chunks_are_split_by_page_and_start_with_context(tmp_path):
    record = _material(
        "Analiza/kol1.pdf",
        content="caly tekst",
        pages=[Page(number=1, text="Zadanie 1. Calka."), Page(number=2, text="   "), Page(number=3, text="Zadanie 2.", ocr=True)],
        course="Analiza", academic_year="2023/24", material_kind="kolokwium",
    )

    first, second = material_documents("mordor", tmp_path, [record])

    assert first.value == first.embed_text == "Analiza › kolokwium › 2023/24 › kol1.pdf › strona 1\nZadanie 1. Calka."
    assert second.value.startswith("Analiza › kolokwium › 2023/24 › kol1.pdf › strona 3\n")
    assert (first.metadata["page"], second.metadata["page"], second.metadata["ocr"]) == (1, 3, True)
    assert [first.metadata["chunk_index"], second.metadata["chunk_index"]] == [0, 1]
    assert first.metadata["course"] == "Analiza" and first.metadata["source_file"] == "kol1.pdf"


def test_scan_document_embeds_course_and_path(tmp_path):
    (document,) = material_documents(
        "mordor", tmp_path, [_material("Bazy/egz.pdf", kind="scan", course="Bazy", material_kind="egzamin")]
    )

    assert document.content_type == "image"
    assert document.embed_text == "Bazy › egzamin\nBazy egz"


# --- mordor: stare pliki (pdf z tekstem, skan z OCR, obraz) ---------------------------

def _text_pdf(path, pages):
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text, fontsize=12)
    doc.save(path)
    doc.close()


def _scan_pdf(path, text):
    """Pdf z obrazem strony (bez warstwy tekstu) - jak zeskanowana kartka."""
    import pymupdf

    source = pymupdf.open()
    source.new_page().insert_text((72, 72), text, fontsize=20)
    pixmap = source[0].get_pixmap(dpi=150)
    scan = pymupdf.open()
    page = scan.new_page(width=source[0].rect.width, height=source[0].rect.height)
    page.insert_image(page.rect, pixmap=pixmap)
    scan.save(path)


def test_legacy_text_pdf_keeps_pages_and_parsed_path(tmp_path):
    directory = tmp_path / "mordor" / "Analiza 1" / "Kolokwia" / "2023-2024"
    directory.mkdir(parents=True)
    _text_pdf(directory / "kol1.pdf", ["Zadanie 1. Oblicz calke z funkcji.", "Zadanie 2. Zbadaj zbieznosc szeregu."])
    (directory / "zdjecie.jpg").write_bytes(b"\xff\xd8\xff")

    records = {r.id: r for r in mordor_legacy.convert(tmp_path)}

    pdf = records["Analiza 1/Kolokwia/2023-2024/kol1.pdf"]
    assert pdf.kind == "text"
    assert [p.number for p in pdf.attributes.pages] == [1, 2]
    assert "Zadanie 2" in pdf.attributes.pages[1].text and not pdf.attributes.pages[0].ocr
    assert (pdf.attributes.course, pdf.attributes.academic_year, pdf.attributes.material_kind) == (
        "Analiza 1", "2023/24", "kolokwium",
    )
    assert records["Analiza 1/Kolokwia/2023-2024/zdjecie.jpg"].kind == "image"


@pytest.mark.skipif(mordor_legacy.find_tessdata() is None, reason="brak danych Tesseracta (pol, eng)")
def test_legacy_scan_is_read_with_ocr(tmp_path):
    directory = tmp_path / "mordor" / "Bazy danych"
    directory.mkdir(parents=True)
    _scan_pdf(directory / "egzamin.pdf", "Egzamin z baz danych")

    (record,) = mordor_legacy.convert(tmp_path)

    assert record.kind == "text"
    assert record.attributes.pages[0].ocr is True
    assert "baz danych" in record.content.lower()


def test_legacy_scan_without_ocr_stays_a_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(mordor_legacy, "find_tessdata", lambda: None)
    directory = tmp_path / "mordor" / "Bazy danych"
    directory.mkdir(parents=True)
    _scan_pdf(directory / "egzamin.pdf", "Egzamin z baz danych")

    (record,) = mordor_legacy.convert(tmp_path)

    assert (record.kind, record.attributes.pages, record.attributes.material_kind) == ("scan", [], "egzamin")


def test_split_table_keeps_its_header_in_every_chunk():
    from src.backend.rag.core.chunking import chunk_markdown

    rows = "\n".join(f"| {i:04d} | {i} | sala ćwiczeniowa z projektorem i tablicą |" for i in range(80))
    chunks = chunk_markdown(f"# Budynek\n\n## Sale\n\n| Sala | Miejsca | Opis |\n| --- | --- | --- |\n{rows}")

    assert len(chunks) > 2
    for chunk in chunks:
        table_lines = [line for line in chunk.text.splitlines() if line.startswith("|")]
        assert table_lines[0] == "| Sala | Miejsca | Opis |" and table_lines[1] == "| --- | --- | --- |"
