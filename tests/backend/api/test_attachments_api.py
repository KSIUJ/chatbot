"""
Testy API zalacznikow: wysylanie pliku (POST /attachments - surowe cialo,
nazwa w naglowku X-Filename), pobieranie i usuwanie, dzienny limit, limity
rozmiaru i typow z panelu administratora oraz dostep tylko dla wlasciciela.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import pytest
from sqlalchemy import select

from src.backend.attachments import router as attachments_router
from src.backend.models import AppSetting, Attachment, DailyAttachmentUsage, User
from tests.backend.attachments.attachment_files import PNG_BYTES, docx_bytes, pdf_bytes

MB = 1024 * 1024


@pytest.fixture
def member(client, member_override):
    client.user_id = member_override
    return client


def upload(client, data, name: str = "plik.pdf", extra_headers: dict[str, str] | None = None):
    headers = {"X-Filename": quote(name), "Content-Type": "application/octet-stream", **(extra_headers or {})}
    return client.post("/attachments", content=data, headers=headers)


def _uploads_dir() -> Path:
    return Path(os.environ["ATTACHMENTS_DIR"])


def _files_on_disk() -> list[str]:
    root = _uploads_dir()
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


def _rows(client) -> list[Attachment]:
    db = client.session_factory()
    try:
        return list(db.execute(select(Attachment)).scalars())
    finally:
        db.close()


def _set(client, key: str, value) -> None:
    db = client.session_factory()
    try:
        db.add(AppSetting(key=key, value=value))
        db.commit()
    finally:
        db.close()


def _uploaded_today(client) -> int:
    db = client.session_factory()
    try:
        counts = db.execute(select(DailyAttachmentUsage.count)).scalars().all()
        return sum(counts)
    finally:
        db.close()


def _other_users_attachment(client) -> str:
    """Zalacznik innego konta (z plikiem na dysku) - do testow IDOR."""
    db = client.session_factory()
    try:
        other = User(oidc_sub="someone-else")
        db.add(other)
        db.flush()
        _uploads_dir().mkdir(parents=True, exist_ok=True)
        (_uploads_dir() / ("f" * 32)).write_bytes(b"cudze")
        row = Attachment(
            user_id=other.id, name="cudze.txt", kind="txt", mime="text/plain", size=5,
            storage_key="f" * 32, text="cudze",
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


# --- wysylanie ---------------------------------------------------------------------

def test_upload_pdf_stores_file_under_random_name(member):
    response = upload(member, pdf_bytes("Regulamin studiow"), "Regulamin studiów.pdf")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Regulamin studiów.pdf"
    assert body["type"] == "pdf"
    assert body["pages"] == 1
    assert body["chars"] > 0
    assert body["size"] == len(pdf_bytes("Regulamin studiow"))
    [row] = _rows(member)
    assert row.id == body["id"]
    assert row.user_id == member.user_id
    assert row.conversation_id is None
    assert "Regulamin studiow" in row.text
    # nazwa na dysku jest losowa - nigdy nazwa od uzytkownika
    assert _files_on_disk() == [row.storage_key]
    assert "Regulamin" not in row.storage_key
    assert _uploaded_today(member) == 1


def test_upload_docx_and_txt(member):
    docx = upload(member, docx_bytes("Akapit"), "notatki.docx").json()
    txt = upload(member, "Zażółć".encode(), "uwagi.txt").json()

    assert (docx["type"], docx["chars"], docx["pages"]) == ("docx", len("Akapit"), None)
    assert (txt["type"], txt["chars"]) == ("txt", len("Zażółć"))


def test_upload_image_has_no_text(member):
    body = upload(member, PNG_BYTES, "zdjecie.png").json()

    assert body["type"] == "png"
    assert body["chars"] is None


def test_type_comes_from_content_not_extension(member):
    body = upload(member, pdf_bytes("x"), "obrazek.png").json()

    assert body["type"] == "pdf"
    assert body["name"] == "obrazek.png.pdf"


def test_unsupported_content_is_rejected_and_still_counted(member):
    response = upload(member, b"MZ\x90\x00binarka", "program.pdf")

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "unsupported_type"
    assert _rows(member) == []
    assert _files_on_disk() == []
    # odrzucenie z winy pliku nie oddaje miejsca - inaczej zle pliki bylyby darmowe
    assert _uploaded_today(member) == 1


def test_type_not_allowed_by_admins_is_rejected(member):
    _set(member, "attachments.allowed_types", ["pdf"])

    response = upload(member, PNG_BYTES, "zdjecie.png")

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "unsupported_type"


def test_empty_file_is_rejected(member):
    response = upload(member, b"", "pusty.txt")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "empty_file"
    assert _uploaded_today(member) == 1


def test_size_cap_from_content_length(member):
    _set(member, "attachments.max_file_mb", 1)

    response = upload(member, b"a" * (MB + 1), "duzy.txt")

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["code"] == "file_too_large"
    assert detail["max_mb"] == 1
    assert _files_on_disk() == []
    assert _uploaded_today(member) == 0


def test_size_cap_while_streaming_without_content_length(member):
    _set(member, "attachments.max_file_mb", 1)
    sent = []

    def body():
        # chunked - bez Content-Length; serwer przerywa po przekroczeniu limitu
        for _ in range(40):
            sent.append(1)
            yield b"a" * (64 * 1024)

    response = upload(member, body(), "strumien.txt")

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"
    assert _files_on_disk() == []
    assert _rows(member) == []
    assert _uploaded_today(member) == 1


def test_images_have_a_lower_size_cap(member, monkeypatch):
    monkeypatch.setattr(attachments_router, "MAX_IMAGE_BYTES", 100)

    response = upload(member, PNG_BYTES + b"\x00" * 200, "duze.png")

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


def test_encrypted_pdf_is_rejected_and_still_counted(member):
    response = upload(member, pdf_bytes("tajne", user_password="haslo"), "tajne.pdf")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unreadable_file"
    assert _files_on_disk() == []
    assert _uploaded_today(member) == 1


def test_daily_upload_limit(member):
    _set(member, "attachments.max_per_day", 2)

    assert upload(member, b"jeden", "1.txt").status_code == 201
    # odrzucony (z winy pliku) tez zuzywa limit
    assert upload(member, b"MZ\x90", "zly.txt").status_code == 415
    response = upload(member, b"dwa", "2.txt")

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == "attachments_limited"
    assert detail["limit"] == 2
    assert "reset_at" in detail
    assert int(response.headers["Retry-After"]) >= 1
    assert len(_rows(member)) == 1


def test_deleting_an_upload_does_not_give_the_daily_slot_back(member):
    _set(member, "attachments.max_per_day", 1)
    first = upload(member, b"jeden", "1.txt").json()

    assert member.delete(f"/attachments/{first['id']}").status_code == 204
    assert upload(member, b"dwa", "2.txt").status_code == 429


def test_attachments_switched_off_by_admins(member):
    _set(member, "attachments.max_per_day", 0)

    response = upload(member, b"tekst", "a.txt")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "attachments_disabled"


def test_upload_refused_while_chat_is_switched_off(member):
    _set(member, "chat_enabled", False)

    response = upload(member, b"tekst", "a.txt")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "chat_disabled"


def test_upload_requires_login(client):
    assert upload(client, b"tekst", "a.txt").status_code == 401


def test_upload_from_foreign_origin_is_rejected(member):
    response = upload(member, b"tekst", "a.txt", {"Origin": "https://evil.example"})

    assert response.status_code == 403


# --- pobieranie i usuwanie -------------------------------------------------------------

def test_owner_downloads_file_as_attachment(member):
    data = pdf_bytes("x")
    attachment = upload(member, data, "Plan zajęć.pdf").json()

    response = member.get(f"/attachments/{attachment['id']}")

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=utf-8''Plan%20zaj%C4%99%C4%87.pdf" in disposition
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]


def test_text_download_is_never_rendered_as_html(member):
    attachment = upload(member, b"<script>alert(1)</script>", "x.html").json()

    response = member.get(f"/attachments/{attachment['id']}")

    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-disposition"].startswith("attachment;")


def test_someone_elses_attachment_looks_missing(member):
    other_id = _other_users_attachment(member)

    assert member.get(f"/attachments/{other_id}").status_code == 404
    assert member.delete(f"/attachments/{other_id}").status_code == 404
    assert len(_rows(member)) == 1


@pytest.mark.parametrize("attachment_id", ["0" * 32, "nie-hex", "../../etc"])
def test_unknown_attachment_is_404(member, attachment_id):
    assert member.get(f"/attachments/{attachment_id}").status_code == 404


def test_delete_unsent_attachment_removes_row_and_file(member):
    attachment = upload(member, b"tekst", "a.txt").json()

    assert member.delete(f"/attachments/{attachment['id']}").status_code == 204
    assert _rows(member) == []
    assert _files_on_disk() == []


def test_sent_attachment_cannot_be_deleted_alone(member):
    attachment = upload(member, b"tekst", "a.txt").json()
    member.post("/chat", json={"message": "streszcz", "attachment_ids": [attachment["id"]]})

    response = member.delete(f"/attachments/{attachment['id']}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "attachment_sent"
    assert len(_rows(member)) == 1


# --- limity w GET /usage ----------------------------------------------------------------

def test_usage_reports_attachment_limits_and_todays_uploads(member, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    upload(member, b"tekst", "a.txt")

    attachments = member.get("/usage").json()["attachments"]

    assert attachments == {
        "max_file_mb": 10,
        "max_image_mb": 5,
        "max_files_per_message": 5,
        "max_per_day": 20,
        "used_today": 1,
        "allowed_types": ["pdf", "docx", "txt", "png", "jpeg", "webp"],
        "images_supported": True,
    }


def test_usage_says_images_unsupported_for_cursor(member, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cursor")

    assert member.get("/usage").json()["attachments"]["images_supported"] is False
