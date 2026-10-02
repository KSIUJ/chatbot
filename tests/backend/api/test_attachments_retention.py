"""
Retencja zalacznikow (malo miejsca na dysku VM): pliki znikaja razem
z rozmowa (usuniecie przez uzytkownika, wygasniecie po N dniach, wypchniecie
przez limit rozmow), a niewyslane - po 24 h (zadanie sprzatajace w tle).
SQLite dziala tu bez wymuszania kluczy obcych, wiec kasowanie jest jawne.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from sqlalchemy import select, update

from src.backend import main as main_module
from src.backend.attachments import storage as storage_module
from src.backend.attachments.service import UNSENT_RETENTION, purge_stale_attachments
from src.backend.history import (
    get_history_settings,
    make_room_for_new_conversation,
    purge_expired_conversations,
)
from src.backend.models import Attachment, Conversation

NOW = datetime.now(timezone.utc)


@pytest.fixture
def member(client, member_override):
    client.user_id = member_override
    return client


def upload(client, data: bytes = b"tresc", name: str = "a.txt") -> str:
    response = client.post(
        "/attachments", content=data,
        headers={"X-Filename": quote(name), "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _dir() -> Path:
    return Path(os.environ["ATTACHMENTS_DIR"])


def _files() -> set[str]:
    return {p.name for p in _dir().iterdir()} if _dir().exists() else set()


def _rows(client) -> list[Attachment]:
    db = client.session_factory()
    try:
        return list(db.execute(select(Attachment)).scalars())
    finally:
        db.close()


def _send(client, attachment_id: str, conversation_id: str | None = None) -> str:
    body = {"message": "streszcz", "attachment_ids": [attachment_id]}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    return client.post("/chat", json=body).json()["conversation_id"]


def _age(client, attachment_id: str, delta: timedelta) -> None:
    db = client.session_factory()
    db.execute(update(Attachment).where(Attachment.id == attachment_id).values(created_at=NOW - delta))
    db.commit()
    db.close()


def test_deleting_conversation_deletes_its_attachments(member):
    kept = upload(member, b"inna", "b.txt")
    cid = _send(member, upload(member))

    assert member.delete(f"/conversations/{cid}").status_code == 204

    assert [r.id for r in _rows(member)] == [kept]
    assert _files() == {_rows(member)[0].storage_key}


def test_expired_conversations_take_attachments_with_them(member):
    cid = _send(member, upload(member))
    db = member.session_factory()
    db.execute(update(Conversation).values(last_message_at=NOW - timedelta(days=40)))
    db.commit()

    purge_expired_conversations(db, retention_days=30)
    db.close()

    assert _rows(member) == []
    assert _files() == set()
    assert cid


def test_evicted_conversation_takes_attachments_with_it(member):
    oldest = _send(member, upload(member))
    db = member.session_factory()

    make_room_for_new_conversation(db, member.user_id, max_per_user=1)
    db.close()

    assert _rows(member) == []
    assert _files() == set()
    assert oldest


def test_eviction_through_chat_limit(member, monkeypatch):
    monkeypatch.setenv("CHAT_HISTORY_MAX_PER_USER", "1")
    get_history_settings.cache_clear()
    _send(member, upload(member, b"pierwszy", "1.txt"))

    _send(member, upload(member, b"drugi", "2.txt"))

    assert [r.name for r in _rows(member)] == ["2.txt"]
    assert len(_files()) == 1


def test_file_deletion_failure_is_logged_not_fatal(member, monkeypatch, caplog):
    cid = _send(member, upload(member))

    def broken_unlink(self, missing_ok=False):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", broken_unlink)
    with caplog.at_level(logging.WARNING, logger="src.backend.attachments"):
        response = member.delete(f"/conversations/{cid}")

    assert response.status_code == 204
    assert _rows(member) == []
    assert "locked" in caplog.text or "deleting attachment file" in caplog.text


# --- sprzatanie w tle -----------------------------------------------------------------------

def test_cleanup_removes_old_unsent_attachments_only(member):
    old_unsent = upload(member, b"stary", "stary.txt")
    fresh_unsent = upload(member, b"nowy", "nowy.txt")
    old_sent = upload(member, b"wyslany", "wyslany.txt")
    _send(member, old_sent)
    _age(member, old_unsent, UNSENT_RETENTION + timedelta(minutes=1))
    _age(member, old_sent, UNSENT_RETENTION + timedelta(days=3))

    db = member.session_factory()
    deleted = purge_stale_attachments(db)
    db.close()

    assert deleted == 1
    assert {r.id for r in _rows(member)} == {fresh_unsent, old_sent}
    assert len(_files()) == 2


def test_cleanup_removes_rows_of_missing_conversations(member):
    attachment_id = upload(member)
    _send(member, attachment_id)
    db = member.session_factory()
    # rozmowa skasowana z pominieciem kodu zalacznikow (np. starsza wersja)
    db.execute(Conversation.__table__.delete())
    db.commit()

    purge_stale_attachments(db)
    db.close()

    assert _rows(member) == []
    assert _files() == set()


def test_cleanup_removes_stray_files_but_not_fresh_ones(member, monkeypatch):
    attachment_id = upload(member)
    _dir().mkdir(parents=True, exist_ok=True)
    stray_old = _dir() / ("1" * 32 + ".part")
    stray_old.write_bytes(b"przerwane wysylanie")
    old = (NOW - UNSENT_RETENTION - timedelta(hours=1)).timestamp()
    os.utime(stray_old, (old, old))
    stray_fresh = _dir() / ("2" * 32 + ".part")
    stray_fresh.write_bytes(b"trwa wysylanie")

    db = member.session_factory()
    purge_stale_attachments(db)
    db.close()

    assert not stray_old.exists()
    assert stray_fresh.exists()
    assert attachment_id in {r.id for r in _rows(member)}


def test_cleanup_job_is_registered(member):
    jobs = main_module.cleanup_jobs(get_history_settings())

    assert "attachments" in jobs


def test_storage_never_touches_files_outside_its_directory(tmp_path, monkeypatch):
    outside = tmp_path / "outside.txt"
    outside.write_text("nie ruszac")
    monkeypatch.setenv("ATTACHMENTS_DIR", str(tmp_path / "uploads"))

    storage_module.remove_files(["../outside.txt", "..", ""])

    assert outside.exists()
