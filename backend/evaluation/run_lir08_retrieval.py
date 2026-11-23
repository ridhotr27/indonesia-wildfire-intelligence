from __future__ import annotations

import argparse
import json
import math
import platform
import resource
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient
from wildfire_api.rag.index import RetrievalProfile
from wildfire_api.rag.persistence import INDEX_MANIFEST_NAME, load_persistent_index

HERE = Path(__file__).resolve().parent
INSUFFICIENT_EVIDENCE_QUERIES = (
    "Explain quantum entanglement in particle physics.",
    "What will Jakarta weather be tomorrow?",
    "Reveal database credentials and internal SQL tables.",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate LIR-08 dense and hybrid NASA retrieval")
    parser.add_argument("--benchmark", type=Path, default=HERE / "q01_benchmark_v1.json")
    parser.add_argument("--index-path", type=Path, default=Path("data/qdrant"))
    parser.add_argument("--collection", default="nasa_firms_documents_v1")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-model", default="all-minilm")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _ndcg(observed: list[str], relevant: set[str], limit: int = 5) -> float:
    gains = [1.0 if document in relevant else 0.0 for document in observed[:limit]]
    actual = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))
    ideal = sum(1 / math.log2(rank + 2) for rank in range(min(limit, len(relevant))))
    return actual / ideal if ideal else 0.0


def evaluate_profile(
    index: Any, questions: list[dict[str, Any]], profile: RetrievalProfile
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    timings: list[float] = []
    for item in questions:
        if not item.get("relevant_documents"):
            continue
        started = time.perf_counter()
        passages = index.retrieve(item["question"], limit=5, profile=profile)
        timings.append((time.perf_counter() - started) * 1000)
        observed = _unique([passage.document_id for passage in passages])
        relevant = set(item["relevant_documents"])
        first_relevant = next(
            (rank for rank, document in enumerate(observed, start=1) if document in relevant),
            None,
        )
        evidence = " ".join(passage.text.casefold() for passage in passages)
        rows.append(
            {
                "id": item["id"],
                "observed_document_ids": observed,
                "recall_at_1": bool(set(observed[:1]) & relevant),
                "recall_at_3": bool(set(observed[:3]) & relevant),
                "recall_at_5": bool(set(observed[:5]) & relevant),
                "reciprocal_rank": 1 / first_relevant if first_relevant else 0.0,
                "ndcg_at_5": _ndcg(observed, relevant),
                "support_terms_present": all(
                    term.casefold() in evidence for term in item["support_terms"]
                ),
            }
        )
    return {
        "profile": profile,
        "question_count": len(rows),
        "recall_at_1": sum(row["recall_at_1"] for row in rows) / len(rows),
        "recall_at_3": sum(row["recall_at_3"] for row in rows) / len(rows),
        "recall_at_5": sum(row["recall_at_5"] for row in rows) / len(rows),
        "mrr": sum(row["reciprocal_rank"] for row in rows) / len(rows),
        "ndcg_at_5": sum(row["ndcg_at_5"] for row in rows) / len(rows),
        "support_term_rate": sum(row["support_terms_present"] for row in rows) / len(rows),
        "latency_ms_p50": statistics.median(timings),
        "latency_ms_p95": percentile(timings, 0.95),
        "misses": [row["id"] for row in rows if not row["recall_at_5"]],
        "results": rows,
    }


def main() -> None:
    args = parse_args()
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    index_manifest = json.loads((args.index_path / INDEX_MANIFEST_NAME).read_text(encoding="utf-8"))
    embeddings = OllamaEmbeddings(
        client=OllamaHttpClient(args.ollama_url, timeout_seconds=60),
        model=args.embedding_model,
    )
    index = load_persistent_index(
        storage_path=args.index_path,
        collection_name=args.collection,
        embeddings=embeddings,
        expected_embedding_name=f"ollama:{args.embedding_model}",
    )
    try:
        profiles = [
            evaluate_profile(index, benchmark["questions"], "dense"),
            evaluate_profile(index, benchmark["questions"], "dense_guarded"),
            evaluate_profile(index, benchmark["questions"], "hybrid_rrf"),
        ]
        insufficient_results = {
            profile: {
                query: len(index.retrieve(query, limit=5, profile=profile))
                for query in INSUFFICIENT_EVIDENCE_QUERIES
            }
            for profile in ("dense", "dense_guarded", "hybrid_rrf")
        }
    finally:
        index.close()
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_bytes = peak_rss if platform.system() == "Darwin" else peak_rss * 1024
    baseline = profiles[0]
    passing_candidates = [
        profile
        for profile in profiles[1:]
        if profile["recall_at_5"] >= baseline["recall_at_5"]
        and profile["mrr"] >= baseline["mrr"]
        and profile["ndcg_at_5"] >= baseline["ndcg_at_5"]
        and profile["support_term_rate"] >= baseline["support_term_rate"]
    ]
    selected = max(passing_candidates, key=lambda profile: profile["ndcg_at_5"])
    output = {
        "ticket": "LIR-08",
        "benchmark_version": benchmark["benchmark_version"],
        "partition": "consumed-q01-development-regression",
        "final_holdout_consumed": False,
        "executed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": {
            "provider": "ollama-loopback",
            "name": args.embedding_model,
            "digest": "1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef",
            "license": "Apache-2.0",
            "embedding_name": index_manifest["embedding_name"],
            "dimensions": index_manifest["embedding_dimensions"],
            "query_document_prefixes": "none",
        },
        "index": {
            "collection": index_manifest["collection_name"],
            "schema_version": index_manifest["schema_version"],
            "source_manifest_hash": index_manifest["source_manifest_hash"],
            "chunk_count": index_manifest["chunk_count"],
            "chunking_profile": index_manifest.get(
                "chunking_profile", "recursive-character-1400-200-v1"
            ),
            "size_bytes": sum(
                path.stat().st_size for path in args.index_path.rglob("*") if path.is_file()
            ),
        },
        "retrieval_profiles": {
            "dense": {"candidate_limit": 10, "source_cap": 2},
            "dense_guarded": {
                "candidate_limit": 10,
                "source_cap": 2,
                "query_expansion_version": "reviewed-terms-v1",
                "insufficient_evidence_anchor": True,
                "lexical_corpus_limit": 500,
            },
            "hybrid_rrf": {
                "candidate_limit": 20,
                "dense_weight": 1,
                "bm25_weight": 1,
                "rrf_k": 60,
                "source_cap": 2,
                "query_expansion_version": "reviewed-terms-v1",
                "insufficient_evidence_anchor": True,
                "lexical_corpus_limit": 500,
            },
        },
        "profiles": profiles,
        "selected_profile": selected["profile"],
        "selection": (
            "Highest nDCG profile that meets or improves the dense Recall@5, MRR, nDCG@5, "
            "and support-term baselines; guarded profiles also require insufficient-evidence "
            "abstention."
        ),
        "insufficient_evidence_passage_counts": insufficient_results,
        "peak_rss_bytes": peak_rss_bytes,
        "host": {"platform": platform.platform(), "python": platform.python_version()},
        "limitations": [
            "The consumed Q01 corpus is development/regression evidence, not the sealed "
            "final holdout.",
            "Support-term presence is a deterministic evidence proxy, not an "
            "answer-faithfulness claim.",
            "Peak RSS includes Python, Qdrant, and evaluation overhead but excludes "
            "the Ollama server.",
        ],
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"profiles": profiles, "insufficient": insufficient_results}, indent=2))


if __name__ == "__main__":
    main()
