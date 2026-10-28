"""Srednie ocen z USOS (usos/averages.py): zasady liczenia, rok akademicki
i rok studiow, przypisanie przedmiotow do kierunkow (pewne i niepewne),
filtry kierunku, roku i listy przedmiotow."""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.usos.averages import GradeEntry, Programme, compute_averages, grade_value, parse_year

INF = Programme(id="1", code="WMI-INF", name="Informatyka", status="aktywny", admission=date(2024, 10, 1), ects_used=90)
SI = Programme(id="2", code="WMI-SI", name="Sztuczna inteligencja", status="aktywny", admission=date(2025, 10, 1),
               ects_used=40)
# kierunek bez zaliczonych punktow (np. dopiero rozpoczety) nie jest kandydatem
NEW = Programme(id="3", code="WMI-X", name="Inny", status="aktywny", admission=date(2025, 10, 1), ects_used=0)
PROGRAMMES = [INF, SI, NEW]
GRADES = [
    GradeEntry("24/25Z", "A", 5), GradeEntry("24/25L", "B", 4),
    GradeEntry("25/26Z", "C", 3), GradeEntry("26/27Z", "D", 4),
]
ECTS = {("24/25Z", "A"): 6, ("24/25L", "B"): 4, ("25/26Z", "C"): 5, ("26/27Z", "D"): 3}
NAMES = {"A": "Analiza", "B": "Bazy", "C": "Całki", "D": "Deep learning"}
# biezacy cykl: powiazanie z rejestracji
LINKS = {("26/27Z", "D"): {"WMI-SI"}}


def _run(**filters):
    return compute_averages(GRADES, ECTS, NAMES, PROGRAMMES, LINKS, **filters)


@pytest.mark.parametrize(("symbol", "value"), [("4,5", 4.5), ("5", 5.0), ("5!", 5.0), ("3.5", 3.5),
                                                ("zal", None), ("NK", None), ("", None), ("7", None)])
def test_grade_values(symbol, value):
    assert grade_value(symbol) == value


def test_academic_year_parsing():
    assert parse_year("2025/26") == parse_year("25/26") == parse_year("2025/2026") == parse_year("25/26Z") == 2025
    assert parse_year("rok") is None


def test_overall_per_year_and_per_programme():
    result = _run()

    assert result["overall"] == {"average": 4.0, "weighted_average": 4.06, "grades": 4, "ects": 18}
    assert [(y["academic_year"], y["average"], y["weighted_average"]) for y in result["by_academic_year"]] == [
        ("2024/25", 4.5, 4.6), ("2025/26", 3.0, 3.0), ("2026/27", 4.0, 4.0),
    ]
    inf, si, new = result["by_programme"]
    assert (inf["programme"], inf["average"], inf["weighted_average"], inf["grades"]) == ("Informatyka", 4.5, 4.6, 2)
    assert [(y["academic_year"], y["year_of_study"]) for y in inf["years"]] == [("2024/25", 1)]
    # biezacy przedmiot z powiazania w rejestracji, 2026/27 to drugi rok SI
    assert (si["average"], [(y["academic_year"], y["year_of_study"]) for y in si["years"]]) == (4.0, [("2026/27", 2)])
    assert new["grades"] == 0 and new["average"] is None
    # 2025/26: dwa kierunki z punktami - przedmiot bez pewnego kierunku
    assert result["unassigned_courses"] == [{"term": "25/26Z", "course_id": "C", "course": "Całki",
                                             "possible_programmes": ["Informatyka", "Sztuczna inteligencja"]}]
    assert result["courses_counted"] == 4 and "szacunek" in result["method"]


def test_programme_filter_counts_only_certain_courses_and_include_adds_confirmed_ones():
    si_only = _run(programme="sztuczna")

    assert si_only["overall"]["average"] == 4.0 and si_only["overall"]["grades"] == 1
    assert [p["programme"] for p in si_only["by_programme"]] == ["Sztuczna inteligencja"]
    assert [c["course_id"] for c in si_only["unassigned_courses"]] == ["C"]

    confirmed = _run(programme="WMI-SI", include=["C"])

    assert confirmed["overall"]["average"] == 3.5 and confirmed["unassigned_courses"] == []
    assert confirmed["by_programme"][0]["grades"] == 2


def test_year_and_exclude_filters():
    first = _run(year=2024)
    assert first["overall"]["average"] == 4.5 and first["filters"]["academic_year"] == "2024/25"
    assert first["unassigned_courses"] == []

    without = _run(exclude=["D", "C"])
    assert without["overall"]["average"] == 4.5 and without["overall"]["grades"] == 2


def test_single_programme_assigns_everything():
    result = compute_averages(GRADES, ECTS, NAMES, [INF], {})

    assert result["by_programme"][0]["grades"] == 4 and result["unassigned_courses"] == []
    assert [y["year_of_study"] for y in result["by_programme"][0]["years"]] == [1, 2, 3]
