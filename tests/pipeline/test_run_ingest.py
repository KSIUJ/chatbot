"""
pipeline/ingest/run_ingest.py: stare polecenie przekierowane na CLI indeksu
(src/backend/rag/index.py).
"""

import pytest

from pipeline.ingest import run_ingest


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ["sync"]),
        (["--source", "usos"], ["sync", "--source", "usos"]),
        (["--source", "usos", "--purge"], ["build", "--source", "usos"]),
        (["--purge"], ["build"]),
        (["--rebuild-lexical"], ["build"]),
    ],
)
def test_old_flags_map_to_index_commands(argv, expected):
    assert run_ingest.index_args(argv) == expected


def test_main_delegates_to_index_cli(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(run_ingest, "index_main", lambda args: calls.append(args) or 0)

    assert run_ingest.main(["--source", "mordor"]) == 0
    assert calls == [["sync", "--source", "mordor"]]
    assert "src.backend.rag.index sync --source mordor" in capsys.readouterr().out
