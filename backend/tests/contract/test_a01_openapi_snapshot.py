import json
from pathlib import Path

from wildfire_api.main import create_app

SNAPSHOT_PATH = Path(__file__).parents[3] / "docs/openapi/api_v1.2.0.openapi.json"


def test_committed_openapi_snapshot_matches_application() -> None:
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert committed == create_app().openapi()


def test_openapi_exposes_versioned_routes_and_coverage_models() -> None:
    document = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert document["info"]["version"] == "1.2.0"
    assert set(document["paths"]) == {
        "/api/v1/chat",
        "/api/v1/health",
        "/api/v1/hotspots/geojson",
        "/api/v1/hotspots/summary",
        "/api/v1/hotspots/year-comparison",
        "/api/v1/metadata",
    }
    schemas = document["components"]["schemas"]
    assert {"CoverageIssue", "SummaryResponse", "GeoJsonResponse", "ErrorResponse"} <= set(schemas)
    assert schemas["SummaryResponse"]["properties"]["total"]["anyOf"][1] == {"type": "null"}
