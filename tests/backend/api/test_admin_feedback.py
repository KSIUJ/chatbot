"""
Przeglad ocen i zgloszen przez adminow (grupa OIDC_ADMIN_GROUP, domyslnie
/Zarząd): lista z filtrami i stronicowaniem, obsluga zgloszenia, eksport CSV
i flaga is_admin w GET /auth/me.
"""

import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.backend.auth.settings import get_auth_settings
from src.backend.models import MessageFeedback, User

from fake_keycloak import ADMIN_GROUP, MEMBER_GROUP, login

BASE_TIME = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _seed(client, minutes: int, **fields) -> str:
    """Wpis oceny/zgloszenia wprost w bazie; `minutes` przesuwa czas utworzenia."""
    db = client.session_factory()
    try:
        at = BASE_TIME + timedelta(minutes=minutes)
        row = MessageFeedback(
            question=fields.pop("question", "Kiedy sesja?"),
            answer=fields.pop("answer", "W lutym."),
            sources=fields.pop("sources", []),
            created_at=at,
            updated_at=at,
            **fields,
        )
        if row.report_reason is not None:
            row.reported_at = at
            row.report_status = row.report_status or "open"
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _row(client, feedback_id: str) -> MessageFeedback:
    db = client.session_factory()
    try:
        return db.get(MessageFeedback, feedback_id)
    finally:
        db.close()


@pytest.fixture
def admin(client):
    login(client, client.keycloak, "boss", groups=[MEMBER_GROUP, ADMIN_GROUP])
    return client


@pytest.fixture
def member(client):
    login(client, client.keycloak, "alice")
    return client


# --- kto jest adminem -------------------------------------------------------------

def test_me_reports_admin_flag(client):
    login(client, client.keycloak, "boss", groups=[MEMBER_GROUP, ADMIN_GROUP])
    assert client.get("/auth/me").json()["is_admin"] is True

    login(client, client.keycloak, "alice")
    assert client.get("/auth/me").json()["is_admin"] is False


def test_admin_endpoints_require_login(client):
    assert client.get("/admin/feedback").status_code == 401
    assert client.patch("/admin/feedback/x", json={"status": "resolved"}).status_code == 401
    assert client.get("/admin/feedback/export.csv").status_code == 401


def test_member_outside_admin_group_gets_403(member):
    feedback_id = _seed(member, 0, report_reason="wrong")

    for response in (
        member.get("/admin/feedback"),
        member.patch(f"/admin/feedback/{feedback_id}", json={"status": "resolved"}),
        member.get("/admin/feedback/export.csv"),
    ):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "not_admin"
    assert _row(member, feedback_id).report_status == "open"


def test_admin_group_only_counts_alongside_membership(client):
    # sam /Zarząd bez /Członek nie wpuszcza do aplikacji w ogole
    r = login(client, client.keycloak, "outsider", groups=[ADMIN_GROUP])

    assert "auth_error=not_member" in r.headers["location"]
    assert client.get("/admin/feedback").status_code == 401


def test_disabled_admin_group_locks_everybody_out(admin, monkeypatch):
    monkeypatch.setenv("OIDC_ADMIN_GROUP", "off")
    get_auth_settings.cache_clear()

    r = admin.get("/admin/feedback")

    assert r.status_code == 403
    assert admin.get("/auth/me").json()["is_admin"] is False


def test_losing_admin_group_takes_effect_on_next_request(admin):
    assert admin.get("/admin/feedback").status_code == 200

    admin.keycloak.users["boss"].groups = [MEMBER_GROUP]

    assert admin.get("/admin/feedback").status_code == 403


# --- lista -------------------------------------------------------------------------

