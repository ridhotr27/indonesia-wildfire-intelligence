from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient
from wildfire_api.rag.fetch import fetch_source
from wildfire_api.rag.index import NasaDocumentIndex, build_index, load_manifest

HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare B09 retrieval models on Q01")
    parser.add_argument("--benchmark", type=Path, default=HERE / "q01_benchmark_v1.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-model", default="all-minilm")
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def evaluate(
    name: str, index: NasaDocumentIndex, questions: list[dict[str, Any]]
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    timings: list[float] = []
    for item in questions:
        if not item.get("relevant_documents"):
            continue
        started = time.perf_counter()
        passages = index.retrieve(item["question"], limit=5)
        timings.append((time.perf_counter() - started) * 1000)
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
    return {
        "name": name,
        "question_count": len(results),
        "recall_at_5": sum(row["recalled_at_5"] for row in results) / len(results),
        "support_term_rate": sum(row["support_terms_present"] for row in results) / len(results),
        "latency_ms_p50": statistics.median(timings),
        "latency_ms_p95": percentile(timings, 0.95),
        "misses": [row["id"] for row in results if not row["recalled_at_5"]],
        "results": results,
    }


def main() -> None:
    args = parse_args()
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    questions = benchmark["questions"]
    sources = load_manifest()
    documents = [fetch_source(source) for source in sources]
    hashing_index, chunks = build_index(documents)
    semantic_index, _ = build_index(
        documents,
        embeddings=OllamaEmbeddings(
            client=OllamaHttpClient(args.ollama_url, timeout_seconds=60),
            model=args.embedding_model,
        ),
    )
    try:
        comparisons = [
            evaluate("local-hashing-v1", hashing_index, questions),
            evaluate(f"ollama:{args.embedding_model}", semantic_index, questions),
        ]
    finally:
        hashing_index.close()
        semantic_index.close()
    payload = {
        "ticket": "B09",
        "benchmark_version": benchmark["benchmark_version"],
        "executed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "target_recall_at_5": 0.85,
        "source_count": len(documents),
        "chunk_count": len(chunks),
        "comparisons": comparisons,
        "limitations": [
            "Latency is a single local-machine run, not a production capacity result.",
            "Support-term presence is not a manual citation-claim audit.",
        ],
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"comparisons": comparisons}, indent=2))


if __name__ == "__main__":
    main()
