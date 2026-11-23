from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel, ConfigDict, Field, model_validator
from qdrant_client import QdrantClient

SemanticIntent = Literal[
    "single_province_count",
    "multi_province_summary",
    "province_comparison",
    "province_ranking",
    "monthly_trend",
    "map_locations",
    "documentation_semantics",
    "combined_analytics_documentation",
]
SemanticRoutingMode = Literal["disabled", "shadow", "guarded"]

INTENT_MANIFEST_NAME = "semantic_intent_manifest.json"
INTENT_INDEX_SCHEMA_VERSION = 1
INTENT_TAXONOMY_VERSION = "wildfire-intents-v1"


class SemanticIntentError(RuntimeError):
    """The separate intent index is absent, corrupt, incompatible, or unavailable."""


class IntentExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,80}$")
    text: str = Field(min_length=4, max_length=500)
    language: Literal["en", "id", "mixed"]
    intent: SemanticIntent
    required_slots: tuple[Literal["province", "date"], ...] = ()
    optional_slots: tuple[Literal["direction", "top_n", "comparison"], ...] = ()
    min_provinces: int = Field(default=0, ge=0, le=38)
    max_provinces: int = Field(default=38, ge=0, le=38)
    review_status: Literal["reviewed"]
    source_category: Literal["authored", "known_regression", "synthetic_paraphrase"]

    @model_validator(mode="after")
    def province_bounds_are_ordered(self) -> IntentExample:
        if self.max_provinces < self.min_provinces:
            raise ValueError("max_provinces must be at least min_provinces")
        return self


class IntentExampleSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_version: str = Field(min_length=1, max_length=80)
    taxonomy_version: Literal["wildfire-intents-v1"]
    examples: tuple[IntentExample, ...] = Field(min_length=8)

    @model_validator(mode="after")
    def example_ids_are_unique(self) -> IntentExampleSet:
        identifiers = [example.id for example in self.examples]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("semantic intent example IDs must be unique")
        return self


class IntentThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: float = Field(ge=-1, le=1)
    margin: float = Field(ge=0, le=2)
    agreement: float = Field(ge=0, le=1)


class SemanticIntentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    taxonomy_version: Literal["wildfire-intents-v1"]
    dataset_version: str
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    collection_name: str
    embedding_name: str
    embedding_dimensions: int = Field(ge=64, le=4096)
    distance_metric: Literal["cosine"] = "cosine"
    example_count: int = Field(gt=0)
    top_k: int = Field(default=5, ge=1, le=8)
    calibration_id: str = Field(default="uncalibrated", min_length=1, max_length=128)
    thresholds: dict[SemanticIntent, IntentThreshold]
    indexed_at: datetime


class SemanticIntentCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    calibration_id: str = Field(min_length=1, max_length=128)
    taxonomy_version: Literal["wildfire-intents-v1"]
    embedding_name: str = Field(min_length=1, max_length=128)
    corpus_version: str = Field(min_length=1, max_length=128)
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    thresholds: dict[SemanticIntent, IntentThreshold]
    measured_at: datetime


