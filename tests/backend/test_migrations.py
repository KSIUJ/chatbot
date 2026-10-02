"""
Migracja security_incidents: upgrade do head tworzy tabele, downgrade o
jeden krok ja usuwa, a ponowny upgrade dziala (pusta baza SQLite w tmp).
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from src.backend import database

REPO_ROOT = Path(__file__).resolve().parents[2]
INCIDENTS_REVISION = "c7e3a9d5f1b2"


@pytest.fixture
def alembic_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, str]:
    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    # alembic/env.py czyta src.backend.database.DATABASE_URL przy kazdym uruchomieniu
    monkeypatch.setattr(database, "DATABASE_URL", url)
    # bez alembic.ini - fileConfig w env.py wylaczylby loggery innych testow
    config = Config()
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return config, url


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_incidents_migration_up_and_down(alembic_config):
    config, url = alembic_config

    command.upgrade(config, "head")
    assert "security_incidents" in _tables(url)
    engine = create_engine(url)
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("security_incidents")}
        indexes = {i["name"] for i in inspect(engine).get_indexes("security_incidents")}
    finally:
        engine.dispose()
    assert {
        "id", "user_id", "conversation_id", "message_id", "question", "source", "rules", "status",
        "admin_note", "reviewed_by", "reviewed_at", "created_at", "updated_at",
    } <= columns
    assert {"ix_security_incidents_user_id", "ix_security_incidents_status", "ix_security_incidents_created_at"} <= indexes

    command.downgrade(config, "b4d9e2f1a8c3")
    tables = _tables(url)
    assert "security_incidents" not in tables
    assert "message_feedback" in tables

    command.upgrade(config, INCIDENTS_REVISION)
    assert "security_incidents" in _tables(url)
