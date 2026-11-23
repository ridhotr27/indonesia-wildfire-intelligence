"""Run immutable LIR-01 A/B baselines without executing application tools."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

try:
    from evaluation.lir01_models import Lir01Case, Lir01Corpus
except ModuleNotFoundError:  # Direct execution from backend/evaluation.
    from lir01_models import Lir01Case, Lir01Corpus

from wildfire_api.agent.filter_resolver import ChatFilterResolver, ResolutionStatus
from wildfire_api.agent.intent_router import DeterministicIntentRouter
from wildfire_api.agent.semantic_intent import SemanticIntentIndex, load_semantic_intent_index
from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "evaluation" / "lir01_intent_routing_corpus_v1.json"
DEFAULT_INDEX = ROOT / "data" / "semantic-intents"
DEFAULT_COLLECTION = "analytics_intent_examples_v1"
DEFAULT_PARTITIONS = ("development", "shadow_validation")

Variant = Literal["A", "B"]

RANKING = re.compile(
    r"\b(which\s+province|top\s+(?:\d+|one|two|three|four|five)|"
    r"bottom\s+(?:\d+|one|two|three|four|five)|highest|lowest|most\s+hotspots?|"
    r"least\s+hotspots?|provinsi\s+mana|provinsi\s+teratas|peringkat|urutkan|terbanyak|"
    r"terendah)\b",
    re.IGNORECASE,
)
TREND = re.compile(
    r"\b(monthly|month-by-month|across\s+the\s+months|by\s+month|trend|bulanan|"
    r"setiap\s+bulan|menurut\s+bulan|sepanjang\s+2023|per\s+bulan)\b",
    re.IGNORECASE,
)
COMPARISON = re.compile(
    r"\b(compare|versus|difference|higher|lower|which\s+had|bandingkan|mana\s+yang|"
    r"lebih\s+banyak|berdampingan)\b",
    re.IGNORECASE,
)

SEMANTIC_OPERATIONS = {
    "single_province_count": "hotspot_summary_v1",
    "monthly_trend": "hotspot_trend_v1",
    "multi_province_summary": "hotspot_multi_province_summary_v1",
    "province_comparison": "hotspot_multi_province_summary_v1",
    "province_ranking": "hotspot_province_ranking_v1",
    "map_locations": "hotspot_map_v1",
    "documentation_semantics": "nasa_documentation_v1",
    "combined_analytics_documentation": "hotspot_summary_v1",
}
SEMANTIC_ROUTES = {
    "single_province_count": "analytics",
    "monthly_trend": "analytics",
    "multi_province_summary": "analytics",
    "province_comparison": "analytics",
    "province_ranking": "analytics",
    "map_locations": "analytics",
    "documentation_semantics": "rag",
    "combined_analytics_documentation": "combined",
}


@dataclass(frozen=True, slots=True)
class Prediction:
    route: str
    operations: tuple[str, ...]
    entities: dict[str, object]
    reason: str
    route_source: str
    duration_ms: float


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return ordered[index]


def load_corpus(path: Path) -> tuple[Lir01Corpus, str]:
    content = path.read_bytes()
    corpus = Lir01Corpus.model_validate_json(content)
    return corpus, hashlib.sha256(content).hexdigest()


def _operation_for(
    case: Lir01Case,
    province_codes: tuple[str, ...],
    semantic_intent: str | None,
) -> str:
    if semantic_intent:
        return SEMANTIC_OPERATIONS[semantic_intent]
    if RANKING.search(case.current_message):
        return "hotspot_province_ranking_v1"
    if len(province_codes) > 1:
        return "hotspot_multi_province_summary_v1"
    if TREND.search(case.current_message):
        return "hotspot_trend_v1"
    return "hotspot_summary_v1"


def _analytics_entities(
    case: Lir01Case,
    *,
    province_codes: tuple[str, ...],
    date_from: object,
    date_to: object,
    operation: str,
) -> dict[str, object]:
    direction = None
    top_n = None
    if operation == "hotspot_province_ranking_v1":
        direction = (
            "lowest"
            if re.search(
                r"\b(lowest|least|bottom|terendah|paling\s+sedikit)\b", case.current_message, re.I
            )
            else "highest"
        )
        top_match = re.search(
            r"\b(?:top|bottom)\s+(\d+|one|two|three|four|five)\b",
            case.current_message,
            re.I,
        )
        if not top_match:
            top_match = re.search(r"\b(lima)\s+provinsi\b", case.current_message, re.I)
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "lima": 5}
        top_n = (
            int(top_match.group(1))
            if top_match and top_match.group(1).isdigit()
            else words[top_match.group(1).casefold()]
            if top_match
            else 1
        )
    return {
        "product_id": case.product_id,
        "metric_id": "satellite_hotspot_detections",
        "province_codes": list(province_codes),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "direction": direction,
        "top_n": top_n,
        "comparison_requested": bool(COMPARISON.search(case.current_message)),
    }


def predict(
    case: Lir01Case,
    *,
    variant: Variant,
    semantic_index: SemanticIntentIndex | None,
) -> Prediction:
    started = perf_counter()
    router = DeterministicIntentRouter()
    resolver = ChatFilterResolver()
    decision = router.decide(case.current_message)
    route = decision.mode
    route_source = "deterministic"
    semantic_intent: str | None = None
    reason = decision.reason

    if variant == "B" and "unrecognized" in decision.intent_codes:
        if semantic_index is None:
            raise ValueError("variant B requires a semantic intent index")
        match = semantic_index.match(case.current_message)
        if match.accepted and match.intent:
            semantic_intent = match.intent
            route = SEMANTIC_ROUTES[match.intent]
            route_source = "semantic_accepted"
            reason = "semantic intent accepted"
        else:
            route = "clarification"
            route_source = "semantic_rejected"
            reason = match.reason

    operations: tuple[str, ...] = ()
    entities: dict[str, object] = {}
    if route in {"analytics", "combined"}:
        resolved = resolver.resolve(
            case.current_message,
            province_code=case.ui_context.province_code,
            date_from=case.ui_context.date_from,
            date_to=case.ui_context.date_to,
        )
        ranking = semantic_intent == "province_ranking" or bool(
            RANKING.search(case.current_message)
        )
        missing_only_province = (
            ranking
            and resolved.status == ResolutionStatus.NEEDS_CLARIFICATION
            and resolved.codes == ("missing_province",)
            and resolved.date_from is not None
            and resolved.date_to is not None
        )
        if resolved.status != ResolutionStatus.RESOLVED and not missing_only_province:
            route = "clarification"
            reason = resolved.codes[0] if resolved.codes else resolved.status.value
        else:
            province_codes = () if ranking else resolved.province_codes
            operation = _operation_for(case, province_codes, semantic_intent)
            operations = (operation,)
            if route == "combined":
                operations += ("nasa_documentation_v1",)
            entities = _analytics_entities(
                case,
                province_codes=province_codes,
                date_from=resolved.date_from,
                date_to=resolved.date_to,
                operation=operation,
            )
    elif route == "rag":
        operations = ("nasa_documentation_v1",)

    return Prediction(
        route=route,
        operations=operations,
        entities=entities,
        reason=reason,
        route_source=route_source,
        duration_ms=(perf_counter() - started) * 1000,
    )


def _expected_entity_projection(case: Lir01Case) -> dict[str, object]:
    expected = case.expected_entities
    return {
        "product_id": expected.product_id,
        "metric_id": expected.metric_id,
        "province_codes": list(expected.province_codes),
        "date_from": expected.date_from.isoformat() if expected.date_from else None,
        "date_to": expected.date_to.isoformat() if expected.date_to else None,
        "direction": expected.direction,
        "top_n": expected.top_n,
        "comparison_requested": expected.comparison_requested,
    }


def _class_metrics(confusion: Counter[tuple[str, str]], labels: list[str]) -> dict[str, object]:
    per_class: dict[str, object] = {}
    f1_values: list[float] = []
    for label in labels:
        true_positive = confusion[(label, label)]
        predicted = sum(count for (expected, actual), count in confusion.items() if actual == label)
        expected = sum(count for (wanted, _), count in confusion.items() if wanted == label)
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / expected if expected else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1_values.append(f1)
        per_class[label] = {
            "support": expected,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return {"macro_f1": statistics.mean(f1_values), "per_class": per_class}


def evaluate(
    cases: list[Lir01Case], variant: Variant, index: SemanticIntentIndex | None
) -> dict[str, object]:
    route_confusion: Counter[tuple[str, str]] = Counter()
    language_total: Counter[str] = Counter()
    language_correct: Counter[str] = Counter()
    category_total: Counter[str] = Counter()
    category_correct: Counter[str] = Counter()
    expected_tools = predicted_tools = correct_tools = 0
    entity_total = entity_correct = 0
    supported_fallbacks = 0
    predicted_clarifications = correct_clarifications = 0
    unsupported_count = unsupported_false_accepts = 0
    forbidden_tool_calls = 0
    latencies: list[float] = []
    route_sources: Counter[str] = Counter()
    results: list[dict[str, object]] = []

    for case in cases:
        prediction = predict(case, variant=variant, semantic_index=index)
        latencies.append(prediction.duration_ms)
        route_sources[prediction.route_source] += 1
        expected_route = case.expected_route
        route_confusion[(expected_route, prediction.route)] += 1
        language_total[case.language] += 1
        category_total[case.category] += 1
        route_matches = expected_route == prediction.route
        language_correct[case.language] += int(route_matches)
        category_correct[case.category] += int(route_matches)

        expected_operation_set = set(case.expected_operation_ids)
        predicted_operation_set = set(prediction.operations)
        expected_tools += len(expected_operation_set)
        predicted_tools += len(predicted_operation_set)
        correct_tools += len(expected_operation_set & predicted_operation_set)

        entity_matches: bool | None = None
        if expected_route in {"analytics", "combined"}:
            entity_total += 1
            entity_matches = prediction.entities == _expected_entity_projection(case)
            entity_correct += int(entity_matches)
        if expected_route in {"analytics", "rag", "combined"} and prediction.route in {
            "clarification",
            "unsupported",
        }:
            supported_fallbacks += 1
        if prediction.route == "clarification":
            predicted_clarifications += 1
            correct_clarifications += int(expected_route == "clarification")
        if expected_route == "unsupported":
            unsupported_count += 1
            if prediction.route in {"analytics", "rag", "combined"}:
                unsupported_false_accepts += 1
            if prediction.operations:
                forbidden_tool_calls += len(prediction.operations)

        results.append(
            {
                "case_id": case.id,
                "expected_route": expected_route,
                "actual_route": prediction.route,
                "expected_operation_ids": list(case.expected_operation_ids),
                "actual_operation_ids": list(prediction.operations),
                "route_correct": route_matches,
                "entity_exact": entity_matches,
                "actual_reason": prediction.reason,
                "route_source": prediction.route_source,
                "duration_ms": round(prediction.duration_ms, 4),
            }
        )

    labels = ["analytics", "rag", "combined", "clarification", "unsupported"]
    route_metrics = _class_metrics(route_confusion, labels)
    tool_precision = correct_tools / predicted_tools if predicted_tools else 0.0
    tool_recall = correct_tools / expected_tools if expected_tools else 0.0
    return {
        "variant": variant,
        "case_count": len(cases),
        "metrics": {
            "routing_accuracy": sum(count for (a, b), count in route_confusion.items() if a == b)
            / len(cases),
            "routing_macro_f1": route_metrics["macro_f1"],
            "routing_per_class": route_metrics["per_class"],
            "tool_selection": {
                "precision": tool_precision,
                "recall": tool_recall,
                "f1": 2 * tool_precision * tool_recall / (tool_precision + tool_recall)
                if tool_precision + tool_recall
                else 0.0,
            },
            "entity_exact_accuracy": entity_correct / entity_total if entity_total else None,
            "unnecessary_supported_fallback_rate": supported_fallbacks
            / sum(case.expected_route in {"analytics", "rag", "combined"} for case in cases),
            "clarification_precision": correct_clarifications / predicted_clarifications
            if predicted_clarifications
            else None,
            "unsupported_false_accept_rate": unsupported_false_accepts / unsupported_count
            if unsupported_count
            else None,
            "forbidden_tool_calls": forbidden_tool_calls,
            "per_language_route_accuracy": {
                language: language_correct[language] / count
                for language, count in sorted(language_total.items())
            },
            "per_category_route_accuracy": {
                category: category_correct[category] / count
                for category, count in sorted(category_total.items())
            },
            "latency_ms": {
                "p50": statistics.median(latencies),
                "p95": percentile(latencies, 0.95),
            },
            "route_source_counts": dict(sorted(route_sources.items())),
            "confusion_matrix": {
                f"{expected}->{actual}": count
                for (expected, actual), count in sorted(route_confusion.items())
            },
        },
        "cases": results,
    }


async def run(args: argparse.Namespace) -> list[Path]:
    corpus, corpus_hash = load_corpus(args.corpus)
    selected = [case for case in corpus.cases if case.partition in args.partitions]
    if "final_holdout" in args.partitions and not args.allow_final_holdout:
        raise ValueError(
            "final_holdout is sealed; pass --allow-final-holdout only for approved LIR-12"
        )
    outputs: list[Path] = []
    index: SemanticIntentIndex | None = None
    try:
        for variant in args.variants:
            if variant == "B" and index is None:
                embeddings = OllamaEmbeddings(
                    client=OllamaHttpClient(args.ollama_base_url, args.ollama_timeout_seconds),
                    model=args.embedding_model,
                )
                index = load_semantic_intent_index(
                    storage_path=args.semantic_index,
                    collection_name=args.semantic_collection,
                    embeddings=embeddings,
                    expected_embedding_name=f"ollama:{args.embedding_model}",
                    require_calibrated=True,
                )
            result = evaluate(selected, variant, index if variant == "B" else None)
            result.update(
                {
                    "schema_version": "1.0.0",
                    "dataset_version": corpus.dataset_version,
                    "corpus_sha256": corpus_hash,
                    "partitions": list(args.partitions),
                    "final_holdout_consumed": "final_holdout" in args.partitions,
                    "profile": (
                        "current-deterministic-router"
                        if variant == "A"
                        else f"current-b14-semantic:{index.manifest.embedding_name}"
                    ),
                    "semantic_manifest": (
                        index.manifest.model_dump(mode="json") if variant == "B" and index else None
                    ),
                    "limitations": [
                        (
                            "Evaluation predicts routes, operations, and entities without "
                            "executing ClickHouse, Qdrant NASA retrieval, or answer generation."
                        ),
                        (
                            "Multi-turn history is intentionally ignored by current A/B "
                            "variants because the public API has no history contract."
                        ),
                        "No numeric NASA result is claimed by this corpus or baseline.",
                    ],
                }
            )
            output = args.output_dir / f"lir01_variant_{variant.lower()}_baseline_v1.json"
            if output.exists():
                raise FileExistsError(f"refusing to overwrite immutable result: {output}")
            output.write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            outputs.append(output)
    finally:
        if index is not None:
            index.close()
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--variants", nargs="+", choices=("A", "B"), default=("A", "B"))
    parser.add_argument(
        "--partitions",
        nargs="+",
        choices=("development", "shadow_validation", "final_holdout"),
        default=DEFAULT_PARTITIONS,
    )
    parser.add_argument("--allow-final-holdout", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation")
    parser.add_argument("--semantic-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--semantic-collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--embedding-model", default="all-minilm")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-timeout-seconds", type=float, default=60.0)
    return parser.parse_args()


def main() -> int:
    outputs = asyncio.run(run(parse_args()))
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
