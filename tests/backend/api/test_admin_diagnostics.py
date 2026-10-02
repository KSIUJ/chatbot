"""
GET /admin/diagnostics: model (dostawca, nazwa, statystyki wywolan z pamieci),
uzycie (pytania i aktywni uzytkownicy), liczby wierszy, indeks RAG, baza
i dysk. Brak dowolnego elementu daje null + opis bledu zamiast 500.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.backend import main as main_module
from src.backend.admin.diagnostics import DiagnosticsCache, DiagnosticsConfig, get_diagnostics_cache, get_diagnostics_config
from src.backend.limits.usage import consume_question, get_clock
from src.backend.llm import stats as llm_stats
from src.backend.models import Conversation, Message, MessageFeedback, MessageRole, SecurityIncident, User

from fake_keycloak import ADMIN_GROUP, MEMBER_GROUP, login

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_clock():
    main_module.app.dependency_overrides[get_clock] = lambda: (lambda: NOW)


@pytest.fixture(autouse=True)
def fresh_stats(monkeypatch):
    stats = llm_stats.LlmStats(window=50)
    monkeypatch.setattr(llm_stats, "LLM_STATS", stats)
    return stats


@pytest.fixture
def config(tmp_path, client) -> DiagnosticsConfig:
    dataset = tmp_path / "dataset"
    cfg = DiagnosticsConfig(
        dataset_dir=dataset,
        vectorstore_dir=dataset / "vectorstore",
        lexical_db=dataset / "lexical.db",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
    )
    main_module.app.dependency_overrides[get_diagnostics_config] = lambda: cfg
    # kazdy test liczy diagnostyke od nowa (bez wspolnego cache)
    main_module.app.dependency_overrides[get_diagnostics_cache] = lambda: DiagnosticsCache(ttl_seconds=0)
    return cfg


@pytest.fixture
def admin(client, config):
    login(client, client.keycloak, "boss", groups=[MEMBER_GROUP, ADMIN_GROUP])
    return client


def _make_lexical(path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(doc_id UNINDEXED, source UNINDEXED, title, text)")
        con.executemany("INSERT INTO chunks_fts VALUES (?, ?, ?, ?)", [(str(i), "strony", "t", "x") for i in range(rows)])
        con.commit()
    finally:
        con.close()


def test_missing_rag_index_gives_nulls_with_errors(admin):
    response = admin.get("/admin/diagnostics")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rag = response.json()["rag"]
    assert rag["vector_count"] is None and rag["vector_error"]
    assert rag["lexical_count"] is None and rag["lexical_error"]
    assert rag["last_ingest_at"] is None and rag["last_ingest_error"]


def test_lexical_index_and_last_ingest(admin, config):
    _make_lexical(config.lexical_db, 7)

    rag = admin.get("/admin/diagnostics").json()["rag"]

    assert rag["lexical_count"] == 7
    assert rag["lexical_size_bytes"] > 0
    assert rag["lexical_error"] is None
    assert rag["last_ingest_at"] is not None
    assert rag["last_ingest_error"] is None


def test_broken_vectorstore_does_not_crash(admin, config):
    config.vectorstore_dir.mkdir(parents=True)
    (config.vectorstore_dir / "chroma.sqlite3").write_bytes(b"not a database")

    rag = admin.get("/admin/diagnostics").json()["rag"]

    assert rag["vector_count"] is None
    assert rag["vector_error"]


def test_storage_reports_database_size_and_free_disk(admin):
    storage = admin.get("/admin/diagnostics").json()["storage"]

    assert storage["database_size_bytes"] > 0
    assert storage["database_error"] is None
    assert storage["disk_free_bytes"] > 0
    assert storage["disk_total_bytes"] >= storage["disk_free_bytes"]


def test_non_sqlite_database_has_no_file_size(admin, config):
    main_module.app.dependency_overrides[get_diagnostics_config] = lambda: DiagnosticsConfig(
        dataset_dir=config.dataset_dir,
        vectorstore_dir=config.vectorstore_dir,
        lexical_db=config.lexical_db,
        database_url="postgresql://user:secret@db/chatbot",
    )

    body = admin.get("/admin/diagnostics").json()

    assert body["storage"]["database_size_bytes"] is None
    assert body["storage"]["database_error"]
    assert "secret" not in str(body)


def test_llm_section_shows_provider_model_and_call_stats(admin, monkeypatch, fresh_stats):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-very-secret")
    fresh_stats.record_success(0.2)
    fresh_stats.record_success(0.4)
    fresh_stats.record_error(1.0, RuntimeError("upstream 502 for key sk-very-secret"))

    body = admin.get("/admin/diagnostics").json()
    llm = body["llm"]

    assert llm["provider"] == "openrouter"
    assert llm["model"] == "google/gemini-2.5-flash"
    assert llm["total_calls"] == 3
    assert llm["total_errors"] == 1
    assert llm["avg_latency_ms"] == pytest.approx(300)
    assert llm["p95_latency_ms"] == pytest.approx(400)
    assert "upstream 502" in llm["last_error"]
    assert llm["last_error_at"] is not None
    assert llm["uptime_seconds"] >= 0
    assert "sk-very-secret" not in str(body)


def test_usage_and_totals(admin):
    db = admin.session_factory()
    try:
        boss = db.query(User).filter_by(oidc_sub="boss").one()
        alice = User(oidc_sub="alice")
        db.add(alice)
        db.commit()
        consume_question(db, boss.id, NOW)
        consume_question(db, boss.id, NOW)
        consume_question(db, alice.id, NOW - timedelta(days=3))
        consume_question(db, alice.id, NOW - timedelta(days=10))
        conversation = Conversation(user_id=alice.id)
        db.add(conversation)
        db.commit()
        db.add(Message(conversation_id=conversation.id, role=MessageRole.USER, content="q"))
        db.add(MessageFeedback(answer="a", report_reason="wrong", report_status="open"))
        db.add(MessageFeedback(answer="b", report_reason="wrong", report_status="resolved"))
        db.add(SecurityIncident(question="q", source="heuristic", rules=["x"], status="open"))
        db.commit()
    finally:
        db.close()

    body = admin.get("/admin/diagnostics").json()

    assert body["usage"] == {
        "questions_today": 2,
        "questions_7d": 3,
        "active_users_today": 1,
        "active_users_7d": 2,
        "error": None,
    }
    totals = body["totals"]
    assert (totals["users"], totals["conversations"], totals["messages"]) == (2, 1, 1)
    assert (totals["open_reports"], totals["open_incidents"]) == (1, 1)
    assert totals["error"] is None


def test_last_ingest_ignores_files_touched_by_opening_chroma(admin, config):
    _make_lexical(config.lexical_db, 1)
    config.vectorstore_dir.mkdir(parents=True)
    segment = config.vectorstore_dir / "segment" / "data_level0.bin"
    segment.parent.mkdir()
    segment.write_bytes(b"x")
    chroma_db = config.vectorstore_dir / "chroma.sqlite3"
    chroma_db.write_bytes(b"x")
    ingest_time = datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc).timestamp()
    for path in (config.lexical_db, segment):
        os.utime(path, (ingest_time, ingest_time))

    rag = admin.get("/admin/diagnostics").json()["rag"]

    assert datetime.fromisoformat(rag["last_ingest_at"]).timestamp() == pytest.approx(ingest_time)


class FakeMonotonic:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_diagnostics_are_cached_and_refresh_bypasses_the_cache(admin, fresh_stats):
    timer = FakeMonotonic()
    cache = DiagnosticsCache(ttl_seconds=15, monotonic=timer)
    main_module.app.dependency_overrides[get_diagnostics_cache] = lambda: cache

    first = admin.get("/admin/diagnostics").json()
    fresh_stats.record_success(0.1)
    cached = admin.get("/admin/diagnostics").json()
    refreshed = admin.get("/admin/diagnostics", params={"refresh": 1}).json()

    assert cached == first
    assert refreshed["llm"]["total_calls"] == 1

    fresh_stats.record_success(0.1)
    timer.now += 16
    expired = admin.get("/admin/diagnostics").json()
    assert expired["llm"]["total_calls"] == 2


def test_cache_is_thread_safe_and_computes_once():
    import threading

    cache = DiagnosticsCache(ttl_seconds=15)
    calls = []
    start = threading.Barrier(8)

    def compute():
        calls.append(1)
        return len(calls)

    results = []

    def worker():
        start.wait()
        results.append(cache.get(compute, refresh=False))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == [1]
    assert results == [1] * 8


def test_error_strings_contain_no_file_paths(admin, config, tmp_path):
    config.vectorstore_dir.mkdir(parents=True)
    (config.vectorstore_dir / "chroma.sqlite3").write_bytes(b"not a database")

    body = admin.get("/admin/diagnostics").json()

    errors = [body["rag"]["vector_error"], body["rag"]["lexical_error"], body["rag"]["last_ingest_error"]]
    assert all(errors)
    for error in errors:
        assert tmp_path.as_posix() not in error
        assert str(tmp_path) not in error
        assert "dataset" not in error
