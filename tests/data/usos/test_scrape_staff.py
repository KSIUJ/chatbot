import scrape_staff
import usos_api


def test_flatten_langdict_returns_empty_for_none():
    assert scrape_staff.flatten_langdict(None) == ({}, "")


def test_flatten_langdict_returns_empty_for_empty_dict():
    assert scrape_staff.flatten_langdict({}) == ({}, "")


def test_flatten_langdict_prefers_polish():
    langdict = {"pl": "Wtorki 10-12", "en": "Tuesdays 10-12"}
    result_dict, text = scrape_staff.flatten_langdict(langdict)
    assert result_dict == langdict
    assert text == "Wtorki 10-12"


def test_flatten_langdict_falls_back_to_other_language():
    langdict = {"en": "Tuesdays 10-12"}
    result_dict, text = scrape_staff.flatten_langdict(langdict)
    assert result_dict == langdict
    assert text == "Tuesdays 10-12"


def test_flatten_langdict_falls_back_when_polish_is_empty_string():
    langdict = {"pl": "", "en": "Tuesdays 10-12"}
    _, text = scrape_staff.flatten_langdict(langdict)
    assert text == "Tuesdays 10-12"


def test_normalize_employee_maps_all_fields():
    raw = {
        "id": 12345,
        "first_name": "Jan",
        "last_name": "Kowalski",
        "titles": {"before": "dr", "after": None},
        "email": "jan.kowalski@uj.edu.pl",
        "phone_numbers": ["123456789"],
        "room": {"id": "0.05", "number": "0.05"},
        "profile_url": "https://usosweb.uj.edu.pl/...",
        "homepage_url": None,
        "office_hours": {"pl": "Wtorki 10-12"},
        "interests": {"pl": "Uczenie maszynowe"},
        "employment_positions": [{"position": {"name": {"pl": "adiunkt"}}}],
    }

    result = scrape_staff.normalize_employee(raw)

    assert result["id"] == 12345
    assert result["first_name"] == "Jan"
    assert result["last_name"] == "Kowalski"
    assert result["titles"] == {"before": "dr", "after": None}
    assert result["email"] == "jan.kowalski@uj.edu.pl"
    assert result["phone_numbers"] == ["123456789"]
    assert result["room"] == {"id": "0.05", "number": "0.05"}
    assert result["profile_url"] == "https://usosweb.uj.edu.pl/..."
    assert result["homepage_url"] is None
    assert result["office_hours"] == {"pl": "Wtorki 10-12"}
    assert result["office_hours_text"] == "Wtorki 10-12"
    assert result["interests"] == {"pl": "Uczenie maszynowe"}
    assert result["interests_text"] == "Uczenie maszynowe"
    assert result["employment_positions"] == [{"position": {"name": {"pl": "adiunkt"}}}]


def test_normalize_employee_handles_missing_optional_fields():
    raw = {"id": 1, "first_name": "Anna", "last_name": "Nowak"}

    result = scrape_staff.normalize_employee(raw)

    assert result["phone_numbers"] == []
    assert result["employment_positions"] == []
    assert result["office_hours"] == {}
    assert result["office_hours_text"] == ""


def test_fetch_all_staff_ids_paginates_until_next_page_false(monkeypatch):
    responses = [
        {"users": [{"id": 1}, {"id": 2}], "next_page": True, "total": 3},
        {"users": [{"id": 3}], "next_page": False, "total": 3},
    ]
    calls = []

    def fake_signed(method_path, params):
        calls.append((method_path, dict(params)))
        return responses[len(calls) - 1]

    monkeypatch.setattr(scrape_staff, "usos_call_signed", fake_signed)
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_all_staff_ids("WMI")

    assert result == [1, 2, 3]
    assert calls[0] == (
        "services/users/staff_index",
        {
            "fac_ids": "WMI",
            "fields": "users[id]|next_page|total",
            "num": "100",
            "start": "0",
        },
    )
    assert calls[1][1]["start"] == "100"


def test_fetch_all_staff_ids_single_page(monkeypatch):
    monkeypatch.setattr(
        scrape_staff,
        "usos_call_signed",
        lambda method_path, params: {"users": [{"id": 7}], "next_page": False, "total": 1},
    )
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_all_staff_ids("WMI")

    assert result == [7]


def test_fetch_employee_detail_calls_signed_with_correct_fields(monkeypatch):
    calls = []

    def fake_signed(method_path, params):
        calls.append((method_path, dict(params)))
        return {"id": 42, "first_name": "Ola"}

    monkeypatch.setattr(scrape_staff, "usos_call_signed", fake_signed)
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_employee_detail(42)

    assert result == {"id": 42, "first_name": "Ola"}
    assert calls == [
        ("services/users/user", {"user_id": "42", "fields": scrape_staff.USER_FIELDS})
    ]


import json
import os


