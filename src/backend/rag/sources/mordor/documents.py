"""Rekordy materialow -> dokumenty indeksu: tekst w chunkach, skany i obrazy
jako pliki (wyszukiwane po sciezce, dolaczane do odpowiedzi)."""

from __future__ import annotations

import posixpath
from pathlib import Path

from ...core.chunking import make_splitter
from ...core.documents import Document, make_id
from .dataset import MaterialRecord


def _file_document(source: str, record: MaterialRecord, file_path: str) -> Document:
    # sciezka bez rozszerzenia, separatory jako spacje: "Analiza 1 2024 kolokwium"
    embed_text = posixpath.splitext(record.attributes.path)[0].replace("/", " ").replace("_", " ").replace("-", " ")
    return Document(
        id=make_id(source, file_path),
        source=source,
        embed_text=embed_text,
        content_type="image",
        value=file_path,
        metadata={"file_name": posixpath.basename(record.attributes.path), "directory": posixpath.dirname(file_path)},
    )


def material_documents(source: str, dataset_dir: Path, records: list[MaterialRecord]) -> list[Document]:
    splitter = make_splitter()
    documents: list[Document] = []
    for record in records:
        file_path = (dataset_dir / record.attributes.path).as_posix()
        if record.kind != "text":
            documents.append(_file_document(source, record, file_path))
            continue
        for index, chunk in enumerate(splitter.split_text(record.content)):
            documents.append(
                Document(
                    id=make_id(source, file_path, str(index)),
                    source=source,
                    embed_text=chunk,
                    content_type="text",
                    value=chunk,
                    metadata={
                        "source_file": posixpath.basename(record.attributes.path),
                        "file_type": f".{record.attributes.file_type}",
                        "directory": posixpath.dirname(file_path),
                        "chunk_index": index,
                    },
                )
            )
    return documents
