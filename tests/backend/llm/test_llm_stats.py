"""
Statystyki wywolan modelu w pamieci (llm/stats.py) dla diagnostyki adminow:
liczniki od startu, opoznienia z ostatnich N wywolan, ostatni blad bez
sekretow, bezpieczenstwo watkowe i zapis w generate.answer/stream_answer.
"""

from __future__ import annotations

import threading

import pytest

from src.backend.llm import generate, stats as llm_stats
from src.backend.llm.stats import LlmStats
from src.backend.rag.context_builder import RagContext


@pytest.fixture
def fresh_stats(monkeypatch) -> LlmStats:
    stats = LlmStats(window=10)
    monkeypatch.setattr(llm_stats, "LLM_STATS", stats)
    return stats


def test_empty_snapshot():
    snapshot = LlmStats(window=5).snapshot()

    assert (snapshot.total_calls, snapshot.total_errors) == (0, 0)
    assert snapshot.avg_latency_ms is None
    assert snapshot.p95_latency_ms is None
    assert snapshot.last_error is None


def test_latency_is_computed_over_the_recent_window():
    stats = LlmStats(window=3)
    for seconds in (10.0, 0.1, 0.2, 0.3):
        stats.record_success(seconds)

    snapshot = stats.snapshot()

    assert snapshot.total_calls == 4
    assert snapshot.recent_calls == 3
    assert snapshot.avg_latency_ms == pytest.approx(200)
    assert snapshot.p95_latency_ms == pytest.approx(300)


def test_errors_are_counted_and_last_one_is_kept(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")
    stats = LlmStats(window=5)
    stats.record_error(0.5, ValueError("first"))
    stats.record_error(0.7, RuntimeError("401 for key sk-ant-secret-value"))

    snapshot = stats.snapshot()

    assert snapshot.total_errors == 2
    assert snapshot.recent_errors == 2
    assert snapshot.last_error is not None
    assert snapshot.last_error.startswith("RuntimeError: 401")
    assert "sk-ant-secret-value" not in snapshot.last_error
    assert snapshot.last_error_at is not None


def test_long_error_messages_are_truncated():
    stats = LlmStats(window=5)
    stats.record_error(0.1, RuntimeError("x" * 5000))

    assert len(stats.snapshot().last_error or "") <= llm_stats.MAX_ERROR_LENGTH


def test_recording_is_thread_safe():
    stats = LlmStats(window=1000)

    def worker() -> None:
        for _ in range(500):
            stats.record_success(0.01)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert stats.snapshot().total_calls == 4000


# --- zapis w generate.py ------------------------------------------------------------------------

def _fake_rag(monkeypatch) -> None:
    monkeypatch.setattr(generate, "condense", lambda query, history: query)
    monkeypatch.setattr(generate, "retrieve_context", lambda query, k_mordor, k_other: RagContext("", [], []))


def test_answer_records_success_and_error(monkeypatch, fresh_stats):
    _fake_rag(monkeypatch)
    monkeypatch.setattr(generate, "_resolve_chat_fn", lambda: lambda **kwargs: "ok")
    generate.answer("pytanie")

    def broken(**kwargs):
        raise ConnectionError("model down")

    monkeypatch.setattr(generate, "_resolve_chat_fn", lambda: broken)
    with pytest.raises(ConnectionError):
        generate.answer("pytanie")

    snapshot = fresh_stats.snapshot()
    assert (snapshot.total_calls, snapshot.total_errors) == (2, 1)
    assert "model down" in (snapshot.last_error or "")


def test_finished_stream_is_recorded(monkeypatch, fresh_stats):
    _fake_rag(monkeypatch)

    def fake_stream(**kwargs):
        yield "a"
        yield "b"

    monkeypatch.setattr(generate, "_resolve_stream_fn", lambda: fake_stream)

    assert list(generate.stream_answer("pytanie").chunks) == ["a", "b"]
    assert fresh_stats.snapshot().total_calls == 1


def test_failed_stream_is_recorded_as_error(monkeypatch, fresh_stats):
    _fake_rag(monkeypatch)

    def fake_stream(**kwargs):
        yield "a"
        raise TimeoutError("read timeout")

    monkeypatch.setattr(generate, "_resolve_stream_fn", lambda: fake_stream)

    with pytest.raises(TimeoutError):
        list(generate.stream_answer("pytanie").chunks)
    assert fresh_stats.snapshot().total_errors == 1


def test_stream_closed_early_is_not_counted_and_closes_upstream(monkeypatch, fresh_stats):
    _fake_rag(monkeypatch)
    closed = []

    def fake_stream(**kwargs):
        try:
            yield "a"
            yield "b"
        finally:
            closed.append(True)

    monkeypatch.setattr(generate, "_resolve_stream_fn", lambda: fake_stream)
    chunks = generate.stream_answer("pytanie").chunks

    assert next(chunks) == "a"
    chunks.close()

    assert closed == [True]
    assert fresh_stats.snapshot().total_calls == 0


@pytest.mark.parametrize(
    ("message", "secret"),
    [
        ("connect failed: https://admin:hunter2pass@llm.example.com/v1", "hunter2pass"),
        ("redis://user:p4ssw0rd@cache:6379/0 refused", "p4ssw0rd"),
        ("401 for header Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", "eyJhbGciOiJIUzI1NiJ9.abc.def"),
        ("token bearer sk_live_1234567890 rejected", "sk_live_1234567890"),
    ],
)
def test_url_credentials_and_bearer_tokens_are_masked(message, secret):
    text = llm_stats.describe_error(RuntimeError(message))

    assert secret not in text
    assert "***" in text
