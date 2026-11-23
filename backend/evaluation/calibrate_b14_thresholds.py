"""Calibrate B14 score/margin/agreement thresholds on development cases only."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

from wildfire_api.agent.intent_router import DeterministicIntentRouter
from wildfire_api.agent.semantic_intent import (
    INTENT_TAXONOMY_VERSION,
    IntentThreshold,
    SemanticIntent,
    SemanticIntentCalibration,
    load_semantic_intent_index,
)
from wildfire_api.core.config import Settings
from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "evaluation" / "b14_semantic_corpus_v1.json"


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _calibrate_intent(
    intent: SemanticIntent,
    observations: list[dict[str, object]],
) -> IntentThreshold:
    best: tuple[int, float, float, float] | None = None
    for score, margin, agreement in product(
        (0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85),
        (0.0, 0.02, 0.04, 0.06, 0.10, 0.15),
        (0.2, 0.4, 0.6, 0.8),
    ):
        accepted = [
            item
            for item in observations
            if item["candidate"] == intent
            and float(item["score"]) >= score
            and float(item["margin"]) >= margin
            and float(item["agreement"]) >= agreement
        ]
        false_accepts = sum(item["expected"] != intent for item in accepted)
        if false_accepts:
            continue
        true_accepts = sum(item["expected"] == intent for item in accepted)
        candidate = (true_accepts, score, margin, agreement)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return IntentThreshold(score=1.0, margin=2.0, agreement=1.0)
    _, score, margin, agreement = best
    return IntentThreshold(score=score, margin=margin, agreement=agreement)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus_payload = json.loads(args.corpus.read_text(encoding="utf-8"))
    development = [
        case for case in corpus_payload["cases"] if case["partition"] == "development"
    ]
    settings = Settings()
    embedding_name = f"ollama:{settings.embedding_model_name}"
    embeddings = OllamaEmbeddings(
        client=OllamaHttpClient(settings.ollama_base_url, settings.ollama_timeout_seconds),
        model=settings.embedding_model_name,
    )
    index = load_semantic_intent_index(
        storage_path=settings.semantic_intent_path,
        collection_name=settings.semantic_intent_collection,
        embeddings=embeddings,
        expected_embedding_name=embedding_name,
    )
    router = DeterministicIntentRouter()
    observations: list[dict[str, object]] = []
    try:
        for case in development:
            if "unrecognized" not in router.decide(case["question"]).intent_codes:
                continue
            match = index.match(case["question"])
            if match.intent is None or match.score is None:
                continue
            observations.append(
                {
                    "expected": case["expected_intent"],
                    "candidate": match.intent,
                    "score": match.score,
                    "margin": match.margin or 0,
                    "agreement": match.agreement or 0,
                }
            )
    finally:
        index.close()
    intents = SemanticIntent.__args__  # type: ignore[attr-defined]
    calibration = SemanticIntentCalibration(
        schema_version=1,
        calibration_id=f"b14-{settings.embedding_model_name}-{corpus_payload['dataset_version']}",
        taxonomy_version=INTENT_TAXONOMY_VERSION,
        embedding_name=embedding_name,
        corpus_version=corpus_payload["dataset_version"],
        corpus_hash=_hash(corpus_payload),
        thresholds={intent: _calibrate_intent(intent, observations) for intent in intents},
        measured_at=datetime.now(UTC),
    )
    args.output.write_text(calibration.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} from {len(observations)} semantic-eligible development cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
