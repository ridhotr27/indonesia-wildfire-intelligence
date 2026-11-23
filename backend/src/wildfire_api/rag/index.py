from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from wildfire_api.rag.embeddings import HashingEmbeddings
from wildfire_api.rag.models import FetchedDocument, RetrievedPassage, SourceSpec

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[3] / "resources" / "nasa_documents" / "manifest.json"
)
CHUNK_NAMESPACE = uuid.UUID("af22a53d-fc68-55c7-91e1-ae1aac8e25a1")
RetrievalProfile = Literal["dense", "dense_guarded", "hybrid_rrf"]
ChunkingProfile = Literal["recursive-character-1400-200-v1", "structure-title-1400-200-v1"]
DEFAULT_RETRIEVAL_PROFILE: RetrievalProfile = "hybrid_rrf"
DEFAULT_CHUNKING_PROFILE: ChunkingProfile = "recursive-character-1400-200-v1"
RRF_K = 60
MAX_LEXICAL_CORPUS_CHUNKS = 500
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "apa",
        "are",
        "bagaimana",
        "dan",
        "dalam",
        "does",
        "explain",
        "how",
        "is",
        "itu",
        "mean",
        "of",
        "the",
        "to",
        "what",
        "which",
        "yang",
    }
)
_REVIEWED_QUERY_EXPANSIONS = (
    (
        re.compile(r"\bscan\s+(?:field|attribute|value)\b", re.IGNORECASE),
        "scan pixel footprint active fire attributes",
    ),
    (re.compile(r"\bdaya\s+radiasi\s+api\b", re.IGNORECASE), "fire radiative power FRP"),
    (re.compile(r"\btingkat\s+kepercayaan\b", re.IGNORECASE), "VIIRS confidence"),
)
_APPROVED_TOPIC_TERMS = frozenset(
    {
        "active",
        "brightness",
        "cloud",
        "confidence",
        "day",
        "detection",
        "fire",
        "firms",
        "frp",
        "hotspot",
        "night",
        "pixel",
        "processing",
        "radiative",
        "resolution",
        "satellite",
        "scan",
        "sensing",
        "viirs",
    }
)


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[SourceSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = [SourceSpec.model_validate(item) for item in payload["sources"]]
    identifiers = [item.document_id for item in sources]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("NASA source manifest contains duplicate document IDs")
    return sources


def chunk_documents(
    documents: Iterable[FetchedDocument],
    *,
    chunk_size: int = 1_400,
    chunk_overlap: int = 200,
    profile: ChunkingProfile = DEFAULT_CHUNKING_PROFILE,
) -> list[Document]:
    chunks: list[Document] = []
    for fetched in documents:
        title_prefix = f"Document: {fetched.source.title}\n\n"
        content_size = (
            max(200, chunk_size - len(title_prefix))
            if profile == "structure-title-1400-200-v1"
            else chunk_size
        )
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=content_size,
            chunk_overlap=min(chunk_overlap, content_size // 3),
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        pieces = splitter.split_text(fetched.text)
        for index, text in enumerate(pieces):
            if profile == "structure-title-1400-200-v1":
                text = f"{title_prefix}{text}"
            chunk_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            identity = f"{fetched.source.document_id}:{index}:{chunk_hash}"
            if profile != DEFAULT_CHUNKING_PROFILE:
                identity = f"{profile}:{identity}"
            chunk_id = hashlib.sha256(identity.encode()).hexdigest()
            metadata = {
                "chunk_id": chunk_id,
                "document_id": fetched.source.document_id,
                "title": fetched.source.title,
                "source_url": str(fetched.final_url),
                "published_at": fetched.source.published_at,
                "retrieved_at": fetched.retrieved_at,
                "version": fetched.source.version,
                "section": f"chunk-{index + 1}",
                "content_hash": fetched.content_hash,
                "chunk_hash": chunk_hash,
                "untrusted_content": True,
            }
            chunks.append(
                Document(
                    id=str(uuid.uuid5(CHUNK_NAMESPACE, chunk_id)),
                    page_content=text,
                    metadata=metadata,
                )
            )
    if not chunks:
        raise ValueError("at least one non-empty NASA document is required")
    return chunks


class NasaDocumentIndex:
    def __init__(
        self,
        vector_store: QdrantVectorStore,
        *,
        retrieval_profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
    ) -> None:
        self._vector_store = vector_store
        self.retrieval_profile = retrieval_profile
        self._lexical_documents: tuple[Document, ...] | None = None

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        profile: RetrievalProfile | None = None,
    ) -> list[RetrievedPassage]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("retrieval query must not be empty")
        if not 1 <= limit <= 10:
            raise ValueError("retrieval limit must be between 1 and 10")
        normalized = self._expand_query(normalized)
        selected_profile = profile or self.retrieval_profile
        candidate_limit = (
            min(20, limit * 4) if selected_profile == "hybrid_rrf" else min(10, limit * 2)
        )
        dense_candidates = self._vector_store.similarity_search(normalized, k=candidate_limit)
        candidates = dense_candidates
        if selected_profile in {"dense_guarded", "hybrid_rrf"} and dense_candidates:
            try:
                lexical_candidates = self._lexical_candidates(normalized, limit=20)
                if not self._has_approved_topic(normalized) or not lexical_candidates:
                    return []
                if selected_profile == "hybrid_rrf":
                    candidates = self._hybrid_rrf(dense_candidates, lexical_candidates)
            except Exception:
                # Lexical ranking is an optimization. Its failure retains the
                # evaluated dense retriever rather than failing the RAG path.
                candidates = dense_candidates
        documents = self._apply_source_diversity(candidates, limit=limit)
        return [self._to_passage(document) for document in documents]

    @staticmethod
    def _expand_query(query: str) -> str:
        additions = [
            value for pattern, value in _REVIEWED_QUERY_EXPANSIONS if pattern.search(query)
        ]
        return " ".join([query, *additions])

    @staticmethod
    def _terms(text: str) -> list[str]:
        return [
            token.casefold()
            for token in _TOKEN_PATTERN.findall(text)
            if len(token) > 1 and token.casefold() not in _STOPWORDS
        ]

    @classmethod
    def _bm25_scores(cls, query: str, documents: list[Document]) -> list[float]:
        query_terms = list(dict.fromkeys(cls._terms(query)))
        document_terms = [cls._terms(document.page_content) for document in documents]
        if not query_terms or not document_terms:
            return [0.0] * len(documents)
        average_length = sum(len(terms) for terms in document_terms) / len(document_terms) or 1.0
        document_frequency = {
            term: sum(term in set(terms) for terms in document_terms) for term in query_terms
        }
        scores: list[float] = []
        for terms in document_terms:
            frequencies = Counter(terms)
            score = 0.0
            for term in query_terms:
                frequency = frequencies[term]
                if not frequency:
                    continue
                inverse_frequency = math.log(
                    1
                    + (len(documents) - document_frequency[term] + 0.5)
                    / (document_frequency[term] + 0.5)
                )
                denominator = frequency + 1.2 * (0.25 + 0.75 * len(terms) / average_length)
                score += inverse_frequency * frequency * 2.2 / denominator
            scores.append(score)
        return scores

    def _lexical_candidates(self, query: str, *, limit: int) -> list[Document]:
        if self._lexical_documents is None:
            client = self._vector_store.client
            collection_name = self._vector_store.collection_name
            count = client.count(collection_name=collection_name, exact=True).count
            if count > MAX_LEXICAL_CORPUS_CHUNKS:
                raise ValueError("NASA lexical corpus exceeds its reviewed bound")
            points, _ = client.scroll(
                collection_name=collection_name,
                limit=MAX_LEXICAL_CORPUS_CHUNKS,
                with_payload=True,
                with_vectors=False,
            )
            documents: list[Document] = []
            for point in points:
                payload = point.payload or {}
                metadata = payload.get("metadata")
                content = payload.get("page_content")
                if isinstance(metadata, dict) and isinstance(content, str):
                    documents.append(
                        Document(id=str(point.id), page_content=content, metadata=metadata)
                    )
            self._lexical_documents = tuple(documents)
        documents = list(self._lexical_documents)
        scores = self._bm25_scores(query, documents)
        ranked = sorted(
            (index for index, score in enumerate(scores) if score > 0),
            key=lambda index: (-scores[index], index),
        )
        return [documents[index] for index in ranked[:limit]]

    @staticmethod
    def _document_key(document: Document) -> str:
        return str(document.metadata.get("chunk_id") or document.id)

    @classmethod
    def _hybrid_rrf(
        cls,
        dense_candidates: list[Document],
        lexical_candidates: list[Document],
    ) -> list[Document]:
        documents: dict[str, Document] = {}
        scores: dict[str, float] = {}
        best_rank: dict[str, int] = {}
        for candidates in (dense_candidates, lexical_candidates):
            for rank, document in enumerate(candidates, start=1):
                key = cls._document_key(document)
                documents.setdefault(key, document)
                scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank)
                best_rank[key] = min(rank, best_rank.get(key, rank))
        ordered = sorted(scores, key=lambda key: (-scores[key], best_rank[key], key))
        return [documents[key] for key in ordered]

    @classmethod
    def _has_approved_topic(cls, query: str) -> bool:
        return bool(set(cls._terms(query)).intersection(_APPROVED_TOPIC_TERMS))

    @staticmethod
    def _apply_source_diversity(candidates: list[Document], *, limit: int) -> list[Document]:
        documents: list[Document] = []
        deferred: list[Document] = []
        per_document: dict[str, int] = {}
        for candidate in candidates:
            document_id = str(candidate.metadata["document_id"])
            if per_document.get(document_id, 0) >= 2:
                deferred.append(candidate)
                continue
            documents.append(candidate)
            per_document[document_id] = per_document.get(document_id, 0) + 1
            if len(documents) == limit:
                break
        if len(documents) < limit:
            documents.extend(deferred[: limit - len(documents)])
        return documents

    @staticmethod
    def _to_passage(document: Document) -> RetrievedPassage:
        metadata = document.metadata
        return RetrievedPassage(
            chunk_id=metadata["chunk_id"],
            document_id=metadata["document_id"],
            title=metadata["title"],
            url=metadata["source_url"],
            section=metadata["section"],
            text=document.page_content,
            content_hash=metadata["content_hash"],
            retrieved_at=metadata["retrieved_at"],
            version=metadata.get("version"),
            published_at=metadata.get("published_at"),
            untrusted_content=True,
        )

    def upsert(self, chunks: list[Document]) -> None:
        """Idempotently replace chunks sharing the same deterministic IDs."""
        self._vector_store.add_documents(
            documents=chunks,
            ids=[document.id for document in chunks],
        )

    def close(self) -> None:
        """Release local Qdrant resources and its filesystem lock."""
        client = self._vector_store.client
        client.close()
        # qdrant-client's destructor otherwise closes the thread-bound local
        # SQLite handle a second time, potentially from a different thread.
        if hasattr(client, "_client"):
            del client._client


def build_index(
    documents: Iterable[FetchedDocument],
    *,
    collection_name: str = "nasa_firms_documents_v1",
    location: str = ":memory:",
    embeddings: Embeddings | None = None,
    retrieval_profile: RetrievalProfile = DEFAULT_RETRIEVAL_PROFILE,
    chunking_profile: ChunkingProfile = DEFAULT_CHUNKING_PROFILE,
) -> tuple[NasaDocumentIndex, list[Document]]:
    chunks = chunk_documents(documents, profile=chunking_profile)
    embedding_model = embeddings or HashingEmbeddings.from_texts(
        [document.page_content for document in chunks]
    )
    kwargs: dict[str, object]
    if location == ":memory:":
        kwargs = {"location": location}
    elif location.startswith("http://") or location.startswith("https://"):
        kwargs = {"url": location}
    else:
        kwargs = {"path": location}
    vector_store = QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=embedding_model,
        collection_name=collection_name,
        ids=[document.id for document in chunks],
        **kwargs,
    )
    return NasaDocumentIndex(vector_store, retrieval_profile=retrieval_profile), chunks
