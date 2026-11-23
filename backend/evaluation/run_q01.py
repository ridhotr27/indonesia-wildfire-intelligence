from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wildfire_api.agent.runtime import RuleBasedPlanner
from wildfire_api.rag.fetch import fetch_source
from wildfire_api.rag.index import build_index, load_manifest

HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the reproducible Q01 benchmark")
    parser.add_argument("--benchmark", type=Path, default=HERE / "q01_benchmark_v1.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-retrieval", action="store_true")
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


async def evaluate_routes(
    questions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[float]]:
    planner = RuleBasedPlanner()
    results: list[dict[str, Any]] = []
    timings: list[float] = []
    for item in questions:
        started = time.perf_counter()
        plan = await planner(item["question"])
        timings.append((time.perf_counter() - started) * 1000)
        results.append({
            "id": item["id"],
            "expected_mode": item["expected_mode"],
            "observed_mode": plan.mode,
            "passed": plan.mode == item["expected_mode"],
        })
    return results, timings


def evaluate_retrieval(
    questions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fetched = [fetch_source(source) for source in load_manifest()]
    index, chunks = build_index(fetched)
    results = []
    for item in questions:
        if not item.get("relevant_documents"):
            continue
        passages = index.retrieve(item["question"], limit=5)
        observed = [passage.document_id for passage in passages]
        recalled = bool(set(observed) & set(item["relevant_documents"]))
        text = " ".join(passage.text.casefold() for passage in passages)
        supported = all(term.casefold() in text for term in item["support_terms"])
        results.append({
            "id": item["id"],
            "observed_document_ids": observed,
            "recalled_at_5": recalled,
            "support_terms_present": supported,
        })
    return results, {
        "source_count": len(fetched),
        "chunk_count": len(chunks),
        "sources": [{
            "document_id": doc.source.document_id,
            "url": str(doc.final_url),
            "bytes": doc.source_bytes,
            "content_hash": doc.content_hash,
        } for doc in fetched],
    }


async def main() -> None:
    args = parse_args()
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    questions = benchmark["questions"]
    if len(questions) < 50:
        raise ValueError("Q01 requires at least 50 reviewed questions")
    route_results, timings = await evaluate_routes(questions)
    retrieval_results: list[dict[str, Any]] = []
    retrieval_provenance = None
    if not args.skip_retrieval:
        retrieval_results, retrieval_provenance = evaluate_retrieval(questions)
    supported = [row for row in route_results if row["expected_mode"] != "unsupported"]
    unsupported = [row for row in route_results if row["expected_mode"] == "unsupported"]
    payload = {
        "ticket": "Q01",
        "benchmark_version": benchmark["benchmark_version"],
        "executed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "question_count": len(questions),
        "metrics": {
            "supported_route_accuracy": sum(row["passed"] for row in supported) / len(supported),
            "unsupported_handling": sum(row["passed"] for row in unsupported) / len(unsupported),
            "retrieval_recall_at_5": (
                sum(row["recalled_at_5"] for row in retrieval_results) / len(retrieval_results)
                if retrieval_results else None
            ),
            "retrieved_support_term_rate": (
                sum(row["support_terms_present"] for row in retrieval_results)
                / len(retrieval_results)
                if retrieval_results else None
            ),
            "planner_latency_ms_median": statistics.median(timings),
            "planner_latency_ms_p95": percentile(timings, 0.95),
            "unsafe_query_executions": 0,
        },
        "route_results": route_results,
        "retrieval_results": retrieval_results,
        "retrieval_provenance": retrieval_provenance,
        "limitations": [
            "Route accuracy is not analytical numeric-answer accuracy.",
            (
                "Support-term presence is a reproducible proxy, not the required "
                "manual citation-claim audit."
            ),
            "The deterministic hashing retriever is not an approved production embedding model.",
            (
                "Unsafe execution is zero because the evaluated planner exposes no "
                "arbitrary SQL execution seam."
            ),
        ],
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    asyncio.run(main())
