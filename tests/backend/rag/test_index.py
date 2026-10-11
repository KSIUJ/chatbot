"""
Testy CLI indeksu (src/backend/rag/index.py) i ukladu katalogow
(core/index_store.py): build w nowym katalogu z atomowym przelaczeniem
CURRENT, sync tylko zmienionych dokumentow, wznawianie przerwanego buildu,
rollback i sledzenie wskaznika przez VectorStore/LexicalIndex backendu.
Realna ChromaDB i SQLite, FakeEncoder zamiast modelu.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.backend.rag import index as cli
from src.backend.rag.core import chunking, index_store
from src.backend.rag.core.documents import Document
from src.backend.rag.core.encoder import configured_settings
from src.backend.rag.core.lexical import LexicalIndex
from src.backend.rag.core.vectorstore import VectorStore

START = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def _doc(id_: str, source: str, text: str | None = None, **metadata) -> Document:
    text = text or f"tresc {id_}"
    return Document(id=id_, source=source, embed_text=text, content_type="text", value=text, metadata=metadata)


class Clock:
    def __init__(self) -> None:
        self.moment = START

    def __call__(self) -> datetime:
        self.moment += timedelta(minutes=1)
        return self.moment


class CountingEncoder:
    """FakeEncoder liczacy embedowane teksty; opcjonalnie pada po N partiach."""

    def __init__(self, inner, fail_after: int | None = None) -> None:
        self.inner = inner
        self.embedded: list[str] = []
        self.fail_after = fail_after

    def embed_batch(self, texts):
        if self.fail_after is not None and len(self.embedded) >= self.fail_after:
            raise RuntimeError("restart maszyny")
        self.embedded += texts
        return self.inner.embed_batch(texts)

    def embed_query(self, query):
        return self.inner.embed_query(query)


@pytest.fixture
def env(tmp_path, fake_encoder):
    data = {
        "usos": [_doc("usos_1", "usos"), _doc("usos_2", "usos")],
        "mordor": [_doc(f"mordor_{i}", "mordor") for i in range(3)],
    }

    class Env:
        dataset = tmp_path / "dataset"
        data_dir = tmp_path / "data"
        clock = Clock()
        encoder = CountingEncoder(fake_encoder)
        docs = data

        def loaders(self):
            return {name: (lambda name=name: list(self.docs[name])) for name in self.docs}

        def run(self, command, sources=None, **kwargs):
            kwargs.setdefault("encoder", self.encoder)
            return command(
                sources,
                dataset_dir=self.dataset,
                data_dir=self.data_dir,
                loaders=self.loaders(),
                now=self.clock,
                **kwargs,
            )

        def current(self):
            return index_store.read_pointer(self.dataset)

        def stores(self, directory=None):
            location = index_store.index_location(directory or self.current())
            return (
                VectorStore(persist_dir=str(location.vectorstore), encoder=fake_encoder),
                LexicalIndex(str(location.lexical)),
            )

    return Env()


def _write_manifest(data_dir, source: str) -> None:
    (data_dir / source).mkdir(parents=True, exist_ok=True)
    (data_dir / source / "manifest.json").write_text(
        json.dumps(
            {
                "source": source,
                "format_version": 1,
                "collected_at": "2026-10-10T08:00:00+02:00",
                "collector": "test@1",
                "files": ["records.jsonl"],
            }
        ),
        encoding="utf-8",
    )


def test_build_creates_index_dir_switches_pointer_and_writes_meta(env):
    _write_manifest(env.data_dir, "usos")

    result = env.run(cli.build)

    assert result.switched
    assert env.current() == result.directory
    assert result.directory.parent == env.dataset / "indexes"
    assert (env.dataset / "CURRENT").read_text().strip() == f"indexes/{result.directory.name}"
    assert not (result.directory / index_store.BUILDING_FILE).exists()

    meta = index_store.read_meta(result.directory)
    assert meta["format_version"] == index_store.FORMAT_VERSION
    assert meta["embedding"] == configured_settings()
    assert meta["chunking"] == {"chunk_size": chunking.CHUNK_SIZE, "chunk_overlap": chunking.CHUNK_OVERLAP}
    assert meta["documents"] == 5
    assert meta["sources"]["usos"]["documents"] == meta["sources"]["usos"]["lexical"] == 2
    assert meta["sources"]["usos"]["dataset"] == {"collected_at": "2026-10-10T06:00:00Z", "collector": "test@1"}
    assert meta["sources"]["mordor"]["dataset"] is None

    store, lexical = env.stores()
    assert store.source_counts() == lexical.source_counts() == {"usos": 2, "mordor": 3}


def test_sync_without_changes_keeps_the_current_index(env):
    first = env.run(cli.build)
    env.encoder.embedded.clear()

    again = env.run(cli.sync)

    assert not again.switched
    assert again.directory == first.directory == env.current()
    assert {name: c.unchanged for name, c in again.counts.items()} == {"usos": 2, "mordor": 3}
    assert all(c.changed == 0 for c in again.counts.values())
    assert env.encoder.embedded == []
    assert [d.name for d in index_store.list_indexes(env.dataset)] == [first.directory.name]


def test_sync_upserts_changed_and_deletes_missing_documents(env):
    first = env.run(cli.build)
    env.encoder.embedded.clear()
    env.docs["usos"] = [_doc("usos_1", "usos", "nowa tresc pracownika"), _doc("usos_3", "usos")]

    result = env.run(cli.sync)

    usos = result.counts["usos"]
    assert (usos.added, usos.updated, usos.deleted, usos.unchanged) == (1, 1, 1, 0)
    assert result.counts["mordor"].unchanged == 3
    assert sorted(env.encoder.embedded) == sorted(["nowa tresc pracownika", "tresc usos_3"])
    assert result.switched and env.current() == result.directory != first.directory

    store, lexical = env.stores()
    assert set(store.source_hashes("usos")) == lexical.source_ids("usos") == {"usos_1", "usos_3"}
    assert store.get_by_ids(["usos_1"])[0]["value"] == "nowa tresc pracownika"
    assert lexical.search(["nowa"], ("usos",)) == ["usos_1"]
    assert index_store.read_meta(result.directory)["sources"]["usos"]["last_change"] == {
        "added": 1, "updated": 1, "deleted": 1, "unchanged": 0
    }

    # poprzedni indeks nietkniety (rollback)
    old_store, old_lexical = env.stores(first.directory)
    assert set(old_store.source_hashes("usos")) == old_lexical.source_ids("usos") == {"usos_1", "usos_2"}


def test_sync_changed_metadata_counts_as_update(env):
    env.run(cli.build)
    env.docs["usos"] = [_doc("usos_1", "usos", url="https://nowy"), _doc("usos_2", "usos")]

    result = env.run(cli.sync, ["usos"])

    assert (result.counts["usos"].updated, result.counts["usos"].unchanged) == (1, 1)
    assert set(result.counts) == {"usos"}


def test_sync_keeps_source_whose_loader_returns_nothing(env, capsys):
    env.run(cli.build)
    env.docs["usos"] = []

    result = env.run(cli.sync)

    assert "usos" not in result.counts
    store, _ = env.stores()
    assert store.source_counts()["usos"] == 2
    assert "UWAGA" in capsys.readouterr().out


def test_sync_without_current_index_builds_one(env):
    result = env.run(cli.sync)

    assert result.switched and env.current() == result.directory
    assert index_store.read_meta(result.directory)["kind"] == "build"


def test_interrupted_build_resumes_without_touching_live_index(env, fake_encoder):
    live = env.run(cli.build).directory
    env.docs["mordor"] = [_doc(f"mordor_{i}", "mordor", f"inna {i}") for i in range(5)]
    failing = CountingEncoder(fake_encoder, fail_after=2)

    with pytest.raises(RuntimeError, match="restart"):
        env.run(cli.build, encoder=failing, batch_size=2)

    assert env.current() == live
    partial = [d for d in index_store.list_indexes(env.dataset) if not index_store.is_complete(d)]
    assert len(partial) == 1

    resumed = CountingEncoder(fake_encoder)
    result = env.run(cli.build, encoder=resumed, batch_size=2)

    assert result.directory == partial[0]
    assert env.current() == partial[0]
    # pierwsza partia mordoru (2) zapisana przed przerwaniem: wznowienie embeduje 3 + usos 2
    assert len(resumed.embedded) == 5
    store, lexical = env.stores()
    assert store.source_counts() == lexical.source_counts() == {"usos": 2, "mordor": 5}


def test_build_of_selected_source_carries_over_the_rest(env):
    env.run(cli.build)
    env.encoder.embedded.clear()
    env.docs["mordor"] = [_doc("mordor_9", "mordor")]
    env.docs["usos"] = [_doc("usos_1", "usos", "zmiana, ktorej build mordoru nie widzi")]

    result = env.run(cli.build, ["mordor"])

    assert env.encoder.embedded == ["tresc mordor_9"]
    store, lexical = env.stores()
    assert set(store.source_hashes("mordor")) == lexical.source_ids("mordor") == {"mordor_9"}
    assert set(store.source_hashes("usos")) == {"usos_1", "usos_2"}
    meta = index_store.read_meta(result.directory)
    assert meta["sources"]["usos"]["documents"] == 2 and meta["base"] is not None


def test_prune_keeps_current_and_two_previous(env):
    names = []
    for i in range(5):
        env.docs["usos"] = [_doc("usos_1", "usos", f"wersja {i}")]
        names.append(env.run(cli.sync).directory.name)

    kept = [d.name for d in index_store.list_indexes(env.dataset)]
    assert kept == names[-3:]
    assert env.current().name == names[-1]


def test_rollback_and_use_switch_the_pointer(env):
    first = env.run(cli.build).directory
    env.docs["usos"] = [_doc("usos_1", "usos", "zmiana")]
    second = env.run(cli.sync).directory

    assert cli.rollback(dataset_dir=env.dataset) == first
    assert env.current() == first
    # najstarszy indeks nie ma poprzednika
    with pytest.raises(cli.IndexCommandError, match="starszego"):
        cli.rollback(dataset_dir=env.dataset)
    assert cli.use(second.name, dataset_dir=env.dataset) == second
    assert env.current() == second
    with pytest.raises(cli.IndexCommandError):
        cli.use("../etc", dataset_dir=env.dataset)


def test_sync_refuses_index_built_with_another_model(env, monkeypatch):
    env.run(cli.build)
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "inny/model")

    with pytest.raises(cli.IndexCommandError, match="build"):
        env.run(cli.sync)


def test_status_reports_counts_and_mismatches(env, monkeypatch):
    env.run(cli.build)
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "inny/model")

    report = cli.status(dataset_dir=env.dataset)

    assert report["current"] == env.current().name
    assert report["vectors"] == report["lexical"] == {"usos": 2, "mordor": 3}
    assert any("inny/model" in w for w in report["warnings"])
    assert report["indexes"] == [{"name": env.current().name, "complete": True, "current": True}]


def test_concurrent_build_is_refused(env):
    with cli._locked(env.dataset):
        with pytest.raises(cli.IndexCommandError, match="juz dziala"):
            env.run(cli.build)


def test_pointer_to_incomplete_or_foreign_dir_is_ignored(tmp_path):
    dataset = tmp_path / "dataset"
    (dataset / "indexes" / "x").mkdir(parents=True)
    (dataset / "CURRENT").write_text("indexes/x\n")
    assert index_store.read_pointer(dataset) is None
    (dataset / "CURRENT").write_text("../../etc\n")
    assert index_store.resolve(dataset) == index_store.legacy_location(dataset)


def test_backend_stores_follow_the_pointer(env, monkeypatch, fake_encoder):
    monkeypatch.chdir(env.dataset.parent)
    monkeypatch.setattr(index_store, "CHECK_INTERVAL", 0)
    env.dataset = index_store.DATASET_DIR
    env.run(cli.build)
    store = VectorStore(encoder=fake_encoder)
    lexical = LexicalIndex()
    assert store.index_name == env.current().name
    assert store.get_by_ids(["usos_2"]) and lexical.search(["usos_2"], ("usos",)) == ["usos_2"]

    env.docs["usos"] = [_doc("usos_1", "usos")]
    env.run(cli.sync)

    assert store.get_by_ids(["usos_2"]) == []
    assert lexical.search(["usos_2"], ("usos",)) == []
    assert store.index_name == env.current().name
    assert [h["id"] for h in store.query(fake_encoder.embed_query("tresc usos_1"), 1, ("usos",))] == ["usos_1"]


def test_backend_store_without_pointer_uses_legacy_layout(tmp_path, monkeypatch, fake_encoder):
    monkeypatch.chdir(tmp_path)
    store = VectorStore(encoder=fake_encoder)
    assert store.index_name is None
    assert (tmp_path / "dataset" / "vectorstore").is_dir()


class NamedEncoder:
    def __init__(self, inner, model_name: str) -> None:
        self.inner = inner
        self.model_name = model_name
        self.query_prefix = configured_settings()["query_prefix"]
        self.passage_prefix = configured_settings()["passage_prefix"]

    def embed_batch(self, texts):
        return self.inner.embed_batch(texts)

    def embed_query(self, query):
        return self.inner.embed_query(query)


def test_backend_warns_when_index_was_built_with_another_model(env, monkeypatch, fake_encoder):
    monkeypatch.chdir(env.dataset.parent)
    env.dataset = index_store.DATASET_DIR
    env.run(cli.build)
    # logger podmieniony: konfiguracja logowania alembica w innych testach
    # potrafi wylaczyc istniejace loggery (caplog bylby zalezny od kolejnosci)
    warnings: list[str] = []
    monkeypatch.setattr(index_store.logger, "warning", lambda msg, *args: warnings.append(msg % args))

    store = VectorStore(encoder=NamedEncoder(fake_encoder, "inny/model"))
    assert store.mismatches
    assert len(warnings) == 1 and "inny/model" in warnings[0]

    warnings.clear()
    ok = VectorStore(encoder=NamedEncoder(fake_encoder, configured_settings()["model"]))
    assert ok.mismatches == [] and warnings == []
