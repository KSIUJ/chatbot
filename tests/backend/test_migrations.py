"""
Migracje (security_incidents, limity, zalaczniki, OCR, blokady, usos_links):
upgrade tworzy tabele/kolumny, downgrade o jeden krok je usuwa, a ponowny
upgrade dziala (pusta baza SQLite w tmp).
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


ATTACHMENTS_REVISION = "f1a7c3e9b2d4"


def test_attachments_migration_up_and_down(alembic_config):
    config, url = alembic_config

    command.upgrade(config, ATTACHMENTS_REVISION)
    assert {"attachments", "daily_attachment_usage"} <= _tables(url)
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("attachments")}
        indexes = {i["name"] for i in inspector.get_indexes("attachments")}
        usage_columns = {c["name"] for c in inspector.get_columns("daily_attachment_usage")}
        usage_pk = inspector.get_pk_constraint("daily_attachment_usage")["constrained_columns"]
    finally:
        engine.dispose()
    assert {
        "id", "user_id", "conversation_id", "message_id", "name", "kind", "mime", "size",
        "storage_key", "text", "pages", "injection_rules", "created_at",
    } <= columns
    assert {
        "ix_attachments_user_id", "ix_attachments_conversation_id", "ix_attachments_message_id",
        "ix_attachments_created_at",
    } <= indexes
    assert usage_columns == {"user_id", "day", "count"}
    assert usage_pk == ["user_id", "day"]

    command.downgrade(config, LIMITS_REVISION)
    tables = _tables(url)
    assert not {"attachments", "daily_attachment_usage"} & tables
    assert "daily_usage" in tables

    command.upgrade(config, "head")
    assert {"attachments", "daily_attachment_usage"} <= _tables(url)


OCR_REVISION = "b7d2e4f6a8c1"


def test_attachment_ocr_migration_up_and_down(alembic_config):
    config, url = alembic_config

    command.upgrade(config, OCR_REVISION)
    engine = create_engine(url)
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("attachments")}
    finally:
        engine.dispose()
    assert "ocr" in columns
    assert columns["ocr"]["nullable"] is False

    command.downgrade(config, ATTACHMENTS_REVISION)
    engine = create_engine(url)
    try:
        assert "ocr" not in {c["name"] for c in inspect(engine).get_columns("attachments")}
    finally:
        engine.dispose()

    command.upgrade(config, "head")


BLOCKS_REVISION = "a9c4e7b2d1f3"
BLOCK_COLUMNS = {"chat_blocked_at", "warnings_reset_at"}


def _user_columns(url: str) -> dict[str, dict]:
    engine = create_engine(url)
    try:
        return {c["name"]: c for c in inspect(engine).get_columns("users")}
    finally:
        engine.dispose()


def test_chat_blocks_migration_up_and_down(alembic_config):
    config, url = alembic_config

    command.upgrade(config, BLOCKS_REVISION)
    columns = _user_columns(url)
    assert BLOCK_COLUMNS <= set(columns)
    assert all(columns[name]["nullable"] for name in BLOCK_COLUMNS)

    command.downgrade(config, OCR_REVISION)
    assert not BLOCK_COLUMNS & set(_user_columns(url))

    command.upgrade(config, "head")
    assert BLOCK_COLUMNS <= set(_user_columns(url))


USOS_REVISION = "d3b8f1c6e2a7"


def test_usos_links_migration_up_and_down(alembic_config):
    config, url = alembic_config

    command.upgrade(config, USOS_REVISION)
    assert "usos_links" in _tables(url)
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        columns = {c["name"]: c for c in inspector.get_columns("usos_links")}
        pk = inspector.get_pk_constraint("usos_links")["constrained_columns"]
        [fk] = inspector.get_foreign_keys("usos_links")
    finally:
        engine.dispose()
    assert set(columns) == {
        "user_id", "usos_user_id", "usos_name", "token_enc", "scopes", "created_at", "last_used_at",
        "needs_reconnect_at",
    }
    assert pk == ["user_id"]
    assert fk["referred_table"] == "users" and fk["options"].get("ondelete") == "CASCADE"
    assert columns["token_enc"]["nullable"] is False
    assert columns["needs_reconnect_at"]["nullable"] is True

    command.downgrade(config, BLOCKS_REVISION)
    tables = _tables(url)
    assert "usos_links" not in tables
    assert "users" in tables

    command.upgrade(config, "head")
    assert "usos_links" in _tables(url)


PERSONAL_DATA_REVISION = "e5c2a9d4f1b8"


def _message_columns(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("messages")}
    finally:
        engine.dispose()


def test_message_personal_data_migration_up_and_down(alembic_config):
    config, url = alembic_config

    command.upgrade(config, PERSONAL_DATA_REVISION)
    assert "personal_data" in _message_columns(url)

    command.downgrade(config, USOS_REVISION)
    assert "personal_data" not in _message_columns(url)

    command.upgrade(config, "head")
    assert "personal_data" in _message_columns(url)
