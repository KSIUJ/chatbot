"""
Znacznik [[NARUSZENIE]] na poczatku odpowiedzi modelu: zdejmowanie z calej
odpowiedzi (POST /chat) i z odpowiedzi strumieniowanej (kawalki moga dzielic
znacznik w dowolnym miejscu).
"""

import pytest

from src.backend.security.marker import VIOLATION_MARKER, MarkerFilter, strip_violation_marker

REFUSAL = "Nie mogę tego zrobić. W czym mogę pomóc w sprawach UJ?"


def _stream(chunks: list[str]) -> tuple[list[str], str, bool]:
    marker_filter = MarkerFilter()
    visible = [marker_filter.feed(chunk) for chunk in chunks]
    visible.append(marker_filter.finish())
    return [v for v in visible if v], "".join(visible), marker_filter.detected


def test_marker_value():
    assert VIOLATION_MARKER == "[[NARUSZENIE]]"


@pytest.mark.parametrize(
    "raw",
    [
        f"[[NARUSZENIE]] {REFUSAL}",
        f"[[NARUSZENIE]]{REFUSAL}",
        f"  \n[[NARUSZENIE]]\n\n{REFUSAL}",
    ],
)
def test_strip_removes_leading_marker_and_whitespace(raw):
    assert strip_violation_marker(raw) == (REFUSAL, True)


def test_strip_keeps_answer_without_marker():
    assert strip_violation_marker("Sesja zaczyna się w lutym.") == ("Sesja zaczyna się w lutym.", False)


def test_strip_keeps_marker_mentioned_later():
    text = "Gdy ktoś łamie zasady, odpowiadam ze znacznikiem [[NARUSZENIE]]."

    assert strip_violation_marker(text) == (text, False)


def test_strip_marker_only_gives_empty_answer():
    assert strip_violation_marker("[[NARUSZENIE]]  ") == ("", True)


@pytest.mark.parametrize(
    "chunks",
    [
        ["[[NARUSZENIE]] Nie mogę", " tego zrobić."],
        ["[[", "NARU", "SZENIE", "]]", " Nie mogę", " tego zrobić."],
        ["[", "[", "N", "A", "R", "U", "S", "Z", "E", "N", "I", "E", "]", "]", " ", "Nie mogę tego zrobić."],
        ["  ", "\n[[NARUSZ", "ENIE]]", "   ", "\n", "Nie mogę tego zrobić."],
        ["[[NARUSZENIE]]", "Nie mogę tego zrobić."],
    ],
)
def test_stream_never_leaks_split_marker(chunks):
    visible_chunks, text, detected = _stream(chunks)

    assert detected is True
    assert text == "Nie mogę tego zrobić."
    assert all("[" not in chunk and "NARU" not in chunk for chunk in visible_chunks)


def test_stream_without_marker_passes_text_through():
    chunks = ["Sesja ", "zaczyna się ", "w lutym."]

    visible_chunks, text, detected = _stream(chunks)

    assert detected is False
    assert text == "Sesja zaczyna się w lutym."
    assert visible_chunks == chunks


def test_stream_releases_buffer_as_soon_as_prefix_breaks():
    marker_filter = MarkerFilter()

    assert marker_filter.feed("[[") == ""
    assert marker_filter.feed("link]] do USOS") == "[[link]] do USOS"
    assert marker_filter.feed(" i dalej") == " i dalej"
    assert marker_filter.detected is False


def test_stream_keeps_marker_mentioned_later():
    _, text, detected = _stream(["Odpowiadam ", "ze znacznikiem ", "[[NARUSZENIE]]", " gdy trzeba."])

    assert detected is False
    assert text == "Odpowiadam ze znacznikiem [[NARUSZENIE]] gdy trzeba."


def test_stream_ending_inside_marker_prefix_returns_buffered_text():
    _, text, detected = _stream(["[[NARU"])

    assert detected is False
    assert text == "[[NARU"


def test_stream_with_marker_only_is_empty():
    _, text, detected = _stream(["[[NARUSZENIE]]", "  "])

    assert detected is True
    assert text == ""
