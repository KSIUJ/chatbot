import sys

import pytest

import usos_api
import usos_client


def test_parse_params_parses_key_value_pairs():
    result = usos_client.parse_params(["fac_id=WMI", "lang=en"])
    assert result == {"fac_id": "WMI", "lang": "en"}


def test_parse_params_raises_on_missing_equals():
    with pytest.raises(ValueError):
        usos_client.parse_params(["not_a_pair"])


def test_main_calls_anonymous_by_default(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["usos_client.py", "services/fac/fac2", "--params", "fac_id=WMI"])
    monkeypatch.setattr(usos_client, "RAW_DATA_DIR", str(tmp_path))

    calls = {}

    def fake_anonymous(method_path, params):
        calls["method_path"] = method_path
        calls["params"] = params
        return {"ok": True}

    def fail_signed(*a, **kw):
        raise AssertionError("should not call signed without --signed")

    monkeypatch.setattr(usos_client, "usos_call_anonymous", fake_anonymous)
    monkeypatch.setattr(usos_client, "usos_call_signed", fail_signed)

    usos_client.main()

    assert calls["method_path"] == "services/fac/fac2"
    assert calls["params"] == {"fac_id": "WMI"}


def test_main_calls_signed_with_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        ["usos_client.py", "services/users/user", "--signed", "--params", "user_id=1"],
    )
    monkeypatch.setattr(usos_client, "RAW_DATA_DIR", str(tmp_path))

    calls = {}

    def fake_signed(method_path, params):
        calls["method_path"] = method_path
        calls["params"] = params
        return {"ok": True}

    def fail_anonymous(*a, **kw):
        raise AssertionError("should not call anonymous with --signed")

    monkeypatch.setattr(usos_client, "usos_call_signed", fake_signed)
    monkeypatch.setattr(usos_client, "usos_call_anonymous", fail_anonymous)

    usos_client.main()

    assert calls["method_path"] == "services/users/user"
    assert calls["params"] == {"user_id": "1"}


def test_main_exits_with_error_on_api_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["usos_client.py", "services/fac/fac2"])
    monkeypatch.setattr(usos_client, "RAW_DATA_DIR", str(tmp_path))

    def fake_anonymous(method_path, params):
        raise usos_api.UsosApiError(400, "bad request")

    monkeypatch.setattr(usos_client, "usos_call_anonymous", fake_anonymous)

    with pytest.raises(SystemExit) as exc_info:
        usos_client.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "400" in captured.err
    assert "bad request" in captured.err
