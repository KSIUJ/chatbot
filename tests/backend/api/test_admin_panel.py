"""
Panel administratora (grupa OIDC_ADMIN_GROUP, domyslnie /Zarząd): globalne
limity (pytania i zalaczniki) z walidacja zakresow, wyszukiwarka uzytkownikow
z dzisiejszym zuzyciem i wyjatkami, edycja wyjatkow per osoba.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.backend import main as main_module
from src.backend.limits.settings import get_attachment_limits
from src.backend.limits.usage import consume_question, get_clock
from src.backend.models import User

from fake_keycloak import ADMIN_GROUP, MEMBER_GROUP, login

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)

VALID_SETTINGS = {
    "daily_question_limit": 15,
    "attachments": {
        "max_file_mb": 8,
        "max_files_per_message": 3,
        "max_per_day": 12,
        "allowed_types": ["pdf", "png"],
    },
}

ADMIN_ENDPOINTS = [
    ("GET", "/admin/settings", None),
    ("PUT", "/admin/settings", VALID_SETTINGS),
    ("GET", "/admin/users", None),
    ("PUT", "/admin/users/x/limit", {"unlimited": True}),
    ("DELETE", "/admin/users/x/limit", None),
    ("GET", "/admin/diagnostics", None),
]


@pytest.fixture(autouse=True)
def fixed_clock():
    main_module.app.dependency_overrides[get_clock] = lambda: (lambda: NOW)


@pytest.fixture
def admin(client):
    login(client, client.keycloak, "boss", groups=[MEMBER_GROUP, ADMIN_GROUP])
    return client


def _add_user(client, sub: str, *, name: str | None = None, email: str | None = None,
              username: str | None = None) -> str:
    db = client.session_factory()
    try:
        user = User(oidc_sub=sub, name=name, email=email, username=username)
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _use(client, user_id: str, times: int) -> None:
    db = client.session_factory()
    try:
        for _ in range(times):
            consume_question(db, user_id, NOW)
    finally:
        db.close()


# --- dostep -----------------------------------------------------------------------------

@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ENDPOINTS)
def test_admin_endpoints_require_login(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ENDPOINTS)
def test_member_outside_admin_group_gets_403(client, method, path, body):
    login(client, client.keycloak, "alice")

    response = client.request(method, path, json=body)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_admin"


# --- ustawienia globalne -------------------------------------------------------------------

def test_settings_default_to_env_values(admin):
    response = admin.get("/admin/settings")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    # conftest: CHAT_DAILY_LIMIT=1000; zalaczniki z wartosci domyslnych w kodzie
    assert body["daily_question_limit"] == 1000
    assert body["attachments"] == {
        "max_file_mb": 10,
        "max_files_per_message": 5,
        "max_per_day": 20,
        "allowed_types": ["pdf", "docx", "txt", "png", "jpeg", "webp"],
    }
    assert body["defaults"]["daily_question_limit"] == 1000
    assert body["available_types"] == ["pdf", "docx", "txt", "png", "jpeg", "webp"]


def test_saved_settings_are_used_everywhere(admin):
    response = admin.put("/admin/settings", json=VALID_SETTINGS)

    assert response.status_code == 200
    assert response.json()["daily_question_limit"] == 15
    assert admin.get("/admin/settings").json()["attachments"]["allowed_types"] == ["pdf", "png"]
    assert admin.get("/usage").json()["limit"] == 15
    db = admin.session_factory()
    try:
        limits = get_attachment_limits(db)
    finally:
        db.close()
    assert (limits.max_file_mb, limits.max_files_per_message, limits.max_per_day) == (8, 3, 12)
    assert limits.allowed_types == ("pdf", "png")


@pytest.mark.parametrize(
    "change",
    [
        {"daily_question_limit": 0},
        {"daily_question_limit": 100_000},
        {"attachments": {**VALID_SETTINGS["attachments"], "max_file_mb": 0}},
        {"attachments": {**VALID_SETTINGS["attachments"], "max_file_mb": 500}},
        {"attachments": {**VALID_SETTINGS["attachments"], "max_files_per_message": 0}},
        {"attachments": {**VALID_SETTINGS["attachments"], "max_per_day": -1}},
        {"attachments": {**VALID_SETTINGS["attachments"], "allowed_types": []}},
        {"attachments": {**VALID_SETTINGS["attachments"], "allowed_types": ["exe"]}},
        {"unexpected": 1},
    ],
)
def test_settings_validation(admin, change):
    response = admin.put("/admin/settings", json={**VALID_SETTINGS, **change})

    assert response.status_code == 422


def test_duplicate_types_are_collapsed(admin):
    body = {**VALID_SETTINGS, "attachments": {**VALID_SETTINGS["attachments"], "allowed_types": ["png", "pdf", "png"]}}

    response = admin.put("/admin/settings", json=body)

    assert response.json()["attachments"]["allowed_types"] == ["png", "pdf"]


# --- uzytkownicy ---------------------------------------------------------------------------------

def test_user_search_matches_name_username_and_email(admin):
    anna = _add_user(admin, "a", name="Anna Nowak", email="anna@student.uj.edu.pl", username="anowak")
    _add_user(admin, "b", name="Bartek Zielinski", email="bz@uj.edu.pl", username="bzielinski")
    _use(admin, anna, 3)

    by_name = admin.get("/admin/users", params={"q": "nowak"}).json()
    by_email = admin.get("/admin/users", params={"q": "BZ@UJ"}).json()

    assert [u["id"] for u in by_name["items"]] == [anna]
    assert by_name["total"] == 1
    assert by_name["items"][0]["used_today"] == 3
    assert by_name["items"][0]["effective_limit"] == 1000
    assert by_name["items"][0]["override"] is None
    assert [u["username"] for u in by_email["items"]] == ["bzielinski"]


def test_user_search_escapes_like_wildcards(admin):
    _add_user(admin, "a", name="Anna")

    assert admin.get("/admin/users", params={"q": "%"}).json()["total"] == 0
    assert admin.get("/admin/users", params={"q": "_"}).json()["total"] == 0


def test_user_list_is_paginated(admin):
    for index in range(5):
        _add_user(admin, f"user{index}", name=f"Osoba {index}")

    page = admin.get("/admin/users", params={"q": "osoba", "limit": 2, "offset": 2}).json()

    assert page["total"] == 5
    assert [u["name"] for u in page["items"]] == ["Osoba 2", "Osoba 3"]
    assert admin.get("/admin/users", params={"limit": 0}).status_code == 422
    assert admin.get("/admin/users", params={"q": "x" * 201}).status_code == 422


def test_override_crud(admin):
    anna = _add_user(admin, "a", name="Anna")

    put = admin.put(f"/admin/users/{anna}/limit", json={"unlimited": False, "daily_limit": 50, "note": " projekt "})
    assert put.status_code == 200
    assert put.json()["override"]["daily_limit"] == 50
    assert put.json()["override"]["unlimited"] is False
    assert put.json()["override"]["note"] == "projekt"
    assert put.json()["effective_limit"] == 50

    unlimited = admin.put(f"/admin/users/{anna}/limit", json={"unlimited": True}).json()
    assert unlimited["override"]["unlimited"] is True
    assert unlimited["effective_limit"] is None

    listed = admin.get("/admin/users", params={"q": "anna"}).json()["items"][0]
    assert listed["override"]["unlimited"] is True

    assert admin.delete(f"/admin/users/{anna}/limit").status_code == 204
    after = admin.get("/admin/users", params={"q": "anna"}).json()["items"][0]
    assert after["override"] is None
    assert after["effective_limit"] == 1000


@pytest.mark.parametrize(
    "body",
    [
        {"unlimited": True, "daily_limit": 5},
        {"unlimited": False},
        {"unlimited": False, "daily_limit": -1},
        {"unlimited": False, "daily_limit": 100_000},
        {"unlimited": False, "daily_limit": 5, "note": "x" * 501},
        {"unlimited": False, "daily_limit": 5, "extra": 1},
    ],
)
def test_override_validation(admin, body):
    anna = _add_user(admin, "a", name="Anna")

    assert admin.put(f"/admin/users/{anna}/limit", json=body).status_code == 422


def test_override_of_unknown_user_is_404(admin):
    assert admin.put("/admin/users/nope/limit", json={"unlimited": True}).status_code == 404
    assert admin.delete("/admin/users/nope/limit").status_code == 404


def test_admin_is_not_exempt_from_the_limit(admin):
    admin.put("/admin/settings", json={**VALID_SETTINGS, "daily_question_limit": 1})

    assert admin.get("/usage").json()["limit"] == 1
