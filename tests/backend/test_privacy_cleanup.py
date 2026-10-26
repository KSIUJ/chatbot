"""
Sprzatanie danych, ktore nie powinny przezyc usuniecia: VACUUM wolnych stron
bazy SQLite, log dostepu bez pobran fasady okazji (zdradzalyby harmonogram)
i bez zapytania powrotu z USOS (jednorazowy token i verifier).
"""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.backend.database import vacuum_free_pages
from src.backend.main import redact_usos_callback, skip_facade_requests


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("172.18.0.3:5000", "GET", path, "1.1", 200), None,
    )


def test_vacuum_reclaims_pages_left_by_deleted_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE notes (body TEXT)"))
        for _ in range(200):
            connection.execute(text("INSERT INTO notes VALUES (:body)"), {"body": "tajne " * 200})
        connection.execute(text("DELETE FROM notes"))
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA freelist_count").scalar_one() > 0

    with Session(engine) as db:
        assert vacuum_free_pages(db) == 0

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA freelist_count").scalar_one() == 0
    assert b"tajne" not in (tmp_path / "chat.db").read_bytes()


def test_facade_requests_are_left_out_of_the_access_log():
    assert not skip_facade_requests(_access_record("/occasion/facade/0123456789abcdef?scheme=dark"))
    assert skip_facade_requests(_access_record("/occasion"))
    assert skip_facade_requests(_access_record("/conversations"))


def test_usos_callback_query_is_redacted_in_the_access_log():
    record = _access_record("/usos/callback?oauth_token=abcdefgh12&oauth_verifier=12345678")

    assert redact_usos_callback(record)

    message = record.getMessage()
    assert "abcdefgh12" not in message and "12345678" not in message
    assert "/usos/callback?[redacted]" in message
    other = _access_record("/usos/status")
    assert redact_usos_callback(other) and "/usos/status" in other.getMessage()
