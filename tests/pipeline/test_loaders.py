"""Testy loaderow pipeline/ingest (from_strony, from_mordor) i wspolnego chunkingu."""

import os

from pipeline.ingest import chunking, from_mordor, from_strony
from src.backend.rag.schema import make_id

SCRAPED = (
    "\n\nURL: https://matinf.uj.edu.pl/a\n\nDziekanat czynny pon-pt."
    "\n\nURL: https://matinf.uj.edu.pl/pusta\n\n   "
    "\n\nURL: https://nkr.si/b\n\nKolo naukowe."
)


def test_splitter_keeps_chunk_parameters():
    splitter = chunking.make_splitter()

    assert (chunking.CHUNK_SIZE, chunking.CHUNK_OVERLAP) == (1000, 200)
    assert all(len(chunk) <= 1000 for chunk in splitter.split_text("slowo " * 1000))


def test_strony_parses_pages_and_skips_empty(tmp_path):
    path = tmp_path / "website_data.txt"
    path.write_text(SCRAPED, encoding="utf-8")

    documents = from_strony.load_documents(str(path))

    assert [d.metadata["url"] for d in documents] == [
        "https://matinf.uj.edu.pl/a",
        "https://nkr.si/b",
    ]
    assert documents[0].id == make_id("strony", "https://matinf.uj.edu.pl/a", "0")
    assert documents[1].metadata["domain"] == "nkr.si"


def test_strony_falls_back_to_legacy_file_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(os.path.join("data", "strony"))
    with open(from_strony.LEGACY_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(SCRAPED)

    assert len(from_strony.load_documents()) == 2

    with open(from_strony.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n\nURL: https://nkr.si/nowy\n\nNowa tresc.")

    assert [d.metadata["url"] for d in from_strony.load_documents()] == ["https://nkr.si/nowy"]


def test_strony_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert from_strony.load_documents() == []


def test_mordor_image_embed_text_is_relative_to_given_directory(tmp_path):
    directory = str(tmp_path / "mordor")
    file_path = os.path.join(directory, "mapy", "plan_budynku-A.png")

    document = from_mordor._image_document(file_path, directory)

    assert document.embed_text == "mapy plan budynku A"
    assert document.id == make_id("mordor", file_path)
    assert document.value == file_path
    assert document.content_type == "image"
