"""Ewaluacja RAG-a (rag_eval/): cele, zbior pytan i metryki - bez modeli."""

from __future__ import annotations

import pytest

from rag_eval import targets
from rag_eval.questions import load_questions
from rag_eval.run import QuestionResult, summarize


def test_page_targets_ignore_scheme_slash_and_encoding():
    actual = targets.page("https://matinf.uj.edu.pl/documents/1/urlop+dzieka%C5%84ski.pdf/abc/")

    assert targets.matches("page:matinf.uj.edu.pl/documents/1/urlop+dziekański.pdf/abc", actual)
    assert targets.matches("page:matinf.uj.edu.pl/documents/1/urlop+dziekański.pdf*", actual)
    assert not targets.matches("page:matinf.uj.edu.pl/documents/1", actual)


def test_staff_targets_ignore_case_and_spaces():
    assert targets.matches("staff:Jan  Kowalski", targets.staff("jan kowalski"))
    assert not targets.matches("staff:Jan Kowalski", targets.staff("Jan Nowak"))


def test_fragment_targets_and_wildcard():
    assert targets.matches("mordor:analiz", targets.mordor("data/mordor/Analiza 1/kolokwium.pdf"))
    assert targets.matches("ksi:*", targets.ksi("o-kole"))
    assert not targets.matches("ksi:*", targets.page("ksi.ii.uj.edu.pl"))


def test_expected_rank_is_the_first_matching_hit():
    hits = [frozenset({targets.page("a.pl/x")}), frozenset({targets.staff("Jan Kowalski")})]

    assert targets.expected_rank(["staff:Jan Kowalski", "page:b.pl"], hits) == 2
    assert targets.expected_rank(["page:b.pl"], hits) is None


@pytest.mark.parametrize("target", ["url:a.pl", "page:", "staff"])
def test_malformed_targets_are_rejected(target):
    with pytest.raises(ValueError):
        targets.validate(target)


def test_question_set_loads_and_covers_every_category():
    questions = load_questions()

    assert len(questions) >= 100
    categories = {q.category for q in questions}
    assert {"staff", "study", "faculty", "usos", "groups", "ksi", "mordor", "followup", "english", "none"} <= categories
    assert all(q.history for q in questions if q.category == "followup")
    assert not any(q.expected for q in questions if q.category == "none")


def _result(id_, category, rank, hits=5, answerable=True):
    return QuestionResult(id_, category, answerable, rank, hits, 1000, 0.1, "q")


def test_summary_metrics():
    summary = summarize([
        _result("a", "staff", 1),
        _result("b", "staff", 4),
        _result("c", "staff", None),
        _result("d", "none", None, hits=2, answerable=False),
    ])

    staff = summary["staff"]
    assert staff["found@1"] == 0.333
    assert staff["found@5"] == staff["found@ctx"] == 0.667
    assert staff["mrr"] == round((1 + 0.25 + 0) / 3, 3)
    assert summary["all"]["hits_when_no_answer"] == 2
    assert summary["none"]["found@1"] is None
