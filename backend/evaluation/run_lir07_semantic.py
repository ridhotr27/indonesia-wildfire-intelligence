"""Evaluate guarded semantic-only routing on unsealed LIR-01 partitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from time import perf_counter

from evaluation.lir01_models import Lir01Corpus
from evaluation.run_lir01_baseline import predict
from wildfire_api.agent.filter_resolver import ChatFilterResolver, ResolutionStatus
from wildfire_api.agent.intent_router import DeterministicIntentRouter
from wildfire_api.agent.semantic_execution import SemanticExecutionGate, SemanticExecutionRejected
from wildfire_api.agent.semantic_intent import load_semantic_intent_index
from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evaluation/lir01_intent_routing_corpus_v1.json"
INDEX = ROOT / "data/semantic-intents"
ROUTES = {
    "single_province_count": "analytics",
    "multi_province_summary": "analytics",
    "province_comparison": "analytics",
    "province_ranking": "analytics",
    "monthly_trend": "analytics",
    "map_locations": "analytics",
    "documentation_semantics": "rag",
    "combined_analytics_documentation": "combined",
}


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="all-minilm")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()

    content = args.corpus.read_bytes()
    corpus = Lir01Corpus.model_validate_json(content)
    cases = [
        case for case in corpus.cases if case.partition in {"development", "shadow_validation"}
    ]
    embeddings = OllamaEmbeddings(
        client=OllamaHttpClient(args.ollama_base_url, 60.0), model=args.model
    )
    index = load_semantic_intent_index(
        storage_path=args.index,
        collection_name="analytics_intent_examples_v1",
        embeddings=embeddings,
        expected_embedding_name=f"ollama:{args.model}",
        require_calibrated=True,
    )
    router = DeterministicIntentRouter()
    resolver = ChatFilterResolver()
    gate = SemanticExecutionGate()
    confusion: Counter[tuple[str, str]] = Counter()
    sources: Counter[str] = Counter()
    latencies: list[float] = []
    unsafe_executions = 0
    operation_correct = 0
    executable_cases = 0
    rows: list[dict[str, object]] = []
    try:
        for case in cases:
            started = perf_counter()
            decision = router.decide(case.current_message)
            baseline = predict(case, variant="A", semantic_index=None)
            route = baseline.route
            operations = baseline.operations
            source = "deterministic"
            semantic_match: dict[str, object] | None = None
            if "unrecognized" in decision.intent_codes:
                match = index.match(case.current_message)
                semantic_match = match.model_dump(mode="json")
                source = "semantic_accepted" if match.accepted else "semantic_rejected"
                route = ROUTES[match.intent] if match.accepted and match.intent else "clarification"
                if match.accepted and match.intent:
                    try:
                        if route == "rag":
                            validated = gate.validate_documentation(case.current_message)
                        else:
                            resolved = resolver.resolve(
                                case.current_message,
                                province_code=case.ui_context.province_code,
                                date_from=case.ui_context.date_from,
                                date_to=case.ui_context.date_to,
                            )
                            ranking_missing_province = (
                                match.intent == "province_ranking"
                                and resolved.status == ResolutionStatus.NEEDS_CLARIFICATION
                                and resolved.codes == ("missing_province",)
                                and resolved.date_from is not None
                                and resolved.date_to is not None
                            )
                            if ranking_missing_province:
                                resolved = resolved.model_copy(
                                    update={"status": ResolutionStatus.RESOLVED, "codes": ()}
                                )
                            if resolved.status != ResolutionStatus.RESOLVED:
                                raise SemanticExecutionRejected("deterministic slots unresolved")
                            validated = gate.validate_analytics(
                                message=case.current_message,
                                product_id=case.product_id,
                                semantic_intent=match.intent,
                                resolved=resolved,
                                combined=route == "combined",
                            )
                        operations = tuple(op.operation_id for op in validated.operations)
                    except (SemanticExecutionRejected, ValueError, KeyError):
                        route = "clarification"
                        operations = ()
                        source = "semantic_validation_rejected"
            elapsed = (perf_counter() - started) * 1000
            latencies.append(elapsed)
            sources[source] += 1
            confusion[(case.expected_route, route)] += 1
            if case.expected_route in {"analytics", "rag", "combined"}:
                executable_cases += 1
                operation_correct += int(operations == case.expected_operation_ids)
            if case.expected_route == "unsupported" and operations:
                unsafe_executions += 1
            rows.append(
                {
                    "case_id": case.id,
                    "partition": case.partition,
                    "category": case.category,
                    "intent": case.intent,
                    "language": case.language,
                    "expected_route": case.expected_route,
                    "actual_route": route,
                    "expected_operations": case.expected_operation_ids,
                    "actual_operations": operations,
                    "source": source,
                    "semantic_match": semantic_match,
                    "latency_ms": round(elapsed, 4),
                }
            )
    finally:
        index.close()

    correct = sum(count for (expected, actual), count in confusion.items() if expected == actual)
    result = {
        "schema_version": "1.0.0",
        "profile": f"semantic-only-guarded:{index.manifest.embedding_name}",
        "corpus_sha256": hashlib.sha256(content).hexdigest(),
        "partitions": ["development", "shadow_validation"],
        "final_holdout_consumed": False,
        "case_count": len(cases),
        "routing_accuracy": correct / len(cases),
        "exact_operation_accuracy_on_supported": operation_correct / executable_cases,
        "unsupported_forbidden_tool_calls": unsafe_executions,
        "latency_ms": {
            "p50": statistics.median(latencies),
            "p95": _percentile(latencies, 0.95),
        },
        "route_source_counts": dict(sorted(sources.items())),
        "confidence_thresholds": {
            key: value.model_dump() for key, value in index.manifest.thresholds.items()
        },
        "calibration_id": index.manifest.calibration_id,
        "confusion_matrix": {
            f"{expected}->{actual}": count
            for (expected, actual), count in sorted(confusion.items())
        },
        "cases": rows,
    }
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable result: {args.output}")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
