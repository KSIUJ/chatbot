import scrape_staff


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
