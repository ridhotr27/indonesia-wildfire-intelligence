from __future__ import annotations

import argparse
import json
from pathlib import Path

from wildfire_api.llm.ollama import OllamaEmbeddings, OllamaHttpClient
from wildfire_api.rag.fetch import fetch_source
from wildfire_api.rag.index import build_index, load_manifest
from wildfire_api.rag.persistence import build_persistent_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index allowlisted NASA documents in Qdrant")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--location", default=":memory:")
    parser.add_argument("--collection", default="nasa_firms_documents_v1")
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--embedding-provider", choices=("hashing", "ollama"), default="hashing")
    parser.add_argument("--embedding-model", default="all-minilm")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--chunking-profile",
        choices=("recursive-character-1400-200-v1", "structure-title-1400-200-v1"),
        default="recursive-character-1400-200-v1",
    )
    parser.add_argument(
        "--retrieval-profile",
        choices=("dense", "dense_guarded", "hybrid_rrf"),
        default="dense_guarded",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = load_manifest(args.manifest) if args.manifest else load_manifest()
    fetched = [fetch_source(source) for source in sources]
    embeddings = (
        OllamaEmbeddings(
            client=OllamaHttpClient(args.ollama_url, timeout_seconds=120),
            model=args.embedding_model,
        )
        if args.embedding_provider == "ollama"
        else None
    )
    embedding_name = (
        f"ollama:{args.embedding_model}" if embeddings is not None else "local-hashing-v1"
    )
    if args.location == ":memory:" or args.location.startswith(("http://", "https://")):
        index, chunks = build_index(
            fetched,
            location=args.location,
            collection_name=args.collection,
            embeddings=embeddings,
            retrieval_profile=args.retrieval_profile,
            chunking_profile=args.chunking_profile,
        )
    else:
        index, index_manifest = build_persistent_index(
            fetched,
            storage_path=Path(args.location),
            collection_name=args.collection,
            approved_sources=sources,
            embeddings=embeddings,
            embedding_name=embedding_name,
            retrieval_profile=args.retrieval_profile,
            chunking_profile=args.chunking_profile,
        )
        chunks = [None] * index_manifest.chunk_count
    results = {
        query: [passage.model_dump(mode="json") for passage in index.retrieve(query)]
        for query in args.query
    }
    print(
        json.dumps(
            {
                "sources": [
                    {
                        "document_id": item.source.document_id,
                        "url": str(item.final_url),
                        "bytes": item.source_bytes,
                        "content_hash": item.content_hash,
                        "retrieved_at": item.retrieved_at,
                    }
                    for item in fetched
                ],
                "chunks": len(chunks),
                "queries": results,
                "limitations": [
                    "Retrieved NASA text is untrusted evidence, never executable instructions.",
                    f"Embedding provider used for this index: {embedding_name}.",
                    f"Chunking profile: {args.chunking_profile}.",
                    f"Retrieval profile: {args.retrieval_profile}.",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    index.close()


if __name__ == "__main__":
    main()
