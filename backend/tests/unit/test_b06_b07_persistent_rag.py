import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wildfire_api.core.config import Settings
from wildfire_api.main import create_app
from wildfire_api.rag.models import FetchedDocument, SourceSpec
from wildfire_api.rag.persistence import (
    INDEX_MANIFEST_NAME,
    PersistentIndexError,
    build_persistent_index,
    load_persistent_index,
)


def _documents() -> list[FetchedDocument]:
    specs = [
        SourceSpec(
            document_id="frp-definition",
            title="NASA fire radiative power reference",
            url="https://www.earthdata.nasa.gov/data/tools/firms/frp-definition",
            media_type="text/html",
            version="test-fixture",
        ),
        SourceSpec(
            document_id="confidence-definition",
            title="NASA VIIRS confidence reference",
            url="https://www.earthdata.nasa.gov/data/tools/firms/confidence-definition",
            media_type="text/html",
            version="test-fixture",
        ),
    ]
    texts = [
        "Fire radiative power, abbreviated FRP, is measured in megawatts.",
        "VIIRS confidence uses low, nominal, and high categorical classes.",
    ]
    return [
        FetchedDocument(
            source=spec,
            retrieved_at="2026-11-06T00:00:00+00:00",
            final_url=spec.url,
            content_hash=str(index + 1) * 64,
            source_bytes=len(text.encode()),
            text=text,
        )
        for index, (spec, text) in enumerate(zip(specs, texts, strict=True))
    ]


def test_persistent_index_reopens_and_unchanged_rebuild_does_not_duplicate(
    tmp_path: Path,
) -> None:
    documents = _documents()
    sources = [document.source for document in documents]
    storage = tmp_path / "qdrant"

    first, first_manifest = build_persistent_index(
        documents,
        storage_path=storage,
        collection_name="persistent_test",
        approved_sources=sources,
    )
    assert first.retrieve("What unit is FRP measured in?")[0].document_id == "frp-definition"
    first.close()

    second, second_manifest = build_persistent_index(
        documents,
        storage_path=storage,
        collection_name="persistent_test",
        approved_sources=sources,
    )
    assert second_manifest.chunk_count == first_manifest.chunk_count
    results = second.retrieve("FRP confidence", limit=10)
    assert len({result.chunk_id for result in results}) == second_manifest.chunk_count
    second.close()

    reopened = load_persistent_index(
        storage_path=storage,
        collection_name="persistent_test",
        approved_sources=sources,
    )
    assert reopened.retrieve("VIIRS confidence")[0].document_id == "confidence-definition"
    reopened.close()


def test_loader_fails_closed_for_missing_corrupt_and_incompatible_indexes(
    tmp_path: Path,
) -> None:
    documents = _documents()
    sources = [document.source for document in documents]
    storage = tmp_path / "qdrant"
    with pytest.raises(PersistentIndexError, match="missing"):
        load_persistent_index(storage_path=storage, approved_sources=sources)

    index, _ = build_persistent_index(documents, storage_path=storage, approved_sources=sources)
    index.close()
    manifest_path = storage / INDEX_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PersistentIndexError, match="incompatible"):
        load_persistent_index(storage_path=storage, approved_sources=sources)

    manifest_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(PersistentIndexError, match="corrupt"):
        load_persistent_index(storage_path=storage, approved_sources=sources)


def test_loader_rejects_unexpected_chunking_profile(tmp_path: Path) -> None:
    documents = _documents()
    sources = [document.source for document in documents]
    storage = tmp_path / "qdrant"
    index, _ = build_persistent_index(
        documents,
        storage_path=storage,
        approved_sources=sources,
        chunking_profile="recursive-character-1400-200-v1",
    )
    index.close()

    with pytest.raises(PersistentIndexError, match="incompatible"):
        load_persistent_index(
            storage_path=storage,
            approved_sources=sources,
            expected_chunking_profile="structure-title-1400-200-v1",
        )


def test_fastapi_loads_configured_local_index_and_closes_it(tmp_path: Path) -> None:
    documents = _documents()
    storage = tmp_path / "qdrant"
    index, _ = build_persistent_index(
        documents,
        storage_path=storage,
        approved_sources=[document.source for document in documents],
        chunking_profile="structure-title-1400-200-v1",
    )
    index.close()

    # This test uses the repository manifest compatibility path through a controlled patch.
    from wildfire_api import main as main_module

    original_loader = main_module.load_persistent_index
    main_module.load_persistent_index = lambda **kwargs: load_persistent_index(
        **kwargs, approved_sources=[document.source for document in documents]
    )
    try:
        settings = Settings(
            environment="test",
            log_level="WARNING",
            rag_backend="local",
            qdrant_path=storage,
        )
        with TestClient(create_app(settings=settings)) as client:
            response = client.post(
                "/api/v1/chat",
                json={
                    "message": "What does FRP mean?",
                    "product_id": "MOCK_ONLY",
                    "context": {
                        "province_code": None,
                        "date_from": None,
                        "date_to": None,
                    },
                },
            )
        assert response.status_code == 200
        assert response.json()["mode"] == "rag"
        assert response.json()["citations"][0]["url"].startswith("https://")
    finally:
        main_module.load_persistent_index = original_loader

    reopened = load_persistent_index(
        storage_path=storage,
        approved_sources=[document.source for document in documents],
    )
    reopened.close()


def test_fastapi_fails_closed_when_enabled_index_is_missing(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        log_level="WARNING",
        rag_backend="local",
        qdrant_path=tmp_path / "missing",
    )
    with pytest.raises(PersistentIndexError, match="missing"):
        with TestClient(create_app(settings=settings)):
            pass
