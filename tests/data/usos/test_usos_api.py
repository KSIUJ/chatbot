import json
import os
import time

import pytest

import usos_api


def test_respect_rate_limit_waits_if_called_too_soon(tmp_path, monkeypatch):
    rate_limit_file = tmp_path / ".last_request_time"
    monkeypatch.setattr(usos_api, "RATE_LIMIT_FILE", str(rate_limit_file))

    fixed_time = 1000.0
    monkeypatch.setattr(time, "time", lambda: fixed_time)
    rate_limit_file.write_text(str(fixed_time - 0.3), encoding="utf-8")

    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleep_calls.append(seconds))

    usos_api._respect_rate_limit()

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(0.7, abs=0.01)
    assert rate_limit_file.read_text(encoding="utf-8") == str(fixed_time)


def test_respect_rate_limit_no_wait_if_enough_time_passed(tmp_path, monkeypatch):
    rate_limit_file = tmp_path / ".last_request_time"
    monkeypatch.setattr(usos_api, "RATE_LIMIT_FILE", str(rate_limit_file))

    fixed_time = 1000.0
    monkeypatch.setattr(time, "time", lambda: fixed_time)
    rate_limit_file.write_text(str(fixed_time - 5.0), encoding="utf-8")

    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleep_calls.append(seconds))

    usos_api._respect_rate_limit()

    assert sleep_calls == []


def test_save_response_writes_file_and_returns_path(tmp_path):
    path = usos_api.save_response("services/fac/fac2", {"a": 1}, str(tmp_path))

    assert os.path.exists(path)
    assert os.path.basename(path).startswith("services_fac_fac2_")
    assert os.path.basename(path).endswith(".json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"a": 1}


def test_usos_call_anonymous_returns_json_on_200(monkeypatch):
    monkeypatch.setattr(usos_api, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True}

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(usos_api.requests, "get", fake_get)

    result = usos_api.usos_call_anonymous("services/fac/fac2", {"fac_id": "WMI"})

    assert result == {"ok": True}
    assert captured["url"] == "https://apps.usos.uj.edu.pl/services/fac/fac2"
    assert captured["params"] == {"fac_id": "WMI"}


def test_usos_call_anonymous_raises_on_non_200(monkeypatch):
    monkeypatch.setattr(usos_api, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 400
        text = "bad request"

    monkeypatch.setattr(usos_api.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(usos_api.UsosApiError) as exc_info:
        usos_api.usos_call_anonymous("services/fac/fac2", {})

    assert exc_info.value.status_code == 400
    assert exc_info.value.body == "bad request"