class SemanticIntentMatch(BaseModel):
    """Privacy-safe internal match result; never serialize it in the public API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: SemanticIntent | None
    accepted: bool
    score: float | None = Field(default=None, ge=-1, le=1)
    margin: float | None = Field(default=None, ge=0, le=2)
    agreement: float | None = Field(default=None, ge=0, le=1)
    reason: Literal["accepted", "low_score", "low_margin", "low_agreement", "no_candidates"]


def load_example_set(path: Path) -> IntentExampleSet:
    try:
        return IntentExampleSet.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SemanticIntentError("semantic intent examples are missing or invalid") from exc


def load_calibration(path: Path) -> SemanticIntentCalibration:
    try:
        return SemanticIntentCalibration.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SemanticIntentError("semantic intent calibration is missing or invalid") from exc


def _dataset_hash(examples: IntentExampleSet) -> str:
    encoded = json.dumps(
        examples.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _default_thresholds() -> dict[SemanticIntent, IntentThreshold]:
    # Conservative initial calibration values. Guarded enablement still requires the
    # committed development/held-out evaluation and explicit review.
    intents = SemanticIntent.__args__  # type: ignore[attr-defined]
    return {intent: IntentThreshold(score=0.62, margin=0.04, agreement=0.4) for intent in intents}


class SemanticIntentIndex:
    def __init__(self, vector_store: QdrantVectorStore, manifest: SemanticIntentManifest) -> None:
        self._vector_store = vector_store
        self.manifest = manifest

    def match(self, query: str) -> SemanticIntentMatch:
        normalized = " ".join(query.split())
        if not normalized:
            return SemanticIntentMatch(intent=None, accepted=False, reason="no_candidates")
        try:
            candidates = self._vector_store.similarity_search_with_score(
                normalized, k=self.manifest.top_k
            )
        except Exception as exc:
            raise SemanticIntentError("semantic intent search is unavailable") from exc
        if not candidates:
            return SemanticIntentMatch(intent=None, accepted=False, reason="no_candidates")
        by_intent: dict[SemanticIntent, list[float]] = defaultdict(list)
        for document, raw_score in candidates:
            intent = document.metadata.get("intent")
            if intent not in self.manifest.thresholds:
                continue
            by_intent[intent].append(float(raw_score))
        if not by_intent:
            return SemanticIntentMatch(intent=None, accepted=False, reason="no_candidates")
        ranked = sorted(
            ((intent, max(scores)) for intent, scores in by_intent.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        intent, score = ranked[0]
        # Cosine implementations can exceed their mathematical bound by a few
        # machine epsilons for identical vectors. Keep the public match schema
        # strict while normalizing that storage-level floating-point noise.
        score = min(1.0, max(-1.0, score))
        runner_up = ranked[1][1] if len(ranked) > 1 else -1.0
        margin = max(0.0, score - runner_up)
        agreement = len(by_intent[intent]) / len(candidates)
        threshold = self.manifest.thresholds[intent]
        reason: Literal["accepted", "low_score", "low_margin", "low_agreement"] = "accepted"
        if score < threshold.score:
            reason = "low_score"
        elif margin < threshold.margin:
            reason = "low_margin"
        elif agreement < threshold.agreement:
            reason = "low_agreement"
        return SemanticIntentMatch(
            intent=intent,
            accepted=reason == "accepted",
            score=score,
            margin=margin,
            agreement=agreement,
            reason=reason,
        )

    def close(self) -> None:
        client = self._vector_store.client
        client.close()
        if hasattr(client, "_client"):
            del client._client


def build_semantic_intent_index(
    examples: IntentExampleSet,
    *,
    storage_path: Path,
    collection_name: str,
    embeddings: Embeddings,
    embedding_name: str,
    calibration_id: str = "uncalibrated",
    thresholds: dict[SemanticIntent, IntentThreshold] | None = None,
) -> tuple[SemanticIntentIndex, SemanticIntentManifest]:
    """Build off to the side and atomically publish a separate intent collection."""
    storage_path = storage_path.resolve()
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    staging = storage_path.with_name(f".{storage_path.name}.staging-{uuid.uuid4().hex}")
    backup = storage_path.with_name(f".{storage_path.name}.backup-{uuid.uuid4().hex}")
    dimensions = len(embeddings.embed_query("dimension probe"))
    if not 64 <= dimensions <= 4096:
        raise SemanticIntentError("semantic embedding dimension is outside approved bounds")
    documents = [
        Document(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"b14:{example.id}")),
            page_content=example.text,
            metadata={
                "example_id": example.id,
                "intent": example.intent,
                "language": example.language,
                "dataset_version": examples.dataset_version,
                "taxonomy_version": examples.taxonomy_version,
            },
        )
        for example in examples.examples
    ]
    store: QdrantVectorStore | None = None
    published = False
    try:
        store = QdrantVectorStore.from_documents(
            documents=documents,
            embedding=embeddings,
            collection_name=collection_name,
            ids=[document.id for document in documents],
            path=str(staging),
        )
        manifest = SemanticIntentManifest(
            schema_version=INTENT_INDEX_SCHEMA_VERSION,
            taxonomy_version=INTENT_TAXONOMY_VERSION,
            dataset_version=examples.dataset_version,
            dataset_hash=_dataset_hash(examples),
            collection_name=collection_name,
            embedding_name=embedding_name,
            embedding_dimensions=dimensions,
            example_count=len(documents),
            calibration_id=calibration_id,
            thresholds=thresholds or _default_thresholds(),
            indexed_at=datetime.now(UTC),
        )
        (staging / INTENT_MANIFEST_NAME).write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        store.client.close()
        store = None
        if storage_path.exists():
            storage_path.rename(backup)
        staging.rename(storage_path)
        published = True
        loaded = load_semantic_intent_index(
            storage_path=storage_path,
            collection_name=collection_name,
            embeddings=embeddings,
            expected_embedding_name=embedding_name,
            expected_dataset_hash=manifest.dataset_hash,
        )
        if backup.exists():
            shutil.rmtree(backup)
        return loaded, manifest
    except Exception:
        if published and backup.exists():
            if storage_path.exists():
                shutil.rmtree(storage_path)
            backup.rename(storage_path)
        elif not published and backup.exists() and not storage_path.exists():
            backup.rename(storage_path)
        raise
    finally:
        if store is not None:
            store.client.close()
        if staging.exists():
            shutil.rmtree(staging)


def load_semantic_intent_index(
    *,
    storage_path: Path,
    collection_name: str,
    embeddings: Embeddings,
    expected_embedding_name: str,
    expected_dataset_hash: str | None = None,
    require_calibrated: bool = False,
) -> SemanticIntentIndex:
    manifest_path = storage_path.resolve() / INTENT_MANIFEST_NAME
    try:
        manifest = SemanticIntentManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise SemanticIntentError("semantic intent index manifest is missing or corrupt") from exc
    try:
        embedding_dimensions = len(embeddings.embed_query("dimension probe"))
    except Exception as exc:
        raise SemanticIntentError("semantic embedding service is unavailable") from exc
    incompatible = (
        manifest.schema_version != INTENT_INDEX_SCHEMA_VERSION
        or manifest.taxonomy_version != INTENT_TAXONOMY_VERSION
        or manifest.collection_name != collection_name
        or manifest.embedding_name != expected_embedding_name
        or (require_calibrated and manifest.calibration_id == "uncalibrated")
        or (expected_dataset_hash is not None and manifest.dataset_hash != expected_dataset_hash)
        or embedding_dimensions != manifest.embedding_dimensions
    )
    if incompatible:
        raise SemanticIntentError("semantic intent index is incompatible; rebuild it offline")
    try:
        client = QdrantClient(path=str(storage_path.resolve()))
        count = client.count(collection_name=collection_name, exact=True).count
        if count != manifest.example_count:
            client.close()
            raise SemanticIntentError("semantic intent index contents do not match its manifest")
        store = QdrantVectorStore(
            client=client, collection_name=collection_name, embedding=embeddings
        )
    except SemanticIntentError:
        raise
    except Exception as exc:
        raise SemanticIntentError("semantic intent index could not be opened") from exc
    return SemanticIntentIndex(store, manifest)
