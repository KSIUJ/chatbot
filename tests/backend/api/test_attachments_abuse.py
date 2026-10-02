"""
Ochrona przed naduzyciem wysylania plikow: miejsce w dziennym limicie wraca
tylko po bledzie serwera, najwyzej MAX_CONCURRENT_UPLOADS wysylan naraz na
osobe, limit czasu na odebranie pliku, limit bajtow niewyslanych zalacznikow
na osobe, minimum wolnego miejsca na dysku i sprzatanie pliku .part w kazdym
przypadku (takze po rozlaczeniu klienta).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import quote

import anyio
import pytest
from sqlalchemy import select
from starlette.requests import ClientDisconnect

from src.backend.attachments import router as attachments_router
from src.backend.attachments.router import UploadSlots
from src.backend.models import AppSetting, Attachment, DailyAttachmentUsage



@pytest.fixture
def member(client, member_override):
    client.user_id = member_override
    yield client
    attachments_router.UPLOAD_SLOTS.reset()


def upload(client, data, name: str = "a.txt"):
    headers = {"X-Filename": quote(name), "Content-Type": "application/octet-stream"}
    return client.post("/attachments", content=data, headers=headers)


def _files() -> list[str]:
    root = Path(os.environ["ATTACHMENTS_DIR"])
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


def _uploaded_today(client) -> int:
    db = client.session_factory()
    try:
        return sum(db.execute(select(DailyAttachmentUsage.count)).scalars().all())
    finally:
        db.close()


def _rows(client) -> int:
    db = client.session_factory()
    try:
        return len(db.execute(select(Attachment)).scalars().all())
    finally:
        db.close()


def _set(client, key: str, value) -> None:
    db = client.session_factory()
    db.add(AppSetting(key=key, value=value))
    db.commit()
    db.close()


# --- zwrot miejsca tylko po bledzie serwera ------------------------------------------------

def test_server_error_refunds_the_slot_and_cleans_up(member, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(attachments_router, "create_attachment", broken)

    with pytest.raises(RuntimeError):
        upload(member, b"tekst")

    assert _uploaded_today(member) == 0
    assert _files() == []


def test_client_disconnect_is_not_refunded_and_leaves_no_part_file(member, monkeypatch):
    async def disconnecting(request, target, max_bytes):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"polowa pliku")
        raise ClientDisconnect()

    monkeypatch.setattr(attachments_router, "_receive", disconnecting)

    with pytest.raises(ClientDisconnect):
        upload(member, b"tekst")

    assert _files() == []
    assert _uploaded_today(member) == 1


# --- wysylania naraz ------------------------------------------------------------------------

def test_upload_slots_per_user():
    slots = UploadSlots(limit=2)

    assert slots.try_acquire("u1")
    assert slots.try_acquire("u1")
    assert not slots.try_acquire("u1")
    assert slots.try_acquire("u2")
    slots.release("u1")
    assert slots.try_acquire("u1")


def test_too_many_parallel_uploads_are_refused(member):
    slots = attachments_router.UPLOAD_SLOTS
    for _ in range(attachments_router.MAX_CONCURRENT_UPLOADS):
        assert slots.try_acquire(member.user_id)

    response = upload(member, b"tekst")

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "uploads_busy"
    assert _uploaded_today(member) == 0

    slots.release(member.user_id)
    assert upload(member, b"tekst").status_code == 201


def test_slot_is_released_after_every_upload(member):
    for index in range(attachments_router.MAX_CONCURRENT_UPLOADS + 2):
        upload(member, b"MZ\x90" if index % 2 else b"tekst")

    assert attachments_router.UPLOAD_SLOTS.active(member.user_id) == 0


# --- limit czasu na odebranie pliku ---------------------------------------------------------

def test_slow_upload_hits_the_deadline(member, monkeypatch):
    # TestClient buforuje cialo przed wywolaniem aplikacji, wiec wolnego
    # klienta udaje wolny odbior (prawdziwy serwer czyta cialo strumieniowo)
    monkeypatch.setattr(attachments_router, "UPLOAD_DEADLINE_SECONDS", 0.3)

    async def slow_receive(request, target, max_bytes):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"poczatek")
        await anyio.sleep(10)
        return 8

    monkeypatch.setattr(attachments_router, "_receive", slow_receive)

    started = time.monotonic()
    response = upload(member, b"tekst")

    assert time.monotonic() - started < 5
    assert response.status_code == 408
    assert response.json()["detail"]["code"] == "upload_timeout"
    assert _files() == []
    assert _uploaded_today(member) == 1


# --- miejsce na dysku -------------------------------------------------------------------------

def test_unsent_bytes_per_user_are_capped(member):
    # limit = plikow w wiadomosci x MB na plik = 1 MB
    _set(member, "attachments.max_files_per_message", 1)
    _set(member, "attachments.max_file_mb", 1)
    assert upload(member, b"a" * (600 * 1024)).status_code == 201

    response = upload(member, b"b" * (600 * 1024))

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "attachments_storage_full"
    assert _rows(member) == 1
    # odrzucone przed odczytem pliku (Content-Length) - nic nie zuzyto
    assert _uploaded_today(member) == 1


def test_unsent_cap_also_applies_without_content_length(member):
    _set(member, "attachments.max_files_per_message", 1)
    _set(member, "attachments.max_file_mb", 1)
    upload(member, b"a" * (600 * 1024))

    def chunked():
        yield b"b" * (600 * 1024)

    response = upload(member, chunked())

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "attachments_storage_full"
    assert _rows(member) == 1
    assert len(_files()) == 1


def test_sent_attachments_do_not_count_against_the_unsent_cap(member):
    _set(member, "attachments.max_files_per_message", 1)
    _set(member, "attachments.max_file_mb", 1)
    first = upload(member, b"a" * (600 * 1024)).json()
    member.post("/chat", json={"message": "streszcz", "attachment_ids": [first["id"]]})

    assert upload(member, b"b" * (600 * 1024)).status_code == 201


def test_low_disk_space_refuses_uploads(member, monkeypatch):
    monkeypatch.setattr(attachments_router, "MIN_FREE_BYTES", 10**18)

    response = upload(member, b"tekst")

    assert response.status_code == 507
    assert response.json()["detail"]["code"] == "storage_unavailable"
    assert _uploaded_today(member) == 0
