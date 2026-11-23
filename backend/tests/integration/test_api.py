from datetime import date

from fastapi.testclient import TestClient

from wildfire_api.core.config import Settings
from wildfire_api.main import create_app
from wildfire_api.rag.models import RetrievedPassage
from wildfire_api.repositories.mock import MockHotspotRepository


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "request_id": response.headers["x-request-id"],
        "status": "ok",
        "api_version": "1.0.0",
    }
    assert response.headers["x-request-id"]


def test_metadata_is_explicitly_mocked(client: TestClient) -> None:
    response = client.get("/api/v1/metadata")

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == response.headers["x-request-id"]
    assert body["data_status"] == "mock"
    assert body["products"] == [
        {"product_id": "MOCK_ONLY", "display_name": "Synthetic fixture (not NASA data)"}
    ]
    assert body["api_version"] == "1.0.0"
    assert "not NASA" in body["source"]["attribution"]
    assert body["data_freshness_at"] is None


def test_summary_returns_labeled_synthetic_aggregate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/hotspots/summary",
        json={
            "product_id": "MOCK_ONLY",
            "province_codes": ["MOCK-WEST"],
            "date_from": "2023-09-01",
            "date_to": "2023-10-31",
            "group_by": "month",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["source"]["data_status"] == "mock"
    assert body["source"]["dataset_version"] == "mock-v1-a01-contract"
    assert body["is_complete"] is True
    assert body["coverage_issues"] == []
    assert body["caveat"] == "Hotspot detections are not confirmed wildfires."


def test_geojson_is_capped_and_marks_truncation(client: TestClient) -> None:
    response = client.get(
        "/api/v1/hotspots/geojson",
        params={
            "product_id": "MOCK_ONLY",
            "province_code": "MOCK-WEST",
            "date_from": "2023-09-01",
            "date_to": "2023-10-31",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 2
    assert body["metadata"]["truncated"] is True
    assert body["metadata"]["returned"] == 2
    assert {feature["properties"]["confidence_code"] for feature in body["features"]} == {
        "n",
        "h",
    }


def test_chat_rag_without_configured_index_abstains_transparently(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What does FRP mean?",
            "product_id": "MOCK_ONLY",
            "context": {"province_code": None, "date_from": None, "date_to": None},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "unsupported"
    assert body["usage"] == {"llm_calls": 0}
    assert body["citations"] == []
    assert any("not configured" in limitation for limitation in body["limitations"])


def test_chat_analytics_is_grounded_in_summary_service(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "How many hotspot detections were recorded?",
            "product_id": "MOCK_ONLY",
            "context": {
                "province_code": "MOCK-WEST",
                "date_from": "2023-09-01",
                "date_to": "2023-09-30",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "analytics"
    assert body["metrics"] == [
        {"name": "satellite_hotspot_detections", "value": 2, "unit": "detections"}
    ]
    assert body["chart"]["series"][0]["count"] == 2
    assert "2 satellite hotspot detections" in body["answer"]


def test_chat_message_month_overrides_full_year_ui_context(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "How many hotspot detections were recorded during September 2023?",
            "product_id": "MOCK_ONLY",
            "context": {
                "province_code": "MOCK-WEST",
                "date_from": "2023-09-01",
                "date_to": "2023-10-31",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "analytics"
    assert body["filters"] == {
        "province_codes": ["MOCK-WEST"],
        "date_from": "2023-09-01",
        "date_to": "2023-09-30",
    }
    assert body["metrics"][0]["value"] == 2


def test_chat_rag_integration_preserves_stable_nasa_citation() -> None:
    class Retriever:
        def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievedPassage]:
            assert query == "What does FRP mean?"
            assert limit == 5
            return [
                RetrievedPassage(
                    chunk_id="b" * 64,
                    document_id="nasa-frp",
                    title="NASA FIRMS attributes",
                    url="https://www.earthdata.nasa.gov/data/tools/firms",
                    section="frp",
                    text="FRP documentation text.",
                    content_hash="a" * 64,
                    retrieved_at="2026-10-21T00:00:00Z",
                    untrusted_content=True,
                )
            ]

    settings = Settings(environment="test", log_level="WARNING")
    with TestClient(create_app(settings=settings, rag_retriever=Retriever())) as rag_client:
        response = rag_client.post(
            "/api/v1/chat",
            json={
                "message": "What does FRP mean?",
                "product_id": "MOCK_ONLY",
                "context": {"province_code": None, "date_from": None, "date_to": None},
            },
        )

    assert response.status_code == 200
    assert response.json()["mode"] == "rag"
    assert response.json()["citations"] == [
        {
            "title": "NASA FIRMS attributes",
            "url": "https://www.earthdata.nasa.gov/data/tools/firms",
            "chunk_id": "b" * 64,
        }
    ]


def test_b11_documentation_questions_never_reach_analytics_from_ui_context() -> None:
    class CountingRepository(MockHotspotRepository):
        def __init__(self) -> None:
            self.analytics_calls = 0

        async def count_by_month(
            self,
            *,
            product_id: str,
            province_codes: tuple[str, ...],
            date_from: date,
            date_to: date,
        ) -> dict[str, int]:
            self.analytics_calls += 1
            return await super().count_by_month(
                product_id=product_id,
                province_codes=province_codes,
                date_from=date_from,
                date_to=date_to,
            )

    class Retriever:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievedPassage]:
            self.queries.append(query)
            assert limit == 5
            return [
                RetrievedPassage(
                    chunk_id="b" * 64,
                    document_id="firms-limitations",
                    title="NASA FIRMS limitations",
                    url="https://www.earthdata.nasa.gov/data/tools/firms/faq",
                    section="limitations",
                    text="Active fire detections are not burned-area or perimeter estimates.",
                    content_hash="a" * 64,
                    retrieved_at="2026-11-08T00:00:00Z",
                    untrusted_content=True,
                )
            ]

    repository = CountingRepository()
    retriever = Retriever()
    questions = [
        "Why can't NASA FIRMS hotspot detections be interpreted as wildfire size or burned area?",
        "What are the limitations of NASA FIRMS hotspot detections as a measure of fire extent?",
    ]
    settings = Settings(environment="test", log_level="WARNING")
    with TestClient(
        create_app(settings=settings, repository=repository, rag_retriever=retriever)
    ) as b11_client:
        for province in ["MOCK-WEST", "MOCK-CENTRAL"]:
            for question in questions:
                response = b11_client.post(
                    "/api/v1/chat",
                    json={
                        "message": question,
                        "product_id": "MOCK_ONLY",
                        "context": {
                            "province_code": province,
                            "date_from": "2023-09-01",
                            "date_to": "2023-10-31",
                        },
                    },
                )

                assert response.status_code == 200
                body = response.json()
                assert body["mode"] == "rag"
                assert body["filters"] is None and body["metrics"] is None
                assert body["citations"]
                assert [step["kind"] for step in body["execution_trace"]["steps"]] == [
                    "route_selection",
                    "vector_retrieval",
                    "citation_validation",
                ]

    assert repository.analytics_calls == 0
    assert retriever.queries == questions * 2


def test_semantic_filter_error_uses_standard_shape(client: TestClient) -> None:
    response = client.post(
        "/api/v1/hotspots/summary",
        json={
            "product_id": "UNSUPPORTED",
            "province_codes": ["MOCK-WEST"],
            "date_from": "2023-09-01",
            "date_to": "2023-09-30",
            "group_by": "month",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "request_id": response.headers["x-request-id"],
        "error": {
            "code": "INVALID_FILTER",
            "message": "Unsupported product_id: UNSUPPORTED",
        },
    }


def test_validation_error_uses_standard_shape(client: TestClient) -> None:
    response = client.post("/api/v1/hotspots/summary", json={"product_id": "MOCK_ONLY"})

    assert response.status_code == 422
    assert response.json() == {
        "request_id": response.headers["x-request-id"],
        "error": {"code": "VALIDATION_ERROR", "message": "Request validation failed."},
    }


def test_geojson_rejects_malformed_date(client: TestClient) -> None:
    response = client.get(
        "/api/v1/hotspots/geojson",
        params={
            "product_id": "MOCK_ONLY",
            "province_code": "MOCK-WEST",
            "date_from": "not-a-date",
            "date_to": "2023-09-30",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_not_found_uses_standard_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "NOT_FOUND",
        "message": "Resource not found.",
    }


def test_openapi_contains_contract_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {
        "/api/v1/health",
        "/api/v1/metadata",
        "/api/v1/hotspots/summary",
        "/api/v1/hotspots/geojson",
        "/api/v1/chat",
    }.issubset(paths)
    validation_response = paths["/api/v1/hotspots/summary"]["post"]["responses"]["422"]
    assert validation_response["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )
