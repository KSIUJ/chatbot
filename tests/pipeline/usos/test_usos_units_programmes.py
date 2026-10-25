"""Kolektory units (jednostki wydzialu) i programmes (programy studiow)."""

from __future__ import annotations

from src.backend.rag.sources.usos.dataset import USOS_RECORD

from pipeline.scrapers.usos.collectors import programmes, units
from tests.pipeline.usos.fake_usos_api import context

UJ = {"id": "UJ", "name": {"pl": "Uniwersytet Jagielloński w Krakowie", "en": "Jagiellonian University in Kraków"}}
WMI_REF = {"id": "UJ.WMI", "name": {"pl": "Wydział Matematyki i Informatyki", "en": "Faculty of Mathematics and Computer Science"}}
II_REF = {"id": "UJ.WMI.II", "name": {"pl": "Instytut Informatyki i Matematyki Komputerowej", "en": ""}}


def unit(fac_id, name, path, en="", **extra):
    return {
        "id": fac_id,
        "name": {"pl": name, "en": en},
        "profile_url": f"https://www.usosweb.uj.edu.pl/kontroler.php?_action=katalog2/jednostki/pokazJednostke&kod={fac_id}",
        "homepage_url": None,
        "phone_numbers": [],
        "phone_numbers2": [],
        "postal_address": None,
        "email": None,
        "is_public": False,
        "path": path,
        **extra,
    }


FACULTY = unit(
    "UJ.WMI", "Wydział Matematyki i Informatyki", [UJ], en="Faculty of Mathematics and Computer Science",
    phone_numbers=["12 664 66 29"], postal_address="prof. Stanisława Łojasiewicza 6, 30-348 Kraków",
    homepage_url="https://www.matinf.uj.edu.pl/",
)
SUBUNITS = {
    "UJ.WMI.II": unit(
        "UJ.WMI.II", "Instytut Informatyki i Matematyki Komputerowej", [UJ, WMI_REF],
        en="Institute of Computer Science and Computational Mathematics",
        phone_numbers=["12 664 75 33"],
        phone_numbers2=[{"number": "12 664 75 33", "type": "STA", "comment": "Sekretariat Dydaktyczny"}],
    ),
    "UJ.WMI.II.ZPI": unit("UJ.WMI.II.ZPI", "Zakład Podstaw Informatyki", [UJ, WMI_REF, II_REF]),
    "UJ.WMI.II.UCP": unit("UJ.WMI.II.UCP", "UJ.WMI.II - Umowy cywilno-prawne", [UJ, WMI_REF, II_REF]),
    "UJ.WMI.DOKT": unit("UJ.WMI.DOKT", "Jednostka pomocnicza dla oddzielenia zajęć doktorantów", [UJ, WMI_REF]),
    "UJ.WMI.DK": unit("UJ.WMI.DK", "Dziekanat Wydziału Matematyki i Informatyki\n", [UJ, WMI_REF]),
}


def faculties(fac_ids, **_params):
    return {i: SUBUNITS.get(i) for i in fac_ids}


def unit_responses(sub_ids=None):
    return {
        "services/fac/faculty": FACULTY,
        "services/fac/subfaculties_deep": sub_ids if sub_ids is not None else list(SUBUNITS),
        "services/fac/faculties": faculties,
    }


def validated(records):
    for record in records:
        USOS_RECORD.validate_python(record.model_dump())
        assert "None" not in record.content
    return {record.id: record for record in records}


# --- units -----------------------------------------------------------------------------

def test_units_records_and_context():
    ctx = context(unit_responses(), consumer=False)
    records = validated(list(units.collect(ctx)))

    # jednostki techniczne (UCP, DOKT) bez rekordow, ale w kontekscie
    assert set(records) == {"unit:UJ.WMI", "unit:UJ.WMI.II", "unit:UJ.WMI.II.ZPI", "unit:UJ.WMI.DK"}
    assert ctx.faculty_units == ["UJ.WMI", *SUBUNITS]
    assert ctx.unit_names["UJ.WMI.II.UCP"] == "UJ.WMI.II - Umowy cywilno-prawne"
    assert ctx.unit_names["UJ.WMI"] == "Wydział Matematyki i Informatyki"
    assert ctx.unit_names["UJ.WMI.DK"] == "Dziekanat Wydziału Matematyki i Informatyki"

    faculty = records["unit:UJ.WMI"]
    assert faculty.kind == "unit" and faculty.title == "Wydział Matematyki i Informatyki"
    assert faculty.attributes.fac_id == "UJ.WMI" and faculty.attributes.parent_id == "UJ"
    assert faculty.url == FACULTY["profile_url"]
    assert faculty.content.startswith("# Wydział Matematyki i Informatyki\n")
    assert "Nazwa angielska: Faculty of Mathematics and Computer Science." in faculty.content
    assert "- Adres: prof. Stanisława Łojasiewicza 6, 30-348 Kraków" in faculty.content
    assert "- Telefon: 12 664 66 29" in faculty.content
    assert "- Strona internetowa: https://www.matinf.uj.edu.pl/" in faculty.content
    assert "- Jednostka nadrzędna: Uniwersytet Jagielloński w Krakowie" in faculty.content
    children = faculty.content.split("## Jednostki podrzędne")[1]
    assert "- Instytut Informatyki i Matematyki Komputerowej (UJ.WMI.II)" in children
    assert "- Dziekanat Wydziału Matematyki i Informatyki (UJ.WMI.DK)" in children
    assert "Zakład Podstaw" not in children and "pomocnicza" not in children

    institute = records["unit:UJ.WMI.II"]
    assert institute.attributes.parent_id == "UJ.WMI"
    assert "część jednostki: Wydział Matematyki i Informatyki" in institute.content
    assert "- Telefon: 12 664 75 33 (Sekretariat Dydaktyczny)" in institute.content
    assert "- Zakład Podstaw Informatyki (UJ.WMI.II.ZPI)" in institute.content
    assert "Umowy" not in institute.content

    leaf = records["unit:UJ.WMI.II.ZPI"]
    assert leaf.attributes.parent_id == "UJ.WMI.II"
    assert "Jednostki podrzędne" not in leaf.content
    assert "Nazwa angielska" not in leaf.content
    assert "Adres" not in leaf.content and "Telefon" not in leaf.content
    assert len(ctx.api.calls) == 3


def test_units_missing_subunit_is_reported():
    ctx = context(unit_responses(["UJ.WMI.II", "UJ.WMI.GONE"]), consumer=False)
    records = validated(list(units.collect(ctx)))
    assert set(records) == {"unit:UJ.WMI", "unit:UJ.WMI.II"}
    assert "UJ.WMI.GONE" in ctx.faculty_units
    assert any("UJ.WMI.GONE" in warning for warning in ctx.warnings)


def test_is_technical_unit_ids():
    assert units.is_technical("UJ.WMI.II.UCP") and units.is_technical("UJ.WMI.DOKT")
    assert not units.is_technical("UJ.WMI") and not units.is_technical("UJ.WMI.II.ZPI")
    # tylko ostatni czlon id
    assert not units.is_technical("UJ.UCP.II")


def test_phones_with_comment_first_then_plain_numbers():
    # phone_numbers2 jednostek i all_phone_numbers budynkow (komentarz moze byc slownikiem jezykowym)
    assert units.phones(SUBUNITS["UJ.WMI.II"]) == ["12 664 75 33 (Sekretariat Dydaktyczny)"]
    assert units.phones({"all_phone_numbers": [{"number": "12 1", "comment": {"pl": "Portiernia", "en": "Lodge"}}]}) == [
        "12 1 (Portiernia)"
    ]
    assert units.phones(FACULTY) == ["12 664 66 29"]
    assert units.phones({"phone_numbers": ["12 2", "12 2", " "], "phone_numbers2": ["zly", {"number": ""}]}) == ["12 2"]


# --- programmes ------------------------------------------------------------------------

def programme(pid, name, level, mode="stacjonarne", duration="3 lata", fac="UJ.WMI.II", en="", status="", enum=None):
    return {
        "id": pid,
        "name": {"pl": name, "en": en},
        "description": {"pl": name, "en": en},
        "faculty": {"id": fac, "name": {"pl": {"UJ.WMI.II": II_REF["name"]["pl"]}.get(fac, ""), "en": ""}},
        "all_faculties": [{"id": "UJ.WMI", "name": WMI_REF["name"]}, {"id": fac, "name": {"pl": "", "en": ""}}],
        "mode_of_studies": {"pl": mode, "en": ""},
        "level_of_studies": {"pl": level, "en": ""},
        "duration": {"pl": duration, "en": ""},
        "professional_status": {"pl": status, "en": ""},
        "level": enum,
    }


