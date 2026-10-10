"""
Pomiar wyszukiwania na zbiorze pytan (questions.jsonl).

Dla kazdego pytania: pozycja pierwszego oczekiwanego zrodla w kontekscie,
liczba trafien, dlugosc kontekstu i czas wyszukiwania. Podsumowanie: trafnosc
@1/@3/@5/w calym kontekscie i MRR (pytania z odpowiedzia), srednia liczba
trafien dla pytan bez odpowiedzi (im mniej, tym mniej szumu), czas (p50/p95)
i szczyt pamieci procesu.

Sciezki danych sa wzgledne (data/, dataset/) - uruchamiac z katalogu, w ktorym
leza dane, z repo w PYTHONPATH:

    cd /sciezka/z/danymi && PYTHONPATH=/repo python -m rag_eval.run --name baseline
"""

from __future__ import annotations

import argparse
import json
import resource
import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .questions import Question, load_questions
from .systems import SYSTEMS, System
from .targets import expected_rank

CUTOFFS = (1, 3, 5)


@dataclass(frozen=True)
class QuestionResult:
    id: str
    category: str
    answerable: bool
    # pozycja (od 1) pierwszego oczekiwanego zrodla; None = nie trafilo do kontekstu
    rank: int | None
    hits: int
    context_chars: int
    seconds: float
    query: str


def evaluate(system: System, questions: list[Question]) -> list[QuestionResult]:
    results = []
    for question in questions:
        started = time.perf_counter()
        retrieval = system.retrieve(question)
        seconds = time.perf_counter() - started
        results.append(
            QuestionResult(
                id=question.id,
                category=question.category,
                answerable=question.answerable,
                rank=expected_rank(question.expected, retrieval.hits) if question.answerable else None,
                hits=len(retrieval.hits),
                context_chars=retrieval.context_chars,
                seconds=round(seconds, 4),
                query=retrieval.query,
            )
        )
    return results


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def summarize(results: list[QuestionResult]) -> dict[str, dict]:
    """Metryki dla calosci ("all") i kazdej kategorii."""
    groups: dict[str, list[QuestionResult]] = defaultdict(list)
    for result in results:
        groups["all"].append(result)
        groups[result.category].append(result)

    summary = {}
    for name, group in groups.items():
        answerable = [r for r in group if r.answerable]
        unanswerable = [r for r in group if not r.answerable]
        metrics: dict[str, float | int | None] = {"questions": len(group), "answerable": len(answerable)}
        for cutoff in CUTOFFS:
            metrics[f"found@{cutoff}"] = _rate([r.rank is not None and r.rank <= cutoff for r in answerable])
        metrics["found@ctx"] = _rate([r.rank is not None for r in answerable])
        metrics["mrr"] = (
            round(statistics.fmean(1 / r.rank if r.rank else 0.0 for r in answerable), 3) if answerable else None
        )
        metrics["hits_when_no_answer"] = (
            round(statistics.fmean(r.hits for r in unanswerable), 2) if unanswerable else None
        )
        metrics["avg_context_chars"] = round(statistics.fmean(r.context_chars for r in group))
        summary[name] = metrics
    return summary


def timing(results: list[QuestionResult]) -> dict[str, float]:
    seconds = sorted(r.seconds for r in results)
    return {
        "p50_s": round(statistics.median(seconds), 3),
        "p95_s": round(seconds[min(len(seconds) - 1, int(0.95 * len(seconds)))], 3),
        "max_s": round(seconds[-1], 3),
    }


def _cell(value: object) -> str:
    if value is None:
        return "-"
    return f"{value:.0%}" if isinstance(value, float) and value <= 1 else str(value)


def table(summary: dict[str, dict]) -> str:
    columns = ["questions", *(f"found@{c}" for c in CUTOFFS), "found@ctx", "mrr", "hits_when_no_answer", "avg_context_chars"]
    lines = ["| category | " + " | ".join(columns) + " |", "|---" * (len(columns) + 1) + "|"]
    order = ["all", *sorted(k for k in summary if k != "all")]
    for name in order:
        row = summary[name]
        cells = [str(row["questions"]), *(_cell(row[c]) for c in columns[1:-3])]
        cells += [str(row["mrr"]) if row["mrr"] is not None else "-", _cell(row["hits_when_no_answer"]), str(row["avg_context_chars"])]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ewaluacja wyszukiwania RAG na zbiorze pytan.")
    parser.add_argument("--system", choices=sorted(SYSTEMS), default="current")
    parser.add_argument("--name", required=True, help="nazwa przebiegu (plik wynikow)")
    parser.add_argument("--category", action="append", help="tylko wybrane kategorie (mozna powtarzac)")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).with_name("results"))
    args = parser.parse_args()

    questions = load_questions()
    if args.category:
        questions = [q for q in questions if q.category in set(args.category)]

    started = time.perf_counter()
    system = SYSTEMS[args.system]()
    # pierwsze wyszukiwanie laduje modele i indeksy - nie wliczamy go do czasow
    system.retrieve(questions[0])
    startup_s = round(time.perf_counter() - started, 1)

    results = evaluate(system, questions)
    summary = summarize(results)
    report = {
        "name": args.name,
        "system": args.system,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "startup_s": startup_s,
        "timing": timing(results),
        # ru_maxrss w KB na Linuksie
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        "summary": summary,
        "questions": [asdict(r) for r in results],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.name}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(table(summary))
    print(f"\nstart {startup_s} s | wyszukiwanie {report['timing']} | pamiec {report['peak_rss_mb']} MB")
    missed = [r.id for r in results if r.answerable and r.rank is None]
    print(f"nie znaleziono ({len(missed)}): {', '.join(missed)}")
    print(f"wyniki: {out}")


if __name__ == "__main__":
    main()
