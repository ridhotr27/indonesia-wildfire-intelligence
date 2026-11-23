"""Calibrate LIR-07 thresholds on reviewed development cases only."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

from evaluation.lir01_models import Lir01Corpus
from wildfire_api.agent.intent_router import DeterministicIntentRouter
from wildfire_api.agent.semantic_intent import (
    INTENT_TAXONOMY_VERSION,
    IntentThreshold,
    SemanticIntent,
    SemanticIntentCalibration,
    load_semantic_intent_index,
)
from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient


def _is_training_family(family_id: str) -> bool:
    return hashlib.sha256(family_id.encode()).digest()[0] % 2 == 0


def _threshold(intent: SemanticIntent, rows: list[dict[str, object]]) -> IntentThreshold:
    best: tuple[int, float, float, float] | None = None
    for score, margin, agreement in product(
        (0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95),
        (0.0, 0.02, 0.04, 0.06, 0.10, 0.15),
        (0.2, 0.4, 0.6, 0.8, 1.0),
    ):
        accepted = [
            row
            for row in rows
            if row["candidate"] == intent
            and float(row["score"]) >= score
            and float(row["margin"]) >= margin
            and float(row["agreement"]) >= agreement
        ]
        if any(row["expected"] != intent for row in accepted):
            continue
        candidate = (sum(row["expected"] == intent for row in accepted), score, margin, agreement)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return IntentThreshold(score=1.0, margin=2.0, agreement=1.0)
    _, score, margin, agreement = best
    return IntentThreshold(score=score, margin=margin, agreement=agreement)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="all-minilm")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    content = args.corpus.read_bytes()
    corpus = Lir01Corpus.model_validate_json(content)
    embeddings = OllamaEmbeddings(
        client=OllamaHttpClient(args.ollama_base_url, 60.0), model=args.model
    )
    index = load_semantic_intent_index(
        storage_path=args.index,
        collection_name="analytics_intent_examples_v1",
        embeddings=embeddings,
        expected_embedding_name=f"ollama:{args.model}",
    )
    router = DeterministicIntentRouter()
    rows: list[dict[str, object]] = []
    try:
        for case in corpus.cases:
            if (
                case.partition != "development"
                or case.category == "multi_turn"
                or _is_training_family(case.semantic_family_id)
            ):
                continue
            if "unrecognized" not in router.decide(case.current_message).intent_codes:
                continue
            match = index.match(case.current_message)
            if match.intent is None or match.score is None:
                continue
            rows.append(
                {
                    "expected": case.intent,
                    "candidate": match.intent,
                    "score": match.score,
                    "margin": match.margin or 0.0,
                    "agreement": match.agreement or 0.0,
                }
            )
    finally:
        index.close()
    intents = SemanticIntent.__args__  # type: ignore[attr-defined]
    calibration = SemanticIntentCalibration(
        schema_version=1,
        calibration_id="lir07-all-minilm-development-v2.0.0",
        taxonomy_version=INTENT_TAXONOMY_VERSION,
        embedding_name=f"ollama:{args.model}",
        corpus_version=corpus.dataset_version,
        corpus_hash=hashlib.sha256(content).hexdigest(),
        thresholds={intent: _threshold(intent, rows) for intent in intents},
        measured_at=datetime.now(UTC),
    )
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable calibration: {args.output}")
    args.output.write_text(calibration.model_dump_json(indent=2) + "\n", encoding="utf-8")
    summary = {
        "observations": len(rows),
        "thresholds": calibration.model_dump(mode="json")["thresholds"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
