import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from wildfire_api.schemas.chat import ChatResponse
from wildfire_api.schemas.common import ErrorResponse
from wildfire_api.schemas.hotspots import GeoJsonResponse, SummaryRequest, SummaryResponse
from wildfire_api.schemas.metadata import MetadataResponse

FIXTURE_PATH = Path(__file__).parents[3] / "docs/fixtures/api_contract_v1.0.0.fixture.json"


@pytest.fixture(scope="module")
def fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_shared_fixture_is_explicitly_synthetic_and_versioned(
    fixture: dict[str, object],
) -> None:
    assert fixture["fixture_classification"] == "synthetic_api_contract_example"
    assert fixture["api_version"] == "1.0.0"


def test_backend_validates_every_shared_success_fixture(
    fixture: dict[str, object],
) -> None:
    MetadataResponse.model_validate(fixture["metadata"])
    SummaryResponse.model_validate(fixture["summary_complete"])
    SummaryResponse.model_validate(fixture["summary_empty"])
    SummaryResponse.model_validate(fixture["summary_partial"])
    SummaryResponse.model_validate(fixture["summary_unavailable"])
    GeoJsonResponse.model_validate(fixture["geojson"])
    GeoJsonResponse.model_validate(fixture["geojson_empty"])
    ChatResponse.model_validate(fixture["chat"])


def test_backend_validates_shared_error_fixtures(fixture: dict[str, object]) -> None:
    errors = fixture["errors"]
    assert isinstance(errors, dict)
    ErrorResponse.model_validate(errors["invalid_filter"])
    ErrorResponse.model_validate(errors["rate_limited"])


def test_unavailable_summary_cannot_be_coerced_to_zero(
    fixture: dict[str, object],
) -> None:
    invalid = copy.deepcopy(fixture["summary_unavailable"])
    assert isinstance(invalid, dict)
    invalid["total"] = 0
    invalid["coverage_issues"] = []
    with pytest.raises(ValidationError, match="incomplete responses require"):
        SummaryResponse.model_validate(invalid)


def test_known_gap_requires_evidence(fixture: dict[str, object]) -> None:
    invalid = copy.deepcopy(fixture["summary_partial"])
    assert isinstance(invalid, dict)
    invalid["coverage_issues"][0]["evidence_url"] = None
    with pytest.raises(ValidationError, match="require evidence_url"):
        SummaryResponse.model_validate(invalid)


def test_geojson_rejects_reversed_coordinates(fixture: dict[str, object]) -> None:
    invalid = copy.deepcopy(fixture["geojson"])
    assert isinstance(invalid, dict)
    invalid["features"][0]["geometry"]["coordinates"] = [0.5, 201.5]
    with pytest.raises(ValidationError, match="WGS84"):
        GeoJsonResponse.model_validate(invalid)


def test_geojson_returned_count_matches_features(fixture: dict[str, object]) -> None:
    invalid = copy.deepcopy(fixture["geojson"])
    assert isinstance(invalid, dict)
    invalid["metadata"]["returned"] = 2
    with pytest.raises(ValidationError, match="must match feature count"):
        GeoJsonResponse.model_validate(invalid)


def test_summary_request_rejects_duplicate_province_codes_without_schema_change() -> None:
    with pytest.raises(ValidationError, match="province_codes must be distinct"):
        SummaryRequest.model_validate(
            {
                "product_id": "VNP14IMG.002_SNPP_FIRMS_SP",
                "province_codes": ["14", "14"],
                "date_from": "2023-09-01",
                "date_to": "2023-09-30",
                "group_by": "month",
            }
        )
