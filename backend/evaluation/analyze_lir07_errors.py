"""Summarize LIR-07 development/shadow failures without reading final-holdout cases."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluation.lir01_models import Lir01Corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    corpus = Lir01Corpus.model_validate_json(args.corpus.read_bytes())
    result = json.loads(args.result.read_text(encoding="utf-8"))
    cases = {
        case.id: case
        for case in corpus.cases
        if case.partition in {"development", "shadow_validation"}
    }
    confusion: Counter[str] = Counter()
    intent_errors: Counter[str] = Counter()
    operation_errors: Counter[str] = Counter()
    language_errors: Counter[str] = Counter()
    source_errors: Counter[str] = Counter()
    samples: dict[str, list[dict[str, object]]] = defaultdict(list)
    correct = 0
    for row in result["cases"]:
        case = cases[row["case_id"]]
        route_pair = f"{case.expected_route}->{row['actual_route']}"
        confusion[route_pair] += 1
        route_ok = case.expected_route == row["actual_route"]
        operation_ok = tuple(row["actual_operations"]) == case.expected_operation_ids
        if route_ok and operation_ok:
            correct += 1
            continue
        intent_errors[case.intent] += 1
        language_errors[case.language] += 1
        source_errors[row["source"]] += 1
        expected_operations = "+".join(case.expected_operation_ids) or "none"
        actual_operations = "+".join(row["actual_operations"]) or "none"
        operation_errors[f"{expected_operations}->{actual_operations}"] += 1
        key = f"{case.intent}:{row['source']}"
        if len(samples[key]) < 5:
            samples[key].append(
                {
                    "case_id": case.id,
                    "language": case.language,
                    "message": case.current_message,
                    "expected_route": case.expected_route,
                    "actual_route": row["actual_route"],
                    "expected_operations": case.expected_operation_ids,
                    "actual_operations": row["actual_operations"],
                }
            )
    payload = {
        "partitions": ["development", "shadow_validation"],
        "final_holdout_consumed": False,
        "case_count": len(cases),
        "exact_route_and_operation_count": correct,
        "confusion_matrix": dict(sorted(confusion.items())),
        "errors_by_intent": dict(intent_errors.most_common()),
        "errors_by_operation": dict(operation_errors.most_common()),
        "errors_by_language": dict(language_errors.most_common()),
        "errors_by_source": dict(source_errors.most_common()),
        "representative_errors": dict(sorted(samples.items())),
    }
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable analysis: {args.output}")
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary = {key: value for key, value in payload.items() if key != "representative_errors"}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
