"""Kolektor places: budynki UJ (sale w budynkach wydzialu i z zajeciami) oraz przeglad domow studenckich."""

from __future__ import annotations

from src.backend.rag.sources.usos.dataset import USOS_RECORD

from pipeline.scrapers.usos.collectors import places, units
from pipeline.scrapers.usos.api import UsosError
from tests.pipeline.usos.fake_usos_api import context

FACULTY_UNITS = ["UJ.WMI", "UJ.WMI.II", "UJ.WMI.IM"]

BUILDINGS = {
    "Loj6": {
        "id": "Loj6",
        "name": {"pl": "III Kampus, budynek Wydziału Matematyki i Informatyki", "en": ""},
        "profile_url": "https://www.usosweb.uj.edu.pl/kontroler.php?_action=katalog2/jednostki/pokazBudynek&bud_kod=Loj6",
        "postal_address": "prof. Stanisława Łojasiewicza 6, Kraków",
        "campus_name": {"pl": "III Kampus", "en": None},
        "phone_numbers": [],
        "all_phone_numbers": [{"number": "12 664 66 29", "comment": {"pl": "Portiernia", "en": ""}}],
        "related_faculties": [
            {"id": "UJ.WMI.II", "name": {"pl": "Instytut Informatyki i Matematyki Komputerowej", "en": ""}},
            {"id": "UJ.WMI", "name": {"pl": "Wydział Matematyki i Informatyki", "en": ""}},
        ],
    },
    "Gol24": {
        "id": "Gol24",
        "name": {"pl": "Collegium Novum", "en": ""},
        "profile_url": None,
        "postal_address": "Gołębia 24, Kraków",
        "campus_name": {"pl": "I Kampus", "en": None},
        "phone_numbers": ["12 422 10 33"],
        "all_phone_numbers": [],
        "related_faculties": [{"id": "UJ.WPiA", "name": {"pl": "Wydział Prawa i Administracji", "en": ""}}],
    },
    "Prad76": {
        "id": "Prad76",
        "name": {"pl": "Prądnicka 76", "en": ""},
        "profile_url": "https://www.usosweb.uj.edu.pl/kontroler.php?_action=katalog2/jednostki/pokazBudynek&bud_kod=Prad76",
        "postal_address": None,
        "campus_name": None,
        "phone_numbers": [],
        "all_phone_numbers": [],
        "related_faculties": [],
    },
}
BUILDING_ROOMS = {"Loj6": ["895", "896", "897", "898"], "Gol24": ["10", "11"], "Prad76": ["50"]}
ROOMS = {
    "895": {
        "id": "895", "number": "0004", "type": "didactics_room", "capacity": 240,
        "attributes": [
            {"id": "SALA-WYK", "description": {"pl": "sala wykładowa", "en": ""}, "count": None},
            {"id": "PROJEKTOR", "description": {"pl": "projektor", "en": ""}, "count": 2},
            {"id": "NIEP", "description": {"pl": "dostęp dla niepełnosprawnych", "en": ""}, "count": None},
        ],
    },
    "896": {"id": "896", "number": "1094", "type": "didactics_room", "capacity": 0, "attributes": []},
    "897": {
        "id": "897", "number": "2017", "type": "staff_members_room", "capacity": 2, "attributes": [],
        # geo/room potrafi zwrocic osoby przypisane do pokoju - nie moga trafic do tresci
        "staff": [{"id": "123", "first_name": "Jan", "last_name": "Kowalski"}],
    },
    "898": {"id": "898", "number": "nn", "type": "staff_members_room", "capacity": 1, "attributes": []},
    "10": {"id": "10", "number": "Aula", "type": "didactics_room", "capacity": 300, "attributes": []},
    "11": {"id": "11", "number": "12", "type": "staff_members_room", "capacity": 1, "attributes": []},
}
DORMS = [
    {"id": "1", "name": {"pl": "Nawojka", "en": None}, "short_name": {"pl": "Naw", "en": None}},
    {"id": "7", "name": {"pl": "Piast", "en": None}, "short_name": {"pl": "Piast", "en": None}},
    {"id": "8", "name": {"pl": "Żaczek", "en": None}, "short_name": {"pl": "", "en": None}},
]


def buildings2(building_ids, fields, **_params):
    ids = building_ids if isinstance(building_ids, list) else building_ids.split("|")
    if "rooms" in fields:
        return {i: {"id": i, "rooms": [{"id": r} for r in BUILDING_ROOMS[i]]} for i in ids}
    return {i: BUILDINGS.get(i) for i in ids}


def rooms(room_ids, **_params):
    ids = room_ids if isinstance(room_ids, list) else room_ids.split("|")
    return {i: ROOMS.get(i) for i in ids}


def responses(**overrides):
    base = {
        "services/geo/building_index": [{"id": "Loj6"}, {"id": "Gol24"}, {"id": "Prad76"}],
        "services/geo/buildings2": buildings2,
        "services/geo/rooms": rooms,
        "services/housing/dormitory_index": DORMS,
    }
    base.update(overrides)
    return base


def collect(ctx):
    records = list(places.collect(ctx))
    for record in records:
        USOS_RECORD.validate_python(record.model_dump())
        assert "None" not in record.content
    return {record.id: record for record in records}