def test_save_staff_dataset_writes_file_with_expected_name(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape_staff, "STAFF_OUTPUT_DIR", str(tmp_path))

    employees = [{"id": 1, "first_name": "Ola"}]
    path = scrape_staff.save_staff_dataset("WMI", employees)

    assert os.path.exists(path)
    assert os.path.basename(path).startswith("staff_WMI_")
    assert os.path.basename(path).endswith(".json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == employees


def test_run_scrape_skips_failed_employees_and_continues(monkeypatch, capsys):
    monkeypatch.setattr(scrape_staff, "fetch_all_staff_ids", lambda fac_id: [1, 2, 3])

    def fake_fetch_detail(user_id):
        if user_id == 2:
            raise usos_api.UsosApiError(500, "server error")
        return {"id": user_id, "first_name": f"User{user_id}", "last_name": "X"}

    monkeypatch.setattr(scrape_staff, "fetch_employee_detail", fake_fetch_detail)

    saved = {}

    def fake_save(fac_id, employees):
        saved["fac_id"] = fac_id
        saved["employees"] = employees
        return "data/usos/staff/staff_WMI_fake.json"

    monkeypatch.setattr(scrape_staff, "save_staff_dataset", fake_save)

    summary = scrape_staff.run_scrape("WMI")

    assert summary["total_found"] == 3
    assert summary["total_fetched"] == 2
    assert summary["skipped_ids"] == [2]
    assert summary["output_path"] == "data/usos/staff/staff_WMI_fake.json"
    assert saved["fac_id"] == "WMI"
    assert [e["id"] for e in saved["employees"]] == [1, 3]

    captured = capsys.readouterr()
    assert "2" in captured.err
    assert "500" in captured.err
    assert "server error" in captured.err


def test_run_scrape_defaults_to_wmi(monkeypatch):
    seen_fac_ids = []
    monkeypatch.setattr(
        scrape_staff,
        "fetch_all_staff_ids",
        lambda fac_id: seen_fac_ids.append(fac_id) or [],
    )
    monkeypatch.setattr(scrape_staff, "save_staff_dataset", lambda fac_id, employees: "path")

    scrape_staff.run_scrape()

    assert seen_fac_ids == ["UJ.WMI"]


def test_fetch_employee_detail_uses_signed_by_default(monkeypatch):
    calls = {"signed": 0, "authenticated": 0}

    monkeypatch.setattr(
        scrape_staff, "usos_call_signed", lambda *a, **kw: calls.__setitem__("signed", calls["signed"] + 1) or {"id": 1}
    )
    monkeypatch.setattr(
        scrape_staff,
        "usos_call_authenticated",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not call authenticated by default")),
    )
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_employee_detail(1)

    assert result == {"id": 1}
    assert calls["signed"] == 1


def test_fetch_employee_detail_uses_authenticated_when_requested(monkeypatch):
    calls = []

    def fake_authenticated(method_path, params):
        calls.append((method_path, dict(params)))
        return {"id": 1, "email": "jan.kowalski@uj.edu.pl"}

    def fail_signed(*a, **kw):
        raise AssertionError("should not call signed when authenticated=True")

    monkeypatch.setattr(scrape_staff, "usos_call_authenticated", fake_authenticated)
    monkeypatch.setattr(scrape_staff, "usos_call_signed", fail_signed)
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_employee_detail(1, authenticated=True)

    assert result == {"id": 1, "email": "jan.kowalski@uj.edu.pl"}
    assert calls == [("services/users/user", {"user_id": "1", "fields": scrape_staff.USER_FIELDS})]


def test_run_scrape_threads_with_email_to_fetch_employee_detail(monkeypatch):
    monkeypatch.setattr(scrape_staff, "fetch_all_staff_ids", lambda fac_id: [1, 2])

    calls = []

    def fake_fetch_detail(user_id, authenticated=False):
        calls.append((user_id, authenticated))
        return {"id": user_id, "first_name": "X", "last_name": "Y"}

    monkeypatch.setattr(scrape_staff, "fetch_employee_detail", fake_fetch_detail)
    monkeypatch.setattr(scrape_staff, "save_staff_dataset", lambda fac_id, employees: "path")

    scrape_staff.run_scrape("WMI", with_email=True)

    assert calls == [(1, True), (2, True)]


def test_run_scrape_defaults_with_email_to_false(monkeypatch):
    monkeypatch.setattr(scrape_staff, "fetch_all_staff_ids", lambda fac_id: [1])

    calls = []

    def fake_fetch_detail(user_id, authenticated=False):
        calls.append(authenticated)
        return {"id": user_id, "first_name": "X", "last_name": "Y"}

    monkeypatch.setattr(scrape_staff, "fetch_employee_detail", fake_fetch_detail)
    monkeypatch.setattr(scrape_staff, "save_staff_dataset", lambda fac_id, employees: "path")

    scrape_staff.run_scrape("WMI")

    assert calls == [False]
