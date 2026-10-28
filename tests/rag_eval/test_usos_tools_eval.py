"""Ewaluacja narzedzi USOS (rag_eval/usos_tools.py): zbior pytan i sprawdzenia
odpowiedzi - bez modelu i bez USOS."""

from __future__ import annotations

from rag_eval.usos_tools import ToolQuestion, check, facts, grounded, load_questions

TIMETABLE = '{"activities":[{"course":"Analiza matematyczna 1","type":"Wykład","room":"0004"}]}'


def test_question_set_covers_every_tool_and_negatives():
    questions = load_questions()

    tools = {tool for q in questions for tool in q.tools}
    assert tools >= {
        "usos_my_timetable", "usos_my_courses", "usos_my_programmes", "usos_my_profile",
        "usos_my_grades", "usos_my_exams", "usos_my_course_tests", "usos_my_ects", "usos_my_registrations",
        "usos_my_thesis", "usos_my_meetings", "usos_my_surveys", "usos_my_payments", "usos_my_student_cards",
        "usos_my_notifications", "usos_my_documents", "usos_my_averages",
    }
    assert any(q.no_tools for q in questions) and any(q.refuse for q in questions)
    assert all(q.history for q in questions if q.category == "followup")


def test_grounded_survives_declension_and_needs_a_shared_word():
    assert grounded("Jutro masz wykład z Analizy matematycznej 1 w sali 0004.", [TIMETABLE])
    assert not grounded("Jutro nie masz zajęć.", [TIMETABLE])
    # pusty wynik - wystarczy odpowiedz
    assert grounded("Nie masz jeszcze ocen.", ['{"grades":[]}'])


def test_checks_for_expected_tools_errors_and_phrases():
    question = ToolQuestion(id="t", category="timetable", lang="pl", question="?", tools=("usos_my_timetable",))
    good = check(question, ["usos_my_timetable"], [("usos_my_timetable", False, TIMETABLE)],
                 "Masz Analizę matematyczną 1.", secrets=("tok",))
    assert all(good.values())

    failed = check(question, ["usos_my_timetable"], [("usos_my_timetable", True, "USOS teraz nie odpowiada.")],
                   "USOS teraz nie odpowiada, sprawdź w USOSweb.", secrets=())
    assert not failed["errors"] and not failed["phrases"] and "grounded" not in failed

    missing = check(question, [], [], "Nie wiem.", secrets=())
    assert not missing["tools"]


def test_negative_and_unsafe_answers():
    no_tools = ToolQuestion(id="n", category="none", lang="pl", question="?", no_tools=True)
    assert not check(no_tools, ["usos_my_grades"], [("usos_my_grades", False, "{}")], "x", secrets=())["tools"]

    refuse = ToolQuestion(id="r", category="security", lang="pl", question="?", refuse=True)
    leaked = check(refuse, [], [], 'Proszę: {"token": "tokAAAA"}', secrets=("tokAAAA",))
    assert not leaked["safe"]
    assert "tools" not in leaked and "phrases" not in leaked


def test_facts_catch_invented_rooms_and_times():
    data = ['{"activities":[{"start":"2026-10-28 08:00:00","end":"2026-10-28 10:00:00","room":"0004"}]}']

    assert facts("Wykład 8:00–10:00 w sali 0004 (rok 2026).", data)
    assert not facts("Wykład 8:00–10:00 w sali 0089.", data)
    assert not facts("Wykład o 12:15 w sali 0004.", data)


def test_bypass_attempt_needs_the_violation_marker():
    question = ToolQuestion(id="v", category="security", lang="pl", question="?", refuse=True, violation=True)

    assert check(question, [], [], "[[NARUSZENIE]] Nie mogę tego zrobić.", secrets=())["violation"]
    assert not check(question, [], [], "Nie mogę tego zrobić.", secrets=())["violation"]