PROGRAMMES = {
    p["id"]: p
    for p in [
        programme("WMI-n037-0-ZD-6", "Informatyka, stacjonarne I stopnia", "pierwszego stopnia",
                  en="Computer Science, full-time, first-cycle", status="Licencjat", enum="first_cycle"),
        programme("WMI-037-0-ZD-6", "Informatyka, stacjonarne I stopnia", "pierwszego stopnia", enum="first_cycle"),
        programme("MSMP-n050-0-ZD-6", "Matematyka w ramach MSMP, stacjonarne I stopnia", "pierwszego stopnia",
                  fac="UJ.WMI.IM", enum="first_cycle"),
        programme("WMI-525A-P", "Testowanie oprogramowania, podyplomowe", "podyplomowe", mode="niestacjonarne",
                  duration="1 rok", fac="UJ.WMI"),
        programme("WMI-525B-P", "Testowanie oprogramowania, podyplomowe", "podyplomowe", mode="niestacjonarne",
                  duration="2 semestry", fac="UJ.WMI"),
        programme("WMI-701A-K", "Blue Team specialist, kurs", "kurs", mode="nie dotyczy", fac="UJ.WMI"),
        programme("WMI-701B-K", "Blue Team specialist, kurs", "kurs", mode="nie dotyczy", fac="UJ.WMI"),
        programme("WMI-701AA-K", "Blue Team Specialist, kurs", "kurs", mode="nie dotyczy", fac="UJ.WMI"),
        programme("MOST-WMI.II", "MOST", "krótkoterminowe", mode="nie dotyczy", duration=""),
        programme("CEEPUS-WMI", "Stypendyści CEEPUS", "krótkoterminowe", mode="nie dotyczy", fac="UJ.WMI"),
        programme("ER-WMI.II", "Program Erasmus w Instytucie Informatyki", "krótkoterminowe", fac="UJ.BOSZ"),
        programme("MSMP-0050-1SO", "Fizyka w ramach MSMP", "pierwszego stopnia", fac="UJ.WF"),
    ]
}
SEARCH = {
    "WMI": ["WMI-n037-0-ZD-6", "WMI-037-0-ZD-6", "WMI-525A-P", "WMI-525B-P", "WMI-701A-K", "WMI-701B-K",
            "WMI-701AA-K", "MOST-WMI.II", "CEEPUS-WMI", "ER-WMI.II"],
    "MSMP": ["MSMP-n050-0-ZD-6", "MSMP-0050-1SO"],
}


def search(lang, query, num, start, fields):
    assert lang == "pl" and num <= 20
    ids = SEARCH.get(query, [])
    page = ids[start:start + num]
    return {
        "items": [{"programme": {"id": i, "faculty": {"id": PROGRAMMES[i]["faculty"]["id"]}}} for i in page],
        "next_page": start + num < len(ids),
    }


def programmes_batch(programme_ids, fields):
    return {i: PROGRAMMES.get(i) for i in programme_ids}


def programme_responses(search_fn=search):
    return {"services/progs/search": search_fn, "services/progs/programmes": programmes_batch}


def programme_context(search_fn=search):
    return context(
        programme_responses(search_fn),
        consumer=False,
        faculty_units=["UJ.WMI", "UJ.WMI.II", "UJ.WMI.IM"],
        unit_names={"UJ.WMI": "Wydział Matematyki i Informatyki", "UJ.WMI.IM": "Instytut Matematyki"},
    )