def test_reports_are_listed_newest_first_with_snapshot(admin):
    sources = [{"kind": "usos", "title": "Jan Kowalski", "url": "https://usosweb.uj.edu.pl/jk"}, "stara/sciezka.txt"]
    older = _seed(admin, 0, report_reason="wrong", comment="zla data", language="pl")
    newer = _seed(admin, 5, report_reason="outdated", rating=-1, sources=sources)
    _seed(admin, 10, rating=1)  # sama ocena - nie jest zgloszeniem

    r = admin.get("/admin/feedback", params={"kind": "reports"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [newer, older]
    first = body["items"][0]
    assert first["report_reason"] == "outdated"
    assert first["rating"] == -1
    assert first["report_status"] == "open"
    assert first["question"] == "Kiedy sesja?" and first["answer"] == "W lutym."
    assert first["sources"] == sources[:1]
    assert body["items"][1]["comment"] == "zla data"
    assert body["items"][1]["language"] == "pl"
    # bez danych osobowych zglaszajacego
    assert "user_id" not in first and "email" not in first


def test_ratings_kind_lists_rated_answers(admin):
    _seed(admin, 0, rating=1)
    down = _seed(admin, 1, rating=-1, report_reason="wrong")
    _seed(admin, 2, report_reason="other")

    body = admin.get("/admin/feedback", params={"kind": "ratings"}).json()

    assert body["total"] == 2
    assert body["items"][0]["id"] == down


def test_default_kind_is_reports(admin):
    report = _seed(admin, 0, report_reason="other")
    _seed(admin, 1, rating=1)

    body = admin.get("/admin/feedback").json()

    assert [item["id"] for item in body["items"]] == [report]


def test_status_filter(admin):
    open_id = _seed(admin, 0, report_reason="wrong")
    resolved_id = _seed(admin, 1, report_reason="wrong", report_status="resolved")
    dismissed_id = _seed(admin, 2, report_reason="other", report_status="dismissed")

    def ids(status: str) -> list[str]:
        r = admin.get("/admin/feedback", params={"kind": "reports", "status": status})
        assert r.status_code == 200, r.text
        return [item["id"] for item in r.json()["items"]]

    assert ids("open") == [open_id]
    assert ids("resolved") == [resolved_id]
    assert ids("dismissed") == [dismissed_id]


def test_pagination_returns_total_and_page(admin):
    ids = [_seed(admin, minute, report_reason="wrong") for minute in range(5)]

    body = admin.get("/admin/feedback", params={"limit": 2, "offset": 2}).json()

    assert body["total"] == 5
    assert (body["limit"], body["offset"]) == (2, 2)
    assert [item["id"] for item in body["items"]] == [ids[2], ids[1]]


@pytest.mark.parametrize(
    "params",
    [{"kind": "all"}, {"status": "closed"}, {"limit": 0}, {"limit": 201}, {"offset": -1}],
)
def test_invalid_list_params_are_rejected(admin, params):
    assert admin.get("/admin/feedback", params=params).status_code == 422


# --- obsluga zgloszenia --------------------------------------------------------------

def test_admin_resolves_report_with_note(admin):
    feedback_id = _seed(admin, 0, report_reason="wrong")

    r = admin.patch(f"/admin/feedback/{feedback_id}", json={"status": "resolved", "admin_note": "  poprawione  "})

    assert r.status_code == 200, r.text
    assert r.json()["report_status"] == "resolved"
    assert r.json()["admin_note"] == "poprawione"
    row = _row(admin, feedback_id)
    assert row.report_status == "resolved"
    assert row.reviewed_at is not None
    db = admin.session_factory()
    boss = db.execute(select(User).where(User.oidc_sub == "boss")).scalar_one()
    db.close()
    assert row.reviewed_by == boss.id


def test_dismiss_without_note_keeps_existing_note(admin):
    feedback_id = _seed(admin, 0, report_reason="other", admin_note="do sprawdzenia")

    r = admin.patch(f"/admin/feedback/{feedback_id}", json={"status": "dismissed"})

    assert r.json()["admin_note"] == "do sprawdzenia"
    assert _row(admin, feedback_id).report_status == "dismissed"


def test_reopening_clears_review(admin):
    feedback_id = _seed(admin, 0, report_reason="wrong")
    admin.patch(f"/admin/feedback/{feedback_id}", json={"status": "resolved"})

    r = admin.patch(f"/admin/feedback/{feedback_id}", json={"status": "open"})

    assert r.json()["report_status"] == "open"
    row = _row(admin, feedback_id)
    assert row.reviewed_at is None and row.reviewed_by is None


def test_patch_rating_without_report_is_404(admin):
    feedback_id = _seed(admin, 0, rating=1)

    assert admin.patch(f"/admin/feedback/{feedback_id}", json={"status": "resolved"}).status_code == 404
    assert admin.patch("/admin/feedback/missing", json={"status": "resolved"}).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [{"status": "closed"}, {}, {"status": "resolved", "admin_note": "x" * 1001}],
)
def test_invalid_review_is_rejected(admin, payload):
    feedback_id = _seed(admin, 0, report_reason="wrong")

    assert admin.patch(f"/admin/feedback/{feedback_id}", json=payload).status_code == 422


# --- eksport CSV --------------------------------------------------------------------

def _csv(response) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.text)))


def test_export_csv_contains_snapshots(admin):
    _seed(admin, 0, rating=1, question="Kto prowadzi AM?", answer="Dr X.",
          sources=[{"kind": "strony", "title": "Plan", "url": "https://wmii.uj.edu.pl/plan"}], language="en")
    _seed(admin, 1, report_reason="wrong", comment="zle")

    r = admin.get("/admin/feedback/export.csv")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    rows = _csv(r)
    assert [row["question"] for row in rows] == ["Kto prowadzi AM?", "Kiedy sesja?"]
    assert rows[0]["rating"] == "1"
    assert rows[0]["language"] == "en"
    assert '"url": "https://wmii.uj.edu.pl/plan"' in rows[0]["sources"]
    assert rows[1]["report_reason"] == "wrong" and rows[1]["comment"] == "zle"


def test_export_csv_respects_kind_filter(admin):
    _seed(admin, 0, rating=1)
    _seed(admin, 1, report_reason="wrong")

    rows = _csv(admin.get("/admin/feedback/export.csv", params={"kind": "reports"}))

    assert [row["report_reason"] for row in rows] == ["wrong"]


def test_export_csv_neutralizes_formulas(admin):
    _seed(admin, 0, report_reason="other", question="=HYPERLINK(\"http://evil\")", comment="@SUM(A1)",
          answer="- punkt listy")

    (row,) = _csv(admin.get("/admin/feedback/export.csv"))

    assert row["question"] == "'=HYPERLINK(\"http://evil\")"
    assert row["comment"] == "'@SUM(A1)"
    assert row["answer"] == "'- punkt listy"
