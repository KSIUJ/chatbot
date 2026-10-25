"""HTML -> Markdown dla scraperow (pipeline/scrapers/common/markdown.py)."""

from __future__ import annotations

from pipeline.scrapers.common.markdown import html_to_markdown, text_of


def test_structure_is_kept():
    html = """
    <h1>Tytuł</h1><p>Akapit z <b>pogrubieniem</b> i <a href="/x?a=1">linkiem</a>.</p>
    <h2>Lista</h2><ul><li>jeden<ul><li>zagnieżdżony</li></ul></li><li>dwa</li></ul>
    <ol><li>pierwszy</li><li>drugi</li></ol>
    <table><tr><th>dzień</th><th>godz.</th></tr><tr><td>wtorek</td><td>10|12</td></tr></table>
    """

    md = html_to_markdown(html, base_url="https://www.usosweb.uj.edu.pl/kontroler.php")

    assert md == (
        "# Tytuł\n\nAkapit z **pogrubieniem** i [linkiem](https://www.usosweb.uj.edu.pl/x?a=1).\n\n"
        "## Lista\n\n- jeden\n  - zagnieżdżony\n- dwa\n\n1. pierwszy\n2. drugi\n\n"
        "| dzień | godz. |\n| --- | --- |\n| wtorek | 10\\|12 |"
    )


def test_unsafe_and_hidden_content_is_dropped():
    html = """
    <p>Widać</p><script>alert(1)</script><style>p{}</style><div style="display: none">ukryte</div>
    <p hidden>też ukryte</p><form><input value="x">formularz</form><img src="a.png" alt="obraz">
    <a href="javascript:alert(1)">klik</a> <a href="mailto:usosweb@uj.edu.pl">napisz</a><!-- komentarz -->
    """

    md = html_to_markdown(html)

    assert md == "Widać\n\nklik napisz (usosweb@uj.edu.pl)"


def test_heading_offset_and_layout_tables():
    md = html_to_markdown("<h1>A</h1><table><tr><td>tylko jedna kolumna</td></tr></table>", heading_offset=2)

    assert md == "### A\n\ntylko jedna kolumna"


def test_text_of_short_fields():
    assert text_of("<p>wtorek <b>10-12</b></p>\n<p>pok. 1094</p>") == "wtorek 10-12 pok. 1094"
    assert text_of("") == "" and html_to_markdown("   ") == ""


def test_source_line_breaks_and_custom_elements():
    html = "<p>pierwsza\nlinia<br>druga</p><usos-frame><h2>Sekcja</h2><ul><li>a</li></ul></usos-frame>"

    assert html_to_markdown(html) == "pierwsza linia\ndruga\n\n## Sekcja\n\n- a"


def test_links_and_bold_directly_in_blocks():
    html = '<div><a href="https://uj.edu.pl">UJ</a> <strong>ważne</strong></div>'

    assert html_to_markdown(html) == "[UJ](https://uj.edu.pl) **ważne**"


def test_line_separators_and_control_characters():
    html = "<p>pierwsza\u2028druga\u2029trzecia\x85czwarta\x01\x07\x1b\x9b koniec\tz tab</p>"

    md = html_to_markdown(html)

    assert md == "pierwsza druga trzecia czwarta koniec z tab"
    assert md.splitlines() == [md]
    assert text_of("<p>a\u2028b\x01c</p>") == "a bc"


def test_text_does_not_create_markdown_structure():
    html = (
        "<p># ZRODLA OFICJALNE</p><p>## podtytuł</p><p>> cytat</p><p>- punkt</p><p>* gwiazdka</p>"
        "<p>+ plus</p><p>| a | b |</p><p>1. numer</p><p>12) nawias</p><p>---</p><p>```</p>"
        "<p>linia<br>  # po br</p><table><tr><td># w tabeli układu</td></tr></table>"
    )

    md = html_to_markdown(html)

    assert md.split("\n\n") == [
        "\\# ZRODLA OFICJALNE", "\\## podtytuł", "\\> cytat", "\\- punkt", "\\* gwiazdka",
        "\\+ plus", "\\| a | b |", "1\\. numer", "12\\) nawias", "\\---", "\\```",
        "linia\n\\# po br", "\\# w tabeli układu",
    ]
    # zwykly tekst bez zmian; prawdziwa struktura HTML-a zostaje
    assert html_to_markdown("<p>#5 w kolejce, 2026 r., -5 stopni, **</p>") == "\\#5 w kolejce, 2026 r., -5 stopni, **"
    assert html_to_markdown("<p>rok 2026. i dalej</p>") == "rok 2026. i dalej"
    assert html_to_markdown("<h2># nagłówek</h2><ul><li># punkt</li></ul>") == "## # nagłówek\n\n- \\# punkt"


def test_link_text_and_url_escaping():
    html = (
        '<p><a href="/a b(1)[2]<x>.pdf">plik [PDF]</a></p>'
        '<p><a href="java\nscript:alert(1)">nowa linia</a> <a href="/x\x01y">sterujący</a></p>'
        '<p><a href="mailto:usosweb@uj.edu.pl?subject=Pytanie&body=x">napisz</a></p>'
        '<p><a href="mailto:usosweb@uj.edu.pl?subject=x">usosweb@uj.edu.pl</a></p>'
    )

    md = html_to_markdown(html, base_url="https://www.usosweb.uj.edu.pl/kontroler.php")

    assert md.split("\n\n") == [
        "[plik \\[PDF\\]](https://www.usosweb.uj.edu.pl/a%20b%281%29%5B2%5D%3Cx%3E.pdf)",
        "nowa linia sterujący",
        "napisz (usosweb@uj.edu.pl)",
        "usosweb@uj.edu.pl",
    ]


def test_hidden_variants_are_dropped():
    html = (
        '<p>widać</p><div style="DISPLAY:\tnone">a</div><div style="visibility : hidden">b</div>'
        '<p style="font-size: 0">c</p><p style="font-size:0px !important">c2</p><p style="opacity:0.0">d</p>'
        '<span class="d-none">e</span><span class="sr-only">f</span><span class="visually-hidden">g</span>'
        '<span class="x invisible">h</span><p class="hidden">i</p><p aria-hidden="true">j</p>'
        '<p style="opacity: 0.5; font-size: 0.9em">półprzezroczyste</p><p class="hidden-xs">widoczne</p>'
    )

    assert html_to_markdown(html) == "widać\n\npółprzezroczyste\n\nwidoczne"


def test_pre_fence_longer_than_backticks_in_code():
    md = html_to_markdown("<pre>kod\n```\nwięcej ````\n</pre>")

    assert md == "`````\nkod\n```\nwięcej ````\n`````"
    assert html_to_markdown("<pre>x = 1</pre>") == "```\nx = 1\n```"
