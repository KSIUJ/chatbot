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


LIMITS_REVISION = "e5b8c2d4f6a1"


def test_limits_migration_up_and_down(alembic_config):
    config, url = alembic_config

    command.upgrade(config, LIMITS_REVISION)
    tables = _tables(url)
    assert {"app_settings", "user_limits", "daily_usage"} <= tables
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        usage_columns = {c["name"] for c in inspector.get_columns("daily_usage")}
        usage_pk = inspector.get_pk_constraint("daily_usage")["constrained_columns"]
        limit_columns = {c["name"] for c in inspector.get_columns("user_limits")}
        setting_columns = {c["name"] for c in inspector.get_columns("app_settings")}
        usage_indexes = {i["name"] for i in inspector.get_indexes("daily_usage")}
    finally:
        engine.dispose()
    assert usage_columns == {"user_id", "day", "count"}
    assert usage_pk == ["user_id", "day"]
    assert {"user_id", "daily_limit", "note", "updated_by", "created_at", "updated_at"} <= limit_columns
    assert {"key", "value", "updated_by", "updated_at"} <= setting_columns
    assert "ix_daily_usage_day" in usage_indexes

    command.downgrade(config, INCIDENTS_REVISION)
    tables = _tables(url)
    assert not {"app_settings", "user_limits", "daily_usage"} & tables
    assert "security_incidents" in tables

    command.upgrade(config, "head")
    assert {"app_settings", "user_limits", "daily_usage"} <= _tables(url)
