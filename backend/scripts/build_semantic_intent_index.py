#!/usr/bin/env python3
"""Build the B14 intent index offline; never rebuild it during API startup."""

from __future__ import annotations

import argparse
from pathlib import Path

from wildfire_api.agent.semantic_intent import (
    build_semantic_intent_index,
    load_calibration,
    load_example_set,
)
from wildfire_api.core.config import Settings
from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--examples",
        type=Path,
        default=Path("resources/semantic_intents/examples_v1.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--calibration", type=Path)
    args = parser.parse_args()
    settings = Settings()
    if settings.embedding_provider != "ollama" or settings.embedding_model_name not in {
        "all-minilm",
        "bge-m3",
    }:
        parser.error("configure the local Ollama provider with all-minilm or bge-m3")
    client = OllamaHttpClient(settings.ollama_base_url, settings.ollama_timeout_seconds)
    embeddings = OllamaEmbeddings(client=client, model=settings.embedding_model_name)
    examples = load_example_set(args.examples)
    calibration = load_calibration(args.calibration) if args.calibration else None
    embedding_name = f"ollama:{settings.embedding_model_name}"
    if calibration and calibration.embedding_name != embedding_name:
        parser.error("calibration embedding profile does not match configured embeddings")
    index, manifest = build_semantic_intent_index(
        examples,
        storage_path=args.output or settings.semantic_intent_path,
        collection_name=settings.semantic_intent_collection,
        embeddings=embeddings,
        embedding_name=embedding_name,
        calibration_id=(calibration.calibration_id if calibration else "uncalibrated"),
        thresholds=(calibration.thresholds if calibration else None),
    )
    index.close()
    print(
        f"published {manifest.example_count} reviewed examples to "
        f"{manifest.collection_name} ({manifest.dataset_hash})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