def test_programmes_filtered_grouped_and_rendered():
    ctx = programme_context()
    records = validated(list(programmes.collect(ctx)))

    # wymiana (MOST, CEEPUS, Erasmus) i programy innych wydzialow pominiete;
    # edycje podyplomowych i kursow w jednym rekordzie
    assert set(records) == {
        "programme:WMI-n037-0-ZD-6", "programme:WMI-037-0-ZD-6", "programme:MSMP-n050-0-ZD-6",
        "programme:WMI-525A-P", "programme:WMI-701A-K",
    }
    queries = [params["query"] for method, params in ctx.api.calls if method == "services/progs/search"]
    assert queries[:2] == ["WMI", "MSMP"] and set(queries) == set(programmes.QUERIES)

    cs = records["programme:WMI-n037-0-ZD-6"]
    assert cs.kind == "programme"
    # rozne programy o tej samej nazwie - kod w tytule
    assert cs.title == "Informatyka, stacjonarne I stopnia (WMI-n037-0-ZD-6)"
    assert records["programme:WMI-037-0-ZD-6"].title == "Informatyka, stacjonarne I stopnia (WMI-037-0-ZD-6)"
    assert cs.url.endswith("pokazProgram&kod=WMI-n037-0-ZD-6")
    assert cs.attributes.model_dump() == {
        "programme_id": "WMI-n037-0-ZD-6", "fac_id": "UJ.WMI.II", "level": "pierwszego stopnia",
        "mode": "stacjonarne", "duration": "3 lata",
    }
    assert cs.content.startswith("# Informatyka, stacjonarne I stopnia\n")
    for line in [
        "- Poziom studiów: pierwszego stopnia",
        "- Tryb studiów: stacjonarne",
        "- Czas trwania: 3 lata",
        "- Kwalifikacje absolwenta: Licencjat",
        "- Jednostka prowadząca: Instytut Informatyki i Matematyki Komputerowej",
        "- Inne jednostki związane z programem: Wydział Matematyki i Informatyki",
        "- Nazwa angielska: Computer Science, full-time, first-cycle",
        "Kod programu w USOS: WMI-n037-0-ZD-6.",
    ]:
        assert line in cs.content
    # description to w USOS alias nazwy - bez sekcji "Opis"
    assert "## Opis" not in cs.content

    # nazwa jednostki z ctx.unit_names, gdy API jej nie podaje; puste pola pominiete
    msmp = records["programme:MSMP-n050-0-ZD-6"].content
    assert "- Jednostka prowadząca: Instytut Matematyki" in msmp
    assert "Kwalifikacje" not in msmp and "Nazwa angielska" not in msmp

    postgrad = records["programme:WMI-525A-P"]
    assert postgrad.title == "Testowanie oprogramowania, podyplomowe"
    assert "kilka kodów (kolejne edycje): WMI-525A-P, WMI-525B-P." in postgrad.content
    assert postgrad.attributes.duration == "1 rok, 2 semestry"

    course = records["programme:WMI-701A-K"]
    # najczestszy wariant nazwy
    assert course.title == "Blue Team specialist, kurs"
    assert "WMI-701A-K, WMI-701AA-K, WMI-701B-K" in course.content
    assert ctx.warnings == []


def test_programmes_capped_query_is_refined():
    capped = {"WMI": [f"WMI-{n:03d}-0-ZD-6" for n in range(120)]}
    for pid in capped["WMI"]:
        PROGRAMMES.setdefault(pid, programme(pid, f"Program {pid}", "pierwszego stopnia"))
    capped["WMI kurs"] = ["WMI-701A-K"]

    def capped_search(lang, query, num, start, fields):
        ids = capped.get(query, [])
        page = ids[start:start + num]
        return {
            "items": [{"programme": {"id": i, "faculty": {"id": PROGRAMMES[i]["faculty"]["id"]}}} for i in page],
            "next_page": start + num < len(ids),
        }

    try:
        ctx = programme_context(capped_search)
        records = validated(list(programmes.collect(ctx)))
    finally:
        for pid in capped["WMI"]:
            PROGRAMMES.pop(pid, None)
    queries = [params["query"] for method, params in ctx.api.calls if method == "services/progs/search"]
    assert {f"WMI {word}" for word in programmes.REFINEMENTS} <= set(queries)
    # najwyzej 100 wynikow na zapytanie (5 stron po 20)
    starts = [params["start"] for method, params in ctx.api.calls if params.get("query") == "WMI"]
    assert starts == [0, 20, 40, 60, 80]
    assert "programme:WMI-701A-K" in records
    assert len(records) == 101
