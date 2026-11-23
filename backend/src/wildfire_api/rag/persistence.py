from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import QdrantClient

from wildfire_api.rag.embeddings import HashingEmbeddings
from wildfire_api.rag.index import (
    DEFAULT_CHUNKING_PROFILE,
    DEFAULT_RETRIEVAL_PROFILE,
    ChunkingProfile,
    NasaDocumentIndex,
    RetrievalProfile,
    build_index,
    load_manifest,
)
from wildfire_api.rag.models import FetchedDocument, SourceSpec

INDEX_MANIFEST_NAME = "wildfire_index_manifest.json"
INDEX_SCHEMA_VERSION = 2
EMBEDDING_NAME = "local-hashing-v1"


class PersistentIndexError(RuntimeError):
    """Raised when a local index is absent, corrupt, or incompatible."""


class IndexManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    collection_name: str
    embedding_name: str
    embedding_dimensions: int = Field(ge=64, le=4096)
    embedding_idf: dict[str, float] | None = None
    source_manifest_hash: str
    source_content_hashes: dict[str, str]
    chunk_count: int = Field(gt=0)
    chunking_profile: ChunkingProfile = DEFAULT_CHUNKING_PROFILE
    indexed_at: datetime


def _source_manifest_hash(sources: list[SourceSpec]) -> str:
    payload = [source.model_dump(mode="json") for source in sources]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _manifest_path(storage_path: Path) -> Path:
    return storage_path / INDEX_MANIFEST_NAME


def build_persistent_index(
    documents: list[FetchedDocument],
    *,
    storage_path: Path,
    collection_name: str = "nasa_firms_documents_v1",
    approved_sources: list[SourceSpec] | None = None,
    embeddings: Embeddings | None = None,
    embedding_name: str = EMBEDDING_NAME,
    retrieval_profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
    chunking_profile: ChunkingProfile = DEFAULT_CHUNKING_PROFILE,
) -> tuple[NasaDocumentIndex, IndexManifest]:
    """Build completely off to the side, then atomically publish the local index."""
    storage_path = storage_path.resolve()
    if storage_path.exists() and not storage_path.is_dir():
        raise PersistentIndexError("Qdrant storage path must be a directory")
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = storage_path.with_name(f".{storage_path.name}.staging-{uuid.uuid4().hex}")
    backup_path = storage_path.with_name(f".{storage_path.name}.backup-{uuid.uuid4().hex}")
    sources = approved_sources or load_manifest()
    allowed_ids = {source.document_id for source in sources}
    document_ids = [document.source.document_id for document in documents]
    if len(document_ids) != len(set(document_ids)) or set(document_ids) != allowed_ids:
        raise PersistentIndexError("documents must exactly match the approved source manifest")

    index: NasaDocumentIndex | None = None
    published = False
    try:
        embedding = embeddings or HashingEmbeddings.from_texts(
            [document.text for document in documents]
        )
        dimensions = len(embedding.embed_query("dimension probe"))
        index, chunks = build_index(
            documents,
            collection_name=collection_name,
            location=str(staging_path),
            embeddings=embedding,
            retrieval_profile=retrieval_profile,
            chunking_profile=chunking_profile,
        )
        manifest = IndexManifest(
            schema_version=INDEX_SCHEMA_VERSION,
            collection_name=collection_name,
            embedding_name=embedding_name,
            embedding_dimensions=dimensions,
            embedding_idf=embedding.idf if isinstance(embedding, HashingEmbeddings) else None,
            source_manifest_hash=_source_manifest_hash(sources),
            source_content_hashes={
                document.source.document_id: document.content_hash for document in documents
            },
            chunk_count=len(chunks),
            chunking_profile=chunking_profile,
            indexed_at=datetime.now(UTC),
        )
        _manifest_path(staging_path).write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        index.close()
        index = None
        if storage_path.exists():
            storage_path.rename(backup_path)
        staging_path.rename(storage_path)
        published = True
        loaded_index = load_persistent_index(
            storage_path=storage_path,
            collection_name=collection_name,
            approved_sources=sources,
            embeddings=embedding,
            expected_embedding_name=embedding_name,
            retrieval_profile=retrieval_profile,
            expected_chunking_profile=chunking_profile,
        )
        if backup_path.exists():
            shutil.rmtree(backup_path)
        return loaded_index, manifest
    except Exception:
        if not published and backup_path.exists() and not storage_path.exists():
            backup_path.rename(storage_path)
        elif published and backup_path.exists():
            if storage_path.exists():
                shutil.rmtree(storage_path)
            backup_path.rename(storage_path)
        raise
    finally:
        if index is not None:
            index.close()
        if staging_path.exists():
            shutil.rmtree(staging_path)


def load_persistent_index(
    *,
    storage_path: Path,
    collection_name: str = "nasa_firms_documents_v1",
    approved_sources: list[SourceSpec] | None = None,
    embeddings: Embeddings | None = None,
    expected_embedding_name: str = EMBEDDING_NAME,
    retrieval_profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
    expected_chunking_profile: ChunkingProfile | None = None,
) -> NasaDocumentIndex:
    storage_path = storage_path.resolve()
    manifest_path = _manifest_path(storage_path)
    if not storage_path.is_dir() or not manifest_path.is_file():
        raise PersistentIndexError("configured local Qdrant index is missing")
    try:
        manifest = IndexManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PersistentIndexError("local Qdrant index manifest is corrupt") from exc
    sources = approved_sources or load_manifest()
    if (
        manifest.schema_version != INDEX_SCHEMA_VERSION
        or manifest.embedding_name != expected_embedding_name
        or manifest.collection_name != collection_name
        or manifest.source_manifest_hash != _source_manifest_hash(sources)
        or (
            expected_chunking_profile is not None
            and manifest.chunking_profile != expected_chunking_profile
        )
    ):
        raise PersistentIndexError("local Qdrant index is incompatible; rebuild it")
    if embeddings is None:
        if manifest.embedding_name != EMBEDDING_NAME or manifest.embedding_idf is None:
            raise PersistentIndexError("local embedding model is required to open this index")
        embeddings = HashingEmbeddings(
            dimensions=manifest.embedding_dimensions,
            idf=manifest.embedding_idf,
        )
    elif len(embeddings.embed_query("dimension probe")) != manifest.embedding_dimensions:
        raise PersistentIndexError("local embedding dimension is incompatible; rebuild it")
    try:
        client = QdrantClient(path=str(storage_path))
        store = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=embeddings,
        )
        if client.count(collection_name=collection_name, exact=True).count != manifest.chunk_count:
            client.close()
            raise PersistentIndexError("local Qdrant index contents do not match its manifest")
    except PersistentIndexError:
        raise
    except Exception as exc:
        raise PersistentIndexError("local Qdrant index could not be opened") from exc
    return NasaDocumentIndex(store, retrieval_profile=retrieval_profile)
