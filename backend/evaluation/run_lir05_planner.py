"""Evaluate the isolated LIR-05 planner on LIR-01 development cases."""

from __future__ import annotations

import argparse
import asyncio
import json
import resource
from collections import Counter
from pathlib import Path

try:
    from evaluation.lir01_models import Lir01Corpus
    from evaluation.run_lir01_baseline import percentile
except ModuleNotFoundError:
    from lir01_models import Lir01Corpus
    from run_lir01_baseline import percentile

from wildfire_api.agent.intent_validator import IntentPlanValidator
from wildfire_api.agent.operation_registry import OperationRegistry
from wildfire_api.agent.structured_planner import (
    OllamaStructuredIntentPlanner,
    PlannerContext,
    PlannerRequest,
)
from wildfire_api.llm.ollama import OllamaHttpClient

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


async def run(args: argparse.Namespace) -> dict[str, object]:
    corpus = Lir01Corpus.model_validate_json(args.corpus.read_bytes())
    cases = [
        case
        for case in corpus.cases
        if case.partition == "development" and case.expected_calls.planner_calls["C"] == 1
    ]
    if args.case_id:
        requested = set(args.case_id)
        cases = [case for case in cases if case.id in requested]
        found = {case.id for case in cases}
        if found != requested:
            raise ValueError(f"unknown or ineligible case IDs: {sorted(requested - found)}")
    if args.limit is not None:
        cases = cases[: args.limit]
    registry = OperationRegistry.from_catalog(args.catalog)
    planner = OllamaStructuredIntentPlanner(
        client=OllamaHttpClient(args.ollama_base_url, args.timeout_seconds),
        registry=registry,
        validator=IntentPlanValidator(registry, args.catalog),
        timeout_seconds=args.timeout_seconds,
        max_tokens=args.max_tokens,
        enabled=True,
    )
    rows = []
    for case in cases:
        result = await planner.plan(
            PlannerRequest(
                question=case.current_message,
                context=PlannerContext(
                    product_id=case.product_id,
                    province_code=case.ui_context.province_code,
                    date_from=case.ui_context.date_from,
                    date_to=case.ui_context.date_to,
                ),
            )
        )
        predicted_route = result.plan.route if result.plan else "clarification"
        operations = tuple(result.plan.operation_ids) if result.plan else ()
        rows.append(
            {
                "case_id": case.id,
                "reason": result.reason,
                "predicted_route": predicted_route,
                "route_correct": predicted_route == case.expected_route,
                "operations_correct": operations == case.expected_operation_ids,
                "duration_ms": result.duration_ms,
                "model_calls": result.model_calls,
                "rejection_codes": list(result.rejection_codes),
            }
        )
    durations = [row["duration_ms"] for row in rows]
    count = len(rows)
    return {
        "profile": "lir05:qwen2.5:1.5b:prompt-v2",
        "corpus_version": corpus.dataset_version,
        "partition": "development",
        "case_count": count,
        "route_accuracy": sum(row["route_correct"] for row in rows) / count if count else None,
        "operation_exactness": (
            sum(row["operations_correct"] for row in rows) / count if count else None
        ),
        "model_calls": sum(row["model_calls"] for row in rows),
        "valid_plan_rate": (
            sum(row["reason"] in {"accepted", "clarification", "unsupported"} for row in rows)
            / count
            if count
            else None
        ),
        "timeout_rate": (
            sum(row["reason"] == "timeout" for row in rows) / count if count else None
        ),
        "rejection_code_counts": dict(
            sorted(Counter(code for row in rows for code in row["rejection_codes"]).items())
        ),
        "latency_ms": {
            "p50": percentile(durations, 0.5),
            "p95": percentile(durations, 0.95),
        },
        "process_max_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "results": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus", type=Path, default=ROOT / "evaluation/lir01_intent_routing_corpus_v1.json"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=REPOSITORY_ROOT / "data/contracts/hotspot_semantic_catalog_v1.0.0.json",
    )
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(run(args))
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite result: {args.output}")
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
