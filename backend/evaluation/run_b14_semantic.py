"""Evaluate deterministic-first B14 routing on the committed corpus."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter

from wildfire_api.agent.intent_router import DeterministicIntentRouter
from wildfire_api.agent.semantic_intent import (
    SemanticIntent,
    build_semantic_intent_index,
    load_example_set,
    load_semantic_intent_index,
)
from wildfire_api.core.config import Settings
from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient
from wildfire_api.rag.embeddings import HashingEmbeddings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "evaluation" / "b14_semantic_corpus_v1.json"
DEFAULT_EXAMPLES = ROOT / "resources" / "semantic_intents" / "examples_v1.json"
INTENT_MODES = {
    "single_province_count": "analytics",
    "multi_province_summary": "analytics",
    "province_comparison": "analytics",
    "province_ranking": "analytics",
    "monthly_trend": "analytics",
    "map_locations": "analytics",
    "documentation_semantics": "rag",
    "combined_analytics_documentation": "combined",
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return ordered[index]


def evaluate(index, cases: list[dict[str, object]], profile: str) -> dict[str, object]:
    router = DeterministicIntentRouter()
    route_correct = 0
    baseline_supported_fallbacks = 0
    recovered_fallbacks = 0
    semantic_eligible = 0
    semantic_intent_correct = 0
    unsupported_false_accepts = 0
    latencies: list[float] = []
    intent_counts: Counter[str] = Counter()
    intent_correct: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    language_correct: Counter[str] = Counter()
    confusion: Counter[tuple[str, str]] = Counter()
    semantic_accepted = 0
    semantic_rejected = 0
    deterministic_routes = 0

    for case in cases:
        question = str(case["question"])
        expected_intent = case["expected_intent"]
        expected_mode = str(case["expected_mode"])
        language = str(case["language"])
        deterministic = router.decide(question)
        predicted_mode = deterministic.mode
        predicted_intent: SemanticIntent | None = None
        if expected_intent and deterministic.mode == "unsupported":
            baseline_supported_fallbacks += 1
        if "unrecognized" in deterministic.intent_codes:
            semantic_eligible += 1
            started = perf_counter()
            match = index.match(question)
            latencies.append((perf_counter() - started) * 1000)
            if match.accepted and match.intent is not None:
                predicted_intent = match.intent
                semantic_accepted += 1
                predicted_mode = INTENT_MODES[match.intent]
                if expected_intent:
                    recovered_fallbacks += 1
                else:
                    unsupported_false_accepts += 1
            else:
                semantic_rejected += 1
            confusion[
                (
                    str(expected_intent) if expected_intent else "unsupported",
                    str(predicted_intent) if predicted_intent else "rejected",
                )
            ] += 1
        else:
            deterministic_routes += 1
        if predicted_mode == expected_mode:
            route_correct += 1
            language_correct[language] += 1
        language_counts[language] += 1
        if expected_intent and "unrecognized" in deterministic.intent_codes:
            intent = str(expected_intent)
            intent_counts[intent] += 1
            if predicted_intent == expected_intent:
                semantic_intent_correct += 1
                intent_correct[intent] += 1

    intent_quality: dict[str, dict[str, float]] = {}
    for intent in sorted(INTENT_MODES):
        true_positive = confusion[(intent, intent)]
        predicted = sum(
            count for (expected, actual), count in confusion.items() if actual == intent
        )
        expected = sum(count for (wanted, actual), count in confusion.items() if wanted == intent)
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / expected if expected else 0.0
        intent_quality[intent] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0,
        }
    rejected = sum(count for (expected, actual), count in confusion.items() if actual == "rejected")
    correct_rejections = confusion[("unsupported", "rejected")]
    return {
        "profile": profile,
        "cases": len(cases),
        "route_accuracy": route_correct / len(cases),
        "baseline_supported_fallbacks": baseline_supported_fallbacks,
        "semantic_eligible": semantic_eligible,
        "semantic_intent_accuracy_on_eligible_supported": (
            semantic_intent_correct / sum(intent_counts.values())
            if intent_counts
            else None
        ),
        "fallback_recovery_rate": (
            recovered_fallbacks / baseline_supported_fallbacks
            if baseline_supported_fallbacks
            else None
        ),
        "unsupported_false_accept_rate": unsupported_false_accepts
        / sum(case["expected_intent"] is None for case in cases),
        "per_intent_recall": {
            intent: intent_correct[intent] / count
            for intent, count in sorted(intent_counts.items())
        },
        "per_intent_precision_recall_f1": intent_quality,
        "confusion_matrix": {
            f"{expected}->{actual}": count
            for (expected, actual), count in sorted(confusion.items())
        },
        "clarification_precision": correct_rejections / rejected if rejected else None,
        "route_share": {
            "deterministic": deterministic_routes / len(cases),
            "semantic_accepted": semantic_accepted / len(cases),
            "semantic_rejected": semantic_rejected / len(cases),
        },
        "per_language_route_accuracy": {
            language: language_correct[language] / count
            for language, count in sorted(language_counts.items())
        },
        "semantic_latency_ms": {
            "count": len(latencies),
            "p50": statistics.median(latencies) if latencies else None,
            "p95": percentile(latencies, 0.95) if latencies else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
    parser.add_argument("--surrogate", action="store_true")
    parser.add_argument(
        "--partition", choices=("all", "development", "heldout"), default="all"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = json.loads(args.corpus.read_text(encoding="utf-8"))["cases"]
    if args.partition != "all":
        cases = [case for case in cases if case["partition"] == args.partition]

    with tempfile.TemporaryDirectory(prefix="b14-evaluation-") as temporary:
        if args.surrogate:
            examples = load_example_set(args.examples)
            embeddings = HashingEmbeddings.from_texts(
                [example.text for example in examples.examples], dimensions=512
            )
            index, _ = build_semantic_intent_index(
                examples,
                storage_path=Path(temporary) / "index",
                collection_name="b14_surrogate",
                embeddings=embeddings,
                embedding_name="evaluation:hashing-v1",
            )
            profile = "hashing-surrogate-not-release-evidence"
        else:
            settings = Settings()
            embeddings = OllamaEmbeddings(
                client=OllamaHttpClient(
                    settings.ollama_base_url, settings.ollama_timeout_seconds
                ),
                model=settings.embedding_model_name,
            )
            index = load_semantic_intent_index(
                storage_path=settings.semantic_intent_path,
                collection_name=settings.semantic_intent_collection,
                embeddings=embeddings,
                expected_embedding_name=f"ollama:{settings.embedding_model_name}",
            )
            profile = f"ollama:{settings.embedding_model_name}"
        try:
            result = evaluate(index, cases, profile)
        finally:
            index.close()

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
