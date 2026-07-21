import usos_login


def test_parse_oauth_response_parses_form_encoded_string():
    result = usos_login.parse_oauth_response(
        "oauth_token=abc123&oauth_token_secret=xyz789&oauth_callback_confirmed=true"
    )

    assert result == {
        "oauth_token": "abc123",
        "oauth_token_secret": "xyz789",
        "oauth_callback_confirmed": "true",
    }


def test_build_authorize_url():
    url = usos_login.build_authorize_url("abc123")

    assert url == "https://apps.usos.uj.edu.pl/services/oauth/authorize?oauth_token=abc123"


def test_update_env_file_replaces_existing_lines(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "USOS_CONSUMER_KEY=abc\nUSOS_CONSUMER_SECRET=def\n", encoding="utf-8"
    )

    usos_login.update_env_file(
        str(env_path),
        {"USOS_CONSUMER_KEY": "new_key", "USOS_ACCESS_TOKEN": "tok123"},
    )

    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert "USOS_CONSUMER_KEY=new_key" in lines
    assert "USOS_CONSUMER_SECRET=def" in lines
    assert "USOS_ACCESS_TOKEN=tok123" in lines


def test_update_env_file_creates_file_if_missing(tmp_path):
    env_path = tmp_path / ".env"

    usos_login.update_env_file(str(env_path), {"USOS_ACCESS_TOKEN": "tok123"})

    assert env_path.read_text(encoding="utf-8") == "USOS_ACCESS_TOKEN=tok123\n"
