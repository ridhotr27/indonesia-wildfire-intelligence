import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.run_q01 import evaluate_routes

BENCHMARK = Path(__file__).resolve().parents[2] / "evaluation" / "q01_benchmark_v1.json"


def test_benchmark_has_reviewable_balanced_fifty_question_set() -> None:
    payload = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    questions = payload["questions"]
    assert len(questions) == 50
    assert len({item["id"] for item in questions}) == 50
    assert {item["category"] for item in questions} >= {
        "analytics",
        "documentation",
        "combined",
        "unsupported",
        "adversarial",
    }
    assert all(item["question"].strip() for item in questions)


def test_q01_expected_routes_are_reproducible() -> None:
    questions = json.loads(BENCHMARK.read_text(encoding="utf-8"))["questions"]
    results, _ = asyncio.run(evaluate_routes(questions))
    failures = [row for row in results if not row["passed"]]
    assert failures == []
