from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.run_lir08_retrieval import evaluate_profile
from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient
from wildfire_api.rag.fetch import fetch_source
from wildfire_api.rag.index import ChunkingProfile, build_index, load_manifest

HERE = Path(__file__).resolve().parent
PROFILES: tuple[ChunkingProfile, ...] = (
    "recursive-character-1400-200-v1",
    "structure-title-1400-200-v1",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate LIR-08 NASA chunking profiles")
    parser.add_argument("--benchmark", type=Path, default=HERE / "q01_benchmark_v1.json")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-model", default="all-minilm")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    sources = load_manifest()
    documents = [fetch_source(source) for source in sources]
    embeddings = OllamaEmbeddings(
        client=OllamaHttpClient(args.ollama_url, timeout_seconds=60),
        model=args.embedding_model,
    )
    results: list[dict[str, object]] = []
    for profile in PROFILES:
        index, chunks = build_index(
            documents,
            collection_name=f"lir08_{profile.replace('-', '_')}",
            embeddings=embeddings,
            retrieval_profile="dense",
            chunking_profile=profile,
        )
        try:
            metrics = evaluate_profile(index, benchmark["questions"], "dense")
        finally:
            index.close()
        results.append({"chunking_profile": profile, "chunk_count": len(chunks), **metrics})
    output = {
        "ticket": "LIR-08",
        "ablation": "chunking-only",
        "benchmark_version": benchmark["benchmark_version"],
        "partition": "consumed-q01-development-regression",
        "final_holdout_consumed": False,
        "executed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": {
            "provider": "ollama-loopback",
            "name": args.embedding_model,
            "digest": "1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef",
            "license": "Apache-2.0",
            "dimensions": 384,
        },
        "sources": {document.source.document_id: document.content_hash for document in documents},
        "profiles": results,
        "limitations": [
            "Live approved NASA pages can differ from the persisted B09 source snapshot.",
            "This development ablation does not consume the sealed final holdout.",
            "Retrieval metrics do not establish answer faithfulness by themselves.",
        ],
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"profiles": results}, indent=2))


if __name__ == "__main__":
    main()