def test_buildings_with_rooms_for_faculty_and_teaching_buildings():
    ctx = context(responses(), consumer=False, faculty_units=FACULTY_UNITS, teaching_buildings={"Gol24"})
    records = collect(ctx)

    assert set(records) == {"building:Loj6", "building:Gol24", "building:Prad76", "dormitory:all"}
    loj6 = records["building:Loj6"]
    assert loj6.kind == "building"
    assert loj6.title == "III Kampus, budynek Wydziału Matematyki i Informatyki"
    assert loj6.url.endswith("bud_kod=Loj6")
    assert loj6.attributes.building_id == "Loj6"
    assert loj6.attributes.campus == "III Kampus"
    assert loj6.attributes.address == "prof. Stanisława Łojasiewicza 6, Kraków"
    assert loj6.attributes.fac_ids == ["UJ.WMI.II", "UJ.WMI"]
    content = loj6.content
    assert content.startswith("# III Kampus, budynek Wydziału Matematyki i Informatyki\n")
    assert "- Telefon: 12 664 66 29 (Portiernia)" in content
    assert "## Jednostki w budynku" in content and "- Instytut Informatyki i Matematyki Komputerowej" in content
    assert "## Sale dydaktyczne" in content
    assert "| Sala | Miejsca | Rodzaj | Wyposażenie |" in content
    assert "| 0004 | 240 | sala wykładowa | projektor (2), dostęp dla niepełnosprawnych |" in content
    # liczba miejsc 0 = nieznana
    assert "| 1094 |  |  |  |" in content
    assert "## Pokoje pracowników\n\n2017" in content
    assert "nn" not in content.split("## Pokoje pracowników")[1]
    assert "Kowalski" not in content and "Jan" not in content

    # budynek z zajeciami wydzialu: sale dydaktyczne, bez pokoi pracownikow
    novum = records["building:Gol24"].content
    assert "| Aula | 300 |" in novum
    assert "Pokoje pracowników" not in novum
    assert "- Telefon: 12 422 10 33" in novum
    # url budowany, gdy API nie podaje profile_url
    assert records["building:Gol24"].url.endswith("bud_kod=Gol24")

    # pozostale budynki - krotko, bez sal (i bez zapytan o nie)
    other = records["building:Prad76"]
    assert "Sale" not in other.content and "Adres" not in other.content and "Kampus" not in other.content
    assert other.attributes.campus == "" and other.attributes.address == "" and other.attributes.fac_ids == []
    room_calls = [params for method, params in ctx.api.calls if method == "services/geo/buildings2" and "rooms" in params["fields"]]
    assert len(room_calls) == 1 and set(room_calls[0]["building_ids"]) == {"Loj6", "Gol24"}
    assert ctx.warnings == []


def test_many_rooms_split_by_first_digit(monkeypatch):
    monkeypatch.setattr(places, "SPLIT_ROOMS", 1)
    ctx = context(responses(), consumer=False, faculty_units=FACULTY_UNITS)
    content = collect(ctx)["building:Loj6"].content
    assert "### Sale 0xxx" in content and "### Sale 1xxx" in content
    assert content.index("### Sale 0xxx") < content.index("| 0004 |") < content.index("### Sale 1xxx")


def test_dormitories_overview_record():
    ctx = context(responses(), consumer=False, faculty_units=FACULTY_UNITS)
    dorms = collect(ctx)["dormitory:all"]
    assert dorms.kind == "dormitory"
    assert dorms.title == "Domy studenckie UJ"
    assert dorms.attributes.dormitory_id == "all"
    assert dorms.content.startswith("# Domy studenckie UJ\n")
    assert "| Nawojka | Naw |" in dorms.content
    # skrot rowny nazwie albo pusty - pusta komorka
    assert "| Piast |  |" in dorms.content and "| Żaczek |  |" in dorms.content


def test_rooms_error_degrades_to_buildings_without_rooms():
    ctx = context(
        responses(**{"services/geo/rooms": UsosError("services/geo/rooms", 500, "blad")}),
        consumer=False,
        faculty_units=FACULTY_UNITS,
    )
    records = collect(ctx)
    assert "building:Loj6" in records
    assert "Sale dydaktyczne" not in records["building:Loj6"].content
    assert any("geo/rooms" in warning for warning in ctx.warnings)


def test_dormitories_error_is_skipped():
    ctx = context(
        responses(**{"services/housing/dormitory_index": UsosError("services/housing/dormitory_index", 500, "blad")}),
        consumer=False,
        faculty_units=FACULTY_UNITS,
    )
    records = collect(ctx)
    assert "dormitory:all" not in records
    assert len(records) == 3
    assert any("dormitory_index" in warning for warning in ctx.warnings)


def test_building_phones_shared_with_units():
    # jedna funkcja telefonow dla budynkow (all_phone_numbers) i jednostek (phone_numbers2)
    assert places.phones is units.phones
    assert units.phones(BUILDINGS["Loj6"]) == ["12 664 66 29 (Portiernia)"]
    assert units.phones(BUILDINGS["Gol24"]) == ["12 422 10 33"]
    assert units.phones(BUILDINGS["Prad76"]) == []


def test_literal_selectors_built_with_fields():
    ctx = context(responses(), consumer=False, faculty_units=FACULTY_UNITS)
    collect(ctx)
    selectors = {method: params.get("fields") for method, params in ctx.api.calls if method != "services/geo/buildings2"}
    assert selectors["services/geo/building_index"] == "id"
    room_ids = [params["fields"] for method, params in ctx.api.calls if method == "services/geo/buildings2" and "rooms" in params["fields"]]
    assert room_ids == ["id|rooms[id]"]


def test_unknown_teaching_building_is_reported():
    ctx = context(responses(), consumer=False, faculty_units=FACULTY_UNITS, teaching_buildings={"XYZ"})
    collect(ctx)
    assert any("XYZ" in warning for warning in ctx.warnings)
